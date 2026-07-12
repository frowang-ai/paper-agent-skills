---
layer: framework
update_mode: rewrite
role: "当前焦点、近期完成、优先级和必须遵守的约束"
read_when: "开始新任务、判断下一步或确认当前里程碑时"
not_for: "模块级实现细节、历史叙事或完整架构设计"
---

# Current Status

## Current Focus

- 当前 PyPI/GitHub Runtime 发布版本为 `0.8.1`；`0.8.1` 增加三个生产 Skill 的 OpenAI
  Agent UI 元数据并清理旧 wrapper 和 `.env.example`。
- 统一运行时 Phase 1 至 Phase 5 已完成：配置/协议、远程论文库、Zotero、Skill 分发、
  Global Artifact Store、项目 workspace 和本地 `rg` 深读主流程均已落地。
- 当前焦点转向 Phase 6：真实服务器 QA、图片/PDF complete profile、页码定位和缓存治理。
- Phase 5 当前只实现 text profile；图片引用和 source PDF 不会被伪装为已离线同步。

## Done（最近里程碑）

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

## In Progress

- [ ] 在 QA automation 中使用部署服务器验证真实 assets 响应、NOT_READY 和 revision 更新。
- [ ] 设计 complete profile 的图片/PDF资产清单，优先推动服务端 artifact manifest。
- [ ] 增加 layout 命中位置到 PDF 页码的定位助手。
- [ ] 将 `paper-agent-setup` 推送到公开 GitHub，并完成干净 Windows/macOS/Linux Agent 安装 E2E。

## Backlog

- P1：真实账号端到端 QA 和跨平台用户验收。
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
