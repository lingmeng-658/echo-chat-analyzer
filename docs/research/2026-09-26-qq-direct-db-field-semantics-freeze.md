# QQ Direct DB Field Semantics Freeze

**日期：** 2026-09-26  
**状态：** 字段研究冻结；不进入 Checkpoint 3 实现  
**范围：** 只覆盖当前 replacement 主链实际携带或依赖的 `40001`、`40027`、`40030`、`40033`、`40050`、`40800`。不涉及 `40008`、reply、各类 face/image、`40800` 内部其它字段、paging、Facade/GUI 或 QCE parity。

## 方法与隐私边界

- 对一份已有 plaintext QQ DB 以 SQLite `mode=ro` 打开；未写入、复制或导出真实数据。
- 只读取表结构与聚合统计；没有输出真实 ID、昵称、路径、聊天正文或 protobuf 内容。
- 样本含 `group_msg_table`（8,829 行、8 个 `40027` 分区）与 `c2c_msg_table`（149 行、7 个分区）。
- “特殊 `40030`”在本文指除 `NULL`、`0` 外的负数或非标量/非数值存储；本样本未出现该类值。`0` 单列，因为它在两类表中均实际出现。

## A. 40030 在 group 中的观察结论

- 8 个 `40027` 分区各有且仅有 1 个 distinct 非零 `40030`；没有多非零值分区。
- `40030` 为 `NULL` 的比例是 0；为 `0` 的比例是 **17.25%**（1,523/8,829）；其它特殊值比例是 0。
- 三个按消息量选择的匿名分区中，非零 dominant `40030` 分别覆盖 **94.37%**、**73.16%**、**72.59%** 的行；每个样本的非零 distinct 数都为 1。
- 8 个分区的 dominant 非零值均未作为该分区的 `40033` 出现。这与“群会话对象而不是发送者”一致；社区证据将 group 的非零 `40030` 解释为群号，并将 `0` 解释为系统/特殊记录。
- 正时间戳记录覆盖 25.2 天；在整个样本（含零值记录）中，每个分区的非零 `40030` 仍保持单值。因此它在此快照中对 group 外部身份是稳定的，但 `0` 必须排除出该结论。

## B. 40030 在 private 中的观察结论

- 7 个 `40027` 分区各有且仅有 1 个 distinct 非零 `40030`；没有多非零值分区。
- `40030` 为 `NULL` 的比例是 0；为 `0` 的比例是 **2.68%**（4/149）；其它特殊值比例是 0。
- 三个按消息量选择的匿名分区中，dominant 非零值均覆盖 **100%** 的行，且各自只有 1 个非零 distinct 值；样本时间跨度为 9.3、25.2、24.9 天。
- 7 个分区的 dominant 非零值都至少一次作为该分区的 `40033` 出现。这与私聊对端可作为入站消息发送者相符；社区证据将 private 的非零 `40030` 解释为 peer QQ。
- 因此，非零 `40030` 在本快照 private 分区内稳定；但 `0` 仍是不能映射到 peer identity 的例外记录。

## C. 40030 是否足以作为 external conversation identity / metadata

**结论：有条件地足够。** 在 `(table/session_type, 40027)` 已经确定的上下文中，取该分区的唯一 dominant **非零** `40030`，可作为当前 Direct DB v0 的 external conversation identity / metadata：group 是 group identity，private 是 peer identity。

它**不**足以作为本地分区键、唯一的读取谓词或无条件会话 ID：

- `0` 在 group 为 17.25%、private 为 2.68%，不表示外部会话身份；
- 一个 session 的查询、分页边界和去重范围应使用 `(table/session_type, 40027)`；
- `40030` 的含义和稳定性没有跨 QQ 版本、账号迁移或数据库快照保证。

当前 replacement 主链与这个结论一致：Provider 的 session materialization 按 `40027` 且按表类型读取；`40030` 被保留为 `session_object` metadata。现有 group-only Adapter v0 仍把它投影为 `conversation_id`，进入 Checkpoint 3 时必须只接受已确认的非零 external identity。

## D. 六个核心字段的 freeze table

| 字段 | 当前语义 | 证据来源 | 当前置信度 | Echo 当前用途 | 明确不保证什么 |
| --- | --- | --- | --- | --- | --- |
| `40027` | local session partition key；只在 `(table/session_type, account snapshot)` 范围内有意义。 | Echo controlled evidence（本次两表均完整分区、每分区仅一 dominant 非零 `40030`）；community evidence。 | 高 | `list_sessions()` 聚合与 `materialize_session_payload()` 的读取谓词。 | 不是 group/peer external identity；不保证跨表、跨账号、跨版本或迁移后仍唯一/不变。 |
| `40030` | 非零时为外部会话对象：group 中为 group identity，private 中为 peer identity；`0` 是不应视作身份的特殊/系统记录。 | Echo controlled evidence（本次稳定性、零值比例、发送者关系）；community evidence。 | 中高（非零、已分区情形）；低（零值行）。 | raw payload 的 `session_object` metadata；现有 group Adapter v0 的 `conversation_id`。 | 不能替代 `40027` 作读取分区；不保证所有行非零、跨版本稳定或可单独作为全局 conversation ID。 |
| `40001` | source-native message identity / dedup candidate；本样本每张表内全 distinct，且两表间无交集。 | Echo controlled evidence（8,829 group + 149 private 行的 distinct/交集检查）；community evidence。 | 中高 | Provider `record_id`、稳定读取排序、下游 message-id 候选。 | 不保证跨账号、跨数据库快照的全局唯一；不是 timestamp，也不保证严格时间序。 |
| `40033` | sender identity candidate；与消息方向相关，可能为 `0` 的系统/特殊发送者。 | Echo controlled evidence（group 85、private 9 个 distinct 值；无 NULL，`0` 分别为 142/8,829 与 4/149）；community evidence。 | 中高（普通非零消息）；低（零值行）。 | Adapter 作为 `SenderIdentity.identity_id` 与临时 display fallback。 | 不保证是可显示昵称、跨版本稳定，或 `0` 能代表真实发送者。 |
| `40050` | Unix seconds timestamp candidate；正值用于消息时间和范围过滤。 | Echo controlled evidence（整数列、正值样本跨度 25.2 天）；community evidence；既有 controlled group plain-text feasibility evidence。 | 高（正常正值消息）；中（全部记录）。 | Provider 时间范围筛选、session `last_message_time`、Adapter `timestamp`。 | 不保证每行都是有效日历时间：group 发现 6 个 `0`；不是毫秒时间戳，也不保证同秒内唯一或严格排序。 |
| `40800` | message content protobuf/blob container。 | Echo controlled evidence（本样本非 NULL BLOB：group 8,821/8,829，private 116/149；既有 group plain-text feasibility）；community evidence。 | 高（容器）；低（内部完整语义）。 | Provider base64 原样携带；Adapter 仅支持当前 narrow text slice。 | 不保证非 NULL、可解析、包含文本，或内部字段在版本/消息类型间恒定；本 freeze 不扩展其内部 protobuf 研究。 |

## E. 仍未解决的风险

1. 这是单一 DB 快照，尚未证明跨 QQ 版本、账号、迁移或多 shard 的一致性。
2. `40030=0` 的具体记录类型不在本任务范围；Checkpoint 3 应排除/显式标记，而不是把它建成 external identity。
3. `40050=0` 在 group 中实际存在，时间范围和 `last_message_time` 需要明确对非正值的处理策略。
4. `40033=0` 与 `40800=NULL` 均实际存在，不能假设每条保留记录都可形成完整的普通文本 `RichMessage`。
5. `40001` 当前只冻结为 source-native dedup candidate；尚未验证跨 snapshot 重导入、跨账号或数据库重建时的稳定性。
6. 现有 Adapter v0 是 group-text narrow slice；private 读取、零值保护和失败记录策略仍属于 Checkpoint 3 实现工作，而非本次字段研究。

## F. 进入 Checkpoint 3 的判定

**可以结束本轮字段研究并进入 Checkpoint 3。** 实现前置条件是将以上冻结边界写入 acceptance criteria：以 `(table/session_type, 40027)` 选取会话；只把 dominant 非零 `40030` 暴露为 external metadata/conversation identity；对 `40030=0`、`40050<=0`、`40033=0` 和 `40800=NULL` 采用明确的 skip/flag 行为。

本结论不把 Direct DB 提升为跨版本稳定协议，也不改变 QCE 仍为当前生产 acquisition path 的架构事实。

