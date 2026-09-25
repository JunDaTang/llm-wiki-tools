# MinerU 精准解析 API 参考（v4 批量接口）

调试 API 层问题时读本文。所有端点基址 `https://mineru.net`，鉴权 `Authorization: Bearer <token>`。

## 端点与流程

```
1. POST /api/v4/file-urls/batch          申请批量上传链接（单批 ≤50 个文件）
2. PUT  {presigned_url}                  逐个上传文件（二进制流，不要设 Content-Type）
3. GET  /api/v4/extract-results/batch/{batch_id}   轮询结果
4. GET  {full_zip_url}                   下载结果 zip（CDN）
```

上传后系统**自动**开始解析，没有单独的"提交"步骤。上传链接 24h 有效。

## 申请上传链接

请求体（关键字段）：

```json
{
  "model_version": "vlm",
  "language": "ch",
  "enable_formula": true,
  "enable_table": true,
  "extra_formats": ["html", "docx", "latex"],
  "files": [
    {"name": "书名_1-200.pdf", "data_id": "书名_1-200", "is_ocr": false}
  ]
}
```

- `model_version`：`vlm`（推荐，默认视觉模型）/ `pipeline`（旧管线，产出 middle.json）/ `MinerU-HTML`（解析 HTML 输入时必须指定）。
- `is_ocr`：仅 pipeline/vlm 生效；文本层 PDF 关闭即可，扫描件开启。
- `page_ranges`：服务端页码范围（如 `"1-200"`）。本 skill 不用它——用本地拆分替代，因为单文件 200 页上限是按上传文件校验的。
- `extra_formats`：可选 `docx/html/latex`，结果进 zip 而不改变 md/json 主产物。
- `callback`/`seed`：可选回调推送（SHA256 校验，最多重推 5 次），本 skill 用轮询，未启用。

响应：

```json
{"code": 0, "data": {"batch_id": "2bb2f0ec-...", "file_urls": ["https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***"]}}
```

`file_urls` 与 `files` 按下标一一对应。`code != 0` 一律视为失败（msg 在 `msg` 字段）。

## 轮询结果

`GET /api/v4/extract-results/batch/{batch_id}` 返回：

```json
{"code": 0, "data": {"batch_id": "...", "extract_result": [
  {"file_name": "书名_1-200.pdf", "state": "done",
   "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/2026-09-25/{uuid}.zip"},
  {"file_name": "b.pdf", "state": "running",
   "extract_progress": {"extracted_pages": 5, "total_pages": 200, "start_time": "..."}}
]}}
```

状态机：`waiting-file`（未上传完）→ `pending` → `running` → `converting`（额外格式转换阶段）→ `done` / `failed`。
`failed` 时看该条目的 `err_msg`。轮询按 batch 进行，批内各文件状态独立。

## 结果 zip 内容（vlm 模式实测）

```
full.md                                    ← Markdown 主产物（CRLF，引用 images/ 相对路径）
{uuid}_content_list.json                   ← 结构化内容清单（json 主产物）
{uuid}_content_list_v2.json                ← v2 清单
{uuid}_model.json                          ← vlm 原始输出
layout.json                                ← 版面分析
{uuid}_origin.pdf                          ← 原文副本
images/*.jpg                               ← 全部裁剪图（含 md 未引用的公式/表格裁剪）
full.html / full.docx / full.tex           ← 仅当申请了 extra_formats
```

注意：vlm 模式**没有** middle.json（那是 pipeline 模式的产物）。

## 实测结论（踩坑记录）

- **MinerU 不读 PDF 书签**：同一 6 页 PDF 带 20 条书签与 0 条书签分别上传，输出逐字节一致（两次独立解析，非缓存）。书签只能用于业务层后处理。
- **单文件限制按上传文件校验**：≤200MB 且 ≤200 页。本地拆分（pypdf）绕过页数限制；拆分后的分片不带 outline（pypdf 不复制书签树），但不影响解析。
- **服务端有结果缓存**：文件内容相同的分片会返回同一份结果（相同结果 uuid）。带/不带书签的 PDF 因元数据不同算不同文件。
- **运行间方差**：同内容两次解析，公式 LaTeX 渲染可能有细微差异、图片裁剪哈希会变（同一张图两次运行得到不同文件名）。跨运行 diff 时先排除这两类。
- **md 里图片是本地相对路径**（`images/xxx.jpg`），不是 CDN 外链——平台网页版导出才是 CDN 链接，两者不可互推（实测 CDN 反推 403）。
