---
layer: framework
update_mode: append
role: "项目演变叙事：关键阶段、转折和重构之间的因果关系"
read_when: "需要理解项目为何形成当前架构时"
not_for: "当前状态、单条决策详情或按提交排列的流水账"
---

# Project History

## 初始阶段：以单个 Skill 快速验证远程论文库能力

项目最初围绕 `paper-library` 展开。Skill 内同时包含 `SKILL.md`、CLI、dotenv 加载和
HTTP 调用，并通过 zip 独立分发。这种结构能够快速验证 Agent 使用 Frowang Paper API
上传、检索和读取论文的可行性，但运行时、配置和 Skill 的边界尚未分离。

随后项目抽取了 `packages/paper_api_client/`，开始减少 Paper API 请求代码重复；然而
Skill 仍直接依赖源码路径和本地 `.env`，分发仍以单 Skill 自包含为主。

## Zotero 阶段：出现第二个生产 Skill 和跨 Skill 重复

项目增加 `zotero-upload`，从 Zotero 本地 API、profile 和 storage 中读取 PDF，再上传到
Frowang。这个能力证明“一个功能一个 Skill”的触发边界是合理的，也暴露了每个 Skill
重复维护 dotenv、Paper API Client、状态文件和运行说明的问题。

`skills/demo-zotero-connection/` 保留为探索和诊断代码，生产入口转移到
`skills/zotero-upload/`。

## 2026-07：确立服务器发现与本地深读的两阶段架构

论文研究项目通常只反复阅读少量到几十篇论文，因此不需要让 Agent 每次在整个服务器
论文库全文中搜索。项目将默认服务器检索收敛到 L1 元数据和 L2 属性树，停止新论文自动
建立 L3 全文索引；选中论文的 `full.md` 和 `layout.json` 应下载到本地工作区，再通过
`rg` 高频定位原文。

这一变化把服务器定位为候选池和权威资产源，把本地项目定位为活跃研究工作集。

- 相关决策：DEC-005

## 2026-07-11：从 Skills 仓库升级为 Paper Agent 工程化运行时

随着 `paper-library`、`zotero-upload` 和计划中的 `paper-workspace` 形成独立能力边界，
项目确认 Skill 不应各自拥有认证和完整运行时。新的方向是：保留多个薄 Skill，建立一个
共享 Python package 和稳定 `paper-agent` CLI，并将配置、安装、同步、缓存、诊断和版本
管理提升为产品级基础设施。

同时引入用户级论文资产库：服务器产物先按 canonical paper UUID 和 task revision 下载到
全局缓存，再按项目 manifest 复制到研究项目的 `papers/`。这既解决大文件没有稳定落点的
问题，也允许多个项目复用下载、离线建立工作区，并保持项目材料可复制和可归档。

- 相关决策：DEC-001 至 DEC-010
- 相关文档：`memory-docs/design/ARCHITECTURE.md`
- 相关文档：`memory-docs/design/SYNC_AND_STORAGE.md`

## 2026-07-11：完成统一运行时 Phase 1

项目建立 `src/paper_agent/` 可安装包和正式 `paper-agent` 入口。第一阶段没有急于迁移远程
论文业务，而是先固定所有后续模块都会依赖的基础合同：JSON envelope v1、稳定错误码和
exit code、`platformdirs` 用户路径、schema v1 TOML、幂等配置迁移、统一凭据状态、
capabilities 和本地 doctor。

Phase 1 使用真实子进程测试约束未知命令也必须返回 JSON，并在全新临时 venv 中安装 wheel
验证 console script，从而确认运行不依赖源码 PYTHONPATH 或当前 editable 环境。旧
`paper-library`/`zotero-upload` 业务入口保持不变，下一阶段再通过 service 逐步迁移。

- 相关决策：DEC-002、DEC-003、DEC-004
- 当前状态：`memory-docs/detail_mem/PROGRESS.md`

## 2026-07-11：完成远程论文库 Phase 2

项目将 Frowang HTTP 请求迁入 `src/paper_agent/clients/frowang.py`，统一处理 API Key、
timeout、GET 有限重试、服务端错误码、静态资产 URL 校验、percent encoding、流式 hash 和
原子落盘。`LibraryService` 承接论文、标签、笔记、Collection 和 JWT Key 管理用例，CLI
通过 `paper-agent library` 输出统一 envelope。

旧 `paper_cli.py` 不再维护业务和 HTTP 实现，只翻译旧命令参数并输出弃用警告；旧
`packages/paper_api_client` 也降级为 import 兼容层。长内容命令现在要求 `--save`，避免把
OCR 全文直接放入 Agent context。`doctor` 默认增加轻量远程认证检查，并支持
`--no-remote` 离线诊断。

- 权威 Client：`src/paper_agent/clients/frowang.py`
- 权威 Service：`src/paper_agent/services/library_service.py`
- Skill：`skills/paper-library/SKILL.md`

## 2026-07-11：完成 Zotero Phase 3

生产 Zotero 连接、跨平台 storage 发现和导入编排从 Skill scripts 迁入统一 runtime。
`ZoteroImportService` 会按唯一 item 去重上传，同时保留它所属的多个 Collection membership；
Frowang Collection 映射和 item 同步记录进入用户 data 目录的 SQLite，解决旧实现重复建树和
Skill 更新丢失 `sync_state.json` 的问题。

本地和远程 Zotero 模式改为 profile 显式选择，不再静默 fallback。旧 JSON 通过幂等
`zotero migrate-state` 导入；旧 CLI 只翻译 `sync-status` 等参数并输出弃用警告。

- Client：`src/paper_agent/clients/zotero.py`
- Service：`src/paper_agent/services/zotero_import_service.py`
- State：`src/paper_agent/storage/state_store.py`

## 2026-07-11：完成安装与分发 Phase 4

项目建立 `skills/manifest.json` 作为生产 Skill 发布 allowlist，并让源码、wheel resources、
standalone 安装、薄 zip 和 Plugin bundle 共用同一 `SkillSource` 与 SHA-256 清单。Codex 和
Claude Code 现在都支持 user/project scope 的 install、status、diff、update 和 uninstall；
安装记录进入用户级 SQLite，未知目录、受管文件修改和状态写入失败都有保护或恢复路径。

同一生成 bundle 同时包含 Codex 与 Claude manifest，并通过两个平台 validator。Plugin 的
真实安装生命周期继续交给 marketplace；Paper Agent 明确不直接修改平台私有 cache。
文档和推荐流程也不再要求每个 Skill 保存 `.env` 或独立依赖。

- 相关决策：DEC-010、DEC-012、DEC-015
- Installer：`src/paper_agent/services/skill_install_service.py`
- Plugin：`src/paper_agent/plugins/bundle.py`

## 2026-07-11：完成资产库与项目工作区 Phase 5

项目把服务器论文产物正式分成用户级 revision 缓存和项目级物化视图。`paper pull` 根据
active profile、canonical paper ID 和最新 task ID 建立 text revision，在 metadata、全文和
layout 全部校验后才写 committed manifest 与 SQLite；相同 revision 重新使用前仍检查 bytes
和 SHA-256。

`workspace init/add/list/status/sync/remove` 以项目 `papers/manifest.json` 管理成员关系，默认
普通复制全局缓存。同步通过 staging/backup/replace 更新 managed assets，并保留用户新增的
阅读笔记；本地修改或缺失默认返回冲突。新的 `paper-workspace` Skill 将服务器 L1/L2 发现、
项目加入和本地 `rg` 深读串成正式 Agent 工作流。

- Artifact：`src/paper_agent/services/artifact_sync_service.py`
- Workspace：`src/paper_agent/services/workspace_service.py`
- Skill：`skills/paper-workspace/SKILL.md`

## 2026-07-12：工作区目录升级为 metadata 可读命名

项目将新论文目录从单独的 `P-xxx/` 升级为版本化的
`year-author-short-title--short-id-v1`，例如
`2024-Smith-et-al-Inflation-Dynamics--P-3a`。canonical ID 仍由 manifest 管理，内部
`full.md` 等文件名保持不变，因此本地 `rg papers/*/full.md` 合同没有变化。

为避免 metadata 更新导致路径漂移，`workspace sync` 明确不自动重命名；旧目录和建议名称
通过 `workspace names plan/apply` 显式迁移。迁移移动整个目录以保留用户笔记，拒绝目标
冲突，并在 manifest 写入失败时恢复旧名称。

- 相关决策：DEC-017
- 协议实现：`src/paper_agent/workspace/naming.py`

## 2026-07-12：增加 Agent 可编排的本地凭据管理

Runtime 新增 `paper-agent auth set/status/delete`。默认 `set` 在终端隐藏输入，Agent 自动化可用
`--stdin`，因此 Key 不进入 `paper-agent` 子进程参数；所有 JSON、错误和状态仍只返回配置状态
与来源。凭据文件通过临时文件原子替换，更新 Frowang Key 时保留 Zotero Key、注释和未知项，
删除时同时清理 `FROWANG_API_KEY` 与旧 `PAPER_API_KEY` 文件项。

同时确定独立公开 GitHub Bootstrap Skill 作为 Marketplace 之外的通用安装入口：用户向 Agent
提供固定 Prompt 和仓库 URL，Agent 读取 Skill 后完成 Runtime 安装、认证、doctor 与 smoke
test。Bootstrap 仓库不复制 Runtime 业务代码。

- 相关决策：DEC-018、DEC-019
- 实现：`src/paper_agent/config/credentials.py`、`src/paper_agent/cli.py`
- 验证：90 项离线测试通过；本轮 Ruff 因沙箱外审批服务 503 未能执行，不能记为已通过。
