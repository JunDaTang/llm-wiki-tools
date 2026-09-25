---
name: mineru-pdf2md
description: 用 MinerU 精准解析 API 批量把 PDF 转成完整 Markdown、结构化 JSON 和目录树 toc.json，并保证 md 标题与 toc 严格一致。当用户提到 PDF 转 md、pdf2md、MinerU、批量解析 PDF、书籍数字化、提取 PDF 目录、合并分片 md、修复标题结构时使用——即使用户没提 MinerU，只要是「把 PDF 或一批 PDF 变成 md」就适用。
---

# mineru-pdf2md

用 MinerU 精准解析 API（model_version=vlm）把 PDF（单本或一批）转成四类产物：**完整 Markdown**、**结构化 JSON**、**目录树 toc.json**（层级 + 全局页码）、**审核报告 toc_review.md**，并以一致性关卡保证完整 md 的标题序列与 toc.json 严格对齐。全部能力由本 skill 自带的两个零安装脚本承载：解析器 `scripts/mineru_pdf2md.py`、整理器 `scripts/build_book.py`（下文以 `<skill>/scripts/` 指代）。

## When to use this

- 「把这个 PDF 转成 md / pdf2md」「批量解析这批 PDF」「用 MinerU 解析」
- 「这几本书的分片 md 合并一下」「整理目录 / 生成 toc」「md 标题和目录对不上」
- 「上次解析好像中断了，继续跑」
- 不适用：只需要抽取纯文本（pdfplumber 等更轻）；需要保留 PDF 版式原样导出（这是内容重排，不是版式转换）。

## 前置条件（每次先确认）

1. **Token**：环境变量 `MINERU_TOKEN`（或 `--token`）。**绝不写入任何被 git 跟踪的文件**——用户在对话里给的 token 也只经环境变量传递，命令示例里用占位符。
2. **运行时**：脚本本身零安装依赖，用 uv 拉起（pypdf 负责拆分/书签，requests 负责 API）：
   `uv run --with pypdf --with requests python <skill>/scripts/<脚本>`
3. **计费意识**：MinerU 按解析计费。重跑已解析内容前先看 `<output>/.mineru_state.json`——已完成任务会自动跳过；`--force` 和删除 state 都会触发重新计费。

## Workflow

### 第 1 步：解析（mineru_pdf2md.py）

```bash
export MINERU_TOKEN=sk-xxxx
uv run --with pypdf --with requests python <skill>/scripts/mineru_pdf2md.py \
    --input input/pdf2md --output outputs/pdf2md
```

脚本自动完成：申请批量上传链接 → 超过 200 页的 PDF 用 pypdf 拆成 `{名}_1-200.pdf` 等分片 → PUT 上传 → 轮询 → 结果 zip 保留到 `<output>/zips/` → 解包 md 实际引用的图片到 `{书名}/images/`。md/json 本身留在 zip 内——**zips/ 是唯一原始来源**，整理器按需从 zip 内存提取，中间产物不落盘。

判断与要点：

- **断点续跑**：中断/失败后重跑同一命令即可，state 里的已完成任务自动跳过。轮询超时（默认 7200s）抛错后同样直接重跑续接。
- **硬限制**：单文件 ≤200MB 且 ≤200 页（超限自动拆分，无需人工干预）、单批 ≤50 个文件、上传链接 24h 有效。
- **过滤与强制**：`--only 关键词` 按文件名过滤；`--force` 忽略已完成状态强制重解析；`--ocr` 扫描件开 OCR（文本层 PDF 不需要，默认关）。
- **额外格式**：`--extra-formats html docx latex` 让 zip 里多出 `full.html/full.docx/full.tex`，但**不展开落盘**——默认产物就是 md + json。
- 结果 zip（在 zips/）是完整原始产物：`full.md`、`{uuid}_content_list.json(_v2)`、`model.json`、`layout.json`、`{uuid}_origin.pdf`、全部裁剪图、可选的额外格式。任何解析层疑问先翻 zip。
- 单任务 `failed` 会让脚本以非零码退出并在 state 里记 `err_msg`；修复原因后重跑，其余任务不受影响（state 各自独立）。

### 第 2 步：整理（build_book.py）

```bash
uv run --with pypdf python <skill>/scripts/build_book.py \
    --input input/pdf2md --output outputs/pdf2md
```

自动完成：分片 md 按页序合并成 `{书名}.md`（含跨片代码块缝合）→ 生成 `{书名}.toc.json` → md 标题清洗对齐 → **一致性关卡** → 审核报告 `toc_review.md`。

目录的生成路径按原书是否带书签分两条：

**A. 有书签（书签路径）**：从原 PDF 书签树生成 toc（层级权威、全局页码），md 标题向书签对齐清洗（降级误判、补插缺失章节、层级重写）。判定规则与探索结论见 `references/cleaning-rules.md`。

**B. 无书签（LLM 分析路径）**：标题层级由 agent 通读分析判定，脚本负责执行与验证，三步：

```bash
# a. 发射分析请求（{书名}.analysis-request.json：标题+上下文+页码，不写产物）
uv run --with pypdf python <skill>/scripts/build_book.py --input ... --output ... --emit-analysis
# b. agent 通读请求文件，判定每个标题的层级(2-6)或噪音，写 {书名}.analysis-result.json
#    （判定规则与噪音模式见 references/cleaning-rules.md「LLM 分析判定规则」）
# c. 应用判定（脚本硬校验：覆盖完整、同形态同层级、编号深度单调）→ 重建产物 + 一致性关卡
uv run --with pypdf python <skill>/scripts/build_book.py --input ... --output ... --apply-analysis
```

c 步校验失败会以明确错误退出（列出违规 idx），修正判定后重跑 c 即可。有书签的文档在 a/c 模式下自动跳过。
- **一致性关卡 FAIL = exit 1**：先读 `toc_review.md` 的差异清单定位，再修脚本逻辑或数据，**不要手改产物**——产物可由脚本幂等重建，手改会在下次重建时丢失。
- **降级策略**（已探索确认）：md 比书签多出的标题全部降级。其中约 58% 是明确噪音（信息框词/页眉/页码/强调句/列表项），42% 灰区里约 3/4 是书签粒度不足的真小节标题——但真小节与强调句形态不可自动区分，宁缺毋滥。完整清单带分类统计留在 toc_review.md 供复查。
- **无书签的书**：自动走 fallback——层级按标题编号深度推断、页码由 content_list.json 的 page_idx + 分片起始页反查。这是尽力而为，报告会明确标注"建议人工复核"；英文书 `Part I`/`Chapter N` 这类无数字编号的标题会被压平，属已知局限。
- **幂等**：重跑安全。分片书每次从原始分片重建；单文档原地清理亦幂等（已清理的标题再次匹配结果不变）。

### 第 3 步：验证与汇报

产物布局（顶层只有按书分文件夹，每本书自包含）：

```
<output>/
├── {书名}/
│   ├── {书名}.md               # 最终成品
│   ├── {书名}.toc.json         # 目录树（书签或 LLM 分析）
│   ├── {书名}.analysis-*.json  # 无书签书的 LLM 分析底稿（有书签书没有）
│   └── images/                 # 该书引用的图片
├── toc_review.md               # 跨书审核报告
├── zips/                       # 原始结果压缩包（唯一原始来源，含全部裁剪图/额外格式）
└── .mineru_state.json          # 解析断点状态
```

1. 看两个脚本的退出码与日志（`[PASS]/[FAIL]` 逐文档）。
2. 抽查 toc_review.md：补插/降级/缝合数量是否符合预期，抽查 2-3 个补插章节的上下文。
3. 检查产物引用完整性：所有 md 里 `images/` 相对引用都存在（搬动目录时尤其要连 images/ 一起搬）。
4. 向用户汇报：产物路径、各文档 PASS/FAIL、补插/降级/缝合计数、**消耗的解析额度**（任务数 × 页数）。

## 常见坑

- **token 入库 = 事故**：命令用 `export MINERU_TOKEN=...` 临时传递；发现 token 出现在任何持久化文件里立即提醒用户撤销重置。
- **文件名自带 `_数字-数字` 后缀的 PDF**（如 `报告_2024-1.pdf`）：整理器的分片正则 `^(.+)_(\d{1,4})-(\d{1,4})$` 会把它误判成分片。遇到时先重命名输入文件。
- **产物目录结构有隐含约定**：`{书名}.md` 引用 `images/` 相对路径；toc.json 的页码是整本 1-based 全局页码（分片书的分片局部页码已在补插/清洗时换算）。移动产物要整目录搬。
- **换行符**：zip 里的 `full.md` 是 CRLF，脚本已统一转 LF；json 统一 4 空格缩进 UTF-8。

## References

- 调 API 层问题（上传失败、轮询状态、payload 字段、callback）→ 读 `references/api.md`。
- 调清洗/一致性层问题（匹配阶段、乱序拒绝、降级分类、fallback 细则、探索结论）→ 读 `references/cleaning-rules.md`。
