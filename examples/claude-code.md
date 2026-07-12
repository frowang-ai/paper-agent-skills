# Claude Code 安装 Paper Agent Skills

Paper Agent Runtime 与 Skills 分开安装。API Key、配置和同步状态均位于统一用户目录，不要
在 `~/.claude/skills/` 中创建 `.env`。

## 1. 安装 Runtime 并配置

```powershell
uv tool install .
paper-agent config init
paper-agent auth status
paper-agent doctor --no-remote
```

将 `FROWANG_API_KEY=pk_xxx` 写入 `config init` 返回的用户级 `credentials.env`，然后运行
`paper-agent doctor` 验证远程认证。

## 2. Standalone 安装

用户级安装到 `~/.claude/skills`：

```powershell
paper-agent skills list
paper-agent skills install --platform claude
paper-agent skills status --platform claude
```

项目级安装到 `<project>/.claude/skills`：

```powershell
paper-agent skills install --platform claude --scope project --project-root F:\research\my-project
```

也可以只操作指定 Skill：

```powershell
paper-agent skills install --platform claude zotero-upload
paper-agent skills diff --platform claude zotero-upload
paper-agent skills update --platform claude zotero-upload
paper-agent skills uninstall --platform claude zotero-upload
```

更新和卸载只管理安装记录中的文件，并保留用户新增文件。受管文件被修改或目标目录来源不明
时默认返回 `CONFLICT`；只有明确接受覆盖后才使用 `--force`。

## 3. Plugin 分发

```powershell
paper-agent skills plugin-build ./dist/paper-agent-plugin
claude plugin validate ./dist/paper-agent-plugin
```

将验证后的 bundle 交给 Claude Plugin marketplace/安装系统。Paper Agent 不直接读写
`~/.claude/plugins/cache`。同一 scope 下 Plugin 与 standalone 是互斥安装方式，不能同时
暴露同名 Skill。

Claude Code 发现 Skill 后会读取 `SKILL.md`，并调用 PATH 上的 `paper-agent`，不依赖仓库
源码路径或 Skill-local Python wrapper。
