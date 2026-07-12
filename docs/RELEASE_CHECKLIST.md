# Release Checklist

Python Runtime、canonical Skills、standalone installer 和双平台 Plugin 必须作为同一 release
验证。MVP 运行时基线为 Python 3.13+。

## Runtime

- [ ] `uv build` 成功生成 wheel 和 sdist。
- [ ] 全新 Python 3.13 venv 安装 wheel 成功，metadata 声明 `Requires-Python >=3.13`。
- [ ] wheel 能从 `<sys.prefix>/share/paper-agent/skills` 发现 canonical Skills。
- [ ] `paper-agent capabilities` 返回单个 JSON envelope。
- [ ] `paper-agent config init` 幂等，`doctor --no-remote` 不读取真实用户配置。
- [ ] `library`、`zotero` 和 `skills` 命令树与 Skills 文档一致。
- [ ] 未知命令返回 `USAGE_ERROR` 和 exit code 2。

## Client 与业务合同

- [ ] 401/403、404 NOT_FOUND、404 NOT_READY、409、5xx 和传输异常映射到公共错误码。
- [ ] 只有安全 GET 执行有限重试，上传不进行盲目重试。
- [ ] 默认 search 用于 L1+L2 discovery，新论文不依赖 L3。
- [ ] fulltext/summary/deep 要求 `--save`，stdout 不包含长内容。
- [ ] 静态资产下载拒绝外部 origin/path traversal，并校验 bytes/SHA-256。
- [ ] Zotero dry-run 不写同步状态；item 去重和 Collection 映射测试通过。
- [ ] `docs/API_SURFACE.md` 与后端路由、CLI、MCP 对齐。

## Canonical Skills 与 Installer

- [ ] `skills/manifest.json` 只列出计划发布的生产 Skills 和文件 allowlist。
- [ ] repo、wheel、standalone 和 Plugin 中每个 Skill 的 source hash 一致。
- [ ] user/project scope 在 Codex 和 Claude targets 上均通过安装测试。
- [ ] `--platform all`、status、diff、update、uninstall 合同通过。
- [ ] 未知已有目录默认拒绝接管；`--force` 行为显式且有测试。
- [ ] managed file 修改触发 `CONFLICT`，不会被普通 update/uninstall 覆盖或删除。
- [ ] 更新和卸载保留用户新增文件，状态写入失败可恢复原目录。
- [ ] zip/standalone 不含 `.env`、requirements、缓存、测试、诊断目录或用户论文。

## Artifact Store 与 Workspace

- [ ] `paper pull` 只在 metadata/full/layout 全部校验后提交 text revision。
- [ ] 同 revision cache hit 会重新校验 manifest、bytes 和 SHA-256。
- [ ] profile/paper/revision 路径拒绝 traversal，缓存身份同时校验 base URL。
- [ ] `workspace init` 幂等，且不接管非空未知 `papers/`。
- [ ] add/sync 使用普通复制和 staging/backup/replace，项目 manifest 原子写入。
- [ ] modified/missing managed asset 阻止默认 sync/remove。
- [ ] update/remove 保留 manifest 外用户文件，remove 不删除 Global Artifact Store。
- [ ] add 生成 `year-author-short-title--short-id-v1`，且目录不超过 120 字符。
- [ ] names plan 不写文件；names apply 保留用户文件、拒绝目标冲突并在 manifest 失败时恢复。
- [ ] sync 遇 metadata 变化不自动重命名目录，内部 managed asset 文件名保持固定。
- [ ] 本地 HTTP E2E 覆盖 remote -> global -> SQLite -> project 完整链路。

## Plugin Bundle

```powershell
paper-agent skills plugin-build ./dist/paper-agent-plugin
```

- [ ] bundle 同时包含合法的 `.codex-plugin/plugin.json` 和 `.claude-plugin/plugin.json`。
- [ ] Codex `validate_plugin.py` 与 `claude plugin validate` 均通过。
- [ ] bundle 只包含 manifest allowlist 文件，且不含 `.env`、API Key、JWT、PDF、下载目录、
      `demo-zotero-connection` 或 compatibility scripts。
- [ ] `paper-agent-plugin-manifest.json` 的逐 Skill hash 与 repo/wheel 一致。
- [ ] 文档声明 Plugin 与 standalone 互斥，且不直接读写平台私有 Plugin cache。

## 自动验证

```powershell
uv run --no-sync pytest -q
uv run --no-sync ruff check src tests packages skills/paper-library/scripts skills/zotero-upload/scripts scripts
uv lock --check
uv build
```

发布前还需在隔离的 Python 3.13 venv 中完成 wheel E2E：`config init`、通过测试 Key 验证
`auth set --stdin/status/delete` 且输出不含 Key、`skills list`、install/status 和
`plugin-build`。
