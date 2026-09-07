---
layer: detail
update_mode: rewrite
role: "模块级实现完成度、入口、验证和剩余缺口"
read_when: "判断某项能力是否已经可用，或接续实现下一阶段时"
not_for: "长期架构理由、代码目录导航或项目历史"
---

# Implementation Progress

## 已实现的 Runtime

### Phase 1：基础合同

- 状态：完成。
- 能力：Python 3.13+ package、`paper-agent` entry point、platformdirs 路径、TOML 配置、统一
  credentials、JSON envelope v1、错误码/exit code、capabilities 和 doctor。
- 入口：`src/paper_agent/config/`、`src/paper_agent/protocol/`、`src/paper_agent/cli.py`。
- 后续：旧 Skill-local `.env` 的交互迁移和 OS Keyring 尚未实现。
- 输出：交互终端自动使用人类格式，非交互/管道/Agent 与显式 `--json` 保持 envelope v1；
  `skills install/update/uninstall/status` 已有专用摘要渲染。

### Phase 2：远程论文库

- 状态：完成。
- 能力：Frowang HTTP/错误映射、GET 重试、安全资产下载、LibraryService、完整 `library`
  命令组和薄 `paper-library` Skill。
- 入口：`src/paper_agent/clients/frowang.py`、`services/library_service.py`。
- 搜索口径：默认 L1+L2 discovery；新论文不自动建立 L3。

### Phase 3：Zotero 导入

- 状态：完成。
- 能力：local/remote Zotero、附件发现、item 去重、Collection 映射、dry-run、SQLite 状态与
  旧 `sync_state.json` 幂等迁移。
- 入口：`src/paper_agent/clients/zotero.py`、`services/zotero_import_service.py`、
  `storage/state_store.py`。

### Phase 4：Skill 安装器

- 状态：完成。
- 能力：Codex/Claude user/project target、`list/install/status/diff/update/uninstall`、
  `--platform all`、逐文件 SHA-256、整批冲突预检、staging/backup/replace 和状态失败恢复。
- 数据：`skill_installations` 位于用户 data `state.sqlite3`，记录 platform、scope、mode、
  target、package version、source hash 和逐文件 hash。
- 保护：未知已有目录默认拒绝接管；managed file 修改返回 `CONFLICT`；`--force` 才覆盖；
  用户新增文件在 update/uninstall 中保留。
- 入口：`src/paper_agent/skills/`、`services/skill_install_service.py`、
  `storage/state_store.py`、`src/paper_agent/cli.py`。

### Phase 4：Canonical Skills 与 Plugin

- 状态：完成。
- inventory：`skills/manifest.json` 发布 `paper-library`、`paper-workspace` 与 `zotero-upload` 的 allowlist 文件。
- Agent UI：三个生产 Skill 均分发 `agents/openai.yaml`，提供显示名、短描述和显式
  `$skill-name` 默认 Prompt。
- wheel：canonical Skills 安装到 `<sys.prefix>/share/paper-agent/skills`，运行时可自动发现。
- Plugin：一个 bundle 同时生成 `.codex-plugin/plugin.json`、`.claude-plugin/plugin.json` 和
  带 hash 的 `paper-agent-plugin-manifest.json`。
- 边界：平台 marketplace 负责 Plugin 安装；Paper Agent 不直接修改平台私有 cache。
- 入口：`src/paper_agent/skills/source.py`、`plugins/bundle.py`、`scripts/build_plugin.py`。

### Phase 5：Global Artifact Store

- 状态：text profile 完成。
- 能力：`paper pull`、canonical paper/task revision 目录、metadata/full/layout required assets、
  committed manifest、bytes/SHA-256 校验、cache hit、staging 原子提交和 per-paper lock。
- 数据：SQLite schema v2 增加 artifact_papers、artifact_revisions 和 artifacts。
- 入口：`src/paper_agent/services/artifact_sync_service.py`。
- 后续：图片/PDF complete profile、公开 cache list/verify/gc 和远程 checksum/ETag。

### Phase 7：论文 Metadata 与 Attribute Tree

- 状态：完成。
- 能力：`GET /papers/{id}/metadata` 与 `/papers/{id}/attribute-tree` 两个新端点的 client
  方法（`get_paper_metadata`/`get_paper_attribute_tree`）、LibraryService 解包、
  `library metadata`/`library attribute-tree` CLI（默认 envelope 输出，`--save` 原子写
  JSON 文件），NOT_FOUND/NOT_READY 走现有错误映射。
- 同步：`artifact_sync_service.sync()` 的 `metadata.json` 改写 metadata 端点的学术元数据
  （paper_id/revision/title 等控制字段仍取自 show 响应）；`attribute_tree_url` 存在时
  下载 `attribute_tree.json` 并登记 manifest（`required: false`），缺失或为 null 时跳过；
  已缓存旧 revision 与旧格式 metadata.json 不迁移。
- 入口：`src/paper_agent/clients/frowang.py`、`services/library_service.py`、
  `services/artifact_sync_service.py`、`cli.py`。
- 测试：`tests/_test_phase7_metadata_tree.py`（client 路由/错误映射、CLI envelope 与
  --save、sync 新 metadata.json 与可选 attribute_tree 条目）。

### Phase 8：论文截图

- 状态：完成。
- 能力：`POST /papers/{id}/screenshots`（query: capture_pdf/capture_html/force_rescreenshot）
  与 `GET /papers/{id}/screenshots`（可选 job_id）的 client 方法与 LibraryService 解包；
  `library screenshots ID [--job-id J]` 查询已有截图（绝对 URL）或 job 进度，
  `--generate [--no-pdf] [--no-html] [--force]` 异步触发并返回 job_id，
  `--wait [--timeout 秒]`（默认 300s）按 2.5s 间隔轮询至 completed/failed 终态，
  超时返回 REMOTE_ERROR；`--no-pdf`+`--no-html` 本地直接 USAGE_ERROR（对齐服务端 422）。
  截图 URL 为绝对地址，不提供本地下载（用现有 `download-asset`）。
- 入口：`src/paper_agent/clients/frowang.py`、`services/library_service.py`、`cli.py`。
- 测试：`tests/_test_phase8_screenshots.py`（POST query 拼装、GET 带/不带 job_id、
  --generate 不轮询、--wait 轮询到完成与超时、双 no 本地报错、NOT_FOUND/TASK_NOT_FOUND 映射）。

### Phase 9：Runtime 更新检查

- 状态：完成（0.9.2）。
- 能力：`UpdateCheckService` 查询 PyPI JSON API 并与当前版本比较；结果缓存 24h
  （`cache_dir/update_check.json`，原子写入），网络失败静默降级为陈旧缓存或 `unknown`，
  `PAPER_AGENT_DISABLE_UPDATE_CHECK=1` 可关闭。CLI 新增 `paper-agent update check [--refresh]`；
  `doctor` 增加 `update` 检查（`--no-remote` 时为 not_run）。升级动作由 Agent 在新进程执行
  `uv tool install paper-agent-skills --upgrade` + `skills update`，CLI 不做运行中自替换。
- 入口：`src/paper_agent/services/update_service.py`、`cli.py` 的 `update` 命令组。
- 测试：`tests/_test_update_service.py`（14 项：版本比较、缓存 TTL、refresh、断网降级、
  env 关闭、CLI envelope、doctor 接线）。

### Phase 5：Project Workspace

- 状态：完成 MVP。
- 能力：init/add/list/status/sync/remove、项目 manifest、普通复制、staging/backup/replace、
  modified/missing 冲突检测和用户文件保留。
- 命名：新论文按 `year-author-short-title--short-id-v1` 物化；`names plan/apply` 显式迁移旧
  `P-xxx/` 或 metadata 变化后的名称，保留用户文件并支持 manifest 失败回滚。
- 数据：SQLite 增加 workspaces 与 workspace_papers；项目成员权威仍是可移植 manifest。
- 入口：`src/paper_agent/services/workspace_service.py`、`skills/paper-workspace/SKILL.md`。
- 后续：revision pin、完整离线 add/sync、workspace doctor 和真实部署服务器 QA。

## 兼容与构建入口

- `scripts/sync_skills.py`：旧 Claude user 同步命令的兼容 wrapper，现委托给安全 installer。
- `scripts/build_skill_zip.py`：从 canonical `SkillSource` snapshot 构建薄 Skill zip。
- `0.8.1` 已删除 Skill 内旧 CLI wrapper 与旧 `.env.example`；生产 Skill 只保留编排、引用和
  Agent UI 元数据，统一调用 PATH 上的 `paper-agent`。
- `skills/demo-zotero-connection/`：只用于探索/诊断，不进入正式分发。

## 测试与验证

- Phase 1-5、7-8、目录命名、凭据管理与 Skill UI 元数据共 114 项离线测试通过，覆盖配置、协议、Client、Service、StateStore、installer、Plugin、artifact、workspace 和 CLI。测试总数因删除 3 条已退役 Skill wrapper 测试、增加 1 条生产 Skill 元数据合同测试而调整。
- Phase 4 测试入口：`tests/_test_phase4_targets_source.py`、`_test_phase4_installer.py`、
  `_test_phase4_plugin.py`、`_test_phase4_cli.py`。
- Phase 5 测试入口：`tests/_test_phase5_artifact_sync.py`、`_test_phase5_workspace.py`、
  `_test_phase5_cli.py`；后者覆盖本地 HTTP remote -> global -> project E2E。
- 目录命名协议：`tests/_test_phase6_workspace_naming.py`；workspace 测试同时覆盖旧目录迁移、
  metadata 更新不自动改名和原子回滚。
- Python 3.13 wheel 已验证 canonical Skill discovery、config init、standalone install/status 与
  Plugin build。
- 生成的 Plugin 已通过 Codex `validate_plugin.py` 和 `claude plugin validate`。

## 尚未实现

### Phase 6 体验增强

- 图片/PDF complete profile、页码定位、结构化日志、OS Keyring、缓存 GC 和可选 FTS5。
- Runtime 已增加 `auth set/status/delete`：隐藏式交互、`--stdin`、dotenv 保留式原子更新、
  新旧 Frowang 别名清除和无 secret JSON 合同。
- 独立 Bootstrap Skill 已在同级 `../paper-agent-setup/` 建立，包含固定安装 Prompt、跨平台
  uv/PyPI 安装、认证、Codex/Claude standalone 编排和故障排查；5 项合同测试与 Skill
  validator 通过。公开 GitHub 推送和干净 Windows/macOS/Linux Agent 安装 E2E 尚未完成。

## 已知技术债

- 旧 `.env`、示例和兼容 wrapper 等迁移遗留文件暂时保留，待用户确认后清理。
- PyPI 网络偶发 TLS EOF；本地测试使用项目 `.venv` 的 `uv run --no-sync`，发布构建需在
  网络稳定时再执行标准 `uv build`。
- `docs/API_SURFACE.md` 中 MCP 侧缺口属于相邻 MCP 仓库，不能在本项目中假装已解决。

## 推荐实施顺序

1. 在 QA automation 用部署服务器验证真实 paper pull/workspace add/sync。
2. 明确服务端图片清单与 PDF 认证下载合同，再实现 complete profile。
3. 增加 cache list/verify/gc 和 workspace doctor。
4. 基于 layout.json 实现原文命中到页码/版面位置的查询助手。
