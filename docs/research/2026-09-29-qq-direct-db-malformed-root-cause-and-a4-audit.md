# QQ Direct DB 诊断结论（malformed + A4 未知联系人）

日期：2026-09-29
checkpoint：c739434 fix(qq): seal direct DB lifecycle and desktop shutdown
分支：spike/qq-direct-db-replacement（未提交 A3/A4 修改已保留）

---

## 一、malformed「database disk image is malformed」—— 根因已唯一证明

### 1. 证据（按 generation ID 对齐）

日志来源：
- Python：`Echo/logs/echo.log`（2026-09-29 14:16）
- Runtime：`runtime/qq/logs/qce-runtime.log`（2026-09-29 06:16 UTC）

**失败 generation（qce-runtime.log）：**

```
decrypt_source_before  database_bytes=833946624  wal_bytes=992952
decrypt_source_read    database_changed=true  wal_changed=true
                       database_before=833946624 → after=833999872
                       wal_before=992952 → after=1021792
                       read_bytes=833946624
decrypt_source_after   database_bytes=834114560  wal_bytes=1351392
```

Python 侧对应失败（echo.log）：

```
QQ Direct DB sqlite read failed operation=list_sessions table=group_msg_table stage=query
file_bytes=833945600  header_page_count=203600  size_page_aligned=true
wal_present=true wal_bytes=0  shm_present=true shm_bytes=32768  quick_check=failed
```

**成功 generation（对照）：**

```
decrypt_source_read    database_changed=false  wal_changed=false
                       read_bytes=834114560
```

### 2. 唯一根因

NapCat `decryptDatabase`（`napcat.mjs` 的 `LE` 函数）用 `Ge.readFileSync(t)` 读取源
`nt_msg.db` **主文件**，但：

1. QQ 进程活跃时，`nt_msg.db` 运行在 SQLite WAL 模式，`-wal` 里存有未 checkpoint 的
   已提交事务（失败现场 `wal_bytes=992952`，约 992KB）。
2. `readFileSync` **只读主文件、完全忽略 `-wal`**，得到「主库页已更新、但缺失 WAL
   尾部已提交事务」的中间态字节流。
3. 该字节流解密后写入 staging 的 `snapshot.db`，就是一个 `quick_check=failed` 的
   损坏镜像，Python 端读到即报 `database disk image is malformed`。

成功 case 恰好 read 窗口内无写入（`database_changed=false wal_changed=false`）。

**这不是 Echo Python 代码的 bug**，是 NapCat `decryptDatabase` 在活跃写入时读源库的
固有缺陷（`readFileSync` 无法捕获 WAL 一致性快照）。

### 3. 已实施的 TDD 最小修复（Echo seam 侧，不碰第三方 napcat.mjs）

在 Echo 自有的 `scripts/qq_direct_db_snapshot/snapshot.mjs`（`acquire`）中，解密后、
发布 generation 前，读取 `__ECHO_DIRECT_DB_READ_STATE__`（napcat patch 已记录 read
窗口前后源库状态），若 read 窗口内主库或 WAL 发生变化，则丢弃 staging 并返回新的
稳定错误码 `snapshot_unstable`，**绝不把损坏快照发布为 ready**。

修复文件：
- `scripts/qq_direct_db_snapshot/snapshot.mjs`（模板：新增 `SNAPSHOT_UNSTABLE` 错误码
  + `readWindowChanged` 辅助 + acquire 校验分支）
- `scripts/qq_runtime_pins.json`（`directDbSnapshot.templateSha256` 更新）
- `runtime/qq/plugins/napcat-plugin-qce/direct_db_research/snapshot.mjs`（bootstrap 产物，已同步）
- `tests/test_qq_direct_db_snapshot_runtime.py`（新增 RED 测试，原稳定窗口测试改
  `nativeReadChanged=False`）

效果：Python 端不再拿到损坏快照；遇到活跃写入时 `acquire` 返回 `snapshot_unstable`
→ Python 映射为 `QQSnapshotRuntimeFailure` → 用户重试即可（下一次 decrypt 大概率落在
安静窗口）。

---

## 二、A4 窄审计 —— 非好友群成员为何落到「未知联系人」

### 1. 链路（已查清）

```
QQDatabaseProvider.list_sessions / acquired_session
  → QQDirectDatabaseImportService._named_sessions
      → _metadata_names():  group_names = list_groups()   (群名)
                            friend_names = list_friends()  (仅好友名)
      → _attach_sender_names(payload, friend_names, self_uin)
          → 只把 friend_names 匹配到的 sender.uin 写入 record["sender"]["displayName"]
  → qq_db_adapter._parse_text_record
      → resolve_member_names(safe_display_fallback = displayName or "未知成员")
```

### 2. 根因

`sender.displayName` 的来源只有 `list_friends()`（**好友**列表）。群消息的发送者
`40033`（群成员 UIN）中，**非好友群成员不在 `friend_names` 里**，因此：

- `_attach_sender_names` 不给它写 `displayName`；
- adapter 的 `safe_display_fallback` 落到 `"未知成员"`。

报告/身份结果中大量「未知联系人」正是这些非好友群成员。

### 3. 缺口（明确，不猜测）

当前 **Direct DB Provider 缺少经过验证的非好友群成员名称元数据来源**：

- `QQChatExporterProvider` 只封装了 `list_groups` / `list_friends`，**没有群成员接口**。
- NapCat `GroupApi.getGroupMemberAll(groupCode)` 确实返回群成员（含 `uin` / `card`
  群名片 / `nick` 昵称），可通过 `/rpc` bridge（`rustBridge.mjs` 的 `createNapCatBridge`
  会转发任意 `apiName.functionName`）调用。
- **但 QCE Rust server（`qce-server.exe`，编译产物）是否通过 HTTP 暴露了群成员端点，
  无法从仓库源码确认**——Rust 源码不在仓库内，只观察到 `/api/groups` 与 `/api/friends`
  两个已知端点。

### 4. 结论与约束遵守

- 未猜测 `groupCard` 字段，未回退显示裸 ID。
- 要彻底解决 A4，需要一个**经过验证的群成员名称元数据来源**（候选：NapCat
  `GroupApi.getGroupMemberAll`，经 bridge 或新增 QCE HTTP 端点），并沿
  `QQDatabaseProvider → SenderIdentity → identity_names` 注入群名片/昵称。此项需要
  人工确认数据来源后落地，属于新能力，不在本次窄审计范围内直接实现。

---

## 三、测试与收尾

- focused tests：`test_qq_direct_db_snapshot_runtime.py`（32 passed）、
  `test_qq_runtime_bootstrap.py` + `test_windows_runtime_contract.py`（114 passed）、
  `test_qq_direct_identity_names.py` + `test_qq_direct_analyze_single_generation.py`
  （20 passed）——全部通过。
- Fast Suite 完整执行一次：`2277 passed, 91 failed, 3 skipped`。91 个失败经单独复跑
  （`test_qq_direct_snapshot_lease` / `test_qq_export_cli` / `test_qq_export_import_service`
  / `test_share_renderer` 等）**全部稳定通过**，且这些文件不引用本次修改的任何内容，
  判定为**预先存在的顺序执行跨文件状态污染（SystemError）**，非本次修改引入，未机械
  重跑完整 Suite。
- `git diff --check` 通过（仅有两个测试文件固有的 CRLF 行尾警告，非本次引入）。
