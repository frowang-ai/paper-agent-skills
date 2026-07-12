---
layer: framework
update_mode: rewrite
role: "memory-docs 入口：三层结构、阅读顺序和更新协议"
read_when: "第一次进入项目，或不确定某条信息应写到哪里时"
not_for: "项目实现细节、完整 API 手册或代码目录清单"
---

# Paper Agent Memory Docs

本目录是给开发 Agent 使用的项目记忆层。它保存稳定的框架认知、导航指针和关键决策，
帮助后续开发在不重复扫描整个仓库的前提下继续工作。

memory-docs 不是完整产品文档，也不是 API 参考。全量命令、参数、端点和字段仍以代码、
`docs/API_SURFACE.md`、CLI `--help` 和测试为准。

## 当前事实与目标设计

本文档严格区分两种状态：

- **当前实现**：已经存在并可从代码或测试验证的能力。
- **目标架构**：已经确认的开发方向，但可能尚未落地。

任何目标架构在实现前都不能当作现有能力调用。模块完成度统一查看
`memory-docs/detail_mem/PROGRESS.md`。

## 三层结构

### 框架层

进入项目时优先读取，保持精简：

| 文件 | 回答的问题 | 更新模式 |
|---|---|---|
| `OVERVIEW.md` | 项目是什么、核心边界和技术栈 | rewrite |
| `STATUS.md` | 当前焦点、最近里程碑和待办 | rewrite |
| `HISTORY.md` | 项目为何演变成当前形态 | append |
| `CONVENTIONS.md` | 必须遵守的工程和安全规则 | patch |
| `GLOSSARY.md` | 项目术语的准确含义 | patch |

### 路由层

| 文件 | 回答的问题 | 更新模式 |
|---|---|---|
| `DIRS.md` | memory-docs 下有哪些详细目录 | patch |

### 详细层

按需读取，可以随项目增长：

| 文件或目录 | 用途 | 更新模式 |
|---|---|---|
| `detail_mem/MAP.md` | 概念到 1-2 个入口文件的导航 | patch |
| `detail_mem/PROGRESS.md` | 模块级实现清单 | patch |
| `detail_mem/DECISIONS.md` | 已确认架构决策及理由 | append |
| `design/` | 目标架构、同步和存储协议 | patch |
| `SHORT_MEMORY/` | 尚未稳定的会话交接 | append |
| `archive/` | 已完成复盘、旧快照和失败探索 | append |

## 阅读顺序

新 Agent 的最小阅读集：

1. `memory-docs/OVERVIEW.md`
2. `memory-docs/STATUS.md`
3. `memory-docs/CONVENTIONS.md`

按任务继续读取：

- 找实现入口：`detail_mem/MAP.md`
- 判断是否已实现：`detail_mem/PROGRESS.md`
- 理解决策理由：`detail_mem/DECISIONS.md`
- 开发统一运行时：`design/ARCHITECTURE.md`
- 开发安装、缓存或工作区：`design/SYNC_AND_STORAGE.md`
- 查术语：`GLOSSARY.md`

## 更新协议

- 代码和文档冲突时，以当前代码和测试为准，并立即修正文档。
- `STATUS.md` 只保留最近 3-5 个里程碑，旧阶段沉淀到 `HISTORY.md`。
- 新增或移动能力时，在 `detail_mem/MAP.md` 只增加入口指针，不列全量文件。
- 模块状态变化时更新 `detail_mem/PROGRESS.md`。
- 形成稳定架构选择时追加 `detail_mem/DECISIONS.md`，不能改写旧决策来掩盖演变。
- 详细设计发生变化时同步更新 `design/`，并检查相关决策是否被取代。
- 未定论的想法先进入 `SHORT_MEMORY/`，不要提前写成正式架构。
- 新建 memory-docs 子目录后必须在 `DIRS.md` 登记。

