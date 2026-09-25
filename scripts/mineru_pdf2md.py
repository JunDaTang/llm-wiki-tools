#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU 批量 PDF 解析脚本（精准解析 API，model_version=vlm）

流程（官方 v4 批量接口）:
  1. POST /api/v4/file-urls/batch        申请批量上传链接（<=50 个文件/批）
  2. PUT  上传 PDF 到预签名 URL          上传后自动开始解析
  3. GET  /api/v4/extract-results/batch/{batch_id}  轮询状态
  4. 下载 full_zip_url，解包 md/json/images 到输出目录；原始 zip 保留到 outputs/zips/

超过 200 页的 PDF 会先用 pypdf 按页数上限本地拆分为 {stem}_{start}-{end}.pdf，
与 mineru.net 平台手动解析的产物命名保持一致（如 xxx_1-200.pdf）。

用法:
  export MINERU_TOKEN=sk-xxxx
  uv run --with pypdf --with requests python scripts/mineru_pdf2md.py \
      --input input/pdf2md --output outputs/pdf2md

常用参数:
  --model-version vlm     解析模型（默认 vlm，可选 pipeline）
  --language ch           文档语言（默认 ch）
  --ocr                   扫描件开启 OCR（默认关闭，文本层 PDF 无需）
  --extra-formats html docx  额外导出格式（默认只出 md/json；额外格式会重新解析计费）
  --only 关键词           只处理文件名包含该关键词的 PDF（测试用）
  --force                 忽略已完成状态重新解析
  --poll-interval 10      轮询间隔秒数
  --timeout 7200          整体轮询超时秒数

状态文件: <output>/.mineru_state.json，中断后重跑会自动续接（跳过已完成、续轮询未完成）。
Token 通过环境变量 MINERU_TOKEN 或 --token 传入，不要写进任何被 git 跟踪的文件。
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import requests
from pypdf import PdfReader, PdfWriter

API_BASE = "https://mineru.net"
BATCH_URL = API_BASE + "/api/v4/file-urls/batch"
RESULT_URL = API_BASE + "/api/v4/extract-results/batch/{}"

TERMINAL_OK = {"done"}
TERMINAL_FAIL = {"failed"}


def log(msg: str):
    print(msg, flush=True)


class MineruError(RuntimeError):
    pass


def api_post(url: str, token: str, payload: dict) -> dict:
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 0:
        raise MineruError(f"API 错误 code={body.get('code')} msg={body.get('msg')} url={url}")
    return body["data"]


def api_get(url: str, token: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 0:
        raise MineruError(f"API 错误 code={body.get('code')} msg={body.get('msg')} url={url}")
    return body["data"]


def split_pdf(src: Path, max_pages: int, tmp_dir: Path) -> list[Path]:
    """按 max_pages 拆分 PDF，返回分片路径列表（命名 {stem}_{start}-{end}.pdf，页码从 1 起）。"""
    reader = PdfReader(str(src))
    total = len(reader.pages)
    parts = []
    start = 0
    while start < total:
        end = min(start + max_pages, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        name = f"{src.stem}_{start + 1}-{end}.pdf"
        dst = tmp_dir / name
        with open(dst, "wb") as f:
            writer.write(f)
        parts.append(dst)
        log(f"  拆分: {src.name} 页 {start + 1}-{end} -> {name}")
        start = end
    return parts


def collect_items(input_dir: Path, only: str, max_pages: int, tmp_dir: Path) -> list[dict]:
    """扫描 PDF，产出上传条目；超页数的拆分后以分片为条目。"""
    items = []
    pdfs = sorted(p for p in input_dir.glob("*.pdf") if not p.name.startswith("._"))
    if only:
        pdfs = [p for p in pdfs if only in p.name]
    if not pdfs:
        raise MineruError(f"未找到匹配的 PDF 文件: {input_dir} (filter={only!r})")
    for pdf in pdfs:
        pages = len(PdfReader(str(pdf)).pages)
        log(f"发现: {pdf.name} ({pages} 页)")
        if pages > max_pages:
            tmp_dir.mkdir(parents=True, exist_ok=True)
            for part in split_pdf(pdf, max_pages, tmp_dir):
                items.append({"name": part.name, "path": str(part), "data_id": part.stem[:128]})
        else:
            items.append({"name": pdf.name, "path": str(pdf), "data_id": pdf.stem[:128]})
    return items


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_state(path: Path, state: dict):
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def create_batch_and_upload(items: list[dict], token: str, args, state: dict, state_path: Path):
    """对没有 batch_id 的条目申请上传链接并上传。"""
    if not items:
        return
    payload = {
        "model_version": args.model_version,
        "language": args.language,
        "enable_formula": True,
        "enable_table": True,
        "files": [
            {"name": it["name"], "data_id": it["data_id"], "is_ocr": args.ocr}
            for it in items
        ],
    }
    if args.extra_formats:
        payload["extra_formats"] = args.extra_formats
    data = api_post(BATCH_URL, token, payload)
    batch_id = data["batch_id"]
    urls = data["file_urls"]
    log(f"批次已创建 batch_id={batch_id}，共 {len(urls)} 个文件")
    if len(urls) != len(items):
        raise MineruError(f"上传链接数量({len(urls)})与文件数量({len(items)})不一致")

    for it, url in zip(items, urls):
        it["batch_id"] = batch_id
        it["url"] = url
        state[it["name"]] = {"batch_id": batch_id, "url": url, "uploaded": False}
    save_state(state_path, state)

    for it in items:
        log(f"上传: {it['name']} ({Path(it['path']).stat().st_size / 1e6:.1f} MB) ...")
        with open(it["path"], "rb") as f:
            r = requests.put(it["url"], data=f, timeout=600)
        r.raise_for_status()
        state[it["name"]]["uploaded"] = True
        save_state(state_path, state)
        log(f"上传完成: {it['name']}")


def poll_batches(items: list[dict], token: str, poll_interval: int, timeout: int, state_path: Path, state: dict) -> dict:
    """轮询所有 batch，返回 {file_name: extract_result}。"""
    batch_ids = sorted({it["batch_id"] for it in items})
    deadline = time.time() + timeout
    results = {}

    while True:
        all_settled = True
        for batch_id in batch_ids:
            data = api_get(RESULT_URL.format(batch_id), token)
            for res in data.get("extract_result", []):
                fname = res.get("file_name") or res.get("data_id")
                prev = state.get(fname, {})
                if prev.get("state") != res.get("state"):
                    prog = res.get("extract_progress") or {}
                    if prog:
                        log(f"  [{fname}] {res['state']} {prog.get('extracted_pages', '?')}/{prog.get('total_pages', '?')} 页")
                    else:
                        extra = f" err={res.get('err_msg')}" if res.get("err_msg") else ""
                        log(f"  [{fname}] {res['state']}{extra}")
                    prev.update({"state": res.get("state"), "zip_url": res.get("full_zip_url"), "err_msg": res.get("err_msg")})
                    state[fname] = prev
                    save_state(state_path, state)
                results[fname] = res
                if res.get("state") not in TERMINAL_OK | TERMINAL_FAIL:
                    all_settled = False
        if all_settled:
            break
        if time.time() > deadline:
            raise MineruError(f"轮询超时（{timeout}s），可用相同命令重跑续接 batch_id={batch_ids}")
        time.sleep(poll_interval)

    failed = [n for n, r in results.items() if r.get("state") in TERMINAL_FAIL]
    if failed:
        raise MineruError(f"解析失败: {failed}，err 见状态文件 {state_path.name}")
    return results


def extract_result(fname: str, zip_url: str, output_dir: Path, tmp_dir: Path):
    """下载结果 zip，解包 md/json/images 到输出目录，命名与平台手动导出一致（{stem}.md / {stem}.json）。"""
    stem = Path(fname).stem
    zip_path = tmp_dir / f"{stem}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(zip_url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)

    # 解析产物是中间件，统一放 parts/ 子目录（最终 md 由 build_book 整理后写在输出根目录）
    parts_dir = output_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    out_md = parts_dir / f"{stem}.md"
    out_json = parts_dir / f"{stem}.json"
    md_text = None
    json_bytes = None
    images = {}  # zip 内路径 -> bytes

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        md_candidates = [n for n in names if n.lower().endswith(".md")]
        md_name = next(
            (n for n in (f"{stem}.md", "full.md") if n in names),
            md_candidates[0] if md_candidates else None,
        )
        if md_name:
            md_text = zf.read(md_name).decode("utf-8", errors="replace").replace("\r\n", "\n")

        def is_aux_json(n):
            base = Path(n).name.lower()
            return base.endswith(("model.json", "layout.json", "_span.json"))

        json_all = [n for n in names if n.lower().endswith(".json") and not is_aux_json(n)]
        json_name = next(
            (
                n
                for n in (
                    f"{stem}_middle.json",
                    f"{stem}_content_list.json",
                    *(x for x in json_all if x.endswith("_middle.json")),
                    *(x for x in json_all if x.endswith("_content_list.json")),
                    *(x for x in json_all if x.endswith("_content_list_v2.json")),
                )
                if n in json_all or n in names
            ),
            json_all[0] if json_all else None,
        )
        if json_name:
            json_bytes = zf.read(json_name)

        # 额外格式（full.html/full.docx/full.tex）不展开落盘，随结果 zip 保留在 zips/ 目录
        for n in names:
            norm = n.replace("\\", "/")
            if (norm.startswith("images/") or "/images/" in norm) and not norm.endswith("/"):
                images[n] = zf.read(n)

    if md_text is None:
        raise MineruError(f"{fname}: 结果 zip 中未找到 markdown（内容: {names[:10]}）")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_text, encoding="utf-8", newline="\n")
    if json_bytes is not None:
        try:
            obj = json.loads(json_bytes)
            out_json.write_text(json.dumps(obj, ensure_ascii=False, indent=4), encoding="utf-8", newline="\n")
        except (ValueError, UnicodeDecodeError):
            out_json.write_bytes(json_bytes)
    # 只保留 md 实际引用的图片；其余裁剪图（公式/表格等）在 zips/ 的结果压缩包里
    if images:
        # md 图片语法与 HTML 表格内嵌 <img src="images/..."> 两种引用都要认
        keep = ({Path(r).name for r in re.findall(r"\]\((?:\./)?images/([^)\s]+)\)", md_text)}
                | {Path(r).name for r in re.findall(r"""<img[^>]*?src=["'](?:\./)?images/([^"'\s>]+)["']""", md_text)})
        img_dir = output_dir / "images"
        img_dir.mkdir(exist_ok=True)
        for n, data in images.items():
            if Path(n).name in keep:
                (img_dir / Path(n).name).write_bytes(data)

    used_json = Path(json_name).name if json_name else "-"
    log(f"完成: {out_md.name} + {used_json} ({len(keep) if images else 0} 张图片)")

    # 原始结果压缩包保留到 zips/（含 layout.json、model.json、额外格式、全部图片等）
    zips_dir = output_dir / "zips"
    zips_dir.mkdir(exist_ok=True)
    shutil.move(str(zip_path), str(zips_dir / f"{stem}.zip"))
    src_part = tmp_dir / fname
    if src_part.exists():
        src_part.unlink()


def main():
    ap = argparse.ArgumentParser(description="MinerU 批量 PDF 解析")
    ap.add_argument("--input", default="input/pdf2md")
    ap.add_argument("--output", default="outputs/pdf2md")
    ap.add_argument("--token", default=None, help="默认读环境变量 MINERU_TOKEN")
    ap.add_argument("--model-version", default="vlm", choices=["vlm", "pipeline"])
    ap.add_argument("--language", default="ch")
    ap.add_argument("--ocr", action="store_true", help="扫描件开启 OCR")
    ap.add_argument("--extra-formats", nargs="+", default=None,
                    choices=["html", "docx", "latex"],
                    help="额外导出格式（默认无）；结果仅保留在结果 zip（zips/）中，不展开落盘")
    ap.add_argument("--max-pages", type=int, default=200, help="单文件页数上限，超出自动拆分")
    ap.add_argument("--only", default=None, help="只处理文件名包含该关键词的 PDF")
    ap.add_argument("--force", action="store_true", help="忽略已完成状态重新解析")
    ap.add_argument("--poll-interval", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=7200)
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    token = args.token or os.environ.get("MINERU_TOKEN")
    if not token:
        raise MineruError("缺少 token：请设置环境变量 MINERU_TOKEN 或使用 --token")

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    tmp_dir = output_dir / ".tmp"
    state_path = output_dir / ".mineru_state.json"
    state = load_state(state_path)

    log(f"扫描输入目录: {input_dir}")
    items = collect_items(input_dir, args.only, args.max_pages, tmp_dir)
    log(f"共 {len(items)} 个解析任务")

    # 已完成且产物存在的直接跳过
    def already_done(it):
        st = state.get(it["name"], {})
        return (not args.force and st.get("extracted")
                and (output_dir / "parts" / (Path(it["name"]).stem + ".md")).exists())

    pending = [it for it in items if not already_done(it)]
    skipped = len(items) - len(pending)
    if skipped:
        log(f"跳过已完成: {skipped} 个")

    # 续接：已有 batch_id 的只轮询；没有的创建新批次并上传
    resume = [it for it in pending if state.get(it["name"], {}).get("batch_id")]
    fresh = [it for it in pending if not state.get(it["name"], {}).get("batch_id")]
    for it in resume:
        it["batch_id"] = state[it["name"]]["batch_id"]
    if resume:
        log(f"续接批次: {len(resume)} 个任务")

    create_batch_and_upload(fresh, token, args, state, state_path)

    poll_items = resume + fresh
    results = poll_batches(poll_items, token, args.poll_interval, args.timeout, state_path, state)

    # 下载并解包结果
    for it in poll_items:
        res = results.get(it["name"])
        if not res or res.get("state") != "done":
            raise MineruError(f"{it['name']} 状态异常: {res}")
        if not args.force and state.get(it["name"], {}).get("extracted"):
            continue
        extract_result(it["name"], res["full_zip_url"], output_dir, tmp_dir)
        state[it["name"]]["extracted"] = True
        save_state(state_path, state)

    # 清理临时目录
    if tmp_dir.exists() and not any(tmp_dir.iterdir()):
        tmp_dir.rmdir()

    ok = sum(1 for it in poll_items if results.get(it["name"], {}).get("state") == "done")
    log(f"全部完成: 本次成功 {ok}/{len(poll_items)}，累计 {len(items) - len(pending) + ok}/{len(items)}")
    log(f"输出目录: {output_dir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except MineruError as e:
        log(f"错误: {e}")
        sys.exit(1)
