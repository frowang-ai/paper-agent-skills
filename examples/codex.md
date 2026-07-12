# Codex 安装 Paper Agent Skills

Paper Agent Runtime 与 Skills 分开安装。凭据只写入统一用户配置目录，不要放进
`~/.codex/skills/` 或项目 Skill 目录。

## 1. 安装 Runtime 并配置

从源码仓库安装开发版本：

```powershell
uv tool install .
paper-agent config init
paper-agent auth status
paper-agent doctor --no-remote
```

`config init` 会创建用户级 `config.toml` 和 `credentials.env`。将
`FROWANG_API_KEY=pk_xxx` 写入命令返回的 credentials 路径，再运行 `paper-agent doctor`。

## 2. Standalone 安装

用户级安装到 `$CODEX_HOME/skills` 或 `~/.codex/skills`：

```powershell
paper-agent skills list
paper-agent skills install --platform codex
paper-agent skills status --platform codex
```

只安装一个 Skill：

```powershell
paper-agent skills install --platform codex paper-library
```

项目级安装必须显式指定项目根，目标为 `<project>/.agents/skills`：

```powershell
paper-agent skills install --platform codex --scope project --project-root F:\research\my-project
```

维护命令：

```powershell
paper-agent skills diff --platform codex
paper-agent skills update --platform codex
paper-agent skills uninstall --platform codex paper-library
```

受管文件被修改或目标目录来源不明时，命令默认返回 `CONFLICT`。确认要接管或覆盖后才使用
`--force`；用户新增的笔记文件不会被更新或卸载删除。

## 3. Plugin 分发

构建同时包含 Codex 与 Claude manifest 的干净 Plugin bundle：

```powershell
paper-agent skills plugin-build ./dist/paper-agent-plugin
```

构建产物交给 Codex marketplace/Plugin 安装系统管理。Paper Agent 不直接写
`~/.codex/plugins/cache`。同一 scope 不要同时启用 Plugin 和 standalone 副本，避免同一
Skill 被重复发现。

安装完成后，Codex 读取 `paper-library` 或 `zotero-upload` 的 `SKILL.md`，并通过 PATH 上的
`paper-agent` 调用统一 JSON CLI。
