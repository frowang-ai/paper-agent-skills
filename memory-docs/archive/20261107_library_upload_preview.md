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

`upload-many` 和 `upload-dir` 现在遵循同一规则：

```bash
# 默认就是本地预览；--dry-run 是显式写法
paper-agent library upload-dir ./pdfs --dry-run

# 用户确认同一份清单后才真正上传
paper-agent library upload-dir ./pdfs --yes
```

- 不带 `--yes`：只预览，不需要 API Key，不发网络请求，不创建 Paper、Task 或 OCR 消费。
- `--yes`：按相同路径执行原批量上传逻辑。
- `--yes` 与 `--dry-run` 同时使用：返回 `USAGE_ERROR`。
- `upload-dir` 仍只处理目录当前层 PDF，不递归子目录。
- 预览逐项返回 `pending/skipped`，汇总 `would_upload/skipped`，并带
  `dry_run=true`、`confirmation_required=true`。
- 正式响应带 `dry_run=false`、`confirmation_required=false`；`would_upload` 表示实际尝试
  上传的合法 PDF 数，原有 `uploaded/duplicate/skipped/errors` 保留。

核心实现：

- `src/paper_agent/services/library_service.py`：`LibraryService.preview_many()` 纯本地分类；
  `upload_many()` 保留原上传流程并补充执行阶段字段。
- `src/paper_agent/cli.py`：两个批量命令共享确认分支，只有 `--yes` 才构造远程服务并写库。
- `skills/paper-library/SKILL.md`：强制“预览 → 展示清单和数量 → 用户明确同意 → `--yes`”。
- `docs/API_SURFACE.md`、`skills/paper-library/references/api-endpoints.md`、CHANGELOG、
  CONVENTIONS、PROGRESS 与 DEC-024 同步记录合同。

## 验证

新增 `tests/test_library_upload_preview.py` 5 项：

1. Service 预览正确区分 PDF、非 PDF 和缺失文件，Client 零调用。
2. `upload-dir` 默认预览不需要凭据，正文与图件都列入清单，非 PDF 和子目录不进入。
3. `upload-many` 默认预览不需要凭据，保持用户给出的文件顺序。
4. `upload-dir --yes` 通过本地 HTTP Server 验证只上传预览中的 PDF，并返回真实执行字段。
5. `--dry-run --yes` 返回 `USAGE_ERROR`。

测试驱动证据：实现前新增测试为 **4 failed / 1 passed**，失败点分别为缺少
`preview_many`、批量命令仍要求凭据以及不识别 `--yes`；实现后目标测试 **5 passed**。

完整检查：

- `PYTHONUTF8=1 uv run --frozen --extra dev pytest -q`：**192 passed**。
- `uv run --frozen --extra dev ruff check src tests`：通过。
- `uv build`：wheel 与 sdist 构建通过。
- 首次不带 `PYTHONUTF8=1` 的全量测试为 191 passed / 1 failed；失败是既有 Windows GBK
  子进程帮助文本解码问题，与本次上传逻辑无关，随后按项目既有 UTF-8 口径全量通过。

## 发布边界与回退

- 本次改动位于独立 worktree `_worktrees/paper-upload-preview` 和任务分支
  `feat/library-upload-preview`；不代表 PyPI 已发布、用户已安装或生产用户已更新 Skill。
- 安装版只有在后续发布 Runtime 并刷新已安装 Skill 后才获得新行为；不能将本地测试通过
  描述成线上误传风险已经消除。
- 批量命令旧的直接上传调用需要有意识地改为预览后加 `--yes`，这是为防止积分消耗和误传
  而作出的行为变更；单篇上传、目录非递归语义及服务端 `/papers` API 均未改变。
- MCP 的上传工具不在本次改动范围内。
- 如需回退，还原上述 CLI、Service 和 Skill 合同即可；本次没有数据库迁移、远程状态变更
  或用户文件迁移。
