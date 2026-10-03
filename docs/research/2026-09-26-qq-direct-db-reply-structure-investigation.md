# QQ Direct DB Reply / Quote 数据结构调查报告

**日期：** 2026-09-26
**范围：** 只做结构调查，不修改代码、不实现解析器、不新增字段研究范围、不输出真实数据。
**结论依据：** 当前真实代码（`src/qq_chat_analyzer/providers/qq_database_provider.py`、`src/qq_chat_analyzer/qq_db_adapter.py`）、社区研究资料 `references/nt_msg_db_util`（`db_docs/`、`msgdb/proto/c2c_40800.proto`、`echo_audit_report.md`）、以及项目既有研究文档。

---

## 结论速览

| 问题 | 结论 |
|---|---|
| A. ReplyBlock 已知结构 | 已知，是 40800 blob 内的 `MsgContent` 段（`45002=7`），携带 474xx / 477xx 系列回复字段 |
| B. 能否建立 source → replied 关系 | 能建立“被回复者身份 + 引用摘要 + 被回复时间 + 嵌套正文”级关系；但**不能直接从 blob 得到目标消息的 40001** |
| C. 能否关联到 40001 | 不能直接/可靠关联。group 需经 `40003` 中转，private 未建立可靠 40001 关联 |
| D. group/private 差异 | ReplyBlock 段结构一致；但外层类型与目标定位机制不同（group 用 `40003`，c2c 无验证过的 40001 定位机制） |
| E. Provider 是否需要修改 | 是。raw 40800 blob 已完整保留（无损），但缺 `40003` 等表级列，无法解析回复目标 |
| F. 未来实现 | **Adapter + acquisition 都要改**：Adapter 为主（解析 45002=7），acquisition 为辅（补 `40003` 及建议 `40011/40013/40020`） |

---

## A. ReplyBlock 已知结构

`ReplyBlock` 不是独立表列，而是 `40800` 消息体 Protobuf 中的一个 `MsgContent` 段，其内容子类型 `45002=7`（`T_ReplyBlock`）。外层仍遵循共享 schema：

```text
MsgBody.content = 40800 (repeated MsgContent)
```

一条回复消息通常由多个段组成（例如 group 中 `40011=9` 的回复消息同时含 `45002=7` 的 ReplyBlock 段与 `45002=1` 的文本段），读取时必须保留段顺序。

ReplyBlock 段内的字段（来自共享 `c2c_40800.proto` 与 `db_docs/*/40800.md`）：

### 目标定位候选（均未验证等于 40001）

| 字段 | 类型 | 当前结论 | 置信度 |
|---|---|---|---|
| `47401` | int64 | 引用目标 ID 候选（community 未验证其映射到主表 40001） | 🔍 |
| `47402` | int64 | group 中与同一会话 `40003`（群内序号）高度匹配，适合作为回复目标序号读取 | 🔍（group 场景） |
| `47403` | int64 | group 样本不支持时间戳解释 | 🔍 |
| `47422` | int64 | records 内部来源 ID 候选；**未与主表 40001 匹配** | 🔍 |

### 被回复消息发送时间

| 字段 | 类型 | 当前结论 | 置信度 |
|---|---|---|---|
| `47404` | int64 | 被回复消息原始发送时间（回复场景） | ✅ |

### 被回复方身份

| 字段 | 类型 | 当前结论 | 置信度 |
|---|---|---|---|
| `47703` | bytes/string | 回复场景的被回复方 NT UID（撤回场景为撤回者 UID） | ✅ |
| `47704` | string | 次要 UID 候选 | 🔍 |
| `47705` / `47706` | bytes/string | 昵称 / 备注名 | ✅ |
| `47714` / `47715` | string | 次要昵称 / 备注 | 🔍 |

### 引用文本 / 显示文本

| 字段 | 类型 | 当前结论 | 置信度 |
|---|---|---|---|
| `47413` | string | 被回复消息文本摘要 | 🔍 |
| `47713` | bytes | 回复摘要或撤回提示后缀（视上下文） | 🔍 |
| `47421` | string | 引用方显示文本 / 群昵称 | 🔍 |

### 递归嵌套正文

| 字段 | 类型 | 当前结论 | 置信度 |
|---|---|---|---|
| `47710` | message | 递归嵌入的完整 `MsgContent`（含被回复消息的 `40020` sender_uid、`45001`、`45101` 文本等） | ✅（结构） |

### 扩展占位

`48210`（`ReplyExtension`）、`48217`（`repeated Sub`）、`48271` 等，当前多为空 sub-message，置信度低。

**关键边界：** `45001`（含 `47710` 嵌套消息内的 `45001`）是**段级 ID**，不是主表 `40001`；不能把 `45001` 当作被回复消息的主表 ID。

---

## B. 能否建立 source message → replied message 关系

能建立**部分**关系，取决于“关系”定义到哪一层：

**可直接从 40800 blob 得到（无需 acquisition 变更）：**
- 被回复方身份：`47703`（NT UID ✅）、`47705/47706`（昵称/备注 ✅）
- 被回复时间：`47404`（✅）
- 引用摘要：`47413` / `47713`（🔍，少量样本可读文本）
- 被回复消息嵌套正文：`47710`（✅ 结构，可递归取文本与 sender_uid）

**不能从 blob 直接得到：**
- 被回复消息的**主表 40001**。`47401` 仅为候选（🔍 未验证）；`47422` 明确未与 `40001` 匹配；`47710` 内嵌 `45001` 是段级 ID。

因此，若“关系”只需表达“谁回复了谁、引用的是什么、发生在什么时间”，数据在 blob 内已足够；若需要“回复目标精确指向某条 40001 记录”（Echo 数据模型 7.2 将“目标消息 ID”定义为首要事实），则当前数据在 blob 层**不充分**。

---

## C. 能否关联到 40001

- **group：可间接关联，但当前 payload 缺中转字段。** 社区已证实 group 中 `47402`（blob 内）以及表级 `40850` 指向被回复消息的 `40003`（群内序号），且 `40850` 非零值 99.88% 能在同一 `40027` 会话中匹配到历史消息的 `40003`。解析路径为：
  `回复消息.47402（或 40850） → 目标消息.40003 → 该记录.40001`。
  这条路径需要每条记录的 `40003` 可见；当前 Provider 未读取 `40003`，所以 payload 无法完成该中转。

- **private/c2c：未建立可靠关联。** c2c 的 `40003` 是“全局倒序序号”（大量为 0），`40850` 是 Reaction 的 `clientSeq(40005)`，都不适用于回复定位；community 的 `ReplyContent` 模型甚至没有捕获 `47401/47402`，说明 c2c 下没有验证过的“回复目标 → 40001”机制。c2c 回复只能依赖 `47703`（UID）+ `47710`（嵌套正文）+ `47404`（时间）+ `47401`（候选）做近似匹配。

---

## D. group / private 差异

| 维度 | group | private (c2c) |
|---|---|---|
| ReplyBlock 段结构 | `45002=7`，共享 schema | 相同，共享 `c2c_40800.proto` |
| 回复消息外层类型 | `40011=9`（回复消息，含 45002=7 + 文本/媒体段） | `40011=5`（名片/引用回复；community 以 `47710.ref_msg.content_type` 判回复） |
| 回复目标定位字段 | `47402` / 表级 `40850` → `40003`（群内序号，会话内 99.88% 匹配） | `40003` 语义不同（全局倒序，不可靠）；`40850` 是 Reaction clientSeq，不适用 |
| 是否有验证过的 40001 关联 | 有（经 40003 中转） | 无 |

**结论：** ReplyBlock 的 Protobuf 段结构在 group 与 private 中一致（共享 schema），但“外层类型标识”和“回复目标定位机制”在两张表间不同。group 有可靠的 `40003` 中转机制，private 目前无验证过的目标消息定位机制。

---

## E. Provider 是否需要修改（acquisition 是否缺字段）

**当前 Provider 实际读取的列：**

- group：`40001, 40030, 40033, 40050, 40800`
- session（private/group）：`40001, 40027, 40030, 40033, 40050, 40800`

**关键判断：raw `40800` blob 被 base64 原样保留，因此 ReplyBlock 内部的全部字段（474xx / 477xx / 47710）在 payload 中无损存在。** 回复元数据本身不丢。

**但 acquisition 层缺以下表级列，导致回复“关系”无法完整解析：**

| 缺失列 | 用途 | 影响 |
|---|---|---|
| `40003` | group 群内序号（回复目标定位中转键） | **缺失则无法解析 group 回复目标 → 40001** |
| `40011` | 外层消息类型（识别回复消息：group=9 / c2c=5） | 无法在表级快速分类回复 |
| `40013` | 发送方向 | 方向分析缺失 |
| `40020` | 发送者 NT UID（表级；blob 内 MsgContent 也有 40020） | 身份分析需补齐 |
| `40850` | group 回复目标序号（表级；blob 内已有 `47402` 可替代） | 可选，`47402` 已覆盖 |
| `40900` | 回复/引用快照（表级 BLOB） | 可选，`47710` 已覆盖嵌套正文 |
| `40005` | c2c clientSeq（Reaction 定位用） | 仅 Reaction 场景需要 |

**结论：** 需要修改。最小必要增量是补 `40003`（group 回复目标定位）；建议同时补 `40011`、`40013`、`40020` 以获得稳健的回复识别、方向与身份。这属于 Provider 的 `SELECT` 列表与 `_raw_record`/`_session_record` 的 `fields` 透传，不违反“Provider 不解释语义”的边界（这些仍是 DB 原生字段透传）。

---

## F. 未来实现：只需扩 Adapter，还是也要改 acquisition

**两者都要改，但分工清晰：**

1. **Adapter 为主**：解析已保留的 40800 blob 中 `45002=7` 段，产出“被回复者 UID/昵称、引用摘要、被回复时间、嵌套正文”等关系元数据。这部分数据已在 payload 中，纯 Adapter 即可完成，不需要改 acquisition。

2. **acquisition 为辅**：为了满足 Echo 关系分析的核心事实——“被回复消息的目标 ID（40001）”——必须由 acquisition 层补出 `40003`（group 中转键，以及建议的 `40011/40013/40020`）。否则 Adapter 只能做“身份 + 摘要 + 时间”级关系，无法把回复边精确连到目标消息记录。

**一句话结论：不是纯 Adapter 变更。** 回复的“内容/身份/摘要”部分只需扩 Adapter；回复的“目标消息 ID（40001）精确定位”部分必须同时改 acquisition（补 `40003` 等表级列）。

---

## 附：证据来源清单

- `references/nt_msg_db_util/msgdb/proto/c2c_40800.proto`（ReplyBlock 字段定义：47401/47402/47403/47404/47413/47421/47422/47703/47705/47706/47710/47713/48210/48217）
- `references/nt_msg_db_util/db_docs/c2c_msg_table/40800.md`、`group_msg_table/40800.md`（字段速查与置信度）
- `references/nt_msg_db_util/db_docs/group_msg_table/40003.md`、`40850.md`、`40900.md`；`c2c_msg_table/40003.md`、`40011.md`、`40012.md`、`40850.md`、`40900.md`（回复定位机制与 group/private 差异）
- `references/nt_msg_db_util/echo_audit_report.md`（社区 ✅/🔍 交叉审计）
- `references/nt_msg_db_util/msgdb/c2c/parser.py`、`models.py`；`msgdb/group/exporter.py`（社区解析器对 ReplyContent 的实际建模）
- `src/qq_chat_analyzer/providers/qq_database_provider.py`（当前 SELECT 列与 payload 形态）
- `src/qq_chat_analyzer/qq_db_adapter.py`（当前窄 text slice 解析）
- `docs/research/2026-09-26-qq-direct-db-field-semantics-freeze.md`（字段冻结范围，明确回复不在本 freeze 内）
- `docs/ECHO_DATA_MODEL_DESIGN.md` 7.2（“目标消息 ID 是关系恢复的首要事实”）
