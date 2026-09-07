# Paper Agent Skills 分发机制深度调研

**调研时间：2026-09-07。**

先把核心结论放在最前面：

> **我不建议把 Paper Agent 的长期主架构做成“一个可见 hub Skill → Read wheel 里的隐藏 SKILL.md”。**
>
> 对你们现在这个产品，最好的折中反而是：**继续保留多个“小而薄”的原生 Skill，让它们各自承担 discoverability；但把“分发单元”从 N 个散落目录升级成 1 个 Plugin。**
>
> 如果以后 Skill 真发展到几十个，再进一步做成 **3–5 个 domain gateway Skill + gateway 内部 `references/*.md` 按需加载**。这个方案正好符合 Agent Skills progressive disclosure 的原生设计。

换句话说，我会把两个概念拆开：

**Skill = capability / discovery unit；Plugin = distribution unit。**

你现在真正不喜欢的是“安装后根目录里铺了一排东西”，这是**分发/文件系统组织问题**；但你设想用 hub 解决它，会顺手把最有价值的 **N 个 description 触发入口**也一起删掉。这个代价有点大。

---

# 1. 先理解现在 Agent Skills 到底是怎么工作的

Agent Skills 的标准本身已经明确规定了三层 progressive disclosure：

1. 启动时加载所有 Skill 的 `name + description`
2. 判断 Skill 相关后加载完整 `SKILL.md`
3. `references/`、`scripts/`、`assets/` 等资源按需加载

标准甚至给出的量级是：metadata 大约 ~100 tokens，完整 SKILL 推荐 <5000 tokens；并明确建议引用 Skill 内文件时使用 **相对于 skill root 的相对路径**。([Agent Skills][1])

所以你现在担忧的一点需要稍微修正：

**装 20 个 Skill ≠ 启动时塞进 20 个 SKILL.md。**

通常塞进去的是类似：

```text
paper-library
Search, upload, download, organize papers...

citation-audit
Audit manuscript citations against original papers...

paper-writing
Draft and revise academic writing using reference papers...
```

而不是所有 workflow 正文。

这也是为什么我认为“不应该为了少几个目录，把所有 discoverability 都收缩进一个 hub”。

[Agent Skills Specification](https://agentskills.io/specification)

---

# 2. 五个平台目前具体怎么做

| 平台                     | 启动/常驻的 Skill 信息                                                                                                                                                         | 正文加载                                                          | 外部目录 / symlink                                                                                                                                    | Plugin / 打包能力                                                                                               | 对你 proposed wheel-hub 的评价            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| **Claude Code**        | 默认 description 在 context；所有 Skill name 始终保留。整个 listing 预算约 **模型 context 的 1%**，超出后优先缩短低频 Skill description；`description + when_to_use` 单 Skill 上限 1536 字符。([Claude][2]) | invoke 时才加载完整 Skill                                           | 普通 personal/project Skill **可以 symlink 到磁盘其他目录**。但 Plugin 中 component **禁止逃出 plugin root**，外部 symlink 会被拒绝/跳过。([Claude][2])                       | 很成熟；一个 Plugin 可包含多个 Skills、agents、hooks、MCP、bin 等。([Claude][3])                                             | **本机可跑，但不适合作为产品契约**                  |
| **OpenAI Codex**       | `name + description + path` 初始可见；Skill list 最多占 **2% context**，context 未知时最多 **8000 chars**。超出先缩 description，再多可能直接省略部分 Skill 并告警。([ChatGPT Learn][4])                  | 决定使用后加载完整 `SKILL.md`                                          | 官方支持 symlinked skill folder；但 Codex filesystem permissions 可以配置成 workspace-only，明确可以禁止读取 workspace 外文件。([ChatGPT Learn][4])                       | 官方目前明确推荐：可复用、多 Skill / connector 能力使用 **Plugin**；`.codex-plugin/plugin.json + skills/`。([ChatGPT Learn][5]) | **本机权限宽松时可跑；sandbox/cloud 下脆弱**      |
| **Cursor**             | 自动发现 Skill，description 用来判断 relevance；正文/资源 progressive load。没有找到官方公开的精确 metadata token budget。([Cursor][6])                                                            | relevant 时加载                                                  | 支持 `.agents/skills`、`.cursor/skills`，还兼容 Claude/Codex skill dirs；递归扫描 nested Skills。Cloud Agent 只同步 `~/.cursor/skills`，其他本机目录不会自动过去。([Cursor][6]) | 已明确支持开放的 **Agent Plugins** 标准 + Cursor Plugins。([Cursor][7])                                                | **local 尚可；Cloud Agent 明显不可靠**       |
| **Kimi Code CLI**      | `description + whenToUse` 用于自动选择                                                                                                                                        | 按需加载                                                          | 一个非常适合你们的特性是官方 `extra_skill_dirs`：可以直接注册额外 Skill 根目录。([Kimi][8])                                                                                  | 有自己的 Plugin；skills 路径必须在 plugin root 内，symlink resolve 后也不能逃出。([Kimi][9])                                   | **没必要造 hub，直接 extra_skill_dirs 更原生** |
| **GitHub Copilot CLI** | prompt 与 description 做匹配                                                                                                                                                | 选中 Skill 后把完整 `SKILL.md` inject 到 context。([GitHub Docs][10]) | 支持 `~/.agents/skills`、`~/.copilot/skills`；还有 `/skills add DIRECTORY` / `COPILOT_SKILLS_DIRS` 可注册任意 skill source。([GitHub Docs][10])               | Plugin 很成熟，并且已经可通过 `$schema` opt-in 到 **Agent Plugins / Open Plugin Spec**。([GitHub Docs][11])              | **同样没必要 hub**                        |

一个对你们安装器很重要的小变化：

**OpenAI 当前官方文档列出的 Codex user-level Skill 根目录已经是 `$HOME/.agents/skills`。**([ChatGPT Learn][4])

所以你们现在硬编码的：

```text
~/.codex/skills/
```

最好不要再作为唯一目标。至少应该做版本/平台探测；更进一步，如果采用 Plugin 分发，就根本不用自己承担这么多路径兼容逻辑。

---

# 3. “SKILL.md 能不能引用 skill 目录之外的文件？”

这里要区分三个完全不同的问题。

### A. Agent Skills 标准允许什么？

标准定义的 portable 写法是：

```text
my-skill/
├── SKILL.md
└── references/
    ├── xxx.md
    └── yyy.md
```

然后：

```markdown
Read `references/xxx.md` when ...
```

官方明确说 **use relative paths from the skill root**，而且建议 reference chain 不要太深。([Agent Skills][1])

所以：

```markdown
Read C:\Users\foo\.venv\...\paper-agent\citation-audit\SKILL.md
```

或者：

```markdown
Read /Users/foo/.local/share/uv/tools/.../SKILL.md
```

**不是 Agent Skills 标准定义的 portable reference mechanism。**

它只是“给 Agent 下了一条普通的文件读取指令”。

这两者差别很大。

---

### B. Agent 本身能不能 Read 那个绝对路径？

本机 unrestricted environment 下：**经常可以。**

例如 Claude Code 普通 Skill 本身甚至允许整个 Skill 目录 symlink 到磁盘其他位置。([Claude][2])

Codex 普通 local session 很多情况下也能读取 workspace 之外的 readable file。

但这件事受：

* filesystem permission
* sandbox
* container
* remote agent
* cloud agent
* enterprise policy

共同影响。

Codex 官方现在甚至给出了一个 `workspace-only` permissions profile：默认 deny 整个磁盘，仅 workspace 和 minimal system paths 可读。这样的环境里，你的 wheel 安装目录就可能根本读不到。([ChatGPT Learn][12])

---

### C. Plugin 能不能声明“我的 Skill 在 plugin 外面”？

这个答案就更明确了：

**通常不行，而且生态正在主动禁止这种做法。**

Claude Code Plugin：

> component path resolve 到 plugin root 外部会被拒绝；外部 marketplace 的 symlink 也会为安全原因跳过。([Claude][3])

Kimi Plugin：

> all paths must remain within plugin root after symbolic link resolution. ([Kimi][9])

新的 Agent Plugins 标准更直接规定：

> plugin package 提供的文件在 filesystem resolution 后 MUST remain within plugin root；symlink 不允许逃逸。([Agent Plugins][13])

这其实告诉我们整个生态的方向：

**plugin package 应该是 self-contained 的。**

但这完全不妨碍 Skill 里面执行：

```bash
paper-agent search ...
```

因为 executable 是 runtime dependency，不是 plugin component。

恰好非常适合你们。

---

# 4. 生态里有没有“Hub / Router Skill”先例？

有，但仔细看以后，会发现主流先例和你设想的版本有一个关键区别：

> **他们更多是“一个 Skill 内部 progressive disclosure”，而不是“一个可见 Skill 隐藏几十个原生 Skill”。**

几个特别值得你们参考的项目如下。

### 1. Anthropic 官方 `claude-api` Skill —— 最像你们需要的 router

这是我认为最重要的先例。

它只有一个大的 `claude-api` Skill，但内部先判断语言：

* Python → `python/`
* TypeScript → `typescript/`
* Java → `java/`
* Go → `go/`
* …

然后再根据任务读特定 reference。([GitHub][14])

它的 Reading Guide 更明确：

> `{lang}/...`、`shared/...` 等路径都相对于 **这个 Skill 的 base directory**；正文并没有预加载这些内容，需要时再 Read。([GitHub][14])

[Anthropic claude-api Skill](https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md)

这个和你们最接近，但 Anthropic 做的是：

```text
claude-api/
├── SKILL.md             ← native Skill / selector
├── python/
├── typescript/
└── shared/
```

而不是：

```text
hub/SKILL.md
        ↓
/random/python/wheel/path/another-native-SKILL.md
```

---

### 2. Anthropic 官方 `skill-creator` —— 直接推荐 selector + references

Anthropic 自己给 Skill 作者的设计建议已经把这个模式画出来了：

```text
cloud-deploy/
├── SKILL.md        # workflow + selection
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

并明确说：

**Claude only reads the relevant reference file.**([GitHub][15])

[Anthropic skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)

这基本就是你们未来做 domain hub 时应该抄的范式。

---

### 3. `obra/superpowers` —— Meta Skill / bootstrap router，但有很值得警惕的副作用

Superpowers 有一个 `using-superpowers` Skill，它的职责几乎就是：

> 开始做事情之前，先检查是否应该调用其他 skill；哪怕只有 1% 可能相关，也先 invoke。([GitHub][16])

[obra/superpowers — using-superpowers](https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md)

但是有个关键点：

**Superpowers 并没有通过一个 hub 把其他 Skill 从 native registry 里藏掉。**

其他 Skill 本身仍然是原生可 discover 的 Skill；`using-superpowers` 更像一层“强制检查 Skill registry”的 policy/bootstrap。

而这个项目恰好暴露了 hub/bootstrap 的典型毛病。

2026 年有人专门提 issue：`using-superpowers` 每个 Claude session 自动 inject 大约 **5.4 KB / 1300 tokens**，哪怕根本用不上 Superpowers，认为应该压缩成 100–200 token 的 trigger。([GitHub][17])

另外还有：

* 不同 Agent host 的 Skill discovery path 不完全一致导致遗漏。([GitHub][18])
* subagent 可能看不到 main session 注入的 bootstrap context。([GitHub][19])
* 有用户直接要求换成 native Codex Plugin，因为安装、toggle、update 更方便且 token overhead 更低。([GitHub][20])

这里的经验非常有价值：

> **自己在 host 的 Skill discovery 之上再造一套 discovery layer，长期很容易和 host 演化打架。**

---

### 4. Vercel `skills` / skills.sh —— “canonical store + native registration”

Vercel 的 skill installer 很有意思。

它不是用一个 hub，而是把 Skill 放到 canonical location，然后给不同 Agent 创建 symlink；默认甚至把 **Symlink** 作为 recommended 模式。([GitHub][21])

[vercel-labs/skills](https://github.com/vercel-labs/skills)

这证明生态更倾向于：

```text
canonical skill store
        ↓
native Agent registry
```

而不是：

```text
one native hub
        ↓
private registry
```

但 symlink 跨平台并不完美。Vercel 项目已经有人报告 Windows/git compatibility、update 把 copy 重新变成 symlink、agent directory 不存在导致 link silently skipped 等问题。([GitHub][22])

这也是为什么我不建议你们把 symlink 当唯一生产级方案。

---

### 5. Docker Dynamic MCP —— 真正的“工具级 Hub”

Docker 的 Dynamic MCP 是非常纯粹的 hub：

Gateway 初始只暴露一小组：

```text
mcp-find
mcp-add
mcp-config-set
mcp-remove
mcp-exec
```

Agent 需要某个 MCP server 时先 `mcp-find`，再动态 `mcp-add`。([Docker Documentation][23])

[Docker Dynamic MCP](https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/)

这是很好的 precedent，但注意：

**它解决的是 tool explosion，而不是 workflow discovery。**

这正是 MCP 和 Skills 的边界。

---

# 5. 为什么你现在提出的 hub 会损失 discoverability

假设现在是：

```text
paper-library
paper-workspace
zotero-upload
paper-writing
citation-audit
idea-generation
```

用户说：

> 帮我检查一下论文里的引用到底有没有被原论文支持。

Native Skills 模式下，Agent 一开始就看到：

```text
citation-audit:
Audit citations and claims in manuscripts against original papers...
```

这几乎直接命中。

但如果只有：

```text
paper-agent:
Paper Agent workflows for working with papers...
```

那么 inference 变成两阶段：

```text
用户请求
   ↓
这是不是 Paper Agent 的事？
   ↓
调用 paper-agent hub
   ↓
hub 再判断 citation-audit
   ↓
Read citation-audit instructions
```

也就是：

$$
P(\text{最终正确路由})
=
P(\text{hub 被触发})
\times
P(\text{hub 内路由正确}\mid\text{hub 已触发})
$$

这不是说 hub 一定差，而是**额外多了一道 recall gate**。

如果第一层没想到 Paper Agent，后面的路由表写得再完美也没有用。

Claude 官方 troubleshooting 甚至直接告诉 Skill 作者：

> Skill 不触发时，检查 description 是否包含用户自然会说的关键词。([Claude][2])

Agent Skills 标准也明确要求 description 包含 specific keywords，帮助 Agent 找到相关任务。([Agent Skills][1])

所以你实际上是在拿：

**6 个独立 semantic retrieval entries**

换成：

**1 个 overloaded semantic retrieval entry。**

---

# 6. 那把所有关键词塞进 hub description 呢？

**有效，但只能部分补救。**

例如可以写成：

```yaml
description: >
  Paper Agent workflows for research papers and academic writing:
  search, upload, download, organize and cite papers; manage Frowang
  libraries, collections and project workspaces; import from Zotero;
  retrieve APA/BibTeX metadata; draft manuscripts; audit citations
  and claims against original sources; and generate research ideas.
  Use whenever the user asks about papers, literature, references,
  citations, bibliography, Zotero, Frowang, manuscripts, academic
  writing, citation verification, or literature-based idea generation.
```

这会比：

```yaml
description: Work with Paper Agent.
```

好太多。

但存在三个问题。

第一，Agent Skills 标准 `description` 最大 **1024 characters**。([Agent Skills][1])

第二，能力越多，description 越像一个“anything research”大类，precision 会下降；你为了 recall 加关键词，又会增加 false positive。

第三，独立 Skill 可以表达很精细的边界：

```text
citation-audit:
Use when checking whether manuscript citations,
claims, quotations or references are actually supported
by original papers.
```

这种信号比 mega-description 里的一个 `"citation audit"` phrase 强得多。

所以：

> **关键词枚举是 hub 的补救措施，不是替代 native capability descriptions 的等价方案。**

---

# 7. 还有一个隐蔽问题：Read 一个 SKILL.md ≠ invoke 一个 Skill

这个很关键。

假设 hub 执行：

```text
Read /.../citation-audit/SKILL.md
```

模型当然能读懂里面的 Markdown，然后照做。

所以“功能上能不能工作”：

**能。**

但是 host 并不会因此自动认为：

> `citation-audit` Skill 已经被 native invoked。

这意味着 child 的很多 host semantics 会丢失。

Claude Code 的 native Skill invocation 有明确 lifecycle：description 先在 context，invoke 后完整 Skill 才进入 context；`disable-model-invocation`、`allowed-tools` 等也属于 Skill invocation 机制。([Claude][2])

Copilot 也是“Copilot chooses a skill → SKILL.md is injected into agent context”。([GitHub Docs][10])

而：

```text
Read foo/SKILL.md
```

只是普通文件读取。

因此 hidden child：

* 不出现在 `/skills`
* 用户不能 native `/citation-audit`
* host 不知道它是一个 independently activated Skill
* Skill-level permissions / lifecycle 语义不能假设被重新应用
* analytics / disable / override / precedence 也无法天然按 child Skill 管理
* Plugin namespace 也不存在

所以我甚至建议：

**如果一个文件已经不准备让 host 当 Skill 注册，就不要再叫 `SKILL.md`。**

叫：

```text
references/citation-audit.md
```

语义反而更诚实、更符合标准。

---

# 8. 各种方案横向比较

评分里 ★★★★★ 越好。

| 方案                                       |                      隐式可发现性 |                    上下文成本 |      安装/升级 | 跨平台一致性 | Claude | Codex  | Cursor | Kimi | Copilot | 判断                                                            |
| ---------------------------------------- | --------------------------: | -----------------------: | ---------: | -----: | ------ | ------ | ------ | ---- | ------- | ------------------------------------------------------------- |
| **多个独立 native thin Skills**              |                       ★★★★★ |                    ★★★★☆ | ★★☆☆☆（裸复制） |  ★★★★★ | ✅      | ✅      | ✅      | ✅    | ✅       | Discovery 最佳；分发方式需要升级                                         |
| **一个 mega hub → wheel 外部 SKILL.md**      |                       ★★☆☆☆ |                    ★★★★★ |      ★★★★☆ |  ★★☆☆☆ | ⚠️     | ⚠️     | ⚠️     | ⚠️   | ⚠️      | **不建议作为主架构**                                                  |
| **3–5 个 domain gateway + `references/`** |                       ★★★★☆ |                    ★★★★★ |      ★★★★☆ |  ★★★★★ | ✅      | ✅      | ✅      | ✅    | ✅       | Skill 数很多以后非常好                                                |
| **一个 Plugin 包多个 native Skills**          |                       ★★★★★ |                    ★★★★☆ |      ★★★★★ |  ★★★★☆ | ✅      | ✅      | ✅      | ✅    | ✅       | **当前最推荐**                                                     |
| **MCP server 暴露 Paper Agent tools**      | ★★★☆☆ workflow / ★★★★★ tool |                    ★★★★☆ |      ★★★★☆ |  ★★★★☆ | ✅      | ✅      | ✅      | ✅    | ✅       | 很适合 atomic capabilities，不替代 workflow Skills                   |
| **slash commands**                       |                       ★☆☆☆☆ |                    ★★★★★ |      ★★★★☆ |  ★★★☆☆ | ✅      | ✅/平台语法 | ✅      | ✅    | ✅       | 非技术用户需要记命令，不适合主入口                                             |
| **subagents**                            |                       ★★☆☆☆ | ★★★★★（context isolation） |      ★★★☆☆ |  ★★☆☆☆ | ✅      | 平台相关   | ✅      | ✅    | ✅       | 是 execution primitive，不是 Skill catalog/distribution primitive |

其中 Plugin 的跨平台只给 ★★★★☆，是因为现在还没有真正做到：

```text
one manifest → every platform
```

新的 **Agent Plugins** 标准正在试图解决这个问题。它明确说不同 Agent 客户端已经发展出不同 plugin formats，因此它只定义 portable interoperability floor，安装、权限、分发、UX 仍由各 host 决定。([Agent Plugins][24])

Cursor 已经原生支持 Agent Plugins。([Cursor][7])

GitHub Copilot CLI 也可以通过 canonical `$schema` opt in 到 Agent Plugins/Open Plugin Spec v1.0.0。([GitHub Docs][11])

但是 Claude Code 目前仍有 `.claude-plugin/plugin.json`，OpenAI 有 `.codex-plugin/plugin.json`，Kimi 又有 `kimi.plugin.json`。

所以短期现实是：

> **Skill 内容高度 portable，Plugin manifest 仍需要 adapter。**

[Agent Plugins open standard](https://agent-plugins.org/)

---

# 9. 针对 Paper Agent，我推荐的架构 A：一个产品 Plugin + 多个 native thin Skills

这是我最推荐你们现在直接做的。

架构变成：

```text
Paper Agent Plugin
│
├── paper-library/
│   └── SKILL.md
│
├── paper-workspace/
│   └── SKILL.md
│
├── zotero-upload/
│   └── SKILL.md
│
├── paper-writing/
│   └── SKILL.md
│
├── citation-audit/
│   └── SKILL.md
│
└── idea-generation/
    └── SKILL.md
             │
             │ all thin
             ▼
       paper-agent CLI
             │
             ▼
    Python Runtime / API
```

Skill 仍然非常薄：

```text
description / trigger
↓
workflow
↓
paper-agent xxx ...
```

**业务逻辑继续 100% 留在 Python runtime。**

这是非常漂亮的分层：

```text
Agent platform
      │
      ▼
Skill
= semantic interface
= trigger
= workflow policy
      │
      ▼
paper-agent CLI
= stable execution interface
      │
      ▼
Python runtime
= actual business logic
```

而 Plugin 只负责：

```text
install
update
enable/disable
version
distribution
```

这正好解决你现在真正的问题。

---

## 分发仓库建议

不要让 wheel 的安装路径成为 Agent 必须知道的 implementation detail。

我会单独维护一个 canonical source：

```text
paper-agent-agent-plugin/
│
├── skills/
│   ├── paper-library/
│   │   └── SKILL.md
│   ├── paper-workspace/
│   │   └── SKILL.md
│   ├── zotero-upload/
│   │   └── SKILL.md
│   ├── paper-writing/
│   │   └── SKILL.md
│   ├── citation-audit/
│   │   └── SKILL.md
│   └── idea-generation/
│       └── SKILL.md
│
├── adapters/
│   ├── claude/
│   ├── codex/
│   └── kimi/
│
└── plugin.json      # Agent Plugins projection where supported
```

CI/release 时生成：

```text
dist/
├── claude/
│   ├── .claude-plugin/plugin.json
│   └── skills/...
│
├── codex/
│   ├── .codex-plugin/plugin.json
│   └── skills/...
│
├── agent-plugin/
│   ├── plugin.json
│   └── skills/...
│
└── kimi/
    ├── kimi.plugin.json
    └── skills/...
```

也就是说：

**一份 Skill source tree，多个 manifest projection。**

不要维护 N 份 SKILL.md。

---

# 10. 这其实还解决了“根目录里好多 Skill”的问题

这一点非常容易混淆：

你们现在看见：

```text
~/.claude/skills/paper-library/
~/.claude/skills/paper-workspace/
~/.claude/skills/zotero-upload/
...
```

感觉“不优雅”。

Plugin 后可以逻辑上变成：

```text
Paper Agent Plugin
    ├─ paper-library
    ├─ paper-workspace
    ├─ zotero-upload
    ├─ paper-writing
    ├─ citation-audit
    └─ idea-generation
```

物理上这些 Skill 仍然存在于 Plugin package 内，但用户不再需要你往 personal skill root 一个个扔。

Claude Code 的官方 plugin layout 本来就支持：

```text
plugin/
├── skills/
│   ├── code-reviewer/SKILL.md
│   └── pdf-processor/SKILL.md
├── agents/
├── hooks/
├── bin/
└── .mcp.json
```

([Claude][3])

OpenAI 目前也明确展示：

```text
plugin/
├── .codex-plugin/plugin.json
└── skills/
    └── ...
```

([ChatGPT Learn][5])

所以：

> **Plugin 天然就是“一个安装入口、多个 Skill”。**

这几乎就是你现在想通过 hub 达成的文件管理效果，只是不会牺牲 Skill-level discoverability。

---

# 11. 架构 B：等 Skill 真多起来，再做 Domain Gateway

如果以后 Paper Agent 从 6 个涨到：

```text
30
50
80
```

那么再做第二级压缩。

但我不会压成 **1 个 universal hub**，而会压成大约：

```text
paper-library
paper-workspace
paper-writing
paper-analysis
paper-research
```

例如：

```text
paper-writing/
├── SKILL.md
└── references/
    ├── drafting.md
    ├── revision.md
    ├── literature-synthesis.md
    ├── journal-style.md
    └── response-to-reviewers.md
```

然后：

```text
paper-research/
├── SKILL.md
└── references/
    ├── idea-generation.md
    ├── literature-gap.md
    ├── related-work.md
    └── hypothesis-development.md
```

其中特别强、用户意图特别清晰、价值又高的 workflow 仍然可以保留独立 native Skill。

比如我倾向于：

```text
citation-audit
```

继续独立。

因为：

> “检查这句话引用的文献到底支不支持”

是一个非常独立且自然语言 trigger 很清晰的 intent。

没有必要为了减少一个 metadata entry 把它藏到 `paper-writing` 里面。

---

# 12. 那 MCP 呢？我建议以后加，但不是拿它替换 Skills

你们的 Python runtime 已经是：

```text
paper-agent upload
paper-agent search
paper-agent download
paper-agent metadata
paper-agent collection ...
```

这其实天然可以再映射成：

```text
paper-agent MCP
├── search_papers
├── upload_paper
├── get_fulltext
├── get_metadata
├── add_to_collection
├── import_zotero
└── sync_workspace
```

这种东西 MCP 非常适合，因为它们是：

**typed atomic capabilities。**

但是像 `citation-audit` 是：

```text
检查 manuscript
↓
extract citations
↓
判断缺哪些论文
↓
指导下载
↓
必要时上传 Frowang
↓
逐个取原文
↓
claim ↔ source evidence
↓
输出 audit report
```

这是一个 **workflow / policy / reasoning procedure**。

这种东西 Skill 反而更自然。

所以长期非常漂亮的架构可能是：

```text
                   Paper Agent Plugin
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
        Native Skills             MCP Server
     workflow / routing         atomic typed tools
             │                       │
             └───────────┬───────────┘
                         ▼
                 Python Runtime
```

但你们现在已经有非常成熟的 CLI interface，所以**完全没必要为了减少 Skill 数立刻重构 MCP**。

MCP 是未来 capability interface 的增强，不是解决 Skill catalog 问题的创可贴。

---

# 13. 对你们 proposed wheel-hub 的最终判定

你原本设想：

```text
~/.claude/skills/paper-agent/SKILL.md

             ↓ route

<sys.prefix>/share/paper-agent/
    skills/citation-audit/SKILL.md
```

我的评分大概是：

**工程可行性：7/10**
**本机短期可用性：8/10**
**跨平台长期可靠性：4/10**
**Skill discoverability：5/10**
**生态原生程度：4/10**

最大的问题不是“Agent 不会 Read 文件”。

Agent 大概率会。

而是它把：

```text
Agent platform native discovery
```

变成：

```text
Agent platform discovery
        ↓
your own discovery
        ↓
generic filesystem read
```

你们由此接管了：

* routing
* path resolution
* version skew
* sandbox compatibility
* cloud compatibility
* trigger recall
* skill lifecycle semantics

但几乎没有获得足够大的收益。

---

# 14. 如果你们坚持保留 hub，至少别直接 expose `<sys.prefix>`

这里我会做一个非常具体的改造。

不要：

```text
Read <sys.prefix>/share/paper-agent/skills/citation-audit/SKILL.md
```

至少改成：

```bash
paper-agent skill show citation-audit
```

或者：

```bash
paper-agent skill path citation-audit
```

这样：

```text
Agent
  ↓
paper-agent skill show citation-audit
  ↓
Runtime 自己知道自己的资源在哪里
```

而不是让 Agent 猜 uv tool env。

因为 `uv tool install` 的 managed environment 路径本来就是安装实现细节；reinstall、Python version、OS、uv layout 都可能变化。

但我仍然只会把这种能力当：

* backwards compatibility
* debug command
* fallback
* internal development facility

而不是主 discovery architecture。

---

# 15. 我建议你们现在具体这么改

如果是我来定 Paper Agent 下一版架构，我会这样做：

### 第一阶段：现在

保留这 6 个 native Skills：

```text
paper-library
paper-workspace
zotero-upload
paper-writing
citation-audit
idea-generation
```

先不要合并。

原因是 6 个实在不多。

Agent Skills 标准本来就是专门为几十个小 capability progressive discovery 设计的。Claude 甚至保证列表里保留所有 skill names，只在 metadata budget 不够时压 description；Codex 也先缩 description，到极大规模才开始 omit。([Claude][2])

然后：

**废掉“runtime 复制 N 个目录”的生产分发方式，改成 Paper Agent Plugin。**

Runtime 依然：

```bash
uv tool install paper-agent-skills
```

Plugin 里面的 Skill 依然调用：

```bash
paper-agent ...
```

---

### 第二阶段：建立 Trigger Eval

这个反而比继续讨论“6 个还是 1 个”更重要。

给每一个 Skill 准备：

```text
should_trigger
should_not_trigger
ambiguous_neighbors
```

比如 `citation-audit`：

```text
✓ 帮我检查这篇稿子的reference引用对不对
✓ 这个 citation 真支持这句话吗
✓ audit every citation in this tex
✓ verify the claims against the original papers

× 帮我找关于minimum wage的论文
× 把这篇论文导入zotero
× 帮我润色introduction
```

然后真正跑：

$$
Recall,\ Precision,\ Confusion\ Matrix
$$

等你发现：

```text
20 Skills → trigger performance 开始下降
```

或者 Codex 开始 warning：

```text
skill listing truncated
```

或者 Claude `/skill-doctor` 明显显示 metadata 占用过大，

**再聚合。**

不要现在为了一个尚未出现的 metadata scaling problem，主动削弱 discoverability。

Anthropic 自己的 `skill-creator` 甚至已经包含 eval/description optimization 这一套思路。([GitHub][15])

---

# 16. 我认为你们最值得采用的最终结构

最终我会把 Paper Agent 想成三层：

```text
                         PAPER AGENT
                              │
               ┌──────────────┴──────────────┐
               │                             │
        Discovery / Workflow             Execution
               │                             │
          Agent Skills                 paper-agent CLI
               │                             │
      ┌────────┼────────┐                    │
      ▼        ▼        ▼                    │
  library   writing   citation ...           │
               │                             │
               └──────────────┬──────────────┘
                              ▼
                        Python Runtime
                              │
                              ▼
                     Frowang APIs / Local FS
```

外面再包：

```text
                   Paper Agent Plugin
                /         |          \
          Claude       Codex      Agent Plugins
                               (Cursor/Copilot)
```

这套架构里：

* **Plugin 解决安装和升级**
* **Skill 解决自然语言 discoverability**
* **references 解决 context scaling**
* **CLI 解决稳定业务接口**
* **Python Runtime 解决实现**
* **未来 MCP 解决 typed tool interoperability**

各层职责很干净。

---

# 最终推荐

**首选方案：Plugin + 多个 native thin Skills。**

这是目前在“根目录占用少”和“功能可发现性高”之间最好的折中。事实上它不是折中得各退一步，而是把两个问题拆开之后分别解决。

你们目前只有 6 个左右 Skill，我甚至认为**完全没有必要开始做 Skill 数量压缩**。

**第二选择：少量 Domain Gateway Skills + Skill-root 内 `references/*.md` progressive disclosure。**

当 Paper Agent 真的出现几十个细粒度 workflow，再把相邻能力聚合；严格按 Anthropic `claude-api` / `skill-creator` 的 selector + references 模式做。

而：

> **一个 mega `paper-agent` hub + 绝对路径读取 wheel 里的隐藏 `SKILL.md`**

我会保留为 fallback technique，而不会把它定成 Paper Agent 的正式架构。

另外还有一个你们现在就值得修的点：**Codex installer 不应继续只假定 `~/.codex/skills`；OpenAI 当前官方 user Skill 路径已经转向 `$HOME/.agents/skills`，并明确把可复用多 Skill 分发引向 Plugin。**([ChatGPT Learn][4])

### 主要官方资料

[Agent Skills Specification](https://agentskills.io/specification)
[OpenAI — Build Skills](https://learn.chatgpt.com/docs/build-skills)
[OpenAI — Build Plugins](https://learn.chatgpt.com/docs/build-plugins)
[Claude Code — Skills](https://code.claude.com/docs/en/skills)
[Claude Code — Plugins Reference](https://code.claude.com/docs/en/plugins-reference)
[Cursor — Agent Skills](https://prod.cursor.com/docs/skills?utm_source=chatgpt.com)
[Cursor — Plugins](https://prod.cursor.com/docs/plugins?utm_source=chatgpt.com)
[Kimi Code — Agent Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html)
[GitHub Copilot CLI — Agent Skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills?utm_source=chatgpt.com)
[Agent Plugins Standard](https://agent-plugins.org/)

**如果只让我给你们工程团队留一句设计原则，就是：不要为了减少 filesystem entries，牺牲 semantic entries。** Paper Agent 的 Skill 本来就是薄壳，description 恰恰是每个功能最有价值的那部分；真正应该被统一起来的是安装和版本管理，而这正是 Plugin 应该干的事。

这个生态最近几个月变化非常快。如果你愿意，我也可以按月监测 **Claude/Codex/Agent Plugins/Skills 规范**的变动，有涉及 Paper Agent 分发架构的变化再提醒你。

[1]: https://agentskills.io/specification "https://agentskills.io/specification"
[2]: https://code.claude.com/docs/en/skills "https://code.claude.com/docs/en/skills"
[3]: https://code.claude.com/docs/en/plugins-reference "https://code.claude.com/docs/en/plugins-reference"
[4]: https://learn.chatgpt.com/docs/build-skills "https://learn.chatgpt.com/docs/build-skills"
[5]: https://learn.chatgpt.com/ja-JP/docs/build-plugins "https://learn.chatgpt.com/ja-JP/docs/build-plugins"
[6]: https://prod.cursor.com/docs/skills "https://prod.cursor.com/docs/skills"
[7]: https://prod.cursor.com/docs/plugins "https://prod.cursor.com/docs/plugins"
[8]: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html "https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html"
[9]: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins "https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins"
[10]: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills"
[11]: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference "https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference"
[12]: https://learn.chatgpt.com/ja-JP/docs/permissions "https://learn.chatgpt.com/ja-JP/docs/permissions"
[13]: https://agent-plugins.org/specification "https://agent-plugins.org/specification"
[14]: https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md "https://github.com/anthropics/skills/blob/main/skills/claude-api/SKILL.md"
[15]: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md "https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md"
[16]: https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md "https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md"
[17]: https://github.com/obra/superpowers/issues/1456 "https://github.com/obra/superpowers/issues/1456"
[18]: https://github.com/obra/superpowers/issues/403 "https://github.com/obra/superpowers/issues/403"
[19]: https://github.com/obra/superpowers/issues/237 "https://github.com/obra/superpowers/issues/237"
[20]: https://github.com/obra/superpowers/issues/1139 "https://github.com/obra/superpowers/issues/1139"
[21]: https://github.com/vercel-labs/skills/blob/main/README.md "https://github.com/vercel-labs/skills/blob/main/README.md"
[22]: https://github.com/vercel-labs/skills/issues/1199 "https://github.com/vercel-labs/skills/issues/1199"
[23]: https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/ "https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/"
[24]: https://agent-plugins.org/ "https://agent-plugins.org/"
