---
layer: detail
update_mode: append
role: "已完成记录、旧快照、失败探索和复盘归档"
read_when: "需要重建历史上下文或回顾被替换方案时"
not_for: "当前状态或活跃会话上下文"
---

# Archive

本目录保存已经结束的方案、复盘、旧状态快照和失败实验。

## 规则

- 归档忠于当时事实，不事后改写。
- 仍然有效的结论应提炼到 `STATUS`、`HISTORY`、`DECISIONS` 或 `design/`。
- 归档与活跃文档冲突时，以活跃文档和当前代码为准。
- 不把归档内容当成当前可调用能力。

## 命名

- `YYYYMMDD_topic.md`
- `YYYYMMDD_retrospective.md`
- `YYYYMMDD_failed_experiment.md`

