# Skill 分发架构演进计划

> 来源：2026-09-07 GPT 深度调研（见 `docs/gpt调研.md`）+ 当日讨论结论。
> 本文是宏观方向计划，具体实施时再单独立项。

## 核心原则

**不要为了减少 filesystem entries，牺牲 semantic entries。**

- Skill = discovery unit（被发现/触发的入口，价值集中在 description）
- Plugin = distribution unit（安装/升级/版本管理的单位）
- 当前"根目录铺一排 skill"的不适感是分发问题，不要用收缩触发入口的方式去解决

## 已否决的方案

**Mega hub + 绝对路径读取 wheel 内隐藏 SKILL.md**（即"根目录只装一个 paper-agent 路由
skill，由它指路到安装目录"）。否决理由：

1. 触发率损失：多一道"先唤醒 hub"的 recall gate，description 从 N 个独立语义入口收缩为
   1 个超载入口。
2. `Read SKILL.md` ≠ invoke skill：host 的 skill 生命周期语义（列表、禁用、权限）全部失效。
3. 跨平台不可靠：skill 目录外引用不是标准机制，sandbox/cloud/企业策略下会断；各平台
   Plugin 规范均在禁止组件逃出包根目录。

可保留为 fallback/调试手段；若实现，用 `paper-agent skill show <name>` 让 runtime 自报
资源位置，不向 agent 暴露 `<sys.prefix>` 安装路径。

## 已确认的事实基础

- 生产 skill 自 0.8.1 起已是纯文档薄壳（SKILL.md + agents/openai.yaml + 参考文档），
  无代码；`skills/manifest.json` include 白名单 + wheel data-files 双重保证未来也不会
  带代码分发。
- 业务逻辑 100% 在 Python runtime，skill 只编排 `paper-agent` CLI 调用。
- `paper-agent skills plugin-build` 已能构建 `.codex-plugin` / `.claude-plugin` 双平台
  bundle（Phase 4 已完成并有测试），Plugin 分发是已有能力的转正，不是新建。
- 平台启动只常驻 skill 的 name+description（约 context 的 1-2%），skill 数量在几十个
  以内时上下文成本不是真问题。

## 阶段计划

### 阶段一：近期修补（随下个 release）

- Codex user 级 skill 路径兼容：OpenAI 官方已转向 `$HOME/.agents/skills`，安装器不能只
  假定 `~/.codex/skills`，需做版本/路径探测。
- 评估新增 `paper-agent skill show <name>`（fallback/调试用途）。
- 核实 Kimi Code `extra_skill_dirs` 特性（若属实，是最省事的原生命名空间扩展方式）。

### 阶段二：新 skill 开发（paper-writing / citation-audit / idea-generation）

- 一律以薄 skill 形式加入，代码进 runtime，文档进 skill。
- **citation-audit 保持独立 skill**：用户意图清晰（"检查引用是否与原文一致"），独立
  description 触发价值高，不并入其他 skill。
- 同步建立 trigger eval 测试集：每个 skill 维护 should_trigger / should_not_trigger /
  ambiguous_neighbors 话术清单，用 recall/precision 数据驱动后续聚合决策。

### 阶段三：Plugin 分发转正

- 一份 canonical skill source tree（`skills/`），release 时投影多平台 manifest
  （Claude / Codex / Agent Plugins 标准 / Kimi），不维护 N 份副本。
- standalone 安装保留，但推荐路径改为 Plugin（一次安装、一次升级、根目录只有一个
  逻辑产品）。
- 跟踪 Agent Plugins 开放标准（agent-plugins.org）进展，Cursor/Copilot 已支持。

### 阶段四：规模化聚合（触发条件驱动，不提前做）

当 skill 涨到几十个、且 trigger eval 显示触发率下降或平台告警列表超限时：

- 聚合为 3-5 个 domain gateway skill（如 paper-writing、paper-research），细节文档放
  gateway 自己目录下的 `references/*.md`（标准 progressive disclosure，相对路径）。
- 意图清晰的高价值 workflow（如 citation-audit）保留独立 skill，不并入 gateway。
- 长期可评估 MCP server 暴露原子工具（search_papers、upload_paper 等）；MCP 是能力
  接口增强，不替代 workflow skill。

## 明确不做

- 不做 mega hub 主架构。
- 不在规模问题出现前压缩 skill 数量。
- 不为减少 skill 数量立刻重构 MCP。
- 不在 skill 分发包中携带代码（白名单机制兜底）。

## 参考

- 调研全文与官方资料链接：`docs/gpt调研.md`
- 决策记录：`memory-docs/detail_mem/DECISIONS.md` DEC-023
