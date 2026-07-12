# Command Contracts

## Global Artifact Store

```bash
paper-agent paper pull P-3a
```

返回 canonical `paper_id`、`short_id`、`revision`、`revision_root`、manifest 路径、逐资产 hash
和 `cache_hit`。text profile 固定包含 metadata、fulltext 和 layout；任一 required asset 未就绪
返回 `NOT_READY`，校验失败返回 `INTEGRITY_ERROR`。

## Workspace

```text
workspace init PROJECT_ROOT
workspace add PROJECT_ROOT PAPER_IDS...
workspace list PROJECT_ROOT
workspace status PROJECT_ROOT
workspace sync PROJECT_ROOT [PAPER_IDS...]
workspace remove PROJECT_ROOT PAPER_IDS... [--force]
workspace names plan PROJECT_ROOT [PAPER_IDS...]
workspace names apply PROJECT_ROOT [PAPER_IDS...]
```

- `init` 幂等；已有非受管且非空 `papers/` 时返回 `CONFLICT`。
- `add` 返回 `added`、`skipped` 和 manifest。
- `add` 使用 `year-author-short-title--short-id-v1` 生成可读目录，并把 protocol/revision 写入 manifest。
- `status/list` 为每篇论文返回 `ok`、`missing` 或 `modified`，以及具体差异文件。
- `sync` 返回 `updated` 与 `unchanged`；每次成功更新后立即原子写 manifest。
- `remove` 返回 `removed` 和 `preserved_user_files`。
- `names plan` 只报告 `current/proposed/status/reason`；`names apply` 原子重命名整个目录，
  manifest 失败时恢复旧名称，目标冲突时拒绝接管。

## Error handling

| code | action |
|---|---|
| `AUTH_MISSING` / `AUTH_INVALID` | 停止远程操作，修复统一凭据 |
| `NOT_READY` | OCR/layout 尚未完成，稍后重试 |
| `WORKSPACE_INVALID` | 核对项目根和 manifest，不新建替代目录掩盖问题 |
| `CONFLICT` | 报告 modified/missing 路径，等待用户决策 |
| `INTEGRITY_ERROR` | 不物化该 revision，保留已有工作区文件 |
| `NETWORK_ERROR` | 保留已提交缓存，有限重试远程同步 |
