# Zotero 连接排查指南

## 常见错误

### 错误 1: Zotero 桌面端未运行

```
❌ Zotero 桌面端未运行

原因：无法连接到 127.0.0.1:23119（Zotero 本地 API 端口）
```

**原因：** Zotero 桌面客户端没有打开，本地 API 端口 23119 无响应。

**修复：**
1. 打开 Zotero 桌面客户端
2. 等待客户端完全启动（几秒钟）
3. 重新运行脚本

---

### 错误 2: Zotero 已运行，但本地 API 未启用

```
❌ Zotero 已运行，但本地 API 未启用或异常

端口 23119 可连通，但 API 响应异常：...
```

**原因：** Zotero 打开了，但没有开启「允许其他应用与 Zotero 通信」选项。

**修复：**

1. 打开 Zotero 桌面客户端
2. 菜单栏 → **编辑(Edit)** → **设置(Settings/Preferences)**
   - Windows/Linux: `编辑` → `设置`
   - macOS: `Zotero` → `Preferences`
3. 切换到 **「高级(Advanced)」** 选项卡
4. 选择 **「杂项(Miscellaneous)」** 子选项卡
5. 勾选 **「允许此计算机上的其他应用程序与 Zotero 通讯」**
   - 英文: `Allow other applications on this computer to communicate with Zotero`
6. 重启 Zotero

**设置路径（Zotero 7）：**
```
设置(Settings)
  └── 高级(Advanced)
       └── 杂项(Miscellaneous)
            └── ☑ 允许此计算机上的其他应用程序与 Zotero 通讯
```

---

### 错误 3: 连接成功但找不到 PDF 文件

```
❌ 未找到 PDF
```

**可能原因：**

1. **PDF 未下载到本地** — Zotero 只有元数据，PDF 存在云端但未同步到本地
   - 打开 Zotero → 找到该论文 → 双击附件 → 触发下载
   
2. **Storage 目录路径不对** — 脚本通过 `prefs.js` 自动发现，但可能定位失败
   - 检查 Zotero 设置 → 高级 → 文件和文件夹 → 数据存储位置
   - 默认路径: `C:\Users\{用户名}\Zotero`
   - 自定义路径: 需确保 `storage/` 子目录存在

3. **坚果云 WebDAV 同步** — 如果用坚果云同步附件，文件可能以 `.zip` 形式存在
   - 本地 storage 目录可能为空
   - 需要先在 Zotero 中打开论文触发解压

---

### 错误 4: Remote API 认证失败

```
❌ 403 Forbidden / 401 Unauthorized
```

**原因：** Zotero Web API Key 无效或过期。

**修复：**
1. 登录 https://www.zotero.org/settings/keys
2. 检查 API Key 是否存在且未过期
3. 确认 Key 有读取权限（至少需要 `library:read`）
4. 更新 Paper Agent 用户级 `credentials.env` 中的 `ZOTERO_API_KEY`

---

### 错误 5: Collection 里没有论文

```
论文数量: 0
```

**可能原因：**
1. Collection key 指错了 — 用 `paper-agent zotero collections` 确认正确的 key
2. 论文在子 collection 里 — 需要递归获取子 collection 的 items
3. Collection 确实是空的

---

## 诊断命令

手动测试 Zotero 本地 API 是否正常：

```bash
# 测试端口是否通
curl http://127.0.0.1:23119/connector/ping
# 正常返回: <html><body>Zotero is running</body></html>

# 测试 API 是否可用
curl http://127.0.0.1:23119/users/0/collections?format=json&limit=5
# 正常返回: JSON 数组
```

Paper Agent 诊断：

```bash
paper-agent doctor --no-remote
paper-agent zotero collections
```

## 环境要求

| 项目 | 要求 |
|---|---|
| Zotero 版本 | ≥ 6.0（推荐 7.x） |
| 本地 API | 必须在设置中启用 |
| Python 包 | 随 `paper-agent` runtime 安装 `pyzotero` |
| Storage 目录 | `prefs.js` 中的 `dataDir` + `/storage/` |
