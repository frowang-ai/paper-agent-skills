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

若 `auth status` 显示未配置，优先让用户运行 `paper-agent auth set` 并在终端隐藏输入。若用户
已经明确在对话中提供 Key，并要求 Agent 代为配置，只能通过进程标准输入调用
`paper-agent auth set --stdin`；不得把 Key 拼进命令参数、回答、日志或临时文件。执行工具不能
单独传递 stdin 时，应改请用户使用隐藏式输入。用户只需配置一次；兼容环境变量
`FROWANG_API_KEY`、`PAPER_API_KEY` 仍可用，但不要在 Skill 目录创建新的 `.env`。

所有正式命令默认向 stdout 输出单个 JSON envelope：

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

更完整的端点和参数语义见 `references/api-endpoints.md`。旧入口
`python scripts/paper_cli.py ...` 仅用于迁移，会向 stderr 输出 deprecation warning；新工作流
不得继续依赖它。
