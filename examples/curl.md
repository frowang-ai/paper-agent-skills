# Paper API — curl 速查

Base URL: `https://frowang.com/paper-api/api/v1`
认证：论文端点用 `X-API-Key: pk_...`；API Key 管理端点用 JWT。

```bash
BASE="https://frowang.com/paper-api/api/v1"
KEY="$PAPER_API_KEY"
H="-H X-API-Key:$KEY"

# ── 论文 ──────────────────────────────────────────────
# 列出
curl -s $H "$BASE/papers?limit=20&offset=0"

# 论文发现（默认 L1 元数据 + L2 属性树）
curl -s $H "$BASE/papers/search?q=attention&limit=10"

# 高级分层检索（all 默认 L1+L2；L3 全文需显式指定）
curl -s $H "$BASE/papers/search/l1?q=IV&limit=20"
curl -s $H "$BASE/papers/search/all?q=IV&layers=L1,L3&limit=20"

# 详情 / 全文 / 摘要 / 深度报告
curl -s $H "$BASE/papers/$PID"
curl -s $H "$BASE/papers/$PID/fulltext"
curl -s $H "$BASE/papers/$PID/summary"
curl -s $H "$BASE/papers/$PID/deep"

# 产物 URL
curl -s $H "$BASE/papers/$PID/assets"

# 上传
curl -s $H -F "file=@paper.pdf" "$BASE/papers"

# 修改元数据
curl -s -X PATCH $H -H "Content-Type: application/json" \
  -d '{"title":"New Title","publication_year":"2025"}' \
  "$BASE/papers/$PID/metadata"

# 重新处理 / 删除
curl -s -X POST $H "$BASE/papers/$PID/reprocess"
curl -s -X DELETE $H "$BASE/papers/$PID"

# ── 标签 ──────────────────────────────────────────────
# 添加（增量，裸数组 body）
curl -s -X POST $H -H "Content-Type: application/json" \
  -d '["NLP","transformer"]' "$BASE/papers/$PID/tags"

# 全量覆盖
curl -s -X PUT $H -H "Content-Type: application/json" \
  -d '["finance","macro"]' "$BASE/papers/$PID/tags"

# 移除单个
curl -s -X DELETE $H "$BASE/papers/$PID/tags/old-tag"

# ── 笔记 ──────────────────────────────────────────────
# 列出
curl -s $H "$BASE/papers/$PID/notes"

# 添加 —— content 走 query param（不是 JSON body）
curl -s -X POST $H "$BASE/papers/$PID/notes?content=note+text"

# ── 文件夹 ────────────────────────────────────────────
curl -s $H "$BASE/collections"
curl -s -X POST $H -H "Content-Type: application/json" \
  -d '{"name":"NLP Papers"}' "$BASE/collections"
curl -s -X POST $H -H "Content-Type: application/json" \
  -d '{"task_ids":["tid1","tid2"]}' "$BASE/collections/$KEY/items"
curl -s $H "$BASE/collections/$KEY/items"

# ── API Key 管理（JWT only，通常在网站 UI 操作）──────
curl -s -X POST -H "Authorization: Bearer $JWT" "$BASE/api-keys?name=my-key"
curl -s -H "Authorization: Bearer $JWT" "$BASE/api-keys"
curl -s -X DELETE -H "Authorization: Bearer $JWT" "$BASE/api-keys/$KEY_ID"
```

## 注意

- `note add` 的 `content` 是 **query param**，不是 JSON body。
- 响应统一 `{"success": true, "data": {...}}`；错误 `{"detail": {"code","message"}}`。
- 全文可能 100KB+，建议管道存文件：`curl -s $H "$BASE/papers/$PID/fulltext" | jq -r .data.content > out.md`。
