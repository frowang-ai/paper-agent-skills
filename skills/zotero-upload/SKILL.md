---
name: zotero-upload
description: 通过 paper-agent 从 Zotero 桌面端或 Web API 发现论文 PDF，并增量上传到 Frowang 远程论文库。用户说“把 Zotero 的论文上传到网站”“同步这个 Zotero Collection”“上传 Zotero 中这篇论文”时触发。
---

# Zotero Upload

使用稳定的 `paper-agent zotero` 命令把 Zotero 论文导入 Frowang。Skill 只编排命令，不能
直接读取 Zotero profile、`.env`、`sync_state.json` 或调用 Skill 目录中的 Python 模块。

## 前置检查

```bash
paper-agent config init
paper-agent auth status
paper-agent doctor
```

若 `doctor` 输出中的 `update` 检查显示 `update_available`（或运行 `paper-agent update check`
确认），告知用户有新版本；经用户确认后执行 `uv tool install paper-agent-skills --upgrade`，
再运行 `paper-agent skills update --platform all` 刷新已安装 Skill，然后重跑用户原本的命令。

认证缺失时，请用户直接把 API Key 发过来，然后运行 `paper-agent auth set --stdin` 代为配置；
用户也可以自己在终端运行 `paper-agent auth set` 隐藏输入。提醒用户：该 Key 权限很高，可访问
和修改其整个论文库，不要泄露给他人。配置完成后无需复述 Key。

本地模式要求 Zotero 桌面端正在运行，并已允许本机应用访问本地 API。Frowang Key 使用
统一的 `FROWANG_API_KEY` 或用户级 `credentials.env`，不在本 Skill 中重复配置。

默认 profile 使用：

```toml
[profiles.default.zotero]
mode = "local"
library_type = "user"
library_id = "0"
storage_dir = ""
```

`storage_dir` 留空时，runtime 从 Zotero `profiles.ini` 和 `prefs.js` 自动发现。只有自动发现
失败时才在 `config.toml` 设置明确路径，或对当前命令传 `--storage-dir PATH`。

远程模式需要设置 `mode = "remote"`、正确的 `library_id/library_type`，并在用户级凭据中
配置 `ZOTERO_API_KEY`。本地失败不会静默 fallback 到远程模式。

## 发现 Collection

```bash
paper-agent zotero collections
paper-agent zotero items COLLECTION_KEY
paper-agent zotero items COLLECTION_KEY --recursive
```

先把 Collection 列表展示给用户，确认目标 key 后再预览上传。`items` 返回每篇论文的
`item_key`、attachment key、PDF 是否已经下载到本地，以及解析后的 PDF 路径。

## 上传 Collection

为用户挑选上传目标时，优先论文较少或最近有更新的 Collection；上传论文会消耗账号积分，
正式上传前用 dry-run 的数量向用户说明规模并取得明确同意。不要提议一次性同步整个
Zotero 库。

始终先 dry-run：

```bash
paper-agent zotero upload COLLECTION_KEY --dry-run
```

dry-run 不要求 Frowang Key，不创建远程 Collection，也不写同步状态。向用户报告：

- Collection 数量和唯一论文数。
- 待上传、已同步、缺少本地 PDF 的数量。
- 一篇论文属于多个子 Collection 时的目标列表。

用户确认后正式执行：

```bash
paper-agent zotero upload COLLECTION_KEY
paper-agent zotero upload COLLECTION_KEY --name "Frowang Collection Name"
```

运行时会：

1. 读取 Zotero Collection 树和本地附件。
2. 从全局 SQLite state store 跳过已同步 item。
3. 复用已记录的 Frowang Collection 映射，避免重复创建目录树。
4. 同一 Zotero item 即使属于多个 Collection，也只上传一次。
5. 将返回的 `task_id` 加入所有对应 Frowang Collection。
6. 逐项记录成功、重复、缺少 PDF、membership error 和上传错误。

`--no-sync` 会忽略 item 同步记录并再次调用上传，仅用于用户明确要求重新导入的场景；
它不会清空状态或删除远程论文。

## 上传单篇论文

```bash
paper-agent zotero upload-one ITEM_KEY
paper-agent zotero upload-one ITEM_KEY --target C-2
```

指定 `--target` 时使用 Frowang Collection short ID。已有同步记录默认返回 `skipped`；只有
用户明确要求时才加 `--no-sync`。

## 同步状态

状态保存在 platformdirs 用户 data 目录的 `state.sqlite3`，不在 Skill 安装目录：

```bash
paper-agent zotero status
paper-agent zotero status --limit 50
```

旧脚本若存在 `sync_state.json`，只迁移一次：

```bash
paper-agent zotero migrate-state /absolute/path/to/sync_state.json
```

迁移是幂等的。成功导入并核对 `zotero status` 后，旧 JSON 可由用户手动归档或删除。

## 错误处理

| `error.code` | 处理方式 |
|---|---|
| `NETWORK_ERROR` | 本地模式检查 Zotero 是否运行及 API 开关；远程模式检查网络 |
| `AUTH_MISSING` | 远程 Zotero 或 Frowang 上传缺少对应 Key |
| `AUTH_INVALID` | 停止重试，让用户更新对应凭据 |
| `NOT_FOUND` | Collection/item key 不存在，重新列出并确认 |
| `NOT_READY` | PDF 附件未下载到本地，让用户在 Zotero 中打开附件触发下载 |
| `LOCAL_IO_ERROR` | 检查 Zotero storage 或全局 state DB 权限 |
| `REMOTE_ERROR` | 查看逐项结果，不要把部分成功误报为整体失败或整体成功 |

详细连接排查见 `docs/zotero_troubleshooting.md`。
