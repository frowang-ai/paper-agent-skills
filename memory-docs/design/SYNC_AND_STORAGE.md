---
layer: detail
update_mode: patch
role: "Skill 安装、配置迁移、论文资产缓存和项目工作区物化的完整协议"
read_when: "实现同步、路径、状态数据库、下载、缓存、manifest 或工作区命令时"
not_for: "整体层次介绍（-> ARCHITECTURE）或当前模块状态（-> PROGRESS）"
---

# Sync and Storage Design

> 状态：目标设计，尚未全部实现。
>
> 本文定义同步与存储的职责边界、数据布局、不变量和失败策略。实现可以调整内部类名，
> 但改变权威来源、身份、覆盖策略或数据安全语义时必须新增决策记录。

## 1. 为什么需要独立同步层

项目中的“同步”至少包含四件不同的事情：

| 同步类型 | 权威来源 | 目标 | 主要冲突 |
|---|---|---|---|
| Skill Installation Sync | 仓库/package 内 canonical `skills/` | Codex/Claude Skill 目录或 Plugin | 用户修改、旧版本、重复安装 |
| Configuration Bootstrap/Migration | 默认 schema + 用户已有配置 | 用户 config/credential store | 不能覆盖用户 secret 和自定义值 |
| Artifact Sync | Frowang 服务器某个 paper revision | 用户级 Global Artifact Store | 下载中断、revision 变化、hash 不一致 |
| Workspace Materialization | Global Artifact Store + workspace manifest | 项目 `papers/` | 用户修改、revision pin、用户笔记 |

四类同步必须有独立 service、状态和测试。一个通用底层可以复用原子写入、hash 和锁，
但不能把它们的业务状态机合并。

## 2. 权威来源与数据所有权

### 2.1 权威关系

```text
Skill 源码权威：repository/package canonical skills/
用户配置权威：user config directory
远程论文权威：Frowang Paper API + server artifacts
全局缓存权威：某个已校验 remote revision 的本地副本
项目成员权威：project papers/manifest.json
项目用户文件权威：project filesystem，Paper Agent 不拥有
```

### 2.2 不变量

- Skill 安装目标不是 Skill 源码权威。
- 包内默认配置不是用户配置权威。
- 全局资产库是可重建缓存，不是服务端论文元数据的编辑入口。
- 项目 workspace membership 不由服务器 Collection 自动决定。
- manifest 未声明的项目文件一律视为用户拥有。
- 只有完整校验并提交的 revision 才能被 workspace 物化。

## 3. 平台目录布局

所有实际路径由 `platformdirs` 解析。下列是逻辑布局，不要求业务代码硬编码 Windows 路径。

### 3.1 用户配置目录

```text
<user-config>/Frowang/paper-agent/
├── config.toml
└── credentials.env          # MVP fallback；未来可由 Keyring 替代
```

内容应随用户配置保留，但不能进入 Plugin cache 或研究项目。

### 3.2 用户数据目录

```text
<user-data>/Frowang/paper-agent/
├── state.sqlite3
├── artifacts/
│   └── papers/
│       └── <profile>/
│           └── <canonical-paper-uuid>/
│               └── <revision>/
│                   ├── artifact-manifest.json
│                   ├── metadata.json
│                   ├── full.md
│                   ├── layout.json
│                   ├── images/
│                   └── source.pdf
└── locks/
```

`images/` 和 `source.pdf` 可以缺失，取决于同步 profile；manifest 必须准确描述实际资产。

### 3.3 缓存和日志目录

```text
<user-cache>/Frowang/paper-agent/
├── downloads/
├── staging/
└── search/                  # 未来可重建 FTS 等派生缓存

<user-log>/Frowang/paper-agent/
└── paper-agent.log
```

下载临时文件和可重建索引进入 cache；已经提交、可供工作区复用的论文 revision 进入 data。

### 3.4 项目工作区

```text
<project>/
└── papers/
    ├── manifest.json
    ├── 2024-Smith-et-al-Inflation-Dynamics--P-3a/
    │   ├── metadata.json
    │   ├── full.md
    │   ├── layout.json
    │   └── images/
    └── 2022-Jones-Monetary-Policy-Shocks--P-8f/
        ├── metadata.json
        ├── full.md
        └── layout.json
```

项目可自行在论文目录增加：

```text
notes.md
reading.md
evidence.json
quotes.md
```

这些文件不进入 managed asset 列表。

## 4. Configuration Bootstrap and Migration

### 4.1 命令目标

```bash
paper-agent config init
paper-agent config show
paper-agent config migrate
paper-agent auth set
paper-agent auth set --stdin
paper-agent auth status
paper-agent auth delete
paper-agent doctor
```

### 4.2 初始化算法

1. 使用 `platformdirs` 解析 config/data/cache/log roots。
2. 创建缺失目录，设置平台可行的最小权限。
3. 若 `config.toml` 不存在，写入带 `schema_version` 的默认配置。
4. 若配置存在，解析并验证，不用默认模板整文件覆盖。
5. 只补充 schema 中新增且用户未设置的非敏感默认字段。
6. 若没有凭据，报告 `AUTH_MISSING` 并给出 `paper-agent auth set`。用户明确把 Key 提供给
   Agent 并要求代配时，使用 `auth set --stdin`，不把值放进命令参数、输出或临时文件。
7. 记录 migration 结果，但日志中不包含 secret。

`auth set` 默认使用隐藏式终端输入；`--stdin` 读取到 EOF，供能独立传递 stdin 的 Agent
执行适配器使用。凭据写入使用 staging + atomic replace，保留非 Frowang dotenv 项；
`auth delete` 同时删除文件中的 `FROWANG_API_KEY` 与兼容 `PAPER_API_KEY`，但不修改环境变量。

### 4.3 旧 `.env` 迁移

迁移器可以只读检查以下旧位置：

- `skills/paper-library/.env`
- `skills/paper-library/scripts/.env`
- `skills/zotero-upload/scripts/.env`
- `~/.claude/.env`

但正式安装后的 package 不应假设源码仓库存在。迁移流程：

1. 列出发现的来源和变量名，不显示变量值。
2. 多个来源值不同则返回 `CONFLICT`，要求用户选择，不猜测。
3. 将选定值写入用户 credential store 或 Keyring。
4. 验证新来源可读取。
5. 不自动删除旧 `.env`；只提示用户在确认后清理。
6. 安装器和日志永远不复制真实 `.env` 到 Skill/Plugin。

### 4.4 配置 migration

每次 migration 必须：

- 从明确旧 schema 迁移到下一 schema，不能跨版本写一个不可审计的大迁移。
- 迁移前在同目录创建不含 secret 泄漏的新备份策略；凭据文件备份需同等权限。
- 使用临时文件和 `replace()` 原子提交 TOML。
- 可重复运行；已迁移配置不产生额外变化。
- 失败时保持原文件可解析。

## 5. Skill Installation Sync

> 实施状态（2026-07-11）：本节的 standalone installer、状态记录、冲突保护和双平台
> Plugin builder 已在 Phase 4 落地。正式发布 inventory 由 `skills/manifest.json` allowlist
> 定义；平台私有 Plugin cache 仍明确不属于 Paper Agent 管理范围。

### 5.1 安装模式

支持两类模式：

```text
standalone：复制单个 Skills 到平台 Skill discovery 目录
plugin：由平台 Plugin 系统安装一个包含多个 Skills 的包
```

同一平台和 scope 下，一个 Paper Agent Skill 不应同时以两种模式启用。由于平台私有
Plugin cache 不属于 Paper Agent 的稳定接口，`doctor` 只诊断受管 standalone 记录；Plugin
重复启用由平台和安装文档约束，不通过扫描私有 cache 猜测。

### 5.2 目标抽象

安装器通过 target adapter 隔离平台差异：

```text
SkillTarget
  - platform: codex | claude
  - scope: user | project
  - mode: standalone | plugin
  - root: resolved absolute Path
```

目标路径发现不能散落在各命令中。project scope 必须显式传入 project root。

### 5.3 安装记录

建议记录：

```json
{
  "schema_version": 1,
  "installations": [
    {
      "installation_id": "uuid",
      "platform": "claude",
      "scope": "user",
      "mode": "standalone",
      "target_root": "<absolute-path>",
      "package_version": "0.2.0",
      "installed_at": "2026-07-11T00:00:00Z",
      "skills": {
        "paper-library": {
          "source_hash": "sha256",
          "files": {
            "SKILL.md": "sha256",
            "references/workflows.md": "sha256"
          }
        }
      }
    }
  ]
}
```

真实实现可以把安装状态放 SQLite；导出/诊断 JSON 仍应提供相同信息。

### 5.4 Standalone 安装算法

1. 从 package resources 或源码 canonical `skills/` 枚举合法 Skill。
2. 校验每个 Skill 有合法 `SKILL.md` 和 frontmatter。
3. 过滤 `.env`、缓存、下载、测试输出和不应分发的诊断资产。
4. 计算源文件清单和 SHA-256。
5. 解析 target root，并确认目标在平台允许的 Skill root 内。
6. 若目标不存在，在同级 staging 目录完整复制并验证后原子重命名。
7. 若目标存在，读取上次安装 manifest：
   - 目标与上次 hash 相同：安全更新。
   - 目标出现用户修改：返回 `CONFLICT`，默认不覆盖。
   - 目标不是 Paper Agent 所有：拒绝接管，除非显式 adopt/force。
8. 更新安装状态并输出 installed/updated/skipped/conflicted 清单。

禁止沿用当前“发现目录存在就 `rmtree` 再复制”的默认行为。

### 5.5 Status、diff、update、uninstall

```bash
paper-agent skills status --platform claude
paper-agent skills diff --platform codex
paper-agent skills update --platform all
paper-agent skills uninstall --platform claude paper-library
```

- `status` 比较 package source hash、记录 hash 和目标实际 hash。
- `diff` 只输出路径和差异摘要，不输出 secret 或大文件全文。
- `update` 遇用户修改默认停止该 Skill，不影响其他无冲突 Skill。
- `uninstall` 只删除安装记录中仍匹配 hash 的受管文件；用户新增文件保留并报告。
- `--force` 必须是显式参数，且输出将被覆盖/删除的路径清单。

### 5.6 Plugin 分发

Plugin 构建从同一 canonical `skills/` 读取。Codex 和 Claude manifest 可以不同，但 Skill
文件 hash 必须一致。Plugin 安装由平台管理时，Paper Agent 只记录和诊断状态，不直接修改
平台私有 cache。

当前实现以 `skills/manifest.json` 为发布 allowlist，生成的 bundle 同时包含两个平台 manifest
和 `paper-agent-plugin-manifest.json`。standalone 安装状态进入用户级 `state.sqlite3`；平台
Plugin 安装状态由平台自身维护，Paper Agent 不扫描或篡改 `~/.codex/plugins/cache`、
`~/.claude/plugins/cache`。

## 6. Global Artifact Store

> 实施状态（2026-07-11）：Phase 5 已实现 text profile、artifact manifest、逐文件 hash、
> staging 提交、per-paper lock 和 SQLite revision 记录。complete profile、cache GC 与远程
> checksum/ETag 仍属于后续增强。

### 6.1 身份模型

```text
Paper identity: canonical paper UUID
User-facing alias: short_id (P-xxx)
Artifact revision: task_id or future explicit content revision
Artifact kind: metadata | fulltext | layout | images | pdf | summary | deep
```

标题、原始文件名、DOI 和 short ID 都不能替代 canonical UUID。

### 6.2 Revision 目录

```text
artifacts/papers/<profile>/<paper_uuid>/<revision>/
```

revision 必须转换为安全路径 segment，只允许受控字符；原始远程路径不得直接拼成本地目录。

一个 revision 只有在 `artifact-manifest.json` 状态为 committed 且所有 required assets 校验
成功后才可用于 workspace。

### 6.3 Artifact manifest

建议 schema：

```json
{
  "schema_version": 1,
  "paper_id": "canonical-uuid",
  "short_id": "P-3a",
  "revision": "task-id",
  "source": {
    "profile": "default",
    "base_url": "https://frowang.com/paper-api/api/v1",
    "synced_at": "2026-07-11T00:00:00Z"
  },
  "artifacts": {
    "metadata": {
      "path": "metadata.json",
      "bytes": 1234,
      "sha256": "...",
      "required": true
    },
    "fulltext": {
      "path": "full.md",
      "bytes": 102400,
      "sha256": "...",
      "required": true
    },
    "layout": {
      "path": "layout.json",
      "bytes": 500000,
      "sha256": "...",
      "required": true
    }
  }
}
```

不要把 API Key、认证 header、服务器绝对路径或用户本机源码路径写入 manifest。

### 6.4 同步 profile

第一阶段建议：

| profile | 默认资产 | 用途 |
|---|---|---|
| `text` | metadata、fulltext、layout | Agent 搜索和页码映射；MVP 默认 |
| `complete` | text + images + source PDF | 完整离线阅读；后续实现 |

`full.md` 可能包含 `images/...` 引用。text profile 可以暂时允许图片缺失，但 manifest 和
命令输出必须明确 `images_available=false`，不能伪装成完整离线副本。

### 6.5 Artifact Sync 算法

```text
resolve user input ID
  -> GET paper metadata and latest task/revision
  -> GET assets manifest/URLs
  -> acquire per-paper lock
  -> check committed local revision
  -> stream required assets to staging
  -> validate status, type, size, JSON/Markdown, sha256
  -> write artifact-manifest.json in staging
  -> atomic rename staging -> revision directory
  -> SQLite transaction records revision/artifacts/current pointer
  -> release lock
```

详细要求：

- 已有相同 revision 且 hash 完整时操作幂等，返回 cache hit。
- 若服务端没有 checksum，客户端计算本地 hash，并记录服务器 task/revision 和 URL。
- 静态 URL 只接受配置的 origin 和允许前缀；相对路径需正确 percent encode。
- 下载使用流式写入，不把 PDF/layout/完整 Markdown 无必要加载进内存。
- Markdown required asset 必须非空；JSON 必须可解析并符合最低结构。
- 断流、超时或校验失败只清理本次 staging，不影响旧 committed revision。
- 数据库事务只在文件提交成功后更新 current revision。

### 6.6 当前 revision 与 pin

全局状态可以把最新成功同步 revision 标为 current，但旧 revision不自动删除。workspace
manifest 可以：

- `tracking = "latest"`：`workspace sync` 检查并升级到最新 committed revision。
- `tracking = "pinned"`：保持指定 revision，除非用户显式升级。

MVP 可默认 `latest`，但每次 revision 变化必须在命令结果中明确报告。

## 7. Global State Database

SQLite 保存同步和安装状态，不保存正文 blob。建议逻辑表：

### papers

```text
profile_id
paper_id
short_id
title
latest_remote_revision
current_local_revision
last_checked_at
```

联合唯一键至少包含 provider/profile 和 canonical paper ID，避免不同服务或账号冲突。

### revisions

```text
profile_id
paper_id
revision
status: staging | committed | corrupt
manifest_path
synced_at
last_verified_at
```

### artifacts

```text
profile_id
paper_id
revision
kind
relative_path
bytes
sha256
source_url_redacted
```

### workspaces

```text
workspace_id
root_path
manifest_path
last_seen_at
```

### workspace_papers

```text
workspace_id
profile_id
paper_id
revision
tracking_mode
materialization_mode
```

### skill_installations

```text
installation_id
platform
scope
mode
target_root
package_version
installed_at
```

数据库 schema 自带 version。migration 在事务中执行，并在升级前验证备份/恢复路径。

## 8. Project Workspace

> 实施状态（2026-07-11）：Phase 5 已实现 init/add/list/status/sync/remove、普通复制物化、
> managed-file 冲突保护和用户文件保留。当前 CLI 使用显式 positional `PROJECT_ROOT`；
> workspace pin 和完整离线命令仍未实现。

### 8.1 工作区身份

`papers/manifest.json` 是项目成员关系和物化状态的权威。workspace 不要求服务器有对应
Collection，也不要求整个项目在线。

建议 schema：

```json
{
  "schema_version": 1,
  "workspace_id": "uuid",
  "created_at": "2026-07-11T00:00:00Z",
  "updated_at": "2026-07-11T00:00:00Z",
  "papers_dir": ".",
  "papers": {
    "canonical-paper-uuid": {
      "short_id": "P-3a",
      "directory": "2024-Smith-et-al-Inflation-Dynamics--P-3a",
      "directory_naming": {
        "protocol": "year-author-short-title--short-id-v1",
        "generated_from_revision": "task-id"
      },
      "title": "Example Paper",
      "profile": "default",
      "revision": "task-id",
      "tracking": "latest",
      "materialization": "copy",
      "materialized_at": "2026-07-11T00:00:00Z",
      "managed_assets": {
        "metadata.json": "sha256",
        "full.md": "sha256",
        "layout.json": "sha256"
      }
    }
  }
}
```

manifest key 使用 canonical UUID；目录名只是可读展示层，不能作为论文身份或反向解析来源。
canonical ID、short ID、revision 和实际目录映射都必须保存在 manifest。

### 8.2 工作区目录命名协议

新加入工作区的论文默认使用确定性的 `year-author-short-title--short-id-v1`：

```text
{year}-{author_slug}-{title_slug}--{short_id}
```

示例：

```text
2024-Smith-et-al-Inflation-Dynamics--P-3a
2022-Smith-Jones-Monetary-Policy-Shocks--P-8f
2021-张三-et-al-地方债务与经济增长--P-a2
```

字段合同：

- year：`publication_year` -> `year` -> 可解析发布日期 -> `n.d.`。
- author：一位作者用姓氏；两位用 `Smith-Jones`；三位及以上用 `Smith-et-al`；缺失用
  `Unknown`。结构化作者优先 `family`、`last_name`、`name`。
- short title：从正式 title 确定性生成，不调用 LLM；保留 Unicode 字母/数字，把空白和
  标点折叠为 `-`，title 部分最多 60 字符。
- short ID：始终作为 `--P-xxx` 后缀以保证可辨识和唯一性；缺失时使用受控 UUID 前缀。
- 整体目录名最多 120 字符，拒绝 Windows 非法字符、尾随空格/句点、`.`、`..` 和保留名。

内部 managed asset 文件名保持固定：`metadata.json`、`full.md`、`layout.json`。目录名变化
不能导致 Skill 和 `rg papers/*/full.md` 合同变化。

命名只在 `workspace add` 首次物化时生成。`workspace sync` 即使发现 metadata 标题、年份或
作者变化，也不得自动重命名已有目录，以免破坏笔记、Git 历史和外部引用。

旧 `P-xxx/` 目录或 metadata 更新后的建议名称通过显式协议迁移：

```bash
paper-agent workspace names plan <project-root> [paper-ids...]
paper-agent workspace names apply <project-root> [paper-ids...]
```

- `plan` 只返回 current/proposed/reason，不修改文件。
- `apply` 原子重命名整个论文目录并更新 manifest；用户文件随目录保留。
- 目标目录已存在或来源不明时返回 `CONFLICT`，不允许 `--force` 接管。
- manifest 提交失败时必须把目录恢复为旧名称。

### 8.3 Init

```bash
paper-agent workspace init --workspace <absolute-project-path>
```

算法：

1. resolve 明确传入的 project path。
2. 检查项目存在、可写且目标 `papers/` 不发生路径逃逸。
3. 若 manifest 不存在，创建空 manifest；若已存在，验证并幂等返回。
4. 不修改项目根 `.gitignore`，除非用户显式要求。
5. 输出 workspace ID、manifest 和 papers root。

### 8.4 Add

```bash
paper-agent workspace add P-3a P-8f --workspace <path>
```

算法：

1. 验证 workspace manifest。
2. 对每个 ID 解析 canonical paper/revision。
3. 调用 ArtifactSyncService 确保全局缓存存在。
4. 从 metadata 按目录命名 protocol 生成目标名，在 `papers/.staging/<operation-id>/` 复制
   managed assets。
5. 验证复制后 bytes/hash/JSON。
6. 检查目标目录冲突。
7. 原子移动到最终目录。
8. 最后原子更新 manifest。
9. 批量操作返回逐论文结果；单篇失败不应隐藏其他结果，但默认 manifest 只登记成功项。

### 8.5 Sync

```bash
paper-agent workspace sync --workspace <path>
paper-agent workspace sync P-3a --workspace <path>
```

对每篇论文：

1. 检查现有 managed asset 与 manifest hash。
2. 发现本地修改时标记 `CONFLICT`，默认跳过该论文。
3. pinned revision 只验证，不升级。
4. latest revision 查询服务器或使用已经 refresh 的全局状态。
5. 无新 revision 时幂等返回 unchanged。
6. 有新 revision 时先同步全局缓存，再在 staging 复制。
7. 保留非 managed files；只替换 managed assets。
8. 成功后更新 manifest revision/hash。
9. metadata 变化不自动重命名目录；名称迁移只由 `workspace names apply` 执行。

### 8.6 Remove

移除有破坏性，默认行为必须明确：

- 从 manifest 取消成员关系。
- 删除 managed assets 前列出将删除文件。
- 论文目录中存在用户文件时，不删除整个目录；保留目录并报告 detached files。
- 不删除全局缓存。
- 批量或 `--purge-user-files` 等未来危险模式需要额外确认，MVP 可以不提供。

### 8.7 Status

```bash
paper-agent workspace status --workspace <path>
```

每篇论文至少报告：

```text
ok                 managed files match manifest
missing            managed file absent
modified           managed file hash changed
update_available   remote/global newer revision exists
pinned             intentionally stays on old revision
cache_missing      manifest revision unavailable in global store
invalid            path or metadata violates schema
```

## 9. 冲突策略

| 情况 | 默认行为 | `--force` 行为 |
|---|---|---|
| managed file 未修改，有新 revision | 安全替换 | 同默认 |
| managed file 被修改 | 返回 `CONFLICT`，跳过 | 备份/列明后覆盖 |
| 用户文件存在 | 保留 | 仍保留，除非另有危险参数 |
| 目标目录属于另一 paper ID | 返回 `CONFLICT` | 不建议允许强制接管 |
| manifest 缺项但目录存在 | 报告 orphan，要求 adopt 或 rename | 不静默删除 |
| 全局 revision 校验失败 | 不物化，保留旧项目文件 | 不允许绕过完整性校验 |
| Skill 目标被用户修改 | 不更新该 Skill | 显式列明后覆盖受管文件 |

`--force` 不是跳过 path、安全或完整性校验的通用开关。

## 10. Managed Assets 与用户文件

初始 managed asset allowlist：

```text
metadata.json
full.md
layout.json
images/<manifest-listed-files>
source.pdf
```

同步器不能通过“目录里除了这几个文件都删除”的方式更新。每次删除仅依据旧 manifest 的
managed asset 列表，并且确认目标路径仍位于论文目录。

用户笔记建议与 managed assets 同目录或项目自定目录均可；Paper Agent 不规定研究笔记
格式，以免工作区基础设施侵入上层研究方法。

## 11. 图片、PDF 与 layout

### 11.1 Markdown 图片

当前 OCR Markdown 可能使用：

```markdown
![](images/<hash>.jpg)
```

服务器 assets API 尚未保证列出每张图片。complete profile 的实现选项：

1. 服务端未来提供完整 artifact manifest/bundle，客户端按清单下载（优先长期方案）。
2. MVP 解析 Markdown 的本地相对图片引用，并在受控 output prefix 下逐个下载。

解析时只接受相对 `images/<safe-name>`，拒绝绝对 URL、`..` 和其他目录。

### 11.2 PDF

PDF 默认可以不进入 text profile，以降低带宽和磁盘占用。用户显式选择 complete profile
或 `--include-pdf` 时下载。PDF 必须流式写入并验证最小 PDF signature/size。

### 11.3 layout.json

layout 是页码和版式映射资产，不作为全文权威文本。MVP 只保证保存和校验；后续可以增加：

- query/snippet 到 page number 的定位助手。
- 按页提取文本。
- 图表、段落和 bbox 定位。

这些派生能力不能改写原始 `layout.json`。

## 12. 本地检索

工作区建立后，Skill 优先调用系统 `rg`：

```bash
rg -n -C 4 "exclusion restriction" <workspace>/papers/*/full.md
rg -l "difference-in-differences" <workspace>/papers/*/full.md
```

Skill 应先用 `rg -l` 或限制匹配数缩小论文，再读取命中行附近内容，避免把所有全文放入
context。

未来 FTS5 必须是 `<user-cache>/.../search/` 下可删除、可重建的派生缓存。workspace manifest
和正文阅读不能依赖索引存在。

## 13. 并发、锁与事务

典型场景包括多个 Agent 同时拉同一篇论文或同步同一工作区。

建议锁粒度：

- config migration：用户配置全局锁。
- artifact sync：`profile + paper_id` 锁。
- workspace write：workspace ID/manifest 锁。
- Skill installation：target root + skill name 锁。

要求：

- 锁文件位于受控 `locks/`，包含 PID、创建时间和 operation ID。
- stale lock 不能仅凭年龄删除；应确认进程不存在或使用可靠锁库。
- 持锁期间避免长时间无进度；下载可使用 staging，但 commit 阶段必须序列化。
- 文件提交与 SQLite 状态更新要定义顺序，崩溃后 `doctor/cache verify` 能修复不一致。

推荐提交顺序：完整 staging -> 原子目录 rename -> SQLite transaction。数据库未更新但目录已
存在时，verify 可重新登记；数据库先写而文件未提交更难恢复，因此禁止。

## 14. 重试、离线与恢复

### 重试

- GET metadata/assets：对连接错误、超时和部分 5xx 进行有限指数退避。
- 静态资产下载：支持重新开始；是否支持 HTTP Range 取决于服务端验证结果。
- 上传：不能盲目重试非幂等 POST；必须使用服务端去重身份或先查询结果。
- 401/403、404、schema 错误和本地冲突不自动重试。

### 离线

- `workspace add` 在指定论文/revision 已完整缓存时可以离线物化。
- `workspace status` 默认只检查本地；`--remote` 才访问服务器检查更新。
- 离线但缓存缺失时返回明确 `cache_missing`，不制造空文件。

### 恢复

- 启动时不自动遍历整个资产库。
- `paper-agent cache verify` 按需扫描 manifest、hash 和数据库引用。
- staging 中无活跃锁的旧操作可以由显式 cleanup 清除。
- committed revision 不因临时失败被覆盖或删除。

## 15. Cache Verify 与 GC

### Verify

```bash
paper-agent cache verify
paper-agent cache verify P-3a
```

检查：

- manifest schema 和身份路径一致。
- required files 存在且 hash/bytes 正确。
- JSON 可解析，Markdown 非空。
- SQLite revision/artifact 行与文件一致。
- current revision 指向 committed revision。

### GC

GC 默认只生成计划：

```bash
paper-agent cache gc --dry-run
paper-agent cache gc --apply
```

候选条件可以包括：

- 非 current revision。
- 没有任何已登记 workspace 引用。
- 超过配置保留期。
- 不处于 pinned 状态。
- manifest 完整可识别。

无法识别的目录不自动删除。GC 输出 paper ID、revision、bytes、最后使用时间和理由。

## 16. 日志与操作结果

每次同步产生 operation ID。结构化日志上下文建议：

```text
operation_id
component
profile
paper_id
revision
workspace_id
artifact_kind
bytes
duration_ms
cache_hit
```

不得记录：

- API Key/JWT/header。
- credentials.env 内容。
- 未经用户请求的正文片段。
- 包含敏感 query 的完整 URL；query/header 应脱敏。

命令 JSON 应返回足够信息让 Agent 决定下一步，不要求解析日志：

```json
{
  "paper_id": "uuid",
  "short_id": "P-3a",
  "revision": "task-id",
  "cache_hit": false,
  "artifacts": [
    {"kind": "fulltext", "path": ".../full.md", "bytes": 100, "sha256": "..."}
  ]
}
```

## 17. 测试矩阵

### 配置和安装

- 全新用户目录初始化。
- 已有配置补字段但保留自定义值。
- 多旧 `.env` 值一致/冲突。
- Codex/Claude user/project targets。
- 目标未修改更新、用户修改冲突、未知目录拒绝接管。
- standalone/plugin 重复检测。

### Artifact Sync

- metadata/full/layout 成功下载。
- NOT_READY、401、404、5xx、timeout、断流。
- layout 非法 JSON、空 Markdown、错误 hash。
- 同 revision cache hit。
- 新 revision 保留旧 revision。
- 并发拉同一 paper 只提交一次。
- malicious URL/path traversal 拒绝。

### Workspace

- init 幂等。
- add 一篇/多篇、缓存命中、离线物化。
- sync 无变化/有新 revision/pinned。
- managed asset 被改时冲突。
- 用户 notes 保留。
- 批量部分失败结果可解释。
- manifest 原子更新和崩溃恢复。
- remove 不删除全局缓存。

### QA E2E

- 用专用账号搜索已知论文，拉到临时 global store。
- 物化到临时项目。
- 断言 metadata/full/layout 存在且可解析。
- 用 `rg` 命中已知术语并读取上下文。
- 全流程不调用服务端 L3。
- 测试结束清理临时目录，不触碰真实用户缓存。

## 18. MVP 范围

第一版应实现：

- 统一用户配置和 Frowang credential。
- Skill 安装到 Codex/Claude standalone user scope。
- metadata/full/layout 的 text profile。
- canonical UUID + task/revision 目录。
- SQLite 最小 papers/revisions/artifacts/workspaces 状态。
- workspace init/add/list/status/sync。
- 普通复制、hash、原子写入和用户文件保护。
- 本地 `rg` 工作流。

第一版不要求：

- 双向服务器 Collection/workspace 同步。
- 默认图片/PDF 完整 bundle。
- 自然语言或向量检索。
- FTS5。
- 自动缓存 GC。
- 多用户共享本地资产库。
- 在 Plugin 安装期间静默安装 Python 依赖。

## 19. 验收不变量

实现完成后必须满足：

1. 删除或升级任意 Skill/Plugin 不会删除配置、缓存或项目论文。
2. 同一 paper/revision 在不同项目中不会重复访问服务器下载。
3. 任意网络中断不会产生可被误认为 committed 的 revision。
4. 任意 workspace 同步不会删除 manifest 之外的文件。
5. 本地修改的 managed asset 不会被默认覆盖。
6. project manifest 足以解释每个论文目录来自哪个 profile、paper ID 和 revision。
7. `doctor` 能识别配置、安装、数据库和工作区的主要不一致。
8. Agent 可以仅通过 JSON 响应和稳定错误码处理成功、等待、重试和冲突。
9. 新论文正文检索体验不依赖服务端 L3。

## 20. 服务端可选增强

本地 MVP 不依赖后端改造，但以下端点能力会显著简化完整同步：

- `/papers/{id}/assets` 返回每个 artifact 的 revision、bytes、sha256 和 content type。
- 提供经过认证的 artifact bundle/manifest，包含 Markdown 引用图片清单。
- 支持 ETag/If-None-Match 或 Last-Modified 条件请求。
- 明确静态资产的稳定认证、URL 编码和 Range 行为。

任何后端增强都必须保持现有 fulltext/assets 路径兼容，并同步 `docs/API_SURFACE.md`、CLI、
MCP 和 QA 合同。
