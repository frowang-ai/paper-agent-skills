---
name: paper-workspace
description: 建立和维护项目级本地论文工作区：把 Frowang 服务器论文同步到全局 revision 缓存，再物化为项目 papers/ 下可用 rg 搜索的 full.md、layout.json 和 metadata.json。用户说“把这些论文加入当前项目”“建立论文工作区”“同步项目论文”“在这些论文全文里查找证据”时触发。
---

# Paper Workspace

使用 `paper-agent workspace` 管理项目论文集合，并使用本地 `rg` 深读正文。服务器 Collection
是长期候选池，workspace 是当前项目的活跃工作集，两者不要混用。

## 前置检查

```bash
paper-agent config init
paper-agent auth status
paper-agent doctor
```

认证缺失时使用 `paper-agent auth set` 隐藏输入。若用户明确要求 Agent 配置已在对话中提供的
Key，只通过 stdin 调用 `paper-agent auth set --stdin`，不得把 Key 放进命令参数、输出或临时
文件；执行工具不能单独传递 stdin 时，改请用户在终端输入。

始终向 workspace 命令传入明确的项目根路径，不根据 Skill 安装目录或不确定的 cwd 猜测。

## 建立工作区

```bash
paper-agent workspace init /absolute/project/root
paper-agent workspace status /absolute/project/root
```

`init` 只创建 `<project>/papers/manifest.json`，不会下载整个远程论文库。

## 发现并加入论文

先通过 `paper-library` 工作流在服务器 L1/L2 中缩小候选范围，再加入用户确认的论文：

```bash
paper-agent library search "instrumental variables" --limit 10
paper-agent library show P-3a
paper-agent workspace add /absolute/project/root P-3a P-8f
```

`add` 自动把 text profile 同步到用户级 Global Artifact Store，再复制
`metadata.json`、`full.md` 和 `layout.json` 到项目。目录按 metadata 生成为
`年份-作者-短标题--P-xxx`，例如 `2024-Smith-et-al-Inflation-Dynamics--P-3a`。目录名只用于
浏览，论文身份以 manifest 的 canonical ID 为准。不要把远程库全部加入单个项目。

## 本地深读

先限制命中文件和数量，再读取上下文，避免把所有全文塞入 context：

```bash
rg -l "difference-in-differences" /absolute/project/root/papers/*/full.md
rg -n -C 5 "parallel trends" /absolute/project/root/papers/*/full.md
```

引用证据时记录论文 short ID、文件路径和行号。需要页码或版式时再读取同目录
`layout.json`。本地全文没有命中时再调整术语或正则，不要自动回退到服务端 L3。

## 状态和同步

```bash
paper-agent workspace list /absolute/project/root
paper-agent workspace status /absolute/project/root
paper-agent workspace sync /absolute/project/root
paper-agent workspace sync /absolute/project/root P-3a
```

`status` 是纯本地检查，不要求认证。`sync` 查询最新 remote revision；managed file 被本地
修改或缺失时返回 `CONFLICT`，不得自动覆盖。`notes.md`、`reading.md` 等 manifest 未声明
文件属于用户，更新时必须保留。

`sync` 不会因标题、年份或作者变化自动改目录名。检查或应用建议名称时使用：

```bash
paper-agent workspace names plan /absolute/project/root
paper-agent workspace names apply /absolute/project/root P-3a
```

始终先执行 `plan` 并展示 current/proposed/conflict。只有用户确认后才执行 `apply`；它会连同
用户笔记移动整个目录。目标目录已存在时停止，不使用 `--force` 接管。

## 移除论文

先展示 workspace status 并取得用户确认：

```bash
paper-agent workspace remove /absolute/project/root P-3a
```

移除只删除 hash 未变化的 managed assets，不删除 Global Artifact Store，也不删除用户新增
文件。只有用户明确接受丢弃 modified managed files 时才使用 `--force`。

完整命令返回和错误处理见 `references/command-contracts.md`。
