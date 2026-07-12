---
layer: detail
update_mode: patch
role: "Paper Agent 目标架构：层次、公共协议、模块边界、分发和实施路线"
read_when: "实现或评审共享运行时、CLI、配置、Skill、Plugin 和发布体系时"
not_for: "当前模块完成度（-> PROGRESS）或同步存储算法细节（-> SYNC_AND_STORAGE）"
---

# Paper Agent Architecture

> 状态：已确认的目标架构，尚未全部实现。
>
> 本文使用“必须”描述目标实现的稳定约束，使用“建议”描述可在实现中调整的内部细节。
> 当前可用能力以 `memory-docs/detail_mem/PROGRESS.md` 为准。
>
> 2026-07-11 实施注记：Phase 1 至 Phase 5 已完成；当前代码采用单文件 `cli.py` 和独立
> `config/`、`protocol/`、`clients/`、`services/`、`storage/` 子包，后续业务增长时再按目标树拆分 CLI 子模块。

## 1. 问题定义

项目需要同时支持多个用户意图：

- 管理 Frowang 远程论文库。
- 从 Zotero 上传论文。
- 在具体研究项目中建立论文工作区并深读全文。
- 未来继续增加论文翻译、证据提取、引用核验等 Skills。

“一个能力一个 Skill”有利于精确触发和渐进加载，但如果每个 Skill 都携带 dotenv、
HTTP Client、错误处理和同步状态，会导致：

- 用户重复配置同一个 API Key。
- Skill 间代码复制并产生版本漂移。
- Codex/Claude Code 的安装路径进入业务代码。
- Plugin 更新时用户状态随缓存目录丢失。
- 新功能无法复用可靠的下载、缓存和工作区能力。

目标是保留 Skill 的产品边界，同时建立一个工程化、可复用、可测试的本地运行时。

## 2. 架构原则

1. **Skill 边界不等于运行时边界。** Skill 负责何时做和如何编排；运行时负责真正执行。
2. **稳定协议隔离内部实现。** Skill 只调用 `paper-agent` 公共命令，不依赖 Python 文件路径。
3. **配置一次，多 Skill/多 Agent 共用。** 凭据属于用户的 Paper Agent 产品配置。
4. **一份 Skill 权威源码。** standalone、Plugin、wheel 和 zip 都是构建或安装产物。
5. **服务端做发现，本地做深读。** 默认不以服务端 L3 承担项目正文检索。
6. **远程、全局缓存、项目工作区三层数据身份分明。** 每层有明确权威来源和冲突规则。
7. **所有同步可恢复。** 临时文件、校验、事务、原子替换和幂等是基础能力。
8. **用户文件优先保护。** 自动化只修改自己声明拥有的文件。
9. **先验证简单方案。** 本地正文先用 `rg`，没有证据不引入 FTS5 或复杂对象存储。
10. **可诊断优先。** Agent 和用户必须能知道配置来源、版本、安装模式和同步状态。

## 3. 逻辑分层

```text
┌─────────────────────────────────────────────────────────────┐
│ Codex / Claude Code / Human / Future MCP Client             │
└──────────────────────────────┬──────────────────────────────┘
                               │ user intent
┌──────────────────────────────▼──────────────────────────────┐
│ Skill Orchestration Layer                                   │
│ paper-library | zotero-upload | paper-workspace | future    │
└──────────────────────────────┬──────────────────────────────┘
                               │ stable commands / JSON
┌──────────────────────────────▼──────────────────────────────┐
│ Tool Protocol Layer                                         │
│ paper-agent CLI | future MCP adapter | doctor/capabilities  │
└──────────────────────────────┬──────────────────────────────┘
                               │ typed requests/results
┌──────────────────────────────▼──────────────────────────────┐
│ Application Services                                        │
│ library | zotero import | skill install | artifact sync     │
│ workspace materialization | config migration                │
└──────────────────────────────┬──────────────────────────────┘
                               │ ports / models
┌──────────────────────────────▼──────────────────────────────┐
│ Adapters and Storage                                        │
│ Frowang client | Zotero client | config | SQLite | files    │
└──────────────────────────────┬──────────────────────────────┘
                               │ external I/O
┌──────────────────────────────▼──────────────────────────────┐
│ Frowang API | Zotero Local API | OS Keyring | Filesystem    │
└─────────────────────────────────────────────────────────────┘
```

配置、凭据、日志、版本和 tracing 是横切基础设施，但不得绕过应用服务直接耦合 Skill。

## 4. 目标仓库结构

```text
paper-agent/
├── pyproject.toml
├── README.md
├── src/
│   └── paper_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli/
│       │   ├── app.py
│       │   ├── library.py
│       │   ├── zotero.py
│       │   ├── workspace.py
│       │   ├── skills.py
│       │   ├── config.py
│       │   └── cache.py
│       ├── services/
│       │   ├── library_service.py
│       │   ├── zotero_import_service.py
│       │   ├── skill_install_service.py
│       │   ├── artifact_sync_service.py
│       │   └── workspace_service.py
│       ├── clients/
│       │   ├── frowang.py
│       │   └── zotero.py
│       ├── config/
│       │   ├── settings.py
│       │   ├── paths.py
│       │   ├── credentials.py
│       │   └── migrations.py
│       ├── storage/
│       │   ├── state_store.py
│       │   ├── artifact_store.py
│       │   ├── workspace_store.py
│       │   └── locks.py
│       ├── models/
│       │   ├── paper.py
│       │   ├── artifact.py
│       │   ├── workspace.py
│       │   └── result.py
│       └── protocol/
│           ├── errors.py
│           ├── envelope.py
│           └── exit_codes.py
├── skills/
│   ├── paper-library/
│   ├── zotero-upload/
│   └── paper-workspace/
├── .codex-plugin/
│   └── plugin.json
├── .claude-plugin/
│   └── plugin.json
├── scripts/
├── tests/
│   ├── unit/
│   ├── contract/
│   └── integration/
├── docs/
└── memory-docs/
```

目录可以在迁移时渐进形成，不要求一次移动所有代码。模块职责比精确文件名更重要。

## 5. Skill 编排层

### 5.1 职责

每个 Skill 只负责：

- 用 description 准确描述触发意图。
- 根据任务选择一组稳定 `paper-agent` 命令。
- 描述需要用户确认的危险操作和业务等待条件。
- 规定 Agent 如何缩小结果、验证返回和处理错误码。
- 在需要时加载 references，而不是把全部参数塞进 `SKILL.md`。

Skill 不负责：

- 解析 `.env` 或定位用户配置。
- 直接实现 HTTP 请求。
- 在 Skill 目录保存同步状态或用户下载。
- 重新实现 JSON 解析、重试、hash 和原子写入。
- 假设自己位于仓库源码路径。

### 5.2 Skill 内容结构

```text
skills/<skill-name>/
├── SKILL.md
├── references/
│   ├── workflows.md
│   └── command-contracts.md
└── assets/                  # 仅真正需要复制到输出的模板
```

核心业务迁出后，生产 Skill 原则上不再需要自己的 Python `scripts/`。少量只属于该工作流、
不涉及认证或共享状态的确定性辅助脚本可以保留。

### 5.3 初始 Skill 边界

| Skill | 触发意图 | 主要运行时命令组 |
|---|---|---|
| `paper-library` | 查找、上传、管理服务器论文 | `paper-agent library ...` |
| `zotero-upload` | 从 Zotero 导入/上传论文 | `paper-agent zotero ...` |
| `paper-workspace` | 建立、添加、同步和深读项目论文 | `paper-agent workspace ...` |

服务器 Collection 和本地 workspace 不合并为一个 Skill 概念：前者是远程整理，后者是
项目级活跃工作集。

## 6. Tool Protocol 层

### 6.1 公共入口

Python package 必须提供：

```bash
paper-agent --version
paper-agent capabilities --json
paper-agent doctor --json
```

目标命令树：

```text
paper-agent
├── config       init/show/set/migrate
├── auth         status/set/delete
├── library      list/search/show/upload/assets/...
├── zotero       collections/items/upload/status
├── workspace    init/add/list/status/sync/remove
├── paper        pull/refresh
├── cache        status/verify/gc
└── skills       install/status/diff/update/uninstall
```

命令名可在实现评审时小幅调整，但上层 Skill 一旦发布依赖后必须遵循兼容策略。

### 6.2 JSON 成功响应

非交互 stdout、管道、重定向和显式 `--json` 输出一个 JSON 文档；交互终端默认使用人类
摘要，`--human` 可强制该模式：

```json
{
  "schema_version": "1",
  "success": true,
  "data": {},
  "meta": {
    "command": "workspace.add",
    "runtime_version": "0.2.0",
    "request_id": "local-uuid"
  }
}
```

要求：

- `schema_version` 是 CLI envelope 版本，不等同于 package version。
- `data` 的结构由具体命令合同定义。
- `meta` 可以增加字段，但不能改变已有字段语义。
- stdout 不得混入进度条、日志或安装提示。

### 6.3 JSON 错误响应

```json
{
  "schema_version": "1",
  "success": false,
  "error": {
    "code": "AUTH_MISSING",
    "message": "Frowang API key is not configured",
    "details": {},
    "retryable": false
  },
  "meta": {
    "command": "library.list",
    "runtime_version": "0.2.0",
    "request_id": "local-uuid"
  }
}
```

公开错误码至少包括：

| 错误码 | 含义 |
|---|---|
| `USAGE_ERROR` | 参数或命令使用错误 |
| `CONFIG_INVALID` | 配置 schema 或值非法 |
| `AUTH_MISSING` | 缺少凭据 |
| `AUTH_INVALID` | 凭据被服务端拒绝 |
| `NOT_FOUND` | 论文、Collection、workspace 或文件不存在 |
| `NOT_READY` | 论文存在但产物尚未就绪 |
| `NETWORK_ERROR` | DNS、连接、超时等传输错误 |
| `REMOTE_ERROR` | 远程服务端错误 |
| `WORKSPACE_INVALID` | manifest 或目录结构非法 |
| `CONFLICT` | 本地文件修改、revision 或安装内容冲突 |
| `INTEGRITY_ERROR` | hash、JSON 或下载完整性验证失败 |
| `LOCAL_IO_ERROR` | 本地配置、状态或资产路径读写失败 |
| `PERMISSION_DENIED` | 本地路径或系统凭据访问失败 |
| `INTERNAL_ERROR` | 未分类内部异常，必须带 request_id |

### 6.4 Exit code

| code | 分类 |
|---:|---|
| 0 | 成功 |
| 1 | 未预期内部错误 |
| 2 | 参数/输入错误 |
| 3 | 配置或认证错误 |
| 4 | 资源不存在或未就绪 |
| 5 | 网络或远程服务错误 |
| 6 | 冲突 |
| 7 | 本地 I/O 或完整性错误 |

CLI 测试必须同时断言 JSON error code 和 process exit code。

### 6.5 大内容输出

`full.md`、PDF、layout 和图片下载命令默认返回保存路径、revision、bytes 和 hash，不把
完整内容输出到 stdout。需要短文本预览时使用显式参数，并限制字符/行数。

## 7. Application Services

Service 层表达完整用例，并通过构造函数注入 Client、Store、Clock 和 Path roots：

```text
LibraryService
  - search/list/show/upload/update

ZoteroImportService
  - discover collections/items
  - resolve local PDFs
  - upload incrementally

SkillInstallService
  - plan/install/diff/update/uninstall

ArtifactSyncService
  - resolve paper identity/revision
  - download/verify/commit artifacts

WorkspaceService
  - init/add/status/sync/remove
  - materialize cached revisions
```

Service 不直接读取 Typer context，不直接 `print()`，也不把 `SystemExit` 当作领域错误。
CLI adapter 将 typed result/error 转成 envelope 和 exit code。

## 8. Clients 与外部适配器

### 8.1 Frowang Client

统一 Client 必须支持：

- X-API-Key 请求和 base URL/profile。
- 可配置 connect/read/write/overall timeout。
- 结构化 HTTP 错误映射。
- JSON API 请求和静态资产流式下载。
- 相对资产 URL 安全拼接和 percent encoding。
- User-Agent/runtime version，便于服务端诊断。
- 对安全的幂等 GET 进行有限重试；上传重试必须理解是否已创建远程任务。

当前 `packages/paper_api_client` 可以作为迁移起点，但最终不能通过 `SystemExit` 向 service
传播错误。

### 8.2 Zotero Client

生产适配器负责：

- 检测本地 Zotero API 可用性。
- 分页读取 collections/items/attachments。
- 通过 profile/prefs 定位 dataDir 和 storage。
- 将 Zotero item/attachment 转为内部模型。
- 不在 Client 内直接调用 Frowang 上传；跨系统编排由 `ZoteroImportService` 完成。

硬编码本机 Zotero 路径只能存在诊断 fixture 或显式用户配置中。

## 9. 配置与凭据架构

### 9.1 目录发现

使用 `platformdirs`：

```python
user_config_dir("paper-agent", "Frowang")
user_data_dir("paper-agent", "Frowang")
user_cache_dir("paper-agent", "Frowang")
user_log_dir("paper-agent", "Frowang")
```

Windows 的典型结果位于 `%APPDATA%`/`%LOCALAPPDATA%`，Linux 的典型结果位于
`~/.config`、`~/.local/share` 和 `~/.cache`。业务代码只依赖解析后的 Path，不拼接平台字符串。

### 9.2 config.toml

建议初始 schema：

```toml
schema_version = 1
active_profile = "default"

[profiles.default.frowang]
base_url = "https://frowang.com/paper-api/api/v1"
timeout_seconds = 120

[profiles.default.zotero]
mode = "local"
library_type = "user"
library_id = "0"
storage_dir = ""

[workspace]
papers_dir = "papers"
materialization = "copy"
```

配置不能包含 API Key、JWT 或 Zotero secret。

### 9.3 凭据来源

MVP：

```dotenv
FROWANG_API_KEY=pk_xxx
ZOTERO_API_KEY=
```

兼容已有 `PAPER_API_KEY`，但新文档和内部模型统一使用 Frowang provider 命名。长期将
secret 值迁移到 OS Keyring；配置只保存 credential reference。

### 9.4 解析优先级

```text
显式命令参数
  > 进程环境变量
  > OS Keyring / 用户 credentials.env
  > 旧 Skill .env（仅迁移窗口）
  > 内置非敏感默认值
```

`paper-agent doctor` 只报告来源和连接状态，例如 `environment`、`keyring`、
`credentials.env`，不得输出 secret。

## 10. 分发与安装

### 10.1 Python package 是执行引擎

主安装方式：

```bash
uv tool install paper-agent
paper-agent setup
paper-agent doctor
```

允许 `pipx`/venv 作为兼容安装，但文档只维护一条推荐路径。wheel 和 sdist 必须包含运行
所需代码；源码仓库链接用于审计和贡献。

### 10.2 Standalone Skills

CLI 可以把 canonical `skills/` 安装到：

- Codex 用户/项目 Skill 目录。
- Claude Code 用户/项目 Skill 目录。

安装器必须记录目标、scope、package version、文件 hash 和安装模式。具体协议见
`SYNC_AND_STORAGE.md`。

### 10.3 Plugins

同一 Plugin 根可以包含：

```text
.codex-plugin/plugin.json
.claude-plugin/plugin.json
skills/
```

两套 manifest 分别适配平台，但共享同一 Skill 内容。一个 Paper Agent Plugin 包含多个
独立 Skills。Plugin 技能可以带命名空间，不改变隐式触发时的业务边界。

Plugin 不存用户凭据，不依赖可写安装根。若运行时命令不存在，Skill 必须返回明确安装
前置条件，不得在无确认时自动从网络安装软件。

### 10.4 Skill 源打包

源码仓库根 `skills/` 是唯一手工维护位置。wheel 需要 Skill resources 时，应由构建配置
或构建步骤复制进 package data；禁止开发者手工同时编辑两份。

发布检查必须比较源码 Skill 与构建产物 hash，并验证两个平台都能发现预期 Skills。

### 10.5 GitHub Bootstrap Skill

Marketplace 之外提供独立公开的轻量 Bootstrap Skill 仓库。官网或仓库首页给出一条固定
Prompt，让用户要求 Agent 下载仓库并读取 `SKILL.md`。该 Skill 只编排：

- 检测 OS、Python/uv 和现有 Runtime。
- 经用户确认后安装或升级发布包。
- 执行 `config init`、`auth set`、`doctor` 和最小 smoke test。
- 安装 Codex/Claude standalone Skills，并避免与 Plugin 重复安装。

Bootstrap 仓库不得复制 HTTP Client、配置解析或业务服务，也不得保存用户 Key。用户明确在
对话中提供 Key 时，Agent 只能通过 `auth set --stdin` 交给 Runtime；执行工具不能独立提供
stdin 时，回退到用户终端中的隐藏式 `auth set`。

## 11. 版本与兼容

需要区分：

- Python runtime semver。
- CLI envelope schema version。
- workspace manifest schema version。
- global state database schema version。
- Skill/Plugin release version。

建议同一 release tag 发布 runtime 和 Skills，但各 schema 只在格式变更时递增。

兼容规则：

- patch/minor 版本不能删除既有命令、字段或错误码。
- 新 JSON 字段默认允许 Agent 忽略。
- 删除或重命名命令必须经历 deprecation 周期，并给出机器可读 warning。
- workspace/config/database migration 必须可重复运行并在失败时保留旧文件。
- Skill metadata 或 manifest 应声明最低 runtime 版本；`doctor` 检查漂移。

## 12. 安全模型

- 所有 secret 在日志、异常、JSON 和诊断中统一 redaction。
- 认证 header 不进入 debug dump。
- 静态资产 URL 只能解析到允许的 Frowang origin 和路径前缀。
- 下载文件名不能直接决定本地目标路径；目标名由受控 artifact kind 映射。
- workspace path 和 manifest relative path 必须拒绝 `..`、绝对路径和目录逃逸。
- Plugin、zip、wheel 和 release artifact 必须扫描 secret 和用户数据。
- 删除、强制覆盖、远程重处理和远程删除必须有明确命令语义，Agent 按 Skill 规则确认。

## 13. 可观测性与诊断

`paper-agent doctor --json` 至少检查：

- runtime/version 和 Python 环境。
- config/data/cache/log 解析路径。
- config schema 与 active profile。
- 凭据是否存在及来源（不显示值）。
- Frowang 连通性和认证。
- Zotero 本地 API（仅相关 profile）。
- SQLite schema 和可写性。
- Skill 安装目标、模式和版本漂移。
- 工作区 manifest 合法性（传入 workspace 时）。

日志默认写用户 log 目录，并含 timestamp、level、component、request_id、paper_id/revision
等非敏感上下文。CLI 正常 JSON 不依赖日志文件才能理解错误。

## 14. 测试架构

### Unit

- Settings 优先级、profile、路径和 migration。
- 错误映射、envelope 和 exit code。
- manifest/schema/hash/path traversal。
- artifact/workspace 冲突矩阵。

### Contract

- 每个公开 CLI 命令的 JSON schema。
- SKILL.md 中出现的命令真实存在。
- API surface 与 Frowang Client 方法对应。
- 双平台 Plugin/Skill discovery 清单。

### Integration

- 使用 fake HTTP server 测成功、超时、404/NOT_READY、401、5xx、断流和重试。
- 使用临时 config/data/workspace roots，禁止触碰真实用户目录。
- 测试 SQLite 并发、下载中断和原子替换。

### QA / E2E

- 在 `qa-automation` 使用专用测试账号验证生产 API。
- 工作区 E2E 下载已知论文到临时目录，再用 `rg` 命中已知原文。
- L3 只作为历史兼容场景，不作为新论文工作区能力前置条件。

## 15. 迁移策略

### Phase 1：基础合同

- [x] 新建 `src/paper_agent/` 和 `paper-agent` entry point。
- [x] 实现 Result/Error、JSON envelope、exit code 和基础测试。
- [x] 实现 `platformdirs` 路径、config schema、credentials 和本地 `doctor`。
- [x] Frowang 远程连通性检查随 Phase 2 Client 实现补充。

### Phase 2：远程论文库迁移

- [x] 将 `packages/paper_api_client` 改造成不退出进程的 Frowang Client 兼容层。
- [x] 通过 `LibraryService` 迁移现有 `paper-library` 命令。
- [x] 保持旧 `paper-cli` 临时 wrapper，输出 deprecation warning。

### Phase 3：Zotero 迁移

- [x] 将生产 Zotero Client/Service 移入统一 package。
- [x] 把 `sync_state.json` 迁到全局 state store。
- [x] 更新 `zotero-upload` 为薄 Skill。

### Phase 4：安装和分发

- [x] 实现 Skill installer、Codex/Claude targets、diff/status/update/uninstall。
- [x] 添加双平台 Plugin manifests、canonical allowlist 和构建验证。
- [x] 更新 README/release checklist，使正式流程不再依赖每 Skill `.env`。

### Phase 5：资产库与工作区

- [x] 实现 ArtifactSyncService、text revision store 和 SQLite schema。
- [x] 实现 WorkspaceService、manifest 和普通复制物化。
- [x] 创建 `paper-workspace` Skill与本地 HTTP E2E；真实部署服务器 QA 进入 Phase 6。

### Phase 6：体验增强

- 图片/PDF profile、页码定位和离线诊断。
- 基于真实需求评估本地 FTS5。

## 16. 架构验收标准

- 新增一个 Frowang 相关 Skill 不需要再实现 dotenv 或 HTTP Client。
- 用户只配置一次 Frowang Key，Codex 和 Claude Code 中的所有 Skills 均可使用。
- Skill 目录可以被安全删除/更新而不影响配置、缓存和工作区。
- `paper-agent` 的非交互输出与显式 `--json` 可稳定解析，并有端到端合同测试；交互终端默认
  输出人类可读摘要。
- 同一 canonical paper/revision 跨项目只需从服务器下载一次。
- 工作区同步失败不会留下半文件，也不会覆盖用户笔记。
- standalone 和 Plugin 安装状态可诊断且不会重复暴露相同 Skill。
- 当前实现、目标设计和历史决策在 memory-docs 中保持一致。

## 17. 暂未定稿事项

以下事项不得在没有新决策记录时当作既定合同：

- PyPI 最终包名和仓库是否从 `paper-agent-skills` 重命名为 `paper-agent`。
- OS Keyring 的具体 backend 和无桌面环境回退细节。
- 图片是否进入默认同步 profile，还是按需下载。
- 服务端是否增加带 checksum/size/version 的 artifact manifest 或 bundle endpoint。
- Codex/Claude marketplace 的最终托管仓库和发布自动化。
