---
layer: framework
update_mode: rewrite
role: "当前焦点、近期完成、优先级和必须遵守的约束"
read_when: "开始新任务、判断下一步或确认当前里程碑时"
not_for: "模块级实现细节、历史叙事或完整架构设计"
---

# Current Status

Last verified: `2026-10-18`

## Current Focus

- **0.9.6：`workspace add` 支持 `collab~` 引用（2026-10-18）**：修复协作副本引用在
  ArtifactSyncService 被拒为 `INTEGRITY_ERROR: Invalid paper_id path segment` 的缺陷：
  scoped 身份保留进项目 manifest 与状态库，仅磁盘缓存路径派生安全目录段；缓存 revision
  改以产物 URL 内嵌任务号为准（collab 副本 detail 报 `task_collab_*` 而只读资产端点
  降级读底层论文产物，两侧任务号会错位），URL 形态异常时退回 detail 任务号，普通私有
  论文保持单请求 cache-hit 路径。新增 5 项 `tests/_test_collab_workspace_sync.py` 回归；
  `PYTHONUTF8=1` 下 176 项全过，Ruff 与 `uv build` 通过。同步更新 API_SURFACE 与
  paper-workspace/paper-library Skill 文档。

- **资源鉴权兼容已实测，流式下载拒绝补丁随 0.9.6 一同发布（2026-10-04 起）**：真实
  list/assets/fulltext/summary/PDF/layout 读取均通过；`87a1f65` 修复下载遭 401/403/404
  时未读取流式错误体导致的堆栈，此前未发 PyPI，随本次版本一并带上。

- 当前已发布版本为 **`0.9.5`**：GitHub tag `v0.9.5` 指向 `b839151`，wheel 与 sdist 已发布
  [PyPI](https://pypi.org/project/paper-agent-skills/0.9.5/)，本机已从 PyPI 重装并确认更新检查返回 0.9.5。
- `library annotation locate/add` 已上线：Agent 引用原文，服务端定位 PDF 坐标并创建高亮或下划线；
  支持私有与协作作用域、候选消歧、revision 和幂等重试。真实私有论文创建/回读通过，用户已确认收到效果。
- 统一运行时 Phase 1 至 Phase 5 已完成：配置/协议、远程论文库、Zotero、Skill 分发、
  Global Artifact Store、项目 workspace 和本地 `rg` 深读主流程均已落地。
- Phase 6 仍包括更广泛的真实服务器 QA、图片/PDF complete profile、项目阅读导航和缓存治理；
  本次完成远程原文到 PDF 页码/坐标的定位，不代表 complete profile 已实现。
- Phase 5 当前只实现 text profile；图片引用和 source PDF 不会被伪装为已离线同步。

## Done（最近里程碑）

- [x] 2026-09-24：0.9.5 原文批注能力、Skill/README/API surface 与 capabilities 清单同步发布。
  160 项测试、Windows Python 3.13 干净 wheel 安装、Skill/Plugin 校验及 PyPI 文件 SHA-256 对照通过；
  详见 [发布历史](HISTORY.md)。
- [x] 0.9.3 / 0.9.4 已补齐 `collab~` 论文副本路由与协作关系管理命令，0.9.5 保留这些能力；
  参数和作用域边界见 [API surface](../docs/API_SURFACE.md)。
- [x] Python 3.13+ Runtime、统一配置、凭据和 JSON CLI 合同。
- [x] Frowang Library 与 Zotero Import 生产模块。
- [x] Codex/Claude standalone installer 与双平台 Plugin。
- [x] 按 profile/canonical paper ID/task revision 保存的 Global Artifact Store。
- [x] metadata/full/layout 校验、manifest、SHA-256、cache hit 和 per-paper lock。
- [x] SQLite papers/revisions/artifacts/workspaces/workspace_papers 状态。
- [x] workspace init/add/list/status/sync/remove、普通复制和用户文件保护。
- [x] `year-author-short-title--short-id-v1` 与旧目录 `names plan/apply` 显式迁移。
- [x] 薄 `paper-workspace` Skill 与 remote -> global -> project 本地 HTTP E2E。
- [x] `auth set/status/delete`，支持隐藏式输入和供 Agent 使用的 `--stdin` 原子凭据写入。
- [x] 独立 `paper-agent-setup` Bootstrap Skill 已在同级仓库完成本地实现和合同验证。
- [x] CLI 输出按终端自适应：交互终端显示人类摘要，管道/Agent 与 `--json` 保持 JSON。
- [x] 论文 metadata/attribute-tree 获取与下载：`library metadata`/`library attribute-tree`
  CLI（含 `--save`），sync 的 `metadata.json` 改用学术元数据端点，可选
  `attribute_tree.json` 进入 manifest（required: false）。
- [x] 论文截图：`library screenshots` 查询已有截图/job 进度，`--generate` 异步触发，
  `--wait` 轮询至终态；截图 URL 为绝对地址，经 `download-asset` 下载。
- [x] PyPI 更新检查（24h 缓存、env 可关闭）与 `paper-agent update check`；Skill 编排
  提醒用户并在确认后升级 Runtime 和已装 Skill。

## In Progress

- [ ] 补充 NOT_READY 与 revision 更新场景；2026-10-04 已完成真实 assets 与授权文件下载验收，不能代替其余 Phase 6 范围。
- [ ] 设计 complete profile 的图片/PDF资产清单，优先推动服务端 artifact manifest。
- [ ] 完善项目本地 layout 命中到 PDF 的阅读导航；远程原文定位已通过 `annotation locate` 提供。
- [ ] 将 `paper-agent-setup` 推送到公开 GitHub，并完成干净 Windows/macOS/Linux Agent 安装 E2E。

## Backlog

- **发布 `87a1f65` 流式下载错误处理补丁并验证安装包**：源码已提交推送，但 PyPI 仍为 0.9.5；不要混入工作树内尚未发布的 assistantAPI 改动，也不要把直接运行修复源码当成安装版已升级。

- P1：扩展扫描件、跨页、协作多人真实账号 QA，以及 macOS/Linux 安装验收；本轮线上实测为私有论文跨行高亮。
- P1：cache status/verify/gc 公共命令与 workspace doctor。
- P1：图片/PDF complete profile 和 Markdown 图片引用处理。
- P2：revision pin、离线操作增强和结构化日志。
- P2：评估 SQLite FTS5；在 `rg` 不足前不提前建设。

## 当前必须遵守的约束

- 服务器 L1/L2 用于发现；项目 `full.md` 和本地 `rg` 用于高频正文检索。
- Global Store 是可重建的 revision 缓存；项目 `papers/manifest.json` 是项目成员权威。
- 只有完整校验并标记 committed 的 revision 可以物化。
- manifest 未声明的项目文件属于用户，sync/remove 不得删除。
- 工作区目录名是可读展示层；canonical paper ID 和 manifest 映射才是身份权威。
- `skills/manifest.json` 是正式 Skill 分发 allowlist。
- API Key、用户论文和全局缓存不得进入 Git、Skill、wheel resources 或 Plugin。
- GitHub Bootstrap Skill 只负责引导安装已发布 Runtime，不成为第二套业务代码。

## 相关文档

- 模块完成度：`memory-docs/detail_mem/PROGRESS.md`
- 同步协议：`memory-docs/design/SYNC_AND_STORAGE.md`
- 代码入口：`memory-docs/detail_mem/MAP.md`
- 稳定决策：`memory-docs/detail_mem/DECISIONS.md`
