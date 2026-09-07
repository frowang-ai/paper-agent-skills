---
layer: detail
update_mode: append
role: "关键架构决策档案，记录选择、理由和影响"
read_when: "准备改变模块边界、分发、配置、搜索、同步或存储方案时"
not_for: "尚未定论的想法、操作规则或当前状态"
---

# Decisions

## 规则

- 新决策追加，不重写历史。
- 决策被取代时新增条目并引用旧 ID。
- 每条包含背景、决策、理由和影响。
- 代码尚未落地不影响设计决策成立，但必须在 `PROGRESS.md` 标为未实现。

## Log

### DEC-001：Skill 边界不等于运行时边界（2026-07-11）

- 背景：`paper-library` 和 `zotero-upload` 各自携带 dotenv、Paper API 调用和 CLI，新增 Skill 会继续复制基础设施。
- 决策：按用户意图保留多个独立 Skill，但认证、配置、Client、业务服务和存储归入一个共享 Paper Agent Runtime。
- 理由：Skill 适合负责触发和编排，不适合作为软件包、凭据和状态的隔离单元。
- 影响：正式 Skill 应变薄，只调用稳定 `paper-agent` 命令；Skill scripts 中的核心逻辑逐步迁出。

### DEC-002：Python package 与 uv tool 是唯一核心运行时（2026-07-11）

- 背景：现有实现和依赖均为 Python，同时维护 NPM 和 Python 两套业务实现会产生版本和测试负担。
- 决策：核心运行时发布为 Python wheel/sdist，并优先通过 `uv tool install` 安装；暂不建立 NPM 复刻实现。
- 理由：复用现有代码和生态，允许工程化模块拆分，也保留可审计源码。
- 影响：未来 `pyproject.toml` 提供稳定 `paper-agent` console entry point；NPM 只能作为有明确需求后的薄安装包装器。

### DEC-003：Skill 只依赖稳定 CLI/Tool 协议（2026-07-11）

- 背景：当前 Skill 直接引用 `python skills/.../paper_cli.py`，绑定仓库布局和源码位置。
- 决策：正式 Skill 调用 PATH 上的 `paper-agent`，默认使用 JSON 协议；内部 Python 路径不构成公共合同。
- 理由：允许重构包内部结构，并让 Codex、Claude Code、Plugin 和 standalone Skill 使用相同执行面。
- 影响：CLI 必须有稳定命令、响应 envelope、错误码、exit code、`--human`、`doctor` 和版本诊断。

### DEC-004：配置和凭据属于用户级产品配置，不属于 Skill/Plugin（2026-07-11）

- 背景：每个 Skill 的 `.env` 重复、难发现、会随 Plugin 缓存和升级产生多份副本。
- 决策：使用 `platformdirs` 定位统一用户配置目录；非敏感项进 `config.toml`，MVP 凭据可进用户级 `credentials.env`，后续优先 Keyring。
- 理由：用户只配置一次，所有平台和 Skill 共用；安装目录可安全替换。
- 影响：旧 `.env` 只用于兼容迁移；初始化/升级不能覆盖用户凭据；CI 继续支持环境变量。

### DEC-005：服务器发现与本地全文深读分离（2026-07-10）

- 背景：线上论文库可能很大，但单个研究项目通常只反复阅读几篇到几十篇论文；全文服务端索引增加存储和维护成本。
- 决策：服务器默认搜索 L1 元数据和 L2 属性树，用于发现候选论文；正文下载到本地后用 `rg` 高频检索。新论文不自动建立 L3。
- 理由：降低服务端负载，减少 Agent 上下文消耗，并把高频精确检索放在低延迟本地文件系统。
- 影响：L3 仅兼容历史或显式索引；QA 不能要求所有新论文有 L3；`paper-workspace` 成为正文阅读主路径。

### DEC-006：建立用户级、按 revision 保存的论文资产库（2026-07-11）

- 背景：直接把远程 Markdown 保存到临时或 Skill 目录没有稳定位置，不同项目还会重复下载同一论文。
- 决策：服务器资产先同步到用户级 Global Artifact Store，按 canonical paper UUID 和 task/revision 组织。
- 理由：复用下载、支持离线物化、保留重新 OCR 前后的版本，并为 hash 校验和缓存治理提供稳定根目录。
- 影响：全局缓存目录位于用户 data 目录；标题和 short ID 不作为全局主键；缓存清理由显式命令管理。

### DEC-007：项目工作区是本地物化视图，不等同于服务器 Collection（2026-07-11）

- 背景：服务器 Collection 面向长期整理，一个研究项目可能从多个 Collection 和搜索结果选择论文。
- 决策：工作区成员由项目 `papers/manifest.json` 管理，从全局资产库物化；第一版不自动双向映射服务器 Collection。
- 理由：避免远程/本地成员冲突，保持项目可迁移，并让研究项目拥有独立 revision 和笔记。
- 影响：后续可增加“从 Collection 导入”，但 Collection 仍不是工作区的远程副本。

### DEC-008：默认以普通复制物化工作区（2026-07-11）

- 背景：符号链接在 Windows、Git 和跨机器归档中不稳定；硬链接会让项目修改污染全局缓存。
- 决策：默认将 managed assets 普通复制到项目目录；链接/引用模式只作为未来显式高级选项。
- 理由：可移植、语义清楚、适合每项目几十篇论文的规模。
- 影响：允许一定存储重复；同步依靠 manifest/hash 检测本地修改，不能静默覆盖。

### DEC-009：同步系统拆为四种职责（2026-07-11）

- 背景：“同步”同时被用于 Skill 安装、配置复制、服务器下载和项目刷新，若合并会产生巨大耦合模块。
- 决策：分别实现 Skill Installation Sync、Configuration Bootstrap/Migration、Artifact Sync 和 Workspace Materialization。
- 理由：四者的权威来源、冲突策略、目标目录和生命周期完全不同。
- 影响：代码中建立独立 service/store；配置只初始化和迁移，不被持续覆盖。

### DEC-010：一份 Skill 源，多种安装适配器（2026-07-11）

- 背景：Codex 和 Claude Code 都能加载 Agent Skills，但 standalone 路径、Plugin manifest 和 marketplace 不同。
- 决策：根 `skills/` 是唯一源码；通过安装器、构建或 Plugin 分别生成目标产物。一个 Paper Agent Plugin 包含多个独立 Skills，不为每个 Skill 建一个 Plugin。
- 理由：避免内容漂移，同时保留每个 Skill 的精确触发边界和一次安装体验。
- 影响：提供 Codex/Claude Code 双 manifest；同一平台不得同时启用相同能力的 Plugin 与 standalone 副本。

### DEC-011：文件系统保存资产，SQLite 保存状态（2026-07-11）

- 背景：Markdown、layout、PDF 和图片需要直接被 `rg`、编辑器和 Agent 读取；同步状态需要事务和并发安全。
- 决策：二进制/文本资产保存在文件系统；全局 `state.sqlite3` 保存 revision、hash、同步状态、安装记录和工作区引用。
- 理由：兼顾文件工具生态、可检查性和 SQLite 的事务能力，不把大文本封装进数据库。
- 影响：项目仍保留可移植的人类可读 manifest；SQLite 是内部状态，不是论文正文存储。

### DEC-012：区分受管资产与用户文件，并采用原子同步（2026-07-11）

- 背景：Agent 会在论文目录写阅读笔记，网络失败也可能产生半截文件；简单全量覆盖会造成数据损失。
- 决策：manifest 明确列出 managed assets；同步使用临时文件、校验、原子替换和冲突检测，默认不触碰其他文件。
- 理由：保证失败可恢复，保护用户成果，并让同步行为可预测。
- 影响：本地文件 hash 变化返回 `CONFLICT`；只有显式 `--force` 才能覆盖；用户笔记从不进入自动删除集合。

### DEC-013：先完成基础设施，再创建 Paper Workspace Skill（2026-07-11）

- 背景：直接新增工作区 Skill 会再次复制配置、下载和路径逻辑。
- 决策：先实现统一配置、Client、CLI 协议和安装器，再实现资产库/物化，最后增加薄 `paper-workspace` Skill。
- 理由：让第一个工作区实现直接建立在长期结构上，避免短期脚本再次迁移。
- 影响：当前文档可定义工作区合同，但在 `PROGRESS.md` 标记完成前不得宣称命令可用。

### DEC-014：本地检索先用 rg，按证据决定是否增加 FTS5（2026-07-11）

- 背景：项目工作集规模有限，`rg` 已能提供字符串、正则、行号和上下文检索。
- 决策：第一版不建立论文级全文索引；只在自然语言排序、跨语言或性能数据证明需要时增加可重建的 SQLite FTS5 缓存。
- 理由：降低实现和状态同步复杂度，先验证核心工作区体验。
- 影响：设计应为未来索引预留 cache 位置，但 manifest 和正文资产不依赖 FTS5。

### DEC-015：以 allowlist inventory 生成所有 Skill 分发产物（2026-07-11）

- 背景：`skills/` 中同时存在生产编排、兼容 wrapper、诊断代码、旧 `.env` 和本地下载；直接复制整个目录会把凭据或用户数据带入安装包。
- 决策：`skills/manifest.json` 是正式发布 inventory，逐 Skill 声明允许分发的文件；wheel、standalone、zip 和双平台 Plugin 都从同一 `SkillSource` snapshot 生成。
- 理由：allowlist 比持续扩张的排除规则更容易审计，并能用逐文件 SHA-256 验证各分发形态一致。
- 影响：新增生产 Skill 或引用文件必须显式更新 manifest；Plugin 安装交给平台 marketplace，Paper Agent 不直接操作平台私有 cache。

### DEC-016：全局论文缓存按 profile 隔离（2026-07-11）

- 背景：不同 Frowang server/account 可能出现相同 canonical paper ID；只按 paper ID 和 revision 建目录会错误复用另一 profile 的资产。
- 决策：Global Artifact Store 使用 `artifacts/papers/<profile>/<paper_id>/<revision>/`，manifest 同时记录 profile 和 base URL；cache hit 必须验证这些身份字段。
- 理由：profile 是本地服务器/账号配置身份，作为第一层 namespace 能阻止跨来源缓存碰撞，而项目 manifest 仍可明确追溯来源。
- 影响：profile 名、paper ID 和 revision 都必须通过安全路径 segment 校验；用户改变同名 profile 的 base URL 时旧缓存不会被静默复用。

### DEC-017：工作区目录使用可读名称，但身份仍由 manifest 管理（2026-07-12）

- 背景：只使用 `P-xxx/` 作为项目论文目录虽然稳定，但几十篇论文并列时难以浏览；直接使用完整标题又会产生超长路径、非法字符、重名和 metadata 更新后的路径漂移。
- 决策：新论文采用确定性的 `year-author-short-title--short-id-v1` 目录命名，例如 `2024-Smith-et-al-Inflation-Dynamics--P-3a`。canonical paper ID 仍是 manifest key，目录名不参与身份判断；内部资产保持 `full.md` 等固定文件名。
- 理由：年份、作者和短标题提高人工可读性，short ID 后缀保证可辨识与唯一性；确定性规则比 LLM 生成名称更可测试、可迁移。
- 影响：`workspace add` 首次生成名称，`workspace sync` 不自动重命名；旧目录和 metadata 变化通过 `workspace names plan/apply` 显式迁移，目标冲突时拒绝接管，manifest 写失败时恢复旧目录。

### DEC-018：通用安装入口采用独立 GitHub Bootstrap Skill（2026-07-12）

- 背景：普通 GitHub 仓库中的 Skill 不会被 Codex/Claude 自动发现，且不能假设用户已经安装 Marketplace Plugin；仍需让不同 Agent 都能协助完成首次安装。
- 决策：建立独立公开的轻量 Bootstrap Skill 仓库，并提供一条固定 Prompt，让用户要求 Agent 下载仓库、读取 `SKILL.md` 并执行 Runtime 安装、认证、doctor 和 smoke test。Marketplace Plugin 可内置同一引导能力，但不是唯一入口。
- 理由：GitHub URL 与自然语言 Prompt 是跨 Agent 平台的最小公共入口，也便于用户审计安装指令；Runtime 继续通过 Python 包或 Release 分发，Bootstrap 仓库不复制业务代码。
- 影响：首次安装需要 Agent 具备网络和终端权限并在网络安装前确认；后续需单独建设仓库、发布地址和干净系统 E2E。

### DEC-019：Agent 凭据配置使用 stdin，凭据文件由 Runtime 原子管理（2026-07-12）

- 背景：用户希望把 Frowang Key 提供给 Agent 代为配置，但位置参数会把 secret 暴露到子进程参数、命令历史和更多日志面。
- 决策：Runtime 提供 `auth set/status/delete`；隐藏式交互是默认输入，Agent 自动化使用 `auth set --stdin`。写入只使用 canonical `FROWANG_API_KEY`，清除凭据文件中的新旧 Frowang 别名，并保留 Zotero、注释和未知项。
- 理由：stdin 避免 secret 进入 `paper-agent` 进程参数；原子替换和统一存储减少手工编辑 dotenv 的损坏风险。用户把 Key 发入对话本身仍属于其选择的信任边界。
- 影响：CLI、JSON、异常和状态永不返回 Key；`auth delete` 无法修改外部环境变量；执行适配器不能独立传递 stdin 时必须回退到用户终端隐藏输入。

### DEC-020：CLI 按终端能力自适应输出（2026-07-12）

- 背景：默认单行 JSON 适合 Skill、Agent 和脚本解析，但人类直接执行安装与状态命令时很难快速判断各平台结果；原 `--human` 仅缩进 JSON，也没有真正改善信息层级。
- 决策：stdout 为交互终端时默认输出人类可读摘要；非交互、管道、重定向和显式 `--json` 保持稳定 JSON envelope。`--human` 用于显式强制文本模式。
- 理由：TTY 检测能在不要求用户记参数的情况下改善直接使用体验，同时让 Agent 和自动化继续消费结构化合同。
- 影响：先为 `skills install/update/uninstall/status` 提供专用摘要；其他命令可渐进增加 renderer。JSON schema、错误码和非交互回归测试继续作为兼容合同。

### DEC-021：放宽 Agent 代配 Key 的措辞，Skill 主动邀请用户在对话中提供 Key（2026-09-07）

- 背景：DEC-019 把 Agent 代配限制为"仅独立 stdin 通道"并禁止 Key 进入命令参数/日志，实际使用中过于严格，多数 Agent 执行工具无法区分该通道，用户体验受阻。
- 决策：Skill 与 setup 编排统一改为邀请用户直接把 Frowang Key 发给 Agent，Agent 经 `auth set --stdin` 写入；只保留面向用户的提醒（Key 权限高、勿泄露给他人、配置后不复述）。本决策取代 DEC-019 中"仅限独立 stdin 通道、否则回退隐藏输入"的部分；DEC-019 的原子写入、统一存储和脱敏输出部分继续有效。
- 理由：用户把 Key 发入对话本来就是其选择的信任边界（DEC-019 已承认）；机械约束不能改变这一点，只会迫使 Agent 走向更差的变通。
- 影响：`skills/` 三个生产 Skill、`paper-agent-setup` 的安全边界与故障排查、CONVENTIONS 凭据节约同步更新；setup 契约测试断言改为新措辞。

### DEC-022：Runtime 更新检查采用缓存式提醒，升级由 Agent 在新进程执行（2026-09-07）

- 背景：用户希望达到 Kimi Code/Codex 式的更新体验——Skill 被使用时发现远端新版并提醒，确认后升级再重跑原命令。
- 决策：`UpdateCheckService` 查询 PyPI JSON API，结果缓存 24h（`cache_dir/update_check.json`，原子写入），3s 短超时，失败静默降级，`PAPER_AGENT_DISABLE_UPDATE_CHECK=1` 可关闭；CLI 暴露 `paper-agent update check [--refresh]`，`doctor` 输出带 `update` 检查。升级动作不内置到 CLI，由 Skill 编排 Agent 执行 `uv tool install paper-agent-skills --upgrade` 加 `paper-agent skills update --platform all`。
- 理由：uv tool 环境在 Windows 上存在运行中文件锁，运行中的 CLI 自替换不可靠；Agent 另起进程执行升级既避开锁，也复用现有 skills update 机制刷新已装 Skill 副本。缓存式检查避免每次命令都付出网络延迟。
- 影响：`update check` 永不因网络失败返回非零；`doctor --no-remote` 跳过更新检查（保持无网络语义）；三个生产 Skill 前置检查段处理 `update_available` 提醒。

### DEC-023：Skill 分发架构演进方向——Plugin 为分发单位，Skill 保持独立入口（2026-09-07）

- 背景：计划新增 paper-writing、citation-audit、idea-generation 等 skill，担心平铺进用户根目录难管理；曾设想"单个 hub skill 路由到 wheel 安装目录"。
- 决策：否决 mega hub 主架构；分发单位演进为 Plugin（plugin-build 能力转正），skill 保持独立 discovery 入口；规模化到几十个 skill 且 trigger eval 显示下降时，再聚合为 3-5 个 domain gateway + 目录内 references 渐进加载。宏观计划见 `docs/skill-distribution-roadmap.md`，调研依据见 `docs/gpt调研.md`。
- 理由：description 是每个功能最有价值的触发入口；Plugin 天然是"一个安装入口、多个 skill"；hub 方案会自建 discovery 层与宿主平台演化冲突，且跨沙箱/云端不可靠。
- 影响：新 skill 一律薄壳（代码进 runtime，manifest 白名单兜底）；citation-audit 等意图清晰的能力保留独立 skill；近期需处理 Codex user skill 路径向 `$HOME/.agents/skills` 迁移的兼容。
