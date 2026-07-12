---
layer: routing
update_mode: patch
role: "memory-docs 子目录注册表"
read_when: "需要查找详细设计、会话记忆或历史归档时"
not_for: "代码入口、术语定义或当前进度"
---

# DIRS — 子目录注册表

## 已注册目录

| 目录 | 用途 | 什么时候读取 | 更新模式 |
|---|---|---|---|
| `detail_mem/` | MAP、PROGRESS、DECISIONS 等详细层核心文件 | 查代码入口、模块完成度和决策理由时 | patch / append |
| `design/` | Paper Agent 目标架构、同步和存储协议 | 实现或评审统一运行时、安装、缓存、工作区时 | patch |
| `SHORT_MEMORY/` | 尚未稳定但需要交接的会话上下文 | 恢复长会话或跨 Agent 交接时 | append |
| `archive/` | 已完成复盘、旧方案和历史快照 | 回顾旧实现或失败探索时 | append |

## 规则

- 新建子目录后必须在本文件登记。
- 目录废弃时标注状态并保留历史指针，不直接制造断链。
- `design/` 记录已经确认的目标方案；未定论讨论进入 `SHORT_MEMORY/`。
- API、命令和字段的全量清单继续留在代码、`docs/` 或生成文档中。

