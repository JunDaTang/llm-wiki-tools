#!/usr/bin/env python
"""按章级标题把整本 md 拆成独立 md（LLM wiki/RAG 页面粒度）。

拆分规则：
- 章级一页：每个章级标题一个文件，章级以下标题内联其中，不单独成页；
- 大小感知二次拆分：章页超过 --max-kb（默认 32KB，0 关闭）时下探一级标题：
  {章}.md 只留章标题行 + 章引言（章头到首个子节之间的内容），直接子节各自成页
  ——与章同级、平铺在书目录下，层级交给 index.md/toc.json 表达；子节仍超限则
  按标题层级继续下探（最深至 H6），叶子仍超限按空行段落边界兜底硬切成 -2/-3
  多个文件（单段超长如整张表格不切，宁可整段落块超限）。被拆页末尾追加
  「本节包含的小节」链接清单，自身即成为可导航的目录页。叶子拆无可拆仍超限则整页保留（不硬切续页）。
  平铺后所有 md 与书根 images/ 同目录，images/xxx.jpg 相对引用天然可解析
  （llm_wiki 摄取同样按源文件所在目录解析相对引用）；
- 章级默认自动判层：H2 数量 >=4 或 H2 全部形似"第 N 章/数字编号"式章名 → H2；
  否则下探到 H3（如 Part/目录 占据 H2 的书）。--level 可强制指定；
- 书名根 H1 一页（封面/前言正文归它），首个标题前的散落正文并入它；
  封面页不做大小拆分，末尾附「本书包含的章」链接清单，作为书目录页；
- 代码块内的 # 行不算标题（与 mineru-pdf2md build_book 同一套围栏/标题正则）。

输入两种形态：
- 单个 md 文件：拆到 {输出}/{文件名}/；
- 目录：遍历子目录中的 {书名}/{书名}.md（mineru-pdf2md 产物布局），
  以及顶层散装 *.md（排除 index/toc_review）。

输出 {输出}/{书名}/：{书名}.md + {章标题}.md + 超限章下探出的 {子节标题}.md
（全部平铺在书目录下）+ index.md（全量标题树：独立成页的标题加链接，内联
标题只列文字）+ images/（源目录存在则整目录复制）。
同名冲突先试冠父章前缀、再退 -2/-3 数字后缀。
若源目录有 {书名}.toc.json（build_book 产物），则与标题锁步校验（宽松口径）
并给每个 toc 节点补 file 字段（该标题内容所在的文件，内联标题指向归属页）
后一并输出。无 toc 也能拆，只是少这层校验。
输出目录整体重建（产物可由脚本从源 md 幂等再生）。

用法：
    uv run python <skill>/scripts/split_md.py --input outputs/mineru-pdf2md --output outputs/mineru-pdf2md-split
    uv run python <skill>/scripts/split_md.py --input 某本书.md --output outputs/split
    uv run python <skill>/scripts/split_md.py --input 某本书.md --output outputs/split --max-kb 0   # 关闭大小拆分
"""
import argparse
import json
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
HEAD_RE = re.compile(r"^(#{1,6}) (.+?)\s*$")
CHAPTER_RE = re.compile(r"第\s*\d+\s*[章讲篇]|chapter\s*\d+|^\d+([.．、]\s|\s)", re.IGNORECASE)

DEFAULT_MAX_KB = 32
MAX_SPLIT_DEPTH = 4  # 章以下最多下探的拆分层数（章=0）；标题最深 H6，叶子超限按段落兜底硬切


def log(msg):
    print(msg, flush=True)


def loose(s: str) -> str:
    """与 build_book 一致性关卡同口径的宽松归一化（去空白/LaTeX 记号/破折号）。
    toc 标题来自书签、md 标题来自 vlm，两者仅宽松相等（如「2. LLM 简介」≡「2. LLM简介」）。"""
    s = re.sub(r"[\s\\]+", "", s)
    s = re.sub(r"[$`_*{}\[\]]", "", s)
    return re.sub("[—–‑-]", "", s)


def sanitize(title: str) -> str:
    # 上限 100：Windows 路径护栏（仓库前缀 + 目录 100 + 最长文件名仍 < MAX_PATH 260）。
    # 原 60 曾把 65 字符书名腰斩（"...Semendyayev e"），且与根页名/上游产物目录名不一致。
    # 书名超 100 时目录名仍会截断而根页保持原文 stem（与上游一致），属已知取舍。
    t = title.replace("\xa0", " ")
    t = re.sub(r'[\\/:*?"<>|]+', " ", t)
    t = re.sub(r"\s+", " ", t).strip().rstrip(". ")
    return t[:100].strip() or "未命名"


def extract_sections(lines):
    """切分点 = 围栏外全部标题行。返回 [(start, level, title, end)]，含书名根；
    start 即标题行下标，end 为下一标题行下标（任意层级，不含）。"""
    secs, fence, cur = [], False, None
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            fence = not fence
            continue
        m = HEAD_RE.match(line)
        if not m or fence:
            continue
        if cur is not None:
            cur[3] = i
            secs.append(tuple(cur))
        cur = [i, len(m.group(1)), m.group(2).replace("\xa0", " ").strip(), len(lines)]
    if cur is not None:
        secs.append(tuple(cur))
    return secs


def pick_level(secs):
    """章级 = H2；H2 退化（少且无章名形态）时下探 H3。"""
    c = Counter(lv for _, lv, _, _ in secs)
    h2 = [t for _, lv, t, _ in secs if lv == 2]
    if len(h2) >= 4 or (h2 and all(CHAPTER_RE.search(t) for t in h2)):
        return 2
    return 3 if c[3] else 2


def flatten_toc(items, depth=1):
    for n in items:
        yield depth, n
        yield from flatten_toc(n.get("children", []), depth + 1)


def body_bytes(lines) -> int:
    return sum(len(line.encode("utf-8")) + 1 for line in lines)


def clear_dir(d: Path):
    """整体重建前清空目录。Windows 下句柄瞬时占用（索引/杀软）会让 rmtree 报
    WinError 32——重试几次；仍失败则告警继续（内容文件总会被重写，残留风险仅限
    本次不再产出的旧文件）。"""
    if not d.exists():
        return
    for attempt in range(3):
        try:
            shutil.rmtree(d)
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(1.5)
    log(f"[WARN] {d}: 目录被其他进程占用，未能清空，直接覆盖写入")


def split_book(md_file: Path, out_dir: Path, level_arg, max_bytes):
    base = md_file.stem
    book_dir = md_file.parent
    toc_file = book_dir / f"{base}.toc.json"
    text = md_file.read_text(encoding="utf-8")
    lines = text.split("\n")
    secs = extract_sections(lines)
    if not secs:
        raise SystemExit(f"{base}: 未提取到任何标题，拒绝拆分")
    level = level_arg if level_arg else pick_level(secs)

    toc = None
    toc_nodes = None
    if toc_file.exists():
        toc = json.loads(toc_file.read_text(encoding="utf-8"))
        toc_nodes = list(flatten_toc(toc["items"]))
        if len(toc_nodes) != len(secs):
            raise SystemExit(f"{base}: 标题 {len(secs)} 个 vs toc 节点 {len(toc_nodes)} 个，"
                             "不一致，请先修复源产物（mineru-pdf2md 场景重跑 build_book.py）")
        for (start, lv, title, _), (depth, node) in zip(secs, toc_nodes):
            nt = node["title"].replace("\xa0", " ").strip()
            if lv != depth or loose(title) != loose(nt):
                raise SystemExit(f"{base}: 第 {start} 行标题「{title[:30]}」(H{lv}) 与 toc 节点"
                                 f"「{nt[:30]}」(L{depth}) 不一致，请先修复源产物")

    clear_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    root_name = f"{base}.md"
    # Windows 文件名大小写不敏感：占用表按小写登记 stem（不含扩展名），
    # 预占书名根与 index，防止正文章节（如 MfML 的「Index」章）与导航文件互相覆盖
    used = {base.lower(), "index"}
    content = {}                            # 文件名 -> 正文行
    file_of_section = [None] * len(secs)    # 每个标题内容所在文件（内联标题指向归属页）
    own_file = set()                        # 独立成页的标题（index 加链接，内联只列文字）
    disp_depth = [0] * len(secs)            # index 展示缩进深度
    oversize_kept = []                      # 拆无可拆仍超限、按用户策略整页保留的叶子
    size_split = 0

    def namekey(s):
        """文件名撞名专用口径：loose 之外再去点号（只用于占用表，不动锁步校验的
        loose）——「7 Infinite Series」与「7. Infinite Series」这类正文章 vs
        书末 References 区同名小节必须视为撞名，否则两个语义相同的页并排出现。"""
        return re.sub(r"[\s.]+", "", loose(s)).lower()

    def busy(s):
        return s.lower() in used or namekey(s) in used_loose

    def claim(s):
        used.add(s.lower())
        used_loose.add(namekey(s))
        return s

    used_loose = {namekey(base), namekey("index")}

    def take_stem(parent_stem, stem):
        """书根占用表取唯一 stem。撞名（严格小写或宽松口径）先冠父章前缀
        （平铺布局下保住归属信息），仍撞退 -2/-3 数字后缀。"""
        s = stem
        if busy(s) and parent_stem:
            cand = f"{parent_stem} - {stem}"
            if not busy(cand):
                return claim(cand)
        if busy(s):
            return claim(f"{stem}-{next(n for n in range(2, 100) if not busy(f'{stem}-{n}'))}")
        return claim(s)

    def emit_section(k: int, end: int, depth: int, allow_recurse: bool = True,
                     parent_stem=None):
        """落盘第 k 个标题（正文范围 [start, end)，end 为排他的 sec 下标），
        返回 (本节页文件名, 标题) 供父级引言页生成子节链接清单。
        allow_recurse=False 的浅层伪章节（层级比章级更浅，如"目录/参考文献"）
        只占自己的直接正文，不下探。"""
        nonlocal size_split
        start, lv, title, _ = secs[k]
        end_line = secs[end][0] if end < len(secs) else len(lines)
        body = lines[start:end_line]
        stem = take_stem(parent_stem, sanitize(title))
        rel = f"{stem}.md"
        own_file.add(k)
        disp_depth[k] = depth
        sub_head = "#" * min(lv + 1, 6)

        # 直接子节 = 范围内逐个扫描，遇到层级 <= 当前子节头的即开启新子节；
        # 更深的标题归属其前一个子节的子树。子节区间恰好无缝平铺本范围。
        children, cur_lv = [], None
        if allow_recurse:
            for j in range(k + 1, end):
                lvj = secs[j][1]
                if cur_lv is None or lvj <= cur_lv:
                    children.append(j)
                    cur_lv = lvj

        over = bool(max_bytes) and body_bytes(body) > max_bytes
        if over and children and depth < MAX_SPLIT_DEPTH:
            # 超限：下探一级。章引言（章头到首个子节之间）留 {章}.md，子节各自成页；
            # 引言页末尾附「本节包含的小节」链接清单，被拆页自身即成为可导航目录页
            size_split += 1
            child_pages = []
            for ci, ck in enumerate(children):
                child_end = children[ci + 1] if ci + 1 < len(children) else end
                child_pages.append(emit_section(ck, child_end, depth + 1, parent_stem=stem))
            links = ["", f"{sub_head} 本节包含的小节", ""]
            links += [f"- [{t}](<{r}>)" for r, t in child_pages]
            content[rel] = lines[start:secs[children[0]][0]] + links
            file_of_section[k] = rel
            return rel, title

        if over:
            # 叶子（伪章节 / 到达下探上限 / 无子节）仍超限：接受超限整页保留。
            # 用户策略（2026-09-29）：最小的子标题已拆无可拆就停止，不再按段落
            # 硬切出 -1/-2/-3 续页——超大索引/表格/长文献拆碎反而破坏可用性
            oversize_kept.append(rel)
            content[rel] = body
            file_of_section[k] = rel
            for j in range(k + 1, end):    # 内联的更深标题归属本文件
                file_of_section[j] = rel
                disp_depth[j] = depth + (secs[j][1] - lv)
            return rel, title

        content[rel] = body
        file_of_section[k] = rel
        for j in range(k + 1, end):    # 内联的更深标题归属本文件
            file_of_section[j] = rel
            disp_depth[j] = depth + (secs[j][1] - lv)
        return rel, title

    # 书名根：封面/前言页（含首个标题前的散落正文），不做大小拆分
    start0, _, _, end0 = secs[0]
    content[root_name] = lines[:start0] + lines[start0:end0]
    file_of_section[0] = root_name

    # 章级循环：lv == level 是真实章（可下探二次拆分）；lv < level 是浅层伪章节
    # （如 H2"目录/参考文献"占据章级 H3 的书），只留直接正文；它与下一章之间
    # 散落的更深标题（孤儿节）一并并入该文件，保持行守恒
    chapter_ks = [k for k in range(1, len(secs)) if secs[k][1] <= level]
    first_chapter = chapter_ks[0] if chapter_ks else len(secs)
    for j in range(1, first_chapter):  # 首章之前的散落低级标题并入封面页
        content[root_name].extend(lines[secs[j][0]:secs[j][3]])
        file_of_section[j] = root_name
    root_links = []
    for i, k in enumerate(chapter_ks):
        next_ch = chapter_ks[i + 1] if i + 1 < len(chapter_ks) else len(secs)
        root_links.append(emit_section(k, next_ch, 0, allow_recurse=secs[k][1] == level))
    if root_links:
        # 封面页 = 书目录页：末尾附「本书包含的章」链接清单
        content[root_name] = content[root_name] + ["", "## 本书包含的章", ""] \
            + [f"- [{t}](<{r}>)" for r, t in root_links]

    for rel, body in content.items():
        while body and not body[-1].strip():
            body.pop()
        (out_dir / rel).write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")

    if toc is not None:
        missing = [i for i, f in enumerate(file_of_section) if f is None]
        if missing:
            raise SystemExit(f"{base}: 第 {missing[:3]} 个标题未归属文件，内部错误")
        # 章节与 toc 节点已锁步一一对应：节点 i 的内容起始于 file_of_section[i]
        for i, name in enumerate(file_of_section):
            toc_nodes[i][1]["file"] = name
        (out_dir / f"{base}.toc.json").write_text(
            json.dumps(toc, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    if (book_dir / "images").exists():
        shutil.copytree(book_dir / "images", out_dir / "images", dirs_exist_ok=True)

    head = (f"由 `{md_file}` 按章级标题（H{level}）拆分，共 {len(content)} 页"
            f"（{len(secs)} 个标题；超过 {max_bytes // 1024}KB 的章按子标题二次拆分 {size_split} 处，"
            f"拆无可拆仍超限整页保留 {len(oversize_kept)} 页）")
    idx = [f"# {base}", "", head + "。", ""]
    # 封面页始终进 index：它现在附「本书包含的章」链接清单，是书目录页
    idx.append(f"- [{base}（封面/前言）](<{root_name}>)")
    # 全量标题树：独立成页的加链接，内联标题只列文字，硬切续页缩进列出
    for k in range(1, len(secs)):
        title = secs[k][2]
        indent = "  " * disp_depth[k]
        if k in own_file:
            idx.append(f"{indent}- [{title}](<{file_of_section[k]}>)")
        else:
            idx.append(f"{indent}- {title}")
    (out_dir / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8", newline="\n")
    return len(content), level, size_split, len(oversize_kept)


def collect_jobs(input_path: Path):
    """返回 [(md_file, base)]：单文件 / {书名}/{书名}.md 目录布局 / 顶层散装 md。"""
    if input_path.is_file():
        return [(input_path, input_path.stem)]
    jobs = []
    for sub in sorted(input_path.iterdir()):
        if sub.is_dir() and (sub / f"{sub.name}.md").exists():
            jobs.append((sub / f"{sub.name}.md", sub.name))
    for md in sorted(input_path.glob("*.md")):
        if md.stem.lower() not in ("index", "toc_review"):
            jobs.append((md, md.stem))
    return jobs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="按章级标题把整本 md 拆成独立 md")
    ap.add_argument("--input", required=True, help="单个 md 文件，或含 <书名>/<书名>.md 的目录")
    ap.add_argument("--output", required=True, help="输出根目录（整体重建）")
    ap.add_argument("--level", choices=["auto", "2", "3", "4", "5", "6"], default="auto",
                    help="章级标题层级，默认按书自动判层")
    ap.add_argument("--max-kb", type=int, default=DEFAULT_MAX_KB,
                    help=f"章页超过该大小（KB）时按子标题二次拆分，0 关闭（默认 {DEFAULT_MAX_KB}）")
    args = ap.parse_args()
    in_path, out_dir = Path(args.input), Path(args.output)
    if in_path.resolve() == out_dir.resolve() or in_path.resolve() in out_dir.resolve().parents:
        raise SystemExit("输出目录不能覆盖输入")
    clear_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    level_arg = None if args.level == "auto" else int(args.level)
    max_bytes = args.max_kb * 1024 if args.max_kb > 0 else 0

    jobs = collect_jobs(in_path)
    if not jobs:
        raise SystemExit(f"{in_path}: 未找到可拆分的 md（单文件 / <书名>/<书名>.md 布局 / 顶层 *.md）")
    total = 0
    for md_file, base in jobs:
        n, level, size_split, oversize = split_book(md_file, out_dir / sanitize(base), level_arg, max_bytes)
        total += n
        extra = f"，{size_split} 处超限二次拆分" if size_split else ""
        if oversize:
            extra += f"，{oversize} 页拆无可拆整页保留"
        log(f"[OK] {base}: 章级=H{level}，拆出 {n} 页{extra} -> {out_dir / sanitize(base)}")
    log(f"合计 {total} 页")


if __name__ == "__main__":
    main()
