---
layer: detail
update_mode: patch
role: "批量上传误传案例、预览确认协议、实现与验证留痕"
read_when: "回溯 2026-11-05 图件批量上传事件，或修改 upload-many/upload-dir、上传 Skill 指引"
not_for: "当前发布状态（-> STATUS）、稳定规则（-> CONVENTIONS 与 DEC-024）"
---

# 批量上传默认预览与明确确认（2026-11-07）

## 背景与证据

2026-11-05 的生产只读排查发现，一个外部 Agent 使用名为 `frowang-agent` 的 API Key，
在短时间内调用主库 `POST /api/v1/papers`，把 `main.pdf`、正文校对版、政策文件以及
`fig1_policy_timeline.pdf`、`图2_各阶段月均企业进入.pdf`、`08_rddid_*.pdf` 等图件
全部提交为独立论文。服务端同时只有 2 次浏览器 JWT 上传；213 次 API Key 请求包含去重
和重复请求，不能解释为 213 个不同文件。站内小 f 的完整引导是在批量上传之后开始的，
不是站内小 f 引导用户逐张上传图件。

服务端看不到用户本机的 Agent 会话和实际命令，因此不能断言用户执行的是 `upload-dir`
还是 `upload-many`，也不能断言用户明确同意了完整清单。已确认的旧行为是：

- `upload-dir` 收集目录当前层全部 PDF，不递归，但不区分正文与图件。
- `upload-many` 顺序上传传入的全部路径。
- `paper-library` Skill 只展示命令，没有批量上传前的预览、规模说明和用户确认步骤。
- 相对的，`zotero-upload` 已要求先 dry-run、报告数量并取得明确同意。

## 优化目标

1. “上传这篇论文”只上传明确指定的正文，单篇 `library upload` 保持立即执行。
2. 批量或目录上传必须在远程副作用之前展示完整清单，不能把图件意外当成独立论文。
3. 不只依赖 Skill 文案；CLI 默认行为也必须安全，防止不同 Agent 忽略编排指引。
4. 不按 `fig`、`图` 等文件名静默猜测和过滤，避免误伤合法论文；由用户确认或改选路径。

## 新协议

`upload-dir` 已移除，不新增发现命令。Coding Agent 使用自身文件工具发现候选，向用户展示
清单和建议，取得明确同意后传绝对路径：

```bash
# 可选预览；不带 --yes 时默认也是相同的本地预览
paper-agent library upload-many /absolute/path/a.pdf /absolute/path/b.pdf --dry-run

# 用户确认明确路径后正式上传
paper-agent library upload-many /absolute/path/a.pdf /absolute/path/b.pdf --yes
```

- 不带 `--yes`：只预览，不需要 API Key，不发网络请求，不创建 Paper、Task 或 OCR 消费。
- `--yes`：只上传明确路径；与 `--dry-run` 同时使用返回 `USAGE_ERROR`。
- 相对路径按 paper-agent 进程 cwd 解析，不是用户项目目录；Agent 必须传绝对路径。
- 预览逐项返回 `pending/skipped`，汇总 `would_upload/skipped`，并带
  `dry_run=true`、`confirmation_required=true` 和英文 `next_action`。
- 文件不存在时返回 `FILE_NOT_FOUND`，非 PDF 返回 `NOT_A_PDF`，同时给出输入路径、解析路径、
  cwd（缺失文件）和英文修正说明。全部无效时执行返回 `USAGE_ERROR` 且零远程调用；部分无效
  保留逐项结果，不能汇报成全部成功。
- 正式响应带 `dry_run=false`、`confirmation_required=false`；`would_upload` 表示实际尝试
  上传的合法 PDF 数，原有 `uploaded/duplicate/skipped/errors` 保留。

核心实现：

- `src/paper_agent/services/library_service.py`：共享逐项预览分类，批量执行复用相同路径与
  错误语义；`next_action` 和路径错误直接指导 Agent 修正。
- `src/paper_agent/cli.py`：仅保留 `upload/upload-many`，英文 help 明确发现职责、绝对路径、
  预览和确认边界，只有 `--yes` 才构造远程服务并写库。
- `skills/paper-library/SKILL.md`：只保留 Agent 自行发现、用户确认、绝对路径和结果检查规则，
  详细契约交给 CLI 自描述。
- `docs/API_SURFACE.md`、`skills/paper-library/references/api-endpoints.md`、CHANGELOG、
  CONVENTIONS、PROGRESS 与 DEC-024 同步记录合同。

## 验证

`tests/test_library_upload_preview.py` 当前为 **10 项**：

1. 预览分类及 `FILE_NOT_FOUND/NOT_A_PDF`、输入路径、解析路径、cwd 和 `next_action`。
2. `upload-many` 默认预览不需要凭据，保持用户给出的文件顺序。
3. 默认预览和显式 `--dry-run` 两个参数化场景均禁止配置管理器、远程服务及 HTTP Client 构造。
4. 先预览再执行 `upload-many --yes`，通过本地 HTTP Server 检查 multipart 实际文件名与预览
   完全一致，预览阶段服务器零请求。
5. `--dry-run --yes` 返回 `USAGE_ERROR`。
6. 全部文件无效时拒绝执行且 Client 零调用；部分无效时合法 PDF 上传、其余逐项标为 skipped。
7. 单篇缺失文件报错包含 cwd、输入路径、解析路径和绝对路径修正建议。
8. help 展示 Agent 契约，且 `upload-dir` 不再出现在命令列表。

测试驱动证据：首轮实现前新增测试为 **4 failed / 1 passed**，失败点分别为缺少
`preview_many`、批量命令仍要求凭据以及不识别 `--yes`；首轮实现后目标测试 5 passed，
独立审核加强证据后为 9 passed，收敛为明确路径和 Agent-native 错误后为 **10 passed**。

收敛后的完整检查：

- `PYTHONUTF8=1 uv run --frozen --extra dev pytest -q`：**197 passed**。
- `uv run --frozen --extra dev ruff check src tests`：通过。
- `uv build`：wheel 与 sdist 构建通过。
- 首轮不带 `PYTHONUTF8=1` 的全量测试为 191 passed / 1 failed；失败是既有 Windows GBK
  子进程帮助文本解码问题，与本次上传逻辑无关，随后按项目既有 UTF-8 口径全量通过。

## 独立审核与处置

- Paseo `evomap/gpt-6.1-sol`、xhigh 审核 `main...8b3b2b2`，结论为 **PASS WITH CHANGES**，
  未发现 P0/P1；审核代理为 `4a57212b-0080-48c8-bc7a-a747fac72727`，只读，未修改文件。
- 两条 P2 均接受：其一，目录在预览后可能新增 PDF，`upload-dir --yes` 重枚举使确认清单与
  执行清单不同；其二，首轮测试未充分证明整个 CLI 不读取配置/凭据，也未检查 multipart
  实际文件名。
- 处置：Skill 改为目录预览后推荐用已确认的明确路径执行 `upload-many --yes`，明确预览不
  锁定成员或内容，不引入快照机制；CLI 帮助说明目录会重枚举。新增 4 个禁止配置/远程构造
  的参数化测试，实际执行测试先预览并核对文件名，最终 196 项全量测试通过。
- 审核代理另执行 22 个内存检查，覆盖真实 Typer 参数解析、预览/确认分支、终端输出和参数
  冲突；其未重复全量测试。上述 196 项、Ruff 和构建由主 Agent 在修正后执行。
- 保留边界：`--yes` 只代表调用者声明已获确认，CLI 无法核实用户是否看过清单；单文件循环、
  直接 HTTP、MCP 和旧安装版仍可直接上传。预览只检查文件存在和扩展名，不验证 PDF 内容、
  服务器接受结果或实际积分消耗。

## PR 收敛：明确路径与 Agent-native 自描述

首轮审核修正后，用户进一步指出 `upload-dir` 的 Upload All 语义仍过于霸道，且现代 Coding
Agent 已能自行发现文件，不需要额外 discovery 命令。PR 因此移除 `upload-dir`，只保留明确
路径的 `upload/upload-many`。Agent 自行发现候选，用户确认，CLI 只执行确认后的绝对路径。

同时采用“help、工具输出、错误”三层自描述：英文 `--help` 说明职责和示例，预览 `next_action`
说明下一步，路径错误给出 `input_path/resolved_path/cwd` 和修正建议。Skill 不再重复长文契约。
全部无效时执行明确失败且零远程调用，部分无效保留逐项状态，避免 Agent 误报全部成功。

## 发布边界与回退

- 本次改动位于独立 worktree `_worktrees/paper-upload-preview` 和任务分支
  `feat/library-upload-preview`；不代表 PyPI 已发布、用户已安装或生产用户已更新 Skill。
- 安装版只有在后续发布 Runtime 并刷新已安装 Skill 后才获得新行为；不能将本地测试通过
  描述成线上误传风险已经消除。
- 旧 `upload-dir` 调用需迁移为 Agent 自行发现后传明确路径；`upload-many` 旧调用需要预览后
  加 `--yes`。这些是为防止积分消耗和误传而作出的行为变更；单篇上传及服务端 `/papers` API
  未改变。
- MCP 的上传工具不在本次改动范围内。
- 如需回退，还原上述 CLI、Service 和 Skill 合同即可；本次没有数据库迁移、远程状态变更
  或用户文件迁移。
