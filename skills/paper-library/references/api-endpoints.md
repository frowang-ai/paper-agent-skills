# Paper API — Endpoint Quick Reference

Base URL: `https://frowang.com/paper-api/api/v1`

下表 CLI 列中的命令均以 `paper-agent library` 为前缀。例如 `search QUERY` 表示
`paper-agent library search QUERY`，`tag add` 表示 `paper-agent library tag add`。

权威来源：`llm_read_paper_ai_workflow/api/routers/{papers,collections,api_keys}.py`。
本表与后端实际路由保持一致，三端（后端 / CLI / MCP）对齐见 `../../docs/API_SURFACE.md`。

## 认证

> ⚠️ 路由表里**没有**"返回 PDF/Markdown 二进制"的端点。`GET /papers/{id}/assets`
> 只返回相对路径 URL（`pdf_url` / `ocr_markdown_url` / 等），文件本身挂在
> `https://frowang.com/paper-api/uploads/` 和 `https://frowang.com/paper-api/outputs/`
> 两个静态资源目录，下载方式见 `SKILL.md` 的 "下载静态资源" 小节。
> 注意：路径前缀是 `/paper-api/`，**不是** `/paper-api/api/v1/`；文件名需要 percent-encode；
> 必须带 `X-API-Key`（否则 Cloudflare 直接 403）。



| 方式 | Header | 适用范围 |
|------|--------|---------|
| API Key | `X-API-Key: pk_...` | 论文 / 标签 / 笔记 / 文件夹端点 |
| JWT | `Authorization: Bearer <token>` | API Key 管理端点 |

## 论文端点

| # | Method | Path | CLI 命令 | 说明 |
|---|--------|------|---------|------|
| 1 | POST | /papers | `upload FILE` / `upload-many` / `upload-dir` | 上传 PDF |
| 2 | GET | /papers | `list` | 列出论文 |
| 3 | GET | /papers/search | `search QUERY` | 论文发现（默认 L1+L2；可选 metadata/title scope） |
| 4 | GET | /papers/search/l1 | `search-layered QUERY --layer L1` | L1 元数据全文检索 |
| 5 | GET | /papers/search/l2 | `search-layered QUERY --layer L2` | L2 属性树全文检索 |
| 6 | GET | /papers/search/l3 | `search-layered QUERY --layer L3` | L3 历史/显式维护的 OCR 全文索引 |
| 7 | GET | /papers/search/all | `search-layered QUERY --layer all` | 跨层联合检索（默认 L1+L2） |
| 8 | GET | /papers/library | —（前端专用） | Library 聚合列表 |
| 9 | GET | /papers/{id} | `show ID` | 论文详情 |
| 10 | GET | /papers/{id}/fulltext | `fulltext ID --save FILE` | OCR 全文 |
| 11 | GET | /papers/{id}/summary | `summary ID --save FILE` | 摘要报告 |
| 12 | GET | /papers/{id}/deep | `deep ID --save FILE` | 深度报告 |
| 13 | GET | /papers/{id}/assets | `assets ID` | 产物 URL |
| 14 | POST | /papers/{id}/reprocess | `reprocess ID` | 重新处理 |
| 15 | PATCH | /papers/{id}/metadata | `update-metadata ID` | 修改元数据 |
| 16 | DELETE | /papers/{id} | `delete ID` | 删除论文（软删） |
| 17 | GET | /papers/{id}/metadata | `metadata ID [--save FILE]` | 学术元数据（title/authors/doi/citations 等） |
| 18 | GET | /papers/{id}/attribute-tree | `attribute-tree ID [--save FILE]` | 属性树 JSON |
| 19 | POST | /papers/{id}/screenshots | `screenshots ID --generate [--no-pdf] [--no-html] [--force] [--wait]` | 异步触发截图生成，返回 job_id |
| 20 | GET | /papers/{id}/screenshots | `screenshots ID [--job-id J]` | 查询已有截图（绝对 URL）或指定 job 进度 |

> `POST screenshots` 的 `capture_pdf` / `capture_html` / `force_rescreenshot` 均走 query
> param；两者同时为 false 时服务端返回 422 `INVALID_REQUEST`（CLI 的 `--no-pdf` +
> `--no-html` 在本地直接报 USAGE_ERROR）。`--wait` 按约 2.5s 间隔轮询
> `GET ?job_id=...` 直到 `completed`/`failed` 或 `--timeout`（默认 300s）。

## 标签端点

| # | Method | Path | CLI 命令 | 说明 |
|---|--------|------|---------|------|
| 21 | POST | /papers/{id}/tags | `tag add ID TAG...` | 添加标签（增量，裸数组 body） |
| 22 | PUT | /papers/{id}/tags | `tag set ID TAG...` | 全量覆盖标签 |
| 23 | DELETE | /papers/{id}/tags/{tag} | `tag remove ID TAG` | 移除单个标签 |

## 笔记端点

| # | Method | Path | CLI 命令 | 说明 |
|---|--------|------|---------|------|
| 24 | GET | /papers/{id}/notes | `note list ID` | 列出笔记 |
| 25 | POST | /papers/{id}/notes | `note add ID CONTENT` | 添加笔记（**content 走 query param**） |

> ⚠️ `note add` 的 `content` 是 query parameter，不是 JSON body：
> `POST /papers/{id}/notes?content=...`。历史版本曾误用 JSON body，已修正。

## 文件夹端点

| # | Method | Path | CLI 命令 | 说明 |
|---|--------|------|---------|------|
| 26 | GET | /collections | `collection list` | 列出文件夹 |
| 27 | POST | /collections | `collection create NAME` | 创建文件夹 |
| 28 | PATCH | /collections/{key} | `collection update KEY` | 重命名/移动/排序 |
| 29 | DELETE | /collections/{key} | `collection delete KEY` | 删除文件夹 |
| 30 | GET | /collections/{key}/items | `collection items KEY` | 文件夹内论文 |
| 31 | POST | /collections/{key}/items | `collection add KEY IDS...` | 论文加入文件夹 |
| 32 | DELETE | /collections/{key}/items | `collection remove KEY IDS...` | 论文移出文件夹 |
| — | GET | /collections/assigned-task-ids | —（UI 辅助，未暴露） | 所有已分配 task_id |
| — | GET | /collections/item-counts | —（UI 辅助，未暴露） | 各文件夹论文计数 |

## Key 管理端点（JWT only）

| # | Method | Path | CLI 命令 | 说明 |
|---|--------|------|---------|------|
| 33 | POST | /api-keys | `key create` | 生成 Key |
| 34 | GET | /api-keys | `key list` | 列出 Key |
| 35 | DELETE | /api-keys/{key_id} | `key revoke ID` | 吊销 Key |

## 响应格式

成功：`{"success": true, "data": {...}}`
错误：`{"detail": {"code": "NOT_FOUND", "message": "..."}}`（或 `{"detail": "string"}`）

常见错误码：`INVALID_FILE` / `FILE_TOO_LARGE` / `INVALID_API_KEY` /
`REVOKED_API_KEY` / `EXPIRED_API_KEY` / `NOT_FOUND` / `NOT_READY`。
