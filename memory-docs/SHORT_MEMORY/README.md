---
layer: detail
update_mode: append
role: "会话级临时上下文和跨 Agent 交接"
read_when: "恢复中断会话或接手尚未稳定的探索时"
not_for: "稳定状态、正式决策、长期规则或历史归档"
---

# Short Memory

本目录保存对下一次开发有用、但尚未稳定到可以进入正式架构和决策档案的内容。

## 适用内容

- 长会话中断时的已读文件、实验结果、未完成步骤和下一步。
- 仍需验证的 API 行为、跨平台安装差异或存储假设。
- 需要另一 Agent 继续调查的窄问题。

## 不应放入

- 稳定状态：更新 `STATUS.md` 或 `detail_mem/PROGRESS.md`。
- 稳定决策：追加 `detail_mem/DECISIONS.md`。
- 长期规则：更新 `CONVENTIONS.md`。
- 已完成复盘：移动到 `archive/`。

## 命名

- `YYYYMMDD_topic.md`
- `session_<id>_topic.md`

