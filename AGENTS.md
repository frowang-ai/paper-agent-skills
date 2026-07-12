Always respond in Chinese-simplified.

# Paper Agent 仓库规则

## 开始工作前

本项目使用 `memory-docs/` 作为 Agent 项目记忆层。进入仓库后先读取：

1. `memory-docs/OVERVIEW.md`
2. `memory-docs/STATUS.md`
3. `memory-docs/CONVENTIONS.md`

按任务继续读取：

- 找代码入口：`memory-docs/detail_mem/MAP.md`
- 判断模块是否实现：`memory-docs/detail_mem/PROGRESS.md`
- 理解决策：`memory-docs/detail_mem/DECISIONS.md`
- 开发统一运行时：`memory-docs/design/ARCHITECTURE.md`
- 开发安装、同步、缓存和工作区：`memory-docs/design/SYNC_AND_STORAGE.md`

`memory-docs/INDEX.md` 说明完整阅读和更新协议。

## 当前实现与目标架构

- 文档明确区分“当前实现”和“目标架构”；不得调用 `PROGRESS.md` 标为未实现的命令。
- 代码、测试和文档冲突时，以当前代码和测试为准，并同步更新 memory-docs。
- `skills/paper-library/` 和 `skills/zotero-upload/` 是当前生产模块。
- `skills/demo-zotero-connection/` 仅用于探索和诊断，生产代码不得依赖它。

## 工程约束

- Python 路径使用 `pathlib.Path`；源码资源基于 `__file__` 或 `importlib.resources`，项目路径显式传入。
- 新增行为优先写 `_test_*.py`、`test_*.py` 或最小诊断脚本，再修改核心代码。
- Skill 负责触发和编排；配置、认证、HTTP、同步和状态应进入共享运行时。
- `skills/` 是唯一权威 Skill 源，分发副本不得手工维护。
- 不提交 `.env`、API Key、JWT、用户论文、Zotero 私有路径、缓存或日志。
- 大型 Markdown/JSON/PDF 使用流式、头部预览或抽样，不无必要整文件读入上下文。
- 不覆盖用户已有修改；同步和迁移必须遵循 manifest、hash、原子写入和冲突规则。

## memory-docs 更新

- 当前焦点或里程碑变化：更新 `STATUS.md`。
- 模块实现状态变化：更新 `detail_mem/PROGRESS.md`。
- 新增/移动入口：更新 `detail_mem/MAP.md`，每个概念只保留 1-2 个入口。
- 稳定架构选择：追加 `detail_mem/DECISIONS.md`。
- 目标协议变化：更新 `design/`，并检查相关决策是否被取代。
- 未定论交接：写入 `SHORT_MEMORY/`；旧方案和复盘进入 `archive/`。

