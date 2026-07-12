---
layer: framework
update_mode: patch
role: "项目领域术语、身份、状态和内部名称定义"
read_when: "遇到不熟悉或容易混淆的 Paper Agent 术语时"
not_for: "代码位置、工程规则或完整 API 字段列表"
---

# Glossary

## 核心产品术语

### Paper Agent

- 定义：由独立 Skills、共享 Python 运行时、统一配置、同步系统和本地论文数据层组成的产品。
- 易混淆点：不等同于单个 `paper-library` Skill，也不等同于 Frowang 服务端。

### Skill

- 定义：包含 `SKILL.md` 及可选 references/scripts/assets 的 Agent 工作流和触发单元。
- 易混淆点：Skill 是编排层，不应该成为独立认证和业务运行时边界。

### Plugin

- 定义：供 Codex 或 Claude Code 安装的一组 Skills、MCP、Hook 和资源的分发容器。
- 易混淆点：两个平台使用不同 manifest 和安装系统；Plugin 目录不是用户数据目录。

### Standalone Skill

- 定义：直接复制到 Codex/Claude Code 用户级或项目级 Skill 目录的 Skill。
- 易混淆点：standalone 与 Plugin 是互斥的安装模式，避免同一 Skill 重复发现。

### Paper Agent Runtime

- 定义：共享 Python package，提供 `paper-agent` CLI、配置、应用服务、Client 和后续存储实现。
- 当前状态：Phase 1-5 已实现，包括配置/协议、远程论文库、Zotero、installer、Plugin、text artifact store 和 workspace。

### Frowang Paper API

- 定义：远程论文库、处理状态、产物、标签、笔记和 Collection 的权威服务端 API。

### Remote Library

- 定义：用户在 Frowang 服务器上的长期论文候选池。
- 易混淆点：它不是某个研究项目的本地活跃工作集。

### Paper Discovery

- 定义：从远程论文库中判断哪些论文值得加入当前项目的低频检索过程。
- 当前默认：L1 元数据 + L2 属性树，不默认搜索 L3 正文。

### Paper Workspace

- 定义：具体研究项目中被选中并可被 Agent 高频读取的本地论文集合。
- 典型位置：`<project>/papers/`。
- 易混淆点：工作区是本地项目状态，不等同于服务器 Collection。

### Global Artifact Store

- 定义：用户级本地论文资产库，缓存从服务器下载的 metadata、Markdown、layout、图片和 PDF。
- 作用：避免多个项目重复下载，并支持离线物化工作区。

### Materialization

- 定义：把全局资产库中的指定论文 revision 复制到某个项目工作区并更新 manifest 的过程。

### Workspace Directory Naming Protocol

- 定义：把论文 metadata 确定性转换为工作区可读目录名的版本化规则；当前为
  `year-author-short-title--short-id-v1`。
- 易混淆点：目录名不是论文身份；metadata 更新不会由 sync 自动改名，迁移需要显式
  `workspace names plan/apply`。

### Managed Asset

- 定义：由 Paper Agent 下载、校验和同步的文件，例如 `full.md`、`layout.json` 和 `metadata.json`。
- 易混淆点：`notes.md`、`reading.md` 等用户文件不属于 managed assets。

## 身份与版本术语

### Canonical Paper ID

- 定义：Frowang 服务端论文的完整 UUID，是全局缓存和同步状态的稳定身份。

### Short ID

- 定义：面向用户的 Base36 短标识，例如论文 `P-3a`、Collection `C-2`。
- 易混淆点：short ID 适合命令和可读目录后缀，不作为跨账号或跨服务器的全局主键。

### Artifact Revision

- 定义：一次 OCR/处理产物版本，优先由服务器 `task_id` 或等价版本标识表示。
- 作用：避免论文重新处理后正文和页码映射静默变化。

### Manifest

- 定义：描述工作区成员、canonical ID、short ID、revision、文件 hash 和同步时间的结构化文件。

### Canonical Skill Inventory

- 定义：`skills/manifest.json` 中明确列出的生产 Skills 与可分发文件 allowlist。
- 易混淆点：仓库 `skills/` 可保留诊断和迁移文件，但它们不会因此自动进入正式分发。

### Profile

- 定义：一组具名运行配置，例如 Frowang base URL、账号上下文和 Zotero library 设置。
- 易混淆点：敏感凭据可以属于 profile，但不直接写入普通 `config.toml`。

## 搜索层级

### L1

- 定义：论文元数据搜索层，包括标题、摘要、作者、DOI、期刊等。

### L2

- 定义：论文属性树搜索层，包括方法、数据集、结论等结构化提取结果。

### L3

- 定义：OCR 全文切片搜索层。
- 当前定位：只兼容历史或显式维护索引；新论文不自动建立，不能作为默认发现能力。

## 同步术语

### Skill Installation Sync

- 定义：把仓库唯一 `skills/` 源安装到 Codex/Claude Code standalone 目录或打入 Plugin。

### Artifact Sync

- 定义：从 Frowang 服务器下载并校验论文 revision 到全局资产库。

### Workspace Sync

- 定义：按照项目 manifest 刷新工作区论文，并处理新 revision、本地修改和冲突。

## 相关文档

- 代码位置：`memory-docs/detail_mem/MAP.md`
- 目标架构：`memory-docs/design/ARCHITECTURE.md`
- 同步协议：`memory-docs/design/SYNC_AND_STORAGE.md`
