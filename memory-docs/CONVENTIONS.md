---
layer: framework
update_mode: patch
role: "必须遵守的工程、接口、路径、数据和安全约定"
read_when: "修改代码、Skill、配置、同步或存储实现之前"
not_for: "决策理由、当前状态、完整运行手册或一次性偏好"
---

# Conventions

## 仓库与模块边界

- `skills/` 是所有 Skill 的唯一权威源码；Codex、Claude Code、zip、wheel 和 Plugin 内的副本只能机械生成。
- `skills/manifest.json` 是正式发布 inventory 和文件 allowlist；未列出的诊断代码、下载、凭据和兼容脚本不得进入 wheel Skill resources、standalone 或 Plugin。
- `skills/paper-library/` 是远程论文库生产 Skill。
- `skills/zotero-upload/` 是 Zotero 上传生产 Skill。
- `skills/demo-zotero-connection/` 仅用于探索、诊断和人工验证，生产代码不得依赖它。
- `src/paper_agent/clients/frowang.py` 是 Frowang HTTP 的唯一权威实现；`packages/paper_api_client/` 只保留旧 import 兼容。
- `src/paper_agent/clients/zotero.py` 是 Zotero 连接和附件发现的唯一权威实现；Skill scripts 只允许兼容 re-export/wrapper。
- Skill 负责触发和工作流编排，不承载认证、HTTP Client 或核心业务实现。
- CLI、未来 MCP 适配器和测试必须调用同一应用服务，不复制业务逻辑。

## 路径与文件

- Python 路径使用 `pathlib.Path`；代码资源路径基于 `__file__` 或 `importlib.resources`。
- 用户配置路径通过 `platformdirs` 解析，不硬编码 Windows/Linux 用户目录。
- 项目工作区必须通过显式 `--workspace PATH` 传入并 `resolve()`，不依赖进程 cwd 或裸相对路径。
- 写文件前校验目标位于预期配置、数据或工作区根目录内，防止路径穿越。
- 网络下载、manifest 和配置迁移使用临时文件加原子替换，失败不能留下半成品。

## 命名与结构

- Python 包、函数、变量使用 `snake_case`；类使用 `PascalCase`；Skill 和 CLI 命令使用 kebab-case。
- Frowang canonical `paper_id` 是全局缓存身份；`P-xxx` short ID 只用于用户交互和项目友好目录名。
- 新工作区论文目录使用 `year-author-short-title--short-id-v1`；目录名是展示层，身份和路径映射以 manifest 为准。
- `workspace sync` 不因 metadata 变化自动改目录名；重命名必须经过显式 plan/apply，并在 manifest 失败时恢复。
- 工作区论文内部资产文件名固定为 `metadata.json`、`full.md`、`layout.json`，不得把标题编码进文件名。
- 全局缓存路径必须先按 active profile 隔离，并在 cache hit 时核对 manifest 的 base URL；不得跨 profile 复用同 ID 资产。
- 服务器 `task_id` 或等价产物版本标识作为 artifact revision，不能用标题充当版本或主键。
- 面向 Agent 的稳定命令统一以 `paper-agent` 为入口，不在正式 Skill 中暴露内部 Python 文件路径。
- 测试可使用 `_test_*.py` 或 `test_*.py`，优先为新增行为先写最小测试或诊断脚本。

## 配置与凭据

- 非敏感配置进入用户级 `config.toml`；敏感值不得写入该文件或项目工作区。
- MVP 可使用用户级 `credentials.env`；长期首选系统 Keyring，并保留环境变量用于 CI/服务器。
- 优先级固定为：显式 CLI 参数 > 环境变量 > 用户配置/凭据存储 > 内置默认值。
- 旧 Skill `.env` 仅作为迁移兼容来源，成功迁移后不继续作为权威配置。
- Zotero local/remote 模式必须由 profile 显式选择；local 失败不得静默 fallback 到 remote。
- 日志、错误、`doctor` 和 JSON 输出必须脱敏，不得显示完整 Key、JWT 或私有文件内容。
- 初始化或升级配置只能创建缺失字段和执行 schema migration，不能覆盖用户已有凭据。
- Skill 引导用户直接把 Frowang Key 发给 Agent 代为配置，写入经 `paper-agent auth set --stdin`；
  用户希望自己输入时也可用 `auth set` 终端隐藏输入。提醒用户 Key 权限高、勿泄露给他人；
  配置完成后输出不复述完整 Key。
- `auth delete` 只管理用户级 `credentials.env` 中的 Frowang 新旧别名，不得声称能够删除当前
  shell、CI 或宿主平台注入的环境变量。

## CLI 与错误协议

- 非交互调用、管道、重定向与显式 `--json` 向 stdout 输出单个合法 JSON 文档；日志和诊断写 stderr。
- 失败必须返回非零 exit code，并包含稳定错误码；不得只打印一句自然语言后返回 0。
- 交互终端默认输出人类可读摘要；`--human` 可显式强制，`--json` 必须始终覆盖终端检测并
  保持机器合同。没有专用摘要渲染器的命令可暂时输出缩进 JSON。
- `fulltext`、`summary`、`deep` 等长内容命令必须显式 `--save`，stdout 只返回路径、bytes 和标识信息。
- 稳定错误码至少覆盖 `AUTH_MISSING`、`AUTH_INVALID`、`NOT_FOUND`、`NOT_READY`、`NETWORK_ERROR`、`CONFIG_INVALID`、`LOCAL_IO_ERROR`、`WORKSPACE_INVALID` 和 `CONFLICT`。
- CLI 参数和响应合同变更必须有测试，并同步 Skill references 和 API surface 文档。

## 同步与数据安全

- 区分 Skill 安装同步、配置初始化/迁移、服务器资产同步、工作区物化，不能用一个无边界的同步模块处理全部职责。
- Plugin/Skill 安装目录视为只读和可替换，不保存用户状态。
- Plugin 安装由 Codex/Claude marketplace 管理；业务代码不得直接读写平台私有 Plugin cache。
- 同一平台和 scope 下，standalone 与 Plugin 不应同时暴露同名 Skill。
- Markdown、JSON、PDF 和图片保存在文件系统；SQLite 只保存索引、状态、hash 和引用关系。
- Zotero item 和 Collection 的远程映射写用户级 `state.sqlite3`；不得在 Skill 目录新建 `sync_state.json`。
- 工作区同步只管理 manifest 声明的资产文件，不能覆盖或删除用户/Agent 自建笔记。
- 项目文件与缓存 hash 不一致时报告冲突；除非显式 `--force`，不得静默覆盖。
- 普通复制是默认工作区物化方式；硬链接和符号链接不能作为跨平台默认方案。
- 缓存清理必须显式执行；不得因为工作区移除而自动删除仍可能被其他项目引用的资产。
- 不自动下载整个线上论文库，只同步用户明确选择的论文或 Collection。

## 搜索与阅读

- 服务器默认论文发现使用 L1 元数据和 L2 属性树。
- 新论文不自动建立 L3 全文索引；不得把 L3 命中作为新论文的稳定业务保证。
- 项目正文检索第一阶段使用本地 `rg`；在证据证明必要前不建设本地 FTS5。
- `full.md` 是正文权威文本资产；`layout.json` 用于版式、页码或选区映射。

## 构建、测试与发布

- 核心运行时只维护 Python 实现；在有明确需求前不并行维护 NPM 版本。
- MVP 运行时基线为 Python 3.13+；在产品进入兼容性阶段前不维护旧 Python 分支和 backport 依赖。
- 包管理和工具安装优先 `uv`；发布应包含 wheel、sdist 和可审计源码链接。
- Skill、Python package 和 Plugin 尽量使用同一 release tag，并提供运行时兼容检查。
- QA 测试必须使用临时用户目录和临时工作区，不能污染真实配置、缓存或 Skill 目录。
- 发布包必须排除 `.env`、Key、JWT、用户论文、缓存、日志、测试输出和 `__pycache__`。
- 通用安装入口使用独立公开 GitHub Bootstrap Skill 和固定 Prompt；Bootstrap 仓库只承载安装、
  认证、doctor 与 smoke-test 编排，不复制 Runtime 业务实现。
- Runtime 更新检查必须缓存（默认 24h）、短超时、失败静默降级，可用
  `PAPER_AGENT_DISABLE_UPDATE_CHECK=1` 关闭；升级由 Agent 在新进程执行
  `uv tool install --upgrade` 加 `skills update`，CLI 不做运行中自替换。

## memory-docs 维护

- 框架层保持精简；详细实现放 `design/`，模块状态放 `detail_mem/PROGRESS.md`。
- 形成架构选择时追加 `detail_mem/DECISIONS.md`；被取代时新增决策并引用旧 ID。
- 新增能力只在 `detail_mem/MAP.md` 留 1-2 个入口指针。
- 代码和文档冲突时以代码与测试为准，并修正文档。
