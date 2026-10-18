# Agent API Surface — 后端 × CLI × MCP 三端矩阵

> 维护原则（见 `website/docs/CONVENTIONS.md` "Agent API Surface Sync"）：
> 新增或修改后端 REST 端点后，必须同步 MCP Server、CLI Skill、SKILL.md 三处。

权威后端源：
- `llm_read_paper_ai_workflow/api/routers/papers.py`
- `llm_read_paper_ai_workflow/api/routers/collections.py`
- `llm_read_paper_ai_workflow/api/routers/api_keys.py`
- `llm_read_paper_ai_workflow/api/chat/agentic/router.py`

## 统一个人助手端点

统一助手使用同一套 API Key 鉴权。`POST /chat/agentic` 和重试端点返回 SSE；共享
`FrowangClient` 与 `mcp_paper_server.PaperAPIClient` 都按事件逐行解析，并对单个事件设置
大小上限。MCP 的一次性 Tool 响应还限制事件数量和总字节数，避免把无界流读入内存。

| 后端路由 | Python client | CLI 命令 | MCP tool | 状态 |
|---------|---------------|----------|----------|------|
| `POST /chat/agentic`（SSE） | `FrowangClient.stream_agentic_chat` / `PaperAPIClient.agentic_chat` | `paper-agent assistant ask` | `assistant_ask` | ✅ |
| `GET /chat/conversations` | `list_chat_conversations` / `list_chat_conversations` | `paper-agent assistant list` | `assistant_list` | ✅ |
| `GET /chat/conversations/{id}/history` | `get_chat_history` / `get_chat_history` | `paper-agent assistant history` | `assistant_history` | ✅ |
| `POST /chat/runs/{id}/stop` | `stop_chat_run` / `stop_chat_run` | `paper-agent assistant stop` | `assistant_stop` | ✅ |
| `POST /chat/conversations/{id}/retry`（SSE） | `retry_agentic_chat` / `retry_agentic_chat` | — | — | ⚪ Python client only（CLI/MCP 当前按最小 ask/list/history/stop 面提供） |
| `DELETE /chat/conversations/{id}` | `delete_chat_conversation` / `delete_chat_conversation` | — | — | ⚪ Python client only |
| `DELETE /chat/conversations/{id}/messages/{id}` | `delete_chat_message` / `delete_chat_message` | — | — | ⚪ Python client only |

## Short ID 支持

所有接受 `{id}` / `{key}` 路径参数的端点同时支持 **short_id**（`P-xxx` / `C-xxx`，Base36 编码）和完整 UUID。列表接口返回的每条记录都包含 `short_id` 字段。

- 论文：`P-1`, `P-a3f`, `P-zzzzzz`（6 位 Base36 = 21 亿条）
- 文件夹：`C-1`, `C-b7`
- fulltext/summary/deep 端点区分 `NOT_FOUND`（论文不存在）和 `NOT_READY`（论文存在但产物未就绪）

## 论文端点

| 后端路由 | CLI 命令 | MCP tool | 状态 |
|---------|---------|----------|------|
| `POST /papers` | `paper-agent library upload/upload-many/upload-dir` | `upload_paper` / `batch_upload_papers` | ✅ 三端 |
| `GET /papers` | `paper-agent library list` | `list_papers` | ✅ |
| `GET /papers/search`（默认 L1+L2 discovery；可选 metadata/title scope） | `paper-agent library search` | `search_papers` | ✅ |
| `GET /papers/search/l1` | `paper-agent library search-layered --layer L1` | `search_papers_layered` | ✅ |
| `GET /papers/search/l2` | `paper-agent library search-layered --layer L2` | `search_papers_layered` | ✅ |
| `GET /papers/search/l3`（仅历史/显式维护索引；新论文不自动建立） | `paper-agent library search-layered --layer L3` | `search_papers_layered` | ✅ |
| `GET /papers/search/all`（默认 L1+L2，L3 需显式指定） | `paper-agent library search-layered --layer all` | `search_papers_layered` | ✅ |
| `GET /papers/library` | —（前端专用，未暴露） | — | ⚪ 仅前端 |
| `GET /papers/{id}` | `paper-agent library show` | `get_paper` | ✅ |
| `GET /papers/{id}/fulltext` | `paper-agent library fulltext --save` | `get_fulltext` | ✅ |
| `GET /papers/{id}/summary` | `paper-agent library summary --save` | `get_summary` | ✅ |
| `GET /papers/{id}/deep` | `paper-agent library deep --save` | `get_deep_report` | ✅ |
| `GET /papers/{id}/assets` | `paper-agent library assets` | `get_assets` | ✅ |
| `POST /papers/{id}/reprocess` | `paper-agent library reprocess` | `reprocess_paper` | ✅ |
| `PATCH /papers/{id}/metadata` | `paper-agent library update-metadata` | `update_paper_metadata` | ✅ |
| `DELETE /papers/{id}` | `paper-agent library delete` | `delete_paper` | ✅ |

## 标签端点

| 后端路由 | CLI 命令 | MCP tool | 状态 |
|---------|---------|----------|------|
| `POST /papers/{id}/tags` | `paper-agent library tag add` | `add_tags` | ✅ |
| `PUT /papers/{id}/tags` | `paper-agent library tag set` | **缺 `replace_tags`** | ⚠️ 见待办 |
| `DELETE /papers/{id}/tags/{tag}` | `paper-agent library tag remove` | `remove_tag` | ✅ |

## 笔记端点

| 后端路由 | CLI 命令 | MCP tool | 状态 |
|---------|---------|----------|------|
| `GET /papers/{id}/notes` | `paper-agent library note list` | **缺 `list_notes`** | ⚠️ 见待办 |
| `POST /papers/{id}/notes`（`content` query param） | `paper-agent library note add` | `add_note` | ✅ |

## 协作作用域端点（collab，0.9.3 起 CLI 支持）

协作收藏夹里的论文是独立副本，scoped ID 形如 `collab~<root_key>~<paper_id>`（由
`collection items` 返回）。CLI paper 级命令接受该 ID 并路由到 workspace 端点，
读写落在共享副本（workspace 存储，全成员可见、带作者归属），不再误写私有库。

| 后端路由 | CLI 命令 | 状态 |
|---------|---------|------|
| `GET /collections/{root}/papers/{id}` | `library show collab~...` | ✅ |
| `GET/PATCH /collections/{root}/papers/{id}/metadata` | `metadata` / `update-metadata collab~...` | ✅ |
| `POST/PUT/DELETE /collections/{root}/papers/{id}/tags[...]` | `tag add/set/remove collab~...` | ✅ |
| `GET /collections/{root}/papers/{id}/notes` | `note list collab~...` | ✅ |
| `POST /collections/{root}/papers/{id}/notes`（JSON body） | `note add collab~...` | ✅ |
| `GET /collections/{root}/papers/{id}/annotations` | `annotation list collab~...`（全量快照，无 `--since`） | ✅ |
| `POST /papers/{id}/annotations/locate`、`POST /collections/{root}/papers/{id}/annotations/locate` | `annotation locate`（原文定位，只读） | ✅ |
| `POST /papers/{id}/annotations`、`POST /collections/{root}/papers/{id}/annotations` | `annotation add`（按原文创建，幂等） | ✅ |
| `POST /collections/{root}/papers/{id}/annotations/sync` | `annotation comment collab~...`（他人批注只读，CLI 写后重读校验） | ✅ |
| `POST /collections/{root}/papers/{id}/actions/reprocess` | `reprocess collab~...` | ✅ |
| 无协作等价端点 | `fulltext`/`summary`/`deep`/`assets`/`attribute-tree`/screenshots GET | ✅ 降级底层 paper 私有读端点 |
| 无协作等价端点 | `delete` / screenshots 生成 | ⛔ 对 collab ID 明确报 USAGE_ERROR |
| 无协作等价端点 | `workspace add/sync`（0.9.6 起） | ✅ 接受 `collab~` 引用：身份保留 scoped 形态，缓存目录派生安全段；revision 以产物 URL 内嵌任务号为准，学术元数据走 workspace metadata 端点 |

## 协作关系管理端点（0.9.4 起 CLI 支持）

服务端路由 `collection_collab.py`，0.9.4 起认证从仅 JWT 放宽为 `get_current_user_id`
（X-API-Key 可用，需服务端部署后生效）。

| Method | Path | CLI 命令 | 说明 |
|--------|------|---------|------|
| POST | /collections/{key}/collab-invites | `collab enable KEY` | 启用协作+生成邀请（树根+owner；单活；明文 invite_url 仅本次返回） |
| GET | /collections/{key}/collab-invites | `collab invite-status KEY` | 当前邀请状态（无明文 token） |
| DELETE | /collections/{key}/collab-invites/{invite_id} | `collab invite-revoke KEY INV` | 撤销邀请 |
| GET | /collab-invites/{token} | `collab invite-preview TOKEN` | 受邀方预览+viewer_state |
| POST | /collab-invites/{token}/apply | `collab apply TOKEN` | 申请加入（幂等三态） |
| GET | /collections/{key}/join-requests | `collab requests KEY [--status]` | 申请者列表（含 requester_user_id） |
| POST | /collections/{key}/join-requests/{id}/approve | `collab approve KEY REQ` | 批准 |
| POST | /collections/{key}/join-requests/approve-all | `collab approve-all KEY` | 批量批准 |
| POST | /collections/{key}/join-requests/{id}/reject | `collab reject KEY REQ` | 拒绝 |
| GET | /collections/{key}/members | `collab members KEY` | 成员列表 |
| DELETE | /collections/{key}/members/{uid} | `collab remove-member KEY UID` | 移除成员 |
| POST | /collections/{key}/leave | `collab leave KEY` | 自行退出 |
| GET | /collections/{key}/collab-info | `collab info KEY` | 我的角色+计数 |
| GET | /collab-pending-summary | `collab pending-summary` | 我名下待审批汇总 |

## 文件夹端点

| 后端路由 | CLI 命令 | MCP tool | 状态 |
|---------|---------|----------|------|
| `GET /collections` | `paper-agent library collection list` | `list_collections` | ✅ |
| `POST /collections` | `paper-agent library collection create` | `create_collection` | ✅ |
| `PATCH /collections/{key}` | `paper-agent library collection update` | `update_collection` | ✅ |
| `DELETE /collections/{key}` | `paper-agent library collection delete` | `delete_collection` | ✅ |
| `GET /collections/{key}/items` | `paper-agent library collection items` | `get_collection_items` | ✅ |
| `POST /collections/{key}/items` | `paper-agent library collection add` | `add_collection_items` | ✅ |
| `DELETE /collections/{key}/items` | `paper-agent library collection remove` | `remove_collection_items` | ✅ |
| `GET /collections/assigned-task-ids` | —（UI 辅助） | — | ⚪ 仅前端 |
| `GET /collections/item-counts` | —（UI 辅助） | — | ⚪ 仅前端 |

## API Key 管理（JWT only）

| 后端路由 | CLI 命令 | MCP tool | 状态 |
|---------|---------|----------|------|
| `POST /api-keys` | `paper-agent library key create` | —（用户应在网站 UI 操作） | ⚪ |
| `GET /api-keys` | `paper-agent library key list` | — | ⚪ |
| `DELETE /api-keys/{key_id}` | `paper-agent library key revoke` | — | ⚪ |

## 本地凭据管理（无对应 REST/MCP）

| 本地能力 | CLI 命令 | 安全合同 |
|---|---|---|
| 隐藏式设置 Frowang Key | `paper-agent auth set` | 在终端读取，不回显 |
| Agent 通过 stdin 设置 | `paper-agent auth set --stdin` | Key 不进入 `paper-agent` 进程参数 |
| 查询状态 | `paper-agent auth status` | 只返回 configured/source，不返回值 |
| 删除受管 Key | `paper-agent auth delete` | 删除凭据文件中新旧 Frowang 别名，不修改环境变量 |

## 本地 Artifact 与 Workspace（无对应 REST/MCP）

| 本地能力 | CLI 命令 | 权威状态 |
|---|---|---|
| 同步 text revision | `paper-agent paper pull <paper-id>` | 用户 data artifact manifest + SQLite |
| 初始化项目工作区 | `paper-agent workspace init <project-root>` | 项目 `papers/manifest.json` |
| 加入论文 | `paper-agent workspace add <project-root> <paper-ids...>` | 项目 manifest |
| 本地状态 | `paper-agent workspace list/status <project-root>` | 项目文件 hash |
| 更新 revision | `paper-agent workspace sync <project-root> [paper-ids...]` | remote assets -> global -> project |
| 移除成员 | `paper-agent workspace remove <project-root> <paper-ids...>` | 项目 manifest，不删除全局缓存 |
| 规划可读目录名 | `paper-agent workspace names plan <project-root> [paper-ids...]` | metadata + 项目 manifest |
| 应用目录重命名 | `paper-agent workspace names apply <project-root> [paper-ids...]` | 项目目录 + manifest 原子更新 |

`paper pull` 组合调用 `GET /papers/{id}` 与 `GET /papers/{id}/assets`，然后下载同源
`/outputs/` 或兼容反向代理前缀下的静态资产。workspace 是纯本地产品层，不应为它新增同名
服务端 Collection API。

---

## 待办（本次不修，记录追踪）

### 1. MCP 缺 `list_notes`

后端有 `GET /papers/{id}/notes`，CLI 有 `note list`，MCP Client 也已有
`list_notes(paper_id)` 方法，但 `mcp_paper_server/server.py` 尚未注册和分发
`list_notes` Tool，因此 Agent 当前不能通过 MCP 列出论文笔记。

`add_note` 已使用正确的 `/papers/{id}/notes` 路径和 `content` query parameter，
并已在 MCP Server 注册、分发，不再属于待办。

### 2. MCP 缺 `replace_tags`

后端有 `PUT /papers/{id}/tags`，CLI 有 `tag set`，但 MCP 只有 `add_tags`/`remove_tag`。
若要三端一致，应在 `mcp_paper_server/server.py` + `client.py` 补 `replace_tags` tool。

### 3. Collections UI 辅助端点

`/collections/assigned-task-ids`、`/collections/item-counts` 偏前端 UI，
当前刻意不给 Agent 暴露。若将来 Agent 有需要再评估。
