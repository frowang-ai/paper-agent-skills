# Paper Agent Skills

> **Alpha/MVP** - 核心功能已完成，正在准备首次公开发布。

Paper Agent 是 Frowang 论文研究工作流的共享 Python 运行时和 Skill 权威源码。Codex、
Claude Code 或人类用户通过稳定的 `paper-agent` CLI 管理远程论文库、Zotero 导入、全局
论文缓存、项目工作区和 Skills。

项目记忆入口是 [`memory-docs/INDEX.md`](memory-docs/INDEX.md)，当前模块完成度以
[`memory-docs/detail_mem/PROGRESS.md`](memory-docs/detail_mem/PROGRESS.md) 为准。

## 当前结构

```text
paper-agent-skills/
├── src/paper_agent/
│   ├── clients/              # Frowang 与 Zotero 适配器
│   ├── services/             # Library、Zotero、资产同步、Workspace、Skill 安装
│   ├── skills/               # canonical source 与安装目标解析
│   ├── plugins/              # 双平台 Plugin bundle builder
│   ├── storage/              # 用户级 SQLite 状态
│   ├── config/               # 用户级配置、路径和凭据
│   ├── protocol/             # JSON envelope、错误码和 exit code
│   └── cli.py                # paper-agent 公共入口
├── skills/                   # Skill 权威源码与发布 allowlist
├── packages/paper_api_client/ # 旧 import 兼容层
├── scripts/                  # 构建与旧同步兼容 wrapper
├── tests/
├── docs/
└── memory-docs/
```

`skills/manifest.json` 是正式发布 inventory。当前发布 `paper-library`、`paper-workspace` 和
`zotero-upload`；诊断代码、`.env`、下载论文和旧 wrapper 不会进入正式安装或 Plugin。

## 开发环境

MVP 要求 Python 3.13+：

```powershell
uv sync --extra dev
uv run paper-agent capabilities
uv run pytest -q
```

`paper-agent` 默认向 stdout 输出单个 JSON 文档。`--human` 只改变 JSON 缩进，不改变字段
合同。

## 安装

### 从 PyPI 安装（推荐）

```powershell
uv tool install paper-agent-skills
```

### 从源码安装

```powershell
git clone https://github.com/frowang-ai/paper-agent-skills.git
cd paper-agent-skills
uv tool install .
```

安装后重新打开 Codex/Claude 会话，让平台重新发现 Skills。

## 统一配置

```powershell
paper-agent config init
paper-agent config show
paper-agent doctor
```

### 配置 API Key

使用安全的隐藏输入方式配置 Frowang API Key：

```powershell
paper-agent auth set
```

或者使用 stdin 模式（适合自动化）：

```powershell
echo "your-api-key" | paper-agent auth set --stdin
```

查看认证状态：

```powershell
paper-agent auth status
```

删除已保存的凭据：

```powershell
paper-agent auth delete
```

非敏感配置位于 `platformdirs` 解析的用户 `config.toml`；Frowang Key 位于同一用户配置根
下的 `credentials.env`。环境变量优先使用 `FROWANG_API_KEY`，并兼容
`PAPER_API_KEY`。配置、凭据和状态不写入 Skill 或 Plugin 目录。测试和 CI 可覆盖：

```text
PAPER_AGENT_CONFIG_DIR
PAPER_AGENT_DATA_DIR
PAPER_AGENT_CACHE_DIR
PAPER_AGENT_LOG_DIR
```

`doctor` 默认检查 Frowang 认证和受管 standalone Skill 状态；离线检查使用
`paper-agent doctor --no-remote`，跳过 Skill 检查使用 `--no-skills`。

## Skill 安装与 Plugin

Standalone 安装支持 Codex/Claude 的 user/project scope：

```powershell
paper-agent skills list
paper-agent skills install --platform codex
paper-agent skills install --platform claude --scope project --project-root F:\research\my-project
paper-agent skills status --platform all
paper-agent skills diff --platform codex paper-library
paper-agent skills update --platform all
paper-agent skills uninstall --platform claude zotero-upload
```

安装器在用户级 `state.sqlite3` 记录 package version、source hash 和逐文件 hash。更新会拒绝
覆盖用户修改，卸载只删除受管文件并保留用户新增文件；确认覆盖时显式使用 `--force`。

双平台 Plugin bundle 从同一 allowlist 构建：

```powershell
paper-agent skills plugin-build ./dist/paper-agent-plugin
```

产物同时包含 `.codex-plugin/plugin.json` 与 `.claude-plugin/plugin.json`，由各平台
marketplace/Plugin 系统安装。Paper Agent 不直接修改平台私有 Plugin cache。同一平台和
scope 下，Plugin 与 standalone 应作为互斥方式使用。

详细步骤见 [`examples/codex.md`](examples/codex.md) 和
[`examples/claude-code.md`](examples/claude-code.md)。

## Paper Library

```powershell
paper-agent library list --limit 5
paper-agent library search "causal inference" --limit 10
paper-agent library show P-1
paper-agent library upload ./paper.pdf
paper-agent library fulltext P-1 --save ./papers/P-1/full.md
paper-agent library assets P-1
paper-agent library tag add P-1 causal
paper-agent library note add P-1 "Review Table 2"
```

服务器检索用于 L1 元数据和 L2 属性树上的候选论文发现。选中的 `full.md` 和
`layout.json` 下载到研究项目后，使用本地 `rg` 高频检索正文；新论文不自动建立 L3 全文
索引。长内容必须落盘，静态资产下载会验证 URL、路径、bytes 和 SHA-256。

## Zotero Import

```powershell
paper-agent zotero collections
paper-agent zotero items COLLECTION_KEY --recursive
paper-agent zotero upload COLLECTION_KEY --dry-run
paper-agent zotero upload COLLECTION_KEY
paper-agent zotero upload-one ITEM_KEY --target C-2
paper-agent zotero status
```

默认 local 模式从 Zotero profile 自动发现 storage。同步状态写入用户 data 目录的
`state.sqlite3`；同一 item 跨多个 Collection 只上传一次，并复用已记录的 Collection
映射。旧状态可用 `paper-agent zotero migrate-state /path/to/sync_state.json` 幂等导入。

## Global Artifact Store 与 Workspace

选中论文先按 active profile、canonical paper ID 和 task revision 同步到用户 data 目录：

```powershell
paper-agent paper pull P-3a
```

text profile 原子提交 `metadata.json`、`full.md`、`layout.json` 和
`artifact-manifest.json`。required asset 未就绪不会提交 revision；已有 revision 通过 hash
校验后直接返回 `cache_hit=true`。

项目工作区必须显式初始化：

```powershell
paper-agent workspace init F:\research\my-project
paper-agent workspace add F:\research\my-project P-3a P-8f
paper-agent workspace status F:\research\my-project
paper-agent workspace sync F:\research\my-project
paper-agent workspace names plan F:\research\my-project
paper-agent workspace remove F:\research\my-project P-8f
```

项目 `<project>/papers/manifest.json` 是成员关系权威。全局 revision 以普通复制物化到
`papers/<year-author-short-title--short-id>/`，例如
`papers/2024-Smith-et-al-Inflation-Dynamics--P-3a/`。更新只替换 managed assets，保留
`notes.md` 等用户文件。managed file
被修改或缺失时返回 `CONFLICT`。正文使用本地命令检索：

```powershell
rg -n -C 5 "parallel trends" F:\research\my-project\papers\*\full.md
```

metadata 更新不会在 `workspace sync` 中自动改变路径。旧 `P-xxx/` 目录或新建议名称通过
`workspace names plan/apply` 显式迁移；内部文件名始终保持 `full.md`、`layout.json` 和
`metadata.json`。

## 测试与安全

```powershell
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests packages skills/paper-library/scripts skills/zotero-upload/scripts scripts
uv lock --check
```

- 不提交 API Key、JWT、用户论文或真实 `.env`。
- Skill/Plugin 安装目录不保存配置、缓存或同步状态。
- stdout 不输出认证 header、长篇全文或调试日志。
- 删除论文、删除 Collection、重新处理等远程变更需要上层 Skill 先取得用户确认。

REST、CLI、MCP 的能力矩阵见 [`docs/API_SURFACE.md`](docs/API_SURFACE.md)。Phase 1 至
Phase 5 已完成；下一阶段是图片/PDF profile、页码定位、缓存治理和真实用户体验验证。
