---
layer: detail
update_mode: patch
role: "概念到入口文件的快速导航，只记录 1-2 个权威入口"
read_when: "需要定位某个功能、产物或测试的代码入口时"
not_for: "完整目录树、全量 API、术语定义或当前状态"
---

# Map — 概念 → 入口文件

## 项目入口与分发

### 项目定位和开发方式

- 入口：`README.md`
- 包定义：`pyproject.toml`

### 统一 Paper Agent CLI

- 入口：`src/paper_agent/cli.py`
- 协议：`src/paper_agent/protocol/`

### 统一配置与凭据

- 入口：`src/paper_agent/config/settings.py`
- 路径/凭据：`src/paper_agent/config/paths.py`、`src/paper_agent/config/credentials.py`

### Skill 安装同步

- 源/目标：`src/paper_agent/skills/source.py`、`src/paper_agent/skills/targets.py`
- 安装服务：`src/paper_agent/services/skill_install_service.py`
- 状态：`src/paper_agent/storage/state_store.py`

### Plugin 构建

- 入口：`src/paper_agent/plugins/bundle.py`
- CLI/脚本：`paper-agent skills plugin-build`、`scripts/build_plugin.py`
- 发布清单：`skills/manifest.json`

### Runtime 更新检查

- 服务：`src/paper_agent/services/update_service.py`
- CLI：`paper-agent update check`；`doctor` 输出含 `update` 检查

### Skill zip 打包

- 当前入口：`scripts/build_skill_zip.py`
- 发布检查：`docs/RELEASE_CHECKLIST.md`

### Global Artifact Store

- 同步服务：`src/paper_agent/services/artifact_sync_service.py`
- 状态与 schema：`src/paper_agent/storage/state_store.py`

### Project Workspace

- 应用服务：`src/paper_agent/services/workspace_service.py`
- 目录命名：`src/paper_agent/workspace/naming.py`
- Skill：`skills/paper-workspace/SKILL.md`
- CLI：`src/paper_agent/cli.py` 的 `paper`、`workspace` 命令组

## 远程论文库

### Paper Library Skill 编排

- 入口：`skills/paper-library/SKILL.md`
- 端点参考：`skills/paper-library/references/api-endpoints.md`

### Paper Library CLI

- 正式入口：`src/paper_agent/cli.py` 的 `library` 命令组
- 测试：`tests/_test_paper_cli.py`

### 共享 Paper API Client

- 权威入口：`src/paper_agent/clients/frowang.py`
- 旧 import 兼容：`packages/paper_api_client/client.py`

### Paper Library Service

- 入口：`src/paper_agent/services/library_service.py`
- CLI 适配：`src/paper_agent/cli.py`

### Agent API Surface 合同

- 入口：`docs/API_SURFACE.md`
- 后端权威实现：相邻仓库 `../llm_read_paper_ai_workflow/api/routers/papers.py`

## Zotero

### 生产 Zotero 上传

- Skill 入口：`skills/zotero-upload/SKILL.md`
- 正式 CLI：`src/paper_agent/cli.py` 的 `zotero` 命令组

### Zotero 与 Paper API 适配器

- Zotero Client：`src/paper_agent/clients/zotero.py`
- 导入服务：`src/paper_agent/services/zotero_import_service.py`

### 全局 Zotero 同步状态

- 入口：`src/paper_agent/storage/state_store.py`
- 数据库：platformdirs 用户 data 目录下 `state.sqlite3`

### Zotero 探索与诊断

- 入口：`skills/demo-zotero-connection/zotero_connection.py`
- 诊断：`skills/demo-zotero-connection/_test_full_pipeline.py`

> 本目录不是生产依赖入口。

## 目标 Paper Agent

### 分层架构和统一运行时

- 设计入口：`memory-docs/design/ARCHITECTURE.md`
- 模块状态：`memory-docs/detail_mem/PROGRESS.md`

### 配置、Skill 安装、论文缓存和工作区

- 设计入口：`memory-docs/design/SYNC_AND_STORAGE.md`
- 决策：`memory-docs/detail_mem/DECISIONS.md`
- 凭据解析与原子管理：`src/paper_agent/config/credentials.py`
- 凭据 CLI：`src/paper_agent/cli.py` 的 `auth set/status/delete`

### Phase 1-4 合同测试

- 配置/协议：`tests/_test_phase1_config.py`、`tests/_test_phase1_protocol.py`
- CLI 子进程：`tests/_test_phase1_cli.py`
- Client/Service：`tests/_test_phase2_frowang_client.py`、`tests/_test_phase2_library_service.py`
- 远程 CLI：`tests/_test_phase2_cli.py`
- Zotero/状态：`tests/_test_phase3_*.py`
- Skill installer/Plugin：`tests/_test_phase4_*.py`
- Artifact/workspace：`tests/_test_phase5_*.py`
- 目录命名协议：`tests/_test_phase6_workspace_naming.py`

## 规则

- 每个概念只挂 1-2 个入口；拿到入口后继续读代码。
- 文件移动或权威实现切换时同步更新本文件。
- 全量命令、端点和字段分别以 CLI、代码和 `docs/API_SURFACE.md` 为准。
