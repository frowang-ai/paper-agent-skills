---
layer: framework
update_mode: rewrite
role: "项目是什么：目标、边界、工作流和技术栈的一页概览"
read_when: "进入项目，或讨论整体架构、范围和技术选型时"
not_for: "当前进度、完整命令参数、全量 API 或单条决策理由"
---

# Project Overview

## 一句话定位

Paper Agent 是面向 Codex、Claude Code 等 Agent 客户端的论文研究基础设施：它用独立
Skills 表达工作流，用共享 Python 运行时执行 Frowang 论文库、Zotero 和本地论文工作区
操作，并让用户只配置一次凭据即可在多个研究项目中复用论文资产。

## 目标

- 将远程论文库管理、Zotero 上传和项目论文工作区拆成边界清晰的独立 Skill。
- 用统一的 `paper-agent` CLI、配置、认证、错误协议和应用服务消除 Skill 间重复代码。
- 支持 Codex 和 Claude Code 的 standalone Skill 与 Plugin 分发方式，同时保持一份 Skill 权威源码。
- 将服务器论文发现与本地全文深读分离，避免默认服务端全文索引和超长上下文。
- 建立用户级论文资产缓存，再把选中论文可靠地物化到具体研究项目的 `papers/` 工作区。
- 提供可诊断、可测试、可升级、不会静默覆盖用户数据的同步系统。

## 核心工作流

```text
服务器论文库
  -> L1 元数据 + L2 属性树发现候选论文
  -> 下载选中论文到用户级资产库
  -> 物化到研究项目 papers/ 工作区
  -> rg 定位 full.md 原文
  -> 按需结合 layout.json、图片和 PDF 深读
```

```text
Zotero 本地库
  -> 读取 collection、元数据和本地 PDF
  -> 上传 Frowang Paper API
  -> 记录可恢复的同步状态
```

```text
仓库 skills/ 权威源码
  -> standalone 安装同步或 Plugin 打包
  -> Codex / Claude Code 发现独立 Skills
  -> Skills 调用统一 paper-agent CLI
```

## 核心模块

| 模块 | 角色 | 当前入口或目标入口 |
|---|---|---|
| `paper-library` Skill | 管理远程论文库和服务器端论文发现 | `skills/paper-library/SKILL.md` |
| `zotero-upload` Skill | 从 Zotero 生产性上传论文 | `skills/zotero-upload/SKILL.md` |
| `paper-workspace` Skill | 管理项目级本地论文工作集 | `skills/paper-workspace/SKILL.md` |
| Frowang Client | 共享 HTTP、错误映射与资产下载 | `src/paper_agent/clients/frowang.py` |
| Zotero Import | 本地/Web API、附件发现和增量上传 | `src/paper_agent/clients/zotero.py`、`services/zotero_import_service.py` |
| 全局状态 | Zotero 映射、同步状态和 standalone 安装记录 | 用户 data `state.sqlite3` |
| 统一运行时 | 已承载配置、协议、论文库、Zotero 和 Skill 分发 | `src/paper_agent/` |
| Skill 安装器 | Codex/Claude user/project 安装、diff、更新和卸载 | `services/skill_install_service.py` |
| Plugin builder | 从 canonical allowlist 生成双平台 Plugin | `src/paper_agent/plugins/bundle.py` |
| 全局资产库 | 缓存 metadata/full/layout text revision | `services/artifact_sync_service.py` |
| 项目工作区 | 面向单个研究项目的可搜索论文集合 | `services/workspace_service.py`、`<project>/papers/` |

`skills/demo-zotero-connection/` 是探索和诊断代码，不是生产模块；生产 Zotero 能力位于
`skills/zotero-upload/`。

## 技术栈

- 语言和运行时：MVP 统一使用 Python 3.13+；目标分发方式为 Python package + `uv tool`。
- CLI：Typer；统一公共入口为 `paper-agent`。
- HTTP：httpx。
- 配置：`platformdirs` + TOML + 环境变量/用户级 `credentials.env`；后续接入 Keyring。
- 状态：SQLite 已保存 Zotero 与 Skill 安装状态；后续扩展论文 revision/workspace metadata。Markdown、JSON、PDF 和图片保存在文件系统。
- 测试：pytest；端到端 API 验证位于相邻 `qa-automation` 项目。
- 外部系统：Frowang Paper API、Zotero 本地 API、Codex、Claude Code。

## 边界

- 本项目不实现 Frowang 服务端业务逻辑；后端权威实现位于相邻 `llm_read_paper_ai_workflow`。
- 本项目不把完整 API 手册复制进 memory-docs；三端矩阵保留在 `docs/API_SURFACE.md`。
- 本地全文检索第一阶段直接使用 `rg`，不急于引入论文级 FTS5。
- Plugin 是安装和发现适配器，不是凭据或用户数据存储位置。

## 相关文档

- 当前状态：`memory-docs/STATUS.md`
- 项目演变：`memory-docs/HISTORY.md`
- 工程约定：`memory-docs/CONVENTIONS.md`
- 代码导航：`memory-docs/detail_mem/MAP.md`
- 模块完成度：`memory-docs/detail_mem/PROGRESS.md`
- 目标架构：`memory-docs/design/ARCHITECTURE.md`
- 同步和存储：`memory-docs/design/SYNC_AND_STORAGE.md`
