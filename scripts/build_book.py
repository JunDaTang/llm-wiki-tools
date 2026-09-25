#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分片 md 合并 + 目录树(toc.json)生成 + 一致性校验

用法:
  uv run --with pypdf python scripts/build_book.py \
      --input input/pdf2md --output outputs/pdf2md [--only 关键词]

对 outputs 下每个文档:
  1. 有分片(_1-200.md 等)的按起始页排序合并为完整 {书名}.md；
     分片边界处"前片以 ``` 结尾 + 后片以 ```lang 开头"视为跨片代码块并缝合
  2. toc.json 优先从原 PDF 书签树生成（层级权威、全局页码）；
     原书无书签时走 LLM 标题集分析（--emit-analysis 发射请求 → agent 通读判定
     层级与噪音 → --apply-analysis 应用，脚本硬校验：同形态同层级、编号深度单调）；
     未提供分析结果时退化为编号深度启发式（质量较差，仅应急用）
  3. md 标题向目录对齐清洗（审核规则，全部记录在 toc_review.md）:
     - 阶段1/2 匹配（严格=去空白反斜杠 / 宽松=再去 LaTeX 残留与破折号）:
       先试单行，再试相邻标题行合并（修复"1.4 …原"+"因？怎样解决？"式断行）
     - 阶段3 匹配（编号相等且剩余文本互相包含或相似度>=0.7）: 处理
       "18.3.2 式 (18.6) 的证明" vs 书签"18.3.2 的证明"这类公式缺失差异，
       toc 采用 md 标题文本（信息更全），页码沿用书签
     - 未匹配但形如 "B. xxx" 的字母编号章节 → 保留为新章节并补进 toc
     - 其余未匹配标题 → 降级为正文（目录页条目/提示框/误判正文句等噪音）
     - 书签有而 md 无的章节 → 按书签顺序锚定到下一个已匹配章节前补插标题行
  4. 一致性校验（最终关卡）: 完整 md 标题序列 == toc.json 扁平序列
     （标题按宽松归一化比较——md 的 "$R_t$" 与书签的 "Rt" 视为一致；层级须相等）
  5. 标题层级重写: # 数 = 书签深度 + 2（H1 为书名根，章 H2、节 H3、以此类推）
"""

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pypdf

PART_RE = re.compile(r"^(?P<base>.+)_(?P<a>\d{1,4})-(?P<b>\d{1,4})$")
HEAD_RE = re.compile(r"^(#{1,6}) (.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
OPEN_FENCE_RE = re.compile(r"^\s*```[A-Za-z0-9_+#.\-]*\s*$")
CALLOUT_WORDS = {"提示", "危险", "通知", "任务", "名词", "目录", "证明", "注意"}

# 降级标题的形态分类（探索结论：约 58% 明确噪音，42% 灰区中约 3/4 是书签粒度
# 不足的真小节标题、1/4 是强调句/页眉/页码等真误判；经确认策略为全部降级，
# 分类仅用于审核报告）
CALLOUT_EXTRA_WORDS = {
    "目录", "名词", "List of Tables", "List of Figures", "封面", "前言", "序",
    "提示", "危险", "通知", "任务", "注意", "证明", "结语",
}


def classify_extra(t: str) -> str:
    s = t.strip()
    if re.fullmatch(r"[IVX]+", s) or s in CALLOUT_EXTRA_WORDS:
        return "装饰页/目录页/信息框"
    if "$" in s or "\\frac" in s or "\\begin" in s:
        return "公式"
    if s.startswith("•") or re.match(r"^\d+[).、]", s) \
            or re.match(r"^[一二三四五六七八九十]+[、.．]", s):
        return "列表/编号项"
    if re.search(r"[。？！?!;；]", s) or len(loose(s)) >= 24:
        return "长句/强调句"
    if re.search(r"[=<>{}_\[\]]|True|False|def |self\.|return |import |None", s):
        return "代码痕迹"
    return "短语(灰区)"


def log(msg):
    print(msg, flush=True)


def norm(s: str) -> str:
    return re.sub(r"[\s\\]+", "", s)


def loose(s: str) -> str:
    s = norm(s)
    s = re.sub(r"[$`_*{}\[\]]", "", s)
    s = re.sub("[—–‑-]", "", s)
    return s


def numkey(s: str):
    """提取标题编号: '11.3.5.5' / 'A.'；编号后可不带分隔点。
    字母编号必须带点（防止 'If' 被当成编号 'I'）。返回 (编号, 剩余文本)"""
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s*(.*)$", s)
    if m:
        return (m.group(1), m.group(2))
    m = re.match(r"^([A-Z])\.\s*(.*)$", s)
    if m:
        return (m.group(1), m.group(2))
    return (None, s)


def heading_shape(t: str):
    """标题的编号形态签名（对 LLM 层级判定做硬校验：同形态必须同层级）"""
    lt = loose(t)
    m = re.match(r"^(\d+(?:\.\d+)*)", lt)
    if m:
        return f"num{m.group(1).count('.') + 1}"
    for pat, name in (
        (r"^第[一二三四五六七八九十百千]+篇", "cn-pian"),
        (r"^第[一二三四五六七八九十百千]+章", "cn-zhang"),
        (r"^第[一二三四五六七八九十百千]+节", "cn-jie"),
        (r"^[一二三四五六七八九十百]+[、.．]", "cn-xu"),
        (r"^\d+[).）]", "paren"),
        (r"^(Part|Chapter)\s+\w+", "en-part-chapter"),
    ):
        if re.match(pat, lt):
            return name
    return None


def check_analysis(result_items, request_items):
    """对 LLM 层级判定做硬校验，返回错误列表（空 = 通过）"""
    errs = []
    req_idx = [it["idx"] for it in request_items]
    got = {it["idx"]: it for it in result_items}
    if sorted(got) != sorted(req_idx):
        missing = sorted(set(req_idx) - set(got))[:8]
        extra = sorted(set(got) - set(req_idx))[:8]
        errs.append(f"覆盖不完整: 缺 idx {missing}，多 idx {extra}")
        return errs
    title_by_idx = {it["idx"]: it["title"] for it in request_items}
    shape_levels = defaultdict(set)
    for idx, it in got.items():
        if it.get("action") == "noise":
            continue
        lv = it.get("level")
        if not isinstance(lv, int) or not 2 <= lv <= 6:
            errs.append(f"idx={idx} 层级非法: {lv!r}（须为 2-6 整数或 noise）")
            continue
        sh = heading_shape(title_by_idx[idx])
        if sh:
            shape_levels[sh].add(lv)
    for sh, lvs in sorted(shape_levels.items()):
        if len(lvs) > 1:
            errs.append(f"形态 {sh} 层级不一致 {sorted(lvs)}（同形态必须同层级）")
    digit_lv = {}
    for sh, lvs in shape_levels.items():
        if sh.startswith("num") and len(lvs) == 1:
            digit_lv[int(sh[3:])] = next(iter(lvs))
    for d1 in sorted(digit_lv):
        for d2 in sorted(digit_lv):
            if d1 < d2 and digit_lv[d2] < digit_lv[d1]:
                errs.append(f"编号深度 {d1} 层级 L{digit_lv[d1]} 不得浅于编号深度 {d2} 层级 L{digit_lv[d2]}")
    return errs


def parse_headings(lines):
    """解析标题（排除代码块）。连续标题行（允许中间隔空行）并入同组 parts，
    供跨空行的断行标题合并判定。
    返回 [{start, parts: [(line_idx, level, title), ...]}]"""
    groups, fence, i = [], False, 0
    while i < len(lines):
        line = lines[i]
        if FENCE_RE.match(line):
            fence = not fence
            i += 1
            continue
        m = HEAD_RE.match(line)
        if m and not fence:
            parts = []
            j = i
            while j < len(lines):
                lj = lines[j]
                if FENCE_RE.match(lj):
                    break
                m2 = HEAD_RE.match(lj)
                if m2:
                    parts.append((j, len(m2.group(1)),
                                  m2.group(2).replace("\xa0", " ").strip()))
                    j += 1
                    continue
                if lj.strip() == "":
                    j += 1
                    continue
                break
            groups.append({"start": i, "parts": parts})
            i = j
            continue
        i += 1
    return groups


def match_bm(title, bm_list, used, stages):
    """标题匹配书签。stages: 1=严格 2=宽松 3=编号+文本相似。返回书签下标或 None"""
    n1, l1 = norm(title), loose(title)
    if 1 in stages:
        for bi, bm in enumerate(bm_list):
            if not used[bi] and norm(bm["title"]) == n1:
                return bi
    if 2 in stages:
        for bi, bm in enumerate(bm_list):
            if not used[bi] and loose(bm["title"]) == l1:
                return bi
    if 3 in stages:
        k1, r1 = numkey(l1)
        if k1:
            for bi, bm in enumerate(bm_list):
                if used[bi]:
                    continue
                k2, r2 = numkey(loose(bm["title"]))
                if k2 == k1 and r1 and r2 and (
                    r1 in r2 or r2 in r1
                    or difflib.SequenceMatcher(None, r1, r2).ratio() >= 0.7
                ):
                    return bi
    return None


def merge_parts(parts):
    """合并分片文本，缝合跨片代码块。返回 (text, seam_events)"""
    seams = []
    chunks = [p["text"].rstrip("\n").split("\n") for p in parts]
    out = list(chunks[0])
    for i in range(1, len(chunks)):
        nxt = list(chunks[i])
        while out and not out[-1].strip():
            out.pop()
        while nxt and not nxt[0].strip():
            nxt.pop(0)
        joined = False
        if out and nxt and out[-1].strip() == "```" and OPEN_FENCE_RE.match(nxt[0]):
            seams.append({"at": f"{parts[i-1]['name']} -> {parts[i]['name']}",
                          "prev_tail": out[-2].strip()[-36:] if len(out) > 1 else "",
                          "next_head": nxt[1].strip()[:36] if len(nxt) > 1 else ""})
            out.pop()
            nxt.pop(0)
            joined = True
        if not joined:
            out.append("")
        out.extend(nxt)
    return "\n".join(out), seams


def iter_part_files(output: Path, base: str):
    """分片原始 md 在 parts/ 子目录（新版布局）；旧布局兜底扫描根目录"""
    parts_dir = output / "parts"
    scan_dirs = [parts_dir] if parts_dir.exists() else [output]
    parts = []
    for d in scan_dirs:
        for f in d.glob(f"{base}_*.md"):
            m = PART_RE.match(f.stem)
            if m and m.group("base") == base:
                parts.append({"name": f.name, "a": int(m.group("a")), "b": int(m.group("b")),
                              "text": f.read_text(encoding="utf-8")})
    if not parts and parts_dir.exists():  # 新版目录但该 base 只有根目录分片（旧布局混入）
        for f in output.glob(f"{base}_*.md"):
            m = PART_RE.match(f.stem)
            if m and m.group("base") == base:
                parts.append({"name": f.name, "a": int(m.group("a")), "b": int(m.group("b")),
                              "text": f.read_text(encoding="utf-8")})
    return sorted(parts, key=lambda p: p["a"])


def get_bookmarks(pdf_path: Path):
    r = pypdf.PdfReader(str(pdf_path))
    out = []

    def walk(ol, d=0):
        for i in ol:
            if isinstance(i, list):
                walk(i, d + 1)
            else:
                out.append({"depth": d, "title": str(i.title).strip(),
                            "page": r.get_destination_page_number(i) + 1})

    try:
        walk(r.outline)
    except Exception:
        return []
    return out


def page_from_content_list(json_files, title):
    """从 content_list.json 推导全局页码: 分片起始页 + page_idx"""
    t = loose(title)[:8]
    if not t:
        return None
    for jf, offset in json_files:
        try:
            blocks = json.loads(Path(jf).read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for b in blocks:
            if b.get("type") in ("text", "title") and loose(b.get("text", "")).startswith(t):
                return offset + int(b.get("page_idx", 0))
    return None


def build_doc(base, parts, pdf_path, output, report, analysis=None):
    """处理一个文档，返回一致性是否通过。
    analysis: None=常规流程; 'emit'=写出标题层级分析请求(不写产物);
    'apply'=应用 .analysis-result.json 的 LLM 层级判定后重建产物。仅对无书签文档生效。"""
    single = not parts
    parts_dir = output / "parts"
    if parts:
        json_files = [(parts_dir / f"{p['name'][:-3]}.json", p["a"]) for p in parts]
    else:
        # 单文档：原始 md/json 在 parts/（新版）或根目录（旧布局）
        raw = parts_dir / f"{base}.md"
        js = parts_dir / f"{base}.json"
        json_files = [(js if js.exists() else output / f"{base}.json", 1)]
    md_file = output / f"{base}.md"          # 最终成品固定写输出根目录
    toc_dir = output / "toc"
    toc_dir.mkdir(parents=True, exist_ok=True)
    req_file = toc_dir / f"{base}.analysis-request.json"
    res_file = toc_dir / f"{base}.analysis-result.json"

    if single:
        if not raw.exists():
            raw = md_file  # 旧布局：根目录单文档 md 即原始版（就地清洗）
        text = raw.read_text(encoding="utf-8").rstrip("\n")
        seams = []
        report += [f"## {base}", "", "- 单文档（无分片）"]
    else:
        text, seams = merge_parts(parts)
        report += [f"## {base}", "", f"- 分片合并: {len(parts)} 片 -> {md_file.name}"]
        for s in seams:
            report += [f"- 缝合跨片代码块: {s['at']}（前片尾 …{s['prev_tail']} / 后片头 {s['next_head']}…）"]
        if not seams:
            report += ["- 分片边界无跨片代码块"]

    # ---- 根标题（H1 书名行）：文档开头的 H1 视为书名根 ----
    lines = text.split("\n")
    root_title, root_idx = base, None
    for g in parse_headings(lines):
        lv, t = g["parts"][0][1], g["parts"][0][2]
        if lv == 1 and g["start"] <= 5:
            root_title, root_idx = t, g["start"]
            break
    if root_idx is None:
        lines = [f"# {base}", ""] + lines
        root_idx = 0
        report += [f"- 添加书名根标题: # {base}"]
    else:
        report += [f"- 书名根标题(已有): {root_title}"]

    # ---- 书签 ----
    bm_list = get_bookmarks(pdf_path) if pdf_path and pdf_path.exists() else []
    total_pages = len(pypdf.PdfReader(str(pdf_path)).pages) if pdf_path and pdf_path.exists() else None
    using_bookmarks = bool(bm_list)
    src_desc = ("PDF 书签树（%d 条，层级权威、全局页码）" % len(bm_list) if using_bookmarks else
                ("LLM 标题集分析（无书签；agent 判定层级与噪音，脚本硬校验）" if analysis == "apply" or res_file.exists()
                 else "md 重建（原书无书签，启发式尽力而为）"))
    report += [f"- 目录来源: {src_desc}"]

    # ---- 标题对齐清洗（计划阶段）----
    used = [False] * len(bm_list)
    actions = {}       # line_idx -> ("keep", level, title) | ("demote", None, title)
    collapse = set()   # 被 keep 组折叠掉的后续标题行
    merged_ev, demoted, fuzzy_ev, inserted_ev = [], [], [], []
    rejected_ev = []
    kept_bm = []       # (line_idx, bm_idx) 按处理顺序
    bm_title = {}      # bm_idx -> toc 使用的标题（模糊匹配时用 md 文本）

    if using_bookmarks:
        last_bm = [-1]     # 已匹配的最大书签下标（保序约束）
        rejected_ev = []

        def keep(parts_, bi, title, fuzzy=False):
            if bi <= last_bm[0]:
                # md 顺序与书签顺序倒挂（如 vlm 把小节标题排到了父标题之后），
                # 以书签顺序为准：拒绝该匹配，标题走降级，书签留给补插机制
                rejected_ev.append({"md": title, "bm": bm_list[bi]["title"]})
                return False
            used[bi] = True
            level = bm_list[bi]["depth"] + 2
            actions[parts_[0][0]] = ("keep", level, title)
            # 折叠范围内所有行（含被合并标题行之间的空行）
            for li in range(parts_[0][0] + 1, parts_[-1][0] + 1):
                collapse.add(li)
            kept_bm.append((parts_[0][0], bi))
            if fuzzy:
                bm_title[bi] = title
            last_bm[0] = bi
            return True

        def process(parts_):
            n = len(parts_)
            if not n:
                return
            # 阶段1/2: 单行优先，再渐进合并（修复断行标题）
            for take in range(1, n + 1):
                concat = "".join(p[2] for p in parts_[:take])
                bi = match_bm(concat, bm_list, used, stages=(1, 2))
                if bi is not None and keep(parts_[:take], bi, concat):
                    if take > 1:
                        merged_ev.append({"title": concat, "n": take})
                    process(parts_[take:])
                    return
            # 阶段3: 编号+文本相似（模糊），toc 沿用 md 标题文本
            for take in range(1, n + 1):
                concat = "".join(p[2] for p in parts_[:take])
                bi = match_bm(concat, bm_list, used, stages=(3,))
                if bi is not None and keep(parts_[:take], bi, concat, fuzzy=True):
                    fuzzy_ev.append({"md": concat, "bm": bm_list[bi]["title"],
                                     "page": bm_list[bi]["page"]})
                    process(parts_[take:])
                    return
            # 未匹配: 一律降级（含字母编号标题——审核发现 10.2 内部的 "B. 处理截断…"
            # 这类小节编号会与附录编号撞形，以书签为权威，宁降级不误保留）
            for p in parts_:
                bi = match_bm(p[2], bm_list, used, stages=(1, 2, 3))
                if bi is not None and keep([p], bi, p[2]):
                    continue
                actions[p[0]] = ("demote", None, p[2])
                demoted.append(p[2])

        for g in parse_headings(lines):
            # 根组可能吸收了紧随其后的标题行（root -> 空行 -> 标题），只跳过根行本身
            gps = [p for p in g["parts"] if p[0] != root_idx]
            if gps:
                process(gps)
    else:
        # 无书签：head_groups 为清洗目标（根行除外）
        head_groups = [[p for p in g["parts"] if p[0] != root_idx]
                       for g in parse_headings(lines)]
        head_groups = [g for g in head_groups if g]

        if analysis == "emit":
            items, idx = [], 0
            for gps in head_groups:
                for (li, lv, t) in gps:
                    cb, ca = [], []
                    j = li - 1
                    while j >= 0 and len(cb) < 2:
                        if lines[j].strip():
                            cb.insert(0, lines[j].strip()[:60])
                        j -= 1
                    j = li + 1
                    while j < len(lines) and len(ca) < 2:
                        if lines[j].strip():
                            ca.append(lines[j].strip()[:60])
                        j += 1
                    items.append({"idx": idx, "title": t, "level_guess": lv,
                                  "page": page_from_content_list(json_files, t),
                                  "before": cb, "after": ca})
                    idx += 1
            req_file.write_text(json.dumps({"book": base, "items": items},
                                           ensure_ascii=False, indent=1),
                                encoding="utf-8", newline="\n")
            log(f"[EMIT] {req_file.name}: {len(items)} 个标题待分析")
            return True

        if analysis == "apply" and not res_file.exists():
            raise SystemExit(f"{base}: 缺 {res_file.name}，请先 --emit-analysis 并完成分析")
        # 已有分析结果则自动应用（粘性）：普通重跑不会退化回启发式
        use_llm = res_file.exists()
        if use_llm:
            result = json.loads(res_file.read_text(encoding="utf-8"))
            req_items = json.loads(
                (toc_dir / f"{base}.analysis-request.json").read_text(encoding="utf-8"))["items"]
            flat = [(li, lv, t) for gps in head_groups for (li, lv, t) in gps]
            if len(req_items) != len(flat):
                raise SystemExit(f"{base}: 请求文件 {len(req_items)} 项与当前标题 {len(flat)} 项不符，"
                                 "请重新 --emit-analysis")
            errs = check_analysis(result["items"], req_items)
            if errs:
                raise SystemExit(f"{base}: 分析结果未通过硬校验:\n- " + "\n- ".join(errs))
            by_idx = {it["idx"]: it for it in result["items"]}
            for idx, (li, lv, t) in enumerate(flat):
                r = by_idx[idx]
                if r.get("action") == "noise":
                    actions[li] = ("demote", None, t)
                    demoted.append(t)
                else:
                    actions[li] = ("keep", int(r["level"]), t)
            report += [f"- 标题层级: LLM 分析判定（keep {len(flat) - len(demoted)} / noise {len(demoted)}）"]
            report += [f"- 分析依据: {result.get('notes', '')[:150]}"]
        if not use_llm:
            # 启发式 fallback：层级按编号深度（与 toc 同源）
            prev_depth = 0
            for gps in head_groups:
                for (li, lv, t) in gps:
                    lt = loose(t)
                    if lt in CALLOUT_WORDS or re.fullmatch(r"[IVX]+", lt) or lt.startswith("•") \
                            or (len(lt) > 50 and re.search(r"[。？！?!]", lt)):
                        actions[li] = ("demote", None, t)
                        demoted.append(t)
                        continue
                    k, _ = numkey(lt)
                    depth = (0 if re.fullmatch(r"[A-Z]", k) else k.count(".")) if k else prev_depth
                    prev_depth = depth
                    actions[li] = ("keep", depth + 2, t)
            # 级别跳变只记录不钳制（钳制会破坏 md/toc 一致性）
            seq = [v[1] for _, v in sorted(actions.items()) if v[0] == "keep"]
            if any(b - a > 1 for a, b in zip(seq, seq[1:])):
                report.append("- 级别跳变警告: 重建目录存在层级跳变（未钳制，建议人工复核）")

    # ---- 书签缺失 -> 补插（锚定到下一个已匹配章节前）----
    if rejected_ev:
        report += [f"- 乱序匹配拒绝: {len(rejected_ev)} 处（md 标题顺序与书签顺序矛盾，标题已降级、书签走补插）:"]
        report += [f"  - md「{e['md'][:30]}」 vs 书签「{e['bm'][:30]}」" for e in rejected_ev[:8]]
    kept_bm.sort()
    pending_ins, tail_ins, removals = {}, [], set()
    for bi, bm in enumerate(bm_list):
        if used[bi]:
            continue
        level = bm["depth"] + 2
        anchor_li = next((li for li, b2 in kept_bm if b2 > bi), None)
        if anchor_li is not None:
            pending_ins.setdefault(anchor_li, []).append((level, bm["title"], bm["page"]))
            # 锚点前紧邻的同名正文行 = 漏识别为标题的章名，吸收掉避免重复
            j = anchor_li - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0 and loose(lines[j].strip()) == loose(bm["title"]):
                removals.add(j)
        else:
            tail_ins.append((level, bm["title"], bm["page"]))
        used[bi] = True
        inserted_ev.append({"title": bm["title"], "page": bm["page"], "level": level})

    # ---- 重建 md ----
    final = []
    fence = False
    for idx, line in enumerate(lines):
        if FENCE_RE.match(line):
            fence = not fence
            final.append(line)
            continue
        if idx in removals:
            continue
        if idx in pending_ins:
            for level, title, _page in pending_ins[idx]:
                if final and final[-1].strip():
                    final.append("")
                final.append(f"{'#' * level} {title}")
                final.append("")
        if idx in actions:
            act = actions[idx]
            if act[0] == "keep":
                final.append(f"{'#' * act[1]} {act[2]}")
            else:
                final.append(act[2])
            continue
        if idx in collapse:
            continue
        final.append(line)
    for level, title, _page in tail_ins:
        final += ["", f"{'#' * level} {title}"]

    md_file.write_text("\n".join(final).rstrip("\n") + "\n", encoding="utf-8", newline="\n")

    # ---- toc.json ----
    if using_bookmarks:
        toc_items, stack = [], []
        for bi, bm in enumerate(bm_list):
            node = {"title": bm_title.get(bi, bm["title"]),
                    "level": bm["depth"] + 2, "page": bm["page"]}
            while stack and stack[-1][0] >= bm["depth"]:
                stack.pop()
            if stack:
                stack[-1][1].setdefault("children", []).append(node)
            else:
                toc_items.append(node)
            stack.append((bm["depth"], node))
        source = "pdf-bookmarks"
        if fuzzy_ev:
            report += ["- 模糊匹配章节（编号一致、文本有公式/破折号差异，toc 沿用 md 标题）:"]
            report += [f"  - 「{e['bm'][:30]}」-> 「{e['md'][:30]}」(p{e['page']})" for e in fuzzy_ev]
    else:
        fence, fh = False, []
        for line in final:
            if FENCE_RE.match(line):
                fence = not fence
                continue
            if fence:
                continue
            m = HEAD_RE.match(line)
            if m:
                fh.append((len(m.group(1)), m.group(2).strip()))
        toc_items, stack = [], []
        for lv, t in [(l, t) for l, t in fh if l > 1]:
            node = {"title": t, "level": lv,
                    "page": page_from_content_list(json_files, t)}
            d = lv - 2
            while stack and stack[-1][0] >= d:
                stack.pop()
            if stack:
                stack[-1][1].setdefault("children", []).append(node)
            else:
                toc_items.append(node)
            stack.append((d, node))
        source = "llm-analysis" if res_file.exists() else "md-rebuild"

    toc = {"book": base, "source": source, "total_pages": total_pages,
           "items": [{"title": root_title, "level": 1, "page": 1, "children": toc_items}]}
    toc_dir = output / "toc"
    toc_dir.mkdir(exist_ok=True)
    toc_file = toc_dir / f"{base}.toc.json"
    toc_file.write_text(json.dumps(toc, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")

    # ---- 一致性校验 ----
    def flatten(nodes):
        for n in nodes:
            yield n["title"], n["level"]
            yield from flatten(n.get("children", []))

    fence, md_seq = False, []
    for line in final:
        if FENCE_RE.match(line):
            fence = not fence
            continue
        if fence:
            continue
        m = HEAD_RE.match(line)
        if m:
            md_seq.append((m.group(2).strip(), len(m.group(1))))
    toc_seq = list(flatten(toc["items"]))

    diffs = []
    if len(md_seq) != len(toc_seq):
        diffs.append(f"数量不一致: md {len(md_seq)} vs toc {len(toc_seq)}")
    for i, ((mt, ml), (tt, tl)) in enumerate(zip(md_seq, toc_seq)):
        if loose(mt) != loose(tt) or ml != tl:
            diffs.append(f"第{i + 1}项: md=H{ml}「{mt[:30]}」 vs toc=L{tl}「{tt[:30]}」")

    report += [f"- 修复断行标题: {len(merged_ev)} 处"
               + ("".join(f"\n  - 合并 {e['n']} 行为「{e['title'][:36]}」" for e in merged_ev) if merged_ev else "（无）")]
    cat_stat = Counter(classify_extra(t) for t in demoted)
    report += [f"- 降级标题: {len(demoted)} 个（形态分类: "
               + "、".join(f"{k} {v}" for k, v in sorted(cat_stat.items(), key=lambda x: -x[1]))
               + "；其中“短语(灰区)”是书签粒度外的书内小节标题与强调句的混合，"
                 "经探索确认策略为全部降级，完整清单如下）:" if demoted else
               f"- 降级标题: 0 个"]
    report += [f"  - 「{t}」" for t in demoted]
    report += [f"- 补插缺失章节: {len(inserted_ev)} 个"
               + ("".join(f"\n  - 「{e['title'][:30]}」(p{e['page']})" for e in inserted_ev) if inserted_ev else "（无）")]
    report += [f"- 一致性校验: {'PASS' if not diffs else 'FAIL'} (md {len(md_seq)} 项 vs toc {len(toc_seq)} 项)"]
    for d in diffs[:10]:
        report += [f"  - {d}"]
    report += [""]
    return not diffs


def main():
    ap = argparse.ArgumentParser(description="分片 md 合并 + toc.json 生成 + 一致性校验")
    ap.add_argument("--input", default="input/pdf2md")
    ap.add_argument("--output", default="outputs/pdf2md")
    ap.add_argument("--only", default=None)
    ap.add_argument("--emit-analysis", action="store_true",
                    help="无书签文档：写出标题层级分析请求（供 LLM 分析），不写产物")
    ap.add_argument("--apply-analysis", action="store_true",
                    help="无书签文档：应用 .analysis-result.json 的层级判定并重建产物")
    args = ap.parse_args()
    if args.emit_analysis and args.apply_analysis:
        ap.error("--emit-analysis 与 --apply-analysis 互斥")
    mode = "emit" if args.emit_analysis else ("apply" if args.apply_analysis else None)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    input_dir, output = Path(args.input), Path(args.output)
    parts_dir = output / "parts"
    scan_dir = parts_dir if parts_dir.exists() else output  # 新版布局扫 parts/，旧布局扫根目录
    groups, singles = {}, []
    for f in sorted(scan_dir.glob("*.md")):
        if f.name == "toc_review.md":  # 审核报告自身不是文档
            continue
        m = PART_RE.match(f.stem)
        if m:
            groups.setdefault(m.group("base"), []).append(f)
        else:
            singles.append(f)
    bases = set(groups)
    singles = [f for f in singles if f.stem not in bases]

    docs = []
    for base, files in groups.items():
        if args.only and args.only not in base:
            continue
        docs.append((base, files))
    for f in singles:
        if args.only and args.only not in f.stem:
            continue
        docs.append((f.stem, [f]))

    report = ["# MinerU 产物整理审核报告", ""]
    all_ok = True
    for base, files in sorted(docs):
        parts = iter_part_files(output, base)
        pdf_path = input_dir / f"{base}.pdf"
        if mode and pdf_path.exists() and get_bookmarks(pdf_path):
            log(f"[SKIP] {base}: 有书签，走书签路径，无需 LLM 分析")
            continue
        ok = build_doc(base, parts, pdf_path, output, report, analysis=mode)
        if mode != "emit":
            all_ok &= ok
            log(f"[{'PASS' if ok else 'FAIL'}] {base}")

    report_path = output / "toc_review.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    log(f"审核报告: {report_path.resolve()}")
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
