---
name: paper-library
description: 通过 paper-agent 管理 Frowang 远程论文库：上传 PDF、发现和查看论文、获取全文或报告、管理标签、笔记和 Collection。用户说“帮我查论文”“上传这篇 paper”“给论文打标签”“下载论文原文”时触发。
---

# Paper Library

使用稳定的 `paper-agent library` 命令管理用户的远程 Frowang 论文库。Skill 只负责编排，
不要直接读取 `.env`、拼 REST URL 或调用 Skill 目录中的 Python 源码。

## 前置检查

首次使用或认证失败时执行：

```bash
paper-agent config init
paper-agent auth status
paper-agent doctor
```

若 `doctor` 输出中的 `update` 检查显示 `update_available`（或运行 `paper-agent update check`
确认），告知用户有新版本；经用户确认后执行 `uv tool install paper-agent-skills --upgrade`，
再运行 `paper-agent skills update --platform all` 刷新已安装 Skill，然后重跑用户原本的命令。

若 `auth status` 显示未配置，请用户直接把 API Key 发过来，然后运行
`paper-agent auth set --stdin` 代为配置；用户也可以自己在终端运行 `paper-agent auth set`
隐藏输入。提醒用户：该 Key 权限很高，可访问和修改其整个论文库，不要泄露给他人。配置完成
后无需复述 Key。用户只需配置一次；兼容环境变量
`FROWANG_API_KEY`、`PAPER_API_KEY` 仍可用，但不要在 Skill 目录创建新的 `.env`。

非交互执行默认向 stdout 输出单个 JSON envelope；若执行工具分配了交互 TTY，必须给需要
结构化解析的命令显式增加 `--json`：

```json
{"schema_version":"1","success":true,"data":{},"meta":{"command":"library.list"}}
```

失败时读取 `error.code` 和进程 exit code，不要只匹配自然语言错误消息。

## 论文发现

默认使用 L1 元数据和 L2 属性树发现候选论文：

```bash
paper-agent library search "instrumental variables" --limit 10
paper-agent library search "attention" --scope metadata
paper-agent library list --limit 20 --tag causal
paper-agent library show P-3a
```

只有用户明确要求检查历史全文索引时才使用分层检索：

```bash
paper-agent library search-layered "exclusion restriction" --layer L3
paper-agent library search-layered "IV" --layer all --layers L1,L3
```

新论文不会自动建立 L3 索引，因此 L3 无命中不表示正文没有相关内容。

## 上传论文

```bash
paper-agent library upload ./paper.pdf
paper-agent library upload-many ./a.pdf ./b.pdf
paper-agent library upload-dir ./pdfs
```

批量上传逐文件返回 `uploaded`、`duplicate`、`skipped` 或 `error`。上传成功后保存返回的
`short_id`、`paper_id` 和 `task_id`；OCR 尚未完成时，内容命令可能返回 `NOT_READY`。

## 获取内容

全文和报告必须保存到文件，不能把长文本直接输出到 Agent context：

```bash
paper-agent library fulltext P-3a --save ./papers/P-3a/full.md
paper-agent library summary P-3a --save ./papers/P-3a/summary.md
paper-agent library deep P-3a --save ./papers/P-3a/deep.md
```

命令成功后 `data` 返回 `path`、`bytes`、`kind` 和 `paper_id`。这是显式导出单个内容文件的
兼容路径；需要建立可同步的项目论文集合时，改用 `paper-workspace` 的 `workspace add`。

产物 URL 与静态文件下载分为两步：

```bash
paper-agent library assets P-3a
paper-agent library download-asset "/paper-api/outputs/.../layout.json" ./papers/P-3a/layout.json
```

`download-asset` 会校验 Frowang origin/path、编码文件名、流式写临时文件、计算 SHA-256，
最后原子替换目标文件。不要用未经校验的 `curl` 代替该命令。

学术元数据（含 `citations.apa` 引文）和属性树内容较小，可直接进入 context，
也可 `--save` 落盘：

```bash
paper-agent library metadata P-3a
paper-agent library metadata P-3a --save ./papers/P-3a/metadata.json
paper-agent library attribute-tree P-3a
paper-agent library attribute-tree P-3a --save ./papers/P-3a/attribute_tree.json
```

需要论文截图（PDF 前三页 + 深度报告长图）用于展示或发帖时：

```bash
paper-agent library screenshots P-3a                    # 查询已有截图
paper-agent library screenshots P-3a --generate --wait  # 触发并等待生成完成
```

返回的 `html_images` / `pdf_images` 是 `https://frowang.com/paper-api/...` 绝对 URL，
可直接展示；`--generate` 不加 `--wait` 时先返回 `job_id`，之后用
`--job-id <id>` 查询进度。可选 `--no-pdf`、`--no-html`、`--force`、`--timeout`。

## 管理论文

```bash
paper-agent library update-metadata P-3a --title "New title" --year 2025
paper-agent library reprocess P-3a
paper-agent library delete P-3a

paper-agent library tag add P-3a causal IV
paper-agent library tag set P-3a economics methods
paper-agent library tag remove P-3a old-tag

paper-agent library note list P-3a
paper-agent library note add P-3a "Check the robustness table"
```

删除和重新处理会改变远程状态。Agent 必须先说明目标论文并取得用户确认，再执行
`delete` 或 `reprocess`。

## PDF 批注

批注是用户在网页端 PDF 阅读器上做的高亮/笔记，按 `pageIndex + rects` 定位。
Agent 只做读和 comment 追加，不创建带坐标的新高亮：

```bash
# 查看某篇论文的全部批注（含 text 选中文本和 comment）
paper-agent library annotation list P-3a

# 增量拉取（配合上次同步的 serverTime）
paper-agent library annotation list P-3a --since 2026-08-01T00:00:00.000000

# 向已有批注追加评论（换行拼接，不覆盖用户原有 comment）
paper-agent library annotation comment P-3a ann-xxxx "Agent: 该方法与 Table 3 的结果矛盾"
```

约束：
- `comment` 是追加语义，绝不覆盖用户已写的批注内容。
- 不通过 `sync` 端点批量 upsert 新批注或删除批注——那是用户客户端的职责。
- 批注 id 是客户端生成的 UUID，只能从 `annotation list` 结果中获取。

## 管理 Collection

Collection 是服务器端文件夹，不等同于本地研究 workspace：

```bash
paper-agent library collection list
paper-agent library collection create "Causal Papers" --parent C-1
paper-agent library collection update C-2 --name "Core Papers"
paper-agent library collection update C-2 --parent null
paper-agent library collection items C-2
paper-agent library collection add C-2 task_id_1 task_id_2
paper-agent library collection remove C-2 task_id_1
paper-agent library collection delete C-2
```

Collection 的 add/remove 参数是论文 `task_id`，不是 `P-xxx` short ID。执行删除前先列出
Collection 和 items，并向用户确认。

## API Key 管理

通常让用户在网站 UI 管理 API Key。只有用户明确提供网页登录 JWT 并要求命令行操作时：

```bash
paper-agent library key create --jwt-token "$JWT" --name codex
paper-agent library key list --jwt-token "$JWT"
paper-agent library key revoke KEY_ID --jwt-token "$JWT"
```

JWT 只能作为当前命令参数使用，不得写入项目文件、Skill 文件或对话结果。

## 错误处理

| `error.code` | 处理方式 |
|---|---|
| `AUTH_MISSING` | 引导用户运行 `config init` 并配置 Key |
| `AUTH_INVALID` | 停止重试，要求用户检查或更新 Key |
| `NOT_FOUND` | 重新搜索或核对 short ID |
| `NOT_READY` | 论文仍在处理，稍后再次查询 |
| `NETWORK_ERROR` | 可在短暂等待后有限重试 |
| `REMOTE_ERROR` | 查看 `retryable`；不可重试时报告服务端错误 |
| `CONFLICT` | 停止自动操作并向用户说明冲突 |
| `LOCAL_IO_ERROR` | 检查目标目录和权限，不要改写其他路径 |

## 推荐工作流

1. 用 `library search` 在服务器候选池中发现论文。
2. 用 `library show` 或保存 summary 判断是否加入当前研究项目。
3. 用 `paper-agent workspace add <project-root> <paper-id>` 把选中论文加入项目。
4. 在本地用 `rg -n -C 5 "term" <project-root>/papers/*/full.md` 高频定位原文。
5. 引用证据时同时记录论文 short ID、文件路径和行号；需要页码时结合 `layout.json`。

更完整的端点和参数语义见 `references/api-endpoints.md`。
