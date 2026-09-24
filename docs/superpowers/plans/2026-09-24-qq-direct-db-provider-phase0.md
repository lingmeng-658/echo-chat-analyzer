# QQ Direct DB Provider — Phase 0 Design Freeze

**状态：** 仅设计冻结。本阶段不实现产品代码，不修改现有行为。
**日期：** 2026-09-24
**前置事实：** QQ Direct DB feasibility spike 已 PASS。最小群聊纯文本链路已在本机受控实验中验证可行。
**当前定位：** Direct DB 仍是 *validated acquisition candidate*；生产 QQ acquisition 仍然是 QCE。
**文档权威边界：** `ARCHITECTURE.md` 只记录当前已实现事实。本文描述的是**未来设计**，不得被当成已实现架构；本阶段不修改 `ARCHITECTURE.md`。

**架构原则（本阶段冻结，不可违反）：**

- Provider 负责外部数据获取 / DB access。
- Adapter 负责 source-specific 数据到 Echo source-neutral model 的转换。
- Analysis Core 不得知道 QQ DB 字段或 protobuf 字段。
- GUI 不直接调用 Provider。
- QCE 与 Direct DB 在迁移期并存。
- 不因为 Direct DB 可行而推翻现有分析架构。

---

## 0. 本阶段（Phase 0）范围

只做：

- 冻结当前 QQ acquisition 链路事实（第 1 节）。
- 冻结目标 seam 的概念接口（第 2 节）。
- 冻结 QCE 与 Direct DB 的关系（第 3 节）。
- 冻结 Provider / Adapter 边界（第 4 节）。
- 冻结 `qq-db` raw payload v0（第 5 节）。
- 冻结 Direct DB v0 capability boundary（第 6 节）。
- 定义 Phase 1 第一颗 RED 测试（第 7 节）。
- 记录 non-goals（第 8 节）与尚未决定的问题（第 9 节）。

不做：任何 Python 产品代码改动、GUI 改动、ARCHITECTURE.md 改动、默认 Provider 决策、fallback、QCE retirement 讨论。

---

## 1. 当前 QQ acquisition 链路（已实现事实）

当前生产链路：

```text
ChatAnalyzerFacade
  → QQExportImportService          （application 编排 / acquisition 生命周期 owner）
      → QQChatExporterProvider     （QCE HTTP provider，外部数据获取）
          → transient lease output dir
              → QCE JSON payload_path
  → AnalysisApplicationService     （Facade 以 payload_path 接入）
      → ImportService → qq_chat_exporter_adapter → RichMessage
      → legacy_projection → ChatMessage → analysis core
```

事实点（均为当前代码）：

- **Facade 通过 payload_path 接入 `AnalysisApplicationService`。**
  `src/qq_chat_analyzer/application/facade.py:272-276` 定义内部 `_SessionExport(payload_path)`；
  `facade.py:1034-1036`（QQ 分支）与 `facade.py:1040-1052`（WeChat 分支）产生它；
  `facade.py:738-739` 把它交给 `self._analyze_path(session_export.payload_path, ...)`。
  Facade 只传递**本地文件路径**，不知道 QCE 语义。
- **QQ acquisition 请求由 Facade 组装，且是 QCE 形状的。**
  `facade.py:1010-1036` 构造 `QQExportImportRequest(group_code, start_time, end_time, chat_type, peer_uin, session_name, force_refresh)`；
  `facade.py:1304-1328` 的 `_scope_export_window` 把 `AnalysisScope` 翻译成 QCE epoch **millis** 边界。
- **获取生命周期由 `QQExportImportService.acquired_export()` 拥有。**
  `src/qq_chat_analyzer/application/qq_export_import_service.py:240-268`：`begin_run()` → 导出 → `yield acquisition` → `finally lease.cleanup()`。
  导出目录是 Echo-owned transient lease，QQ 原始 export 不是长期 cache / 资产。
- **`QQExportProvider` Protocol 是 QCE-specific contract。**
  `qq_export_import_service.py:63-90`：`list_groups()`、`list_friends()`、`list_tasks()`、`export_group_json(...)`。
- **`QQChatExporterProvider` 实现的是本机 HTTP + QCE task 语义。**
  `src/qq_chat_analyzer/providers/qq_chat_exporter_provider.py:270` 起：health check、token 解析、`ExportTask`、`create_export_task` / `wait_export_task`、`TASK_NOT_FOUND` / `EXPORT_TASK_LIMIT_REACHED`、`downloadUrl` / `filePath`。
- **Adapter 产出 source-neutral RichMessage，并标注 QCE 来源。**
  `src/qq_chat_analyzer/qq_chat_exporter_adapter.py:236-256`：`source="qq"`、`source_type="qce-json"`；`message_type` 来自 QCE `type`；`conversation_type` 来自 `chatInfo.chatType`（1 = private / 2 = group，见 `qq_chat_exporter_adapter.py:78-101`）。
- **Facade 的 QQ 会话列表也走 QCE 语义。**
  `facade.py:357-370` 调用 `service.list_sessions()`，`_to_session_info`（`facade.py:1390`）读取 `group_code` / `group_name` / `member_count` 等 QCE 字段名。
- **QQ 时间范围探测读取 QCE JSON。**
  `qq_export_import_service.py:201-238` 的 `get_session_message_range()` 读 `messages[].timestamp`。

**结论：** 现有 QQ 生产链路是 QCE-specific 的 —— 会话来自 QCE 群/好友列表，获取来自 QCE export task，输入是 QCE JSON。因此 Direct DB **不应被强迫实现 QCE task / export 语义**（task id、progress 轮询、`downloadUrl`、`chatType=1/2`、`group_code`、`peer_uin`）。

---

## 2. Target seam（概念冻结，不写生产实现）

### 2.1 目标依赖方向

```text
Facade
  → QQ acquisition seam（application 层抽象，source-neutral）
      → 实现 A：QCE acquisition（现有 QCE provider 语义藏在其内部）
      → 实现 B：Direct DB acquisition（只读 DB + DB provider 语义藏在其内部）
          → payload（transient 本地文件）
  → AnalysisApplicationService
      → ImportService → 对应 adapter（qce-json / qq-db）→ RichMessage
      → legacy_projection → ChatMessage → analysis core
```

Facade 只依赖 seam 的抽象：不 import providers、不知道 QCE task、不知道 DB 表/列、不知道 protobuf 字段。

### 2.2 概念接口（仅概念，Phase 1+ 才决定落地形式与命名）

会话摘要（seam 输出的会话形状，source-neutral）：

- `session_id`：稳定会话标识
- `session_type`：`"group"` / `"private"` / `"unknown"`
- `display_name`
- 可选：`message_count`、`last_timestamp`

获取结果（seam 输出的 acquisition 形状）：

- `payload_path`：已物化的 transient 本地 payload 路径（供现有 path-based 导入路径消费）
- 可选：`source_format`、会话 id / 类型提示

概念接口（示意，非产品代码）：

```python
class QQAcquisitionService(Protocol):
    def list_sessions(self) -> list[Any]: ...

    @contextmanager
    def acquire_session(
        self,
        session_id: str,
        *,
        session_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        progress: Callable[[Any], None] | None = None,
    ) -> Iterator[Any]: ...

    def session_message_range(
        self,
        session_id: str,
        *,
        session_type: str | None = None,
    ) -> tuple[int, int] | None: ...
```

覆盖要求：

- **list_sessions** —— 返回会话摘要，且**不得**向 Facade 暴露 `group_code` / `peer_uin` / `chatType`。归一化为 `SessionInfo` 仍归 Facade（或日后迁入共享 normalizer，见第 9 节）。
- **acquire one session payload with optional time range** —— 一次获取一个会话的 payload，时间范围为可选。范围语义（包含/半开、单位）由 seam 定义，不得沿用 QCE millis 或 DB 原生单位（见第 9 节）。
- **acquisition 生命周期 ownership** —— acquisition service 创建并清理它产生的 transient 本地 payload；消费者只在 `with` 内读取；payload 不是长期资产；清理失败只记录日志，不得把已成功的分析变成失败（对齐现有 lease 行为）。
- **progress** —— 若提供，只接收 source-neutral 快照（可显示文案 + 可选 message count）；QCE task 快照必须留在 QCE 实现内部。

接口禁止出现：QCE task / task_id / 轮询状态 / `downloadUrl`、DB schema 字段（表名、列名）、protobuf 字段名、GUI/分析字段。

### 2.3 与现状的差距（迁移期必须显式处理）

- 今天 Facade 传 `chat_type` / `peer_uin` / `session_name` / `force_refresh`。目标 seam 收敛为 `session_id` / `session_type` / 可选时间范围。
- `get_qq_export_tasks()`、QQ connection / setup / environment 服务仍是 QCE-specific，v0 留在 seam 之外。
- 迁移期：QCE 实现保持现有行为，Direct DB 作为第二个实现满足同一 seam；Facade 如何按来源装配由后续阶段决定（本阶段不决定）。
---

## 3. QCE 与 Direct DB 的关系（冻结）

- 二者是**同一 application acquisition 层的两种实现**（peer implementations），满足同一个 seam。
- **本阶段不决定默认 Provider。**
- **不实现 fallback**：QCE 失败不自动切 Direct DB，Direct DB 失败也不自动切 QCE。
- **不讨论 QCE retirement**：QCE 仍是生产 acquisition，Direct DB 是已验证候选。
- 共享：payload → adapter → `RichMessage` → `legacy_projection` → `ChatMessage` → `ImportService` / `AnalysisApplicationService` 的下游路径。
- 不共享：provider 内部语义（本机 HTTP + QCE task ↔ 只读 SQLite 查询、无 task 概念）。

---

## 4. Provider / Adapter 边界（冻结）

### 4.1 Provider（Direct DB provider）

负责：

- 定位并**只读**打开 QQ 本地 DB（只读句柄；不写入、不改 schema、不做迁移）。
- 查询目标 session / time range。
- 取得 source-specific raw rows / opaque message payload（**不解释聊天语义**）。
- 必要时物化为 transient local payload（在该次 acquisition 生命周期内拥有并清理）。

不负责：文本抽取语义、`RichMessage`、分析、过滤、面向用户的错误措辞。

禁止依赖：`ChatMessage`、`RichMessage`、`analysis/`、`presentation/`、`gui/`、`application/`（对齐 `ARCHITECTURE.md` 4.1 的层级约束）。

### 4.2 Adapter（`qq_db_adapter`）

负责：

- 解释 QQ DB source-specific message semantics。
- protobuf / message element 语义映射。
- sender / conversation / timestamp / content mapping。
- 构造 `RichMessage`，再沿现有 projection（`project_legacy_messages`）得到 `ChatMessage`。

不负责：打开 DB、查询、文件发现、分析、过滤策略。

可依赖：`rich_message.py`、`message.py` / `legacy_projection.py`、标准库（对齐 `ARCHITECTURE.md` 4.2）。

### 4.3 边界判定规则

- DB 表名、列名、protobuf / element 字段名只允许出现在 Provider（及其 payload 物化代码）或 Adapter 的解析函数内部。
- 这些名字不得出现在 seam 契约、`RichMessage`、`ChatMessage`、Facade、Analysis Core 中。
- Provider 不解释语义；Adapter 不接触外部世界。两者不互相调用。
- payload 只承载 source-specific raw records；Provider 不得在 payload 中提前产出归一化语义字段（`conversation_id`、`sender_id`、归一化 `timestamp`、归一化 `message_type`、`text`）。

---

## 5. `qq-db` raw payload v0（最小 + 可扩展）

只设计最小、可扩展格式。职责边界：Provider 只输出**真正的 source-specific raw record**；conversation / sender / timestamp / message type / text 等统一语义只在 Adapter 中产生。v0 = 一个 JSON envelope + 每记录一条 raw record。

```json
{
  "format": "qq-db-json",
  "format_version": 0,
  "source": "qq",
  "source_type": "qq-db-json",
  "query": {
    "requested_session": "<被要求拉取的会话选择器>",
    "time_range": null
  },
  "records": [
    {
      "record_id": "<DB row / record identifier>",
      "fields": {
        "<db-native column / field name>": "<raw value，不重命名、不换算、不转换类型>"
      },
      "message_blob": "<opaque raw / protobuf message payload>",
      "blob_encoding": "base64",
      "source_meta": { "table": "<db-native table name>", "qq_version": null }
    }
  ]
}
```

字段规则（冻结）：

- **只承载**：
  - row / record identifier（`record_id`）；
  - 查询所需或 DB 原生字段（`fields`，键为 DB 原生名字）；
  - opaque / raw message blob 或 protobuf（`message_blob`）；
  - 必要的 source metadata（`source_meta`，以及 envelope 的 `format` / `format_version` / `source` / `source_type` / `query`）。
- **payload 层不得提前定义统一语义字段**。明确禁止出现：`conversation_id`、`sender_id`、归一化 `timestamp`、归一化 `message_type`、`text`，以及任何 Echo 词汇（`RichMessage` / `ChatMessage` 的字段名）。
- `fields` 是 DB 原生字段的**透传容器**：Provider 不重命名、不做单位换算、不做类型推断。
- `message_blob` 对除 Adapter 以外的一切都是 opaque；它可以承载已解码 element 列表、base64 protobuf 等；只有 Adapter 读取它；它绝不进入 `RichMessage` / `ChatMessage`。
- **unknown keys 必须保留**：Provider 不得丢弃自己不理解的数据。
- envelope 的 `format` / `source_type` 只是 **payload 溯源标识**（供 loader 分发），不是消息语义；`RichMessage.source_type` 由 Adapter 依据该格式常量产生，不从 record 字段拷贝。
- `query.requested_session` 是**获取请求的回显**（acquisition provenance），不是消息字段。若源 DB 的 record 本身不携带会话身份，Adapter 可把它作为推导 `conversation_id` 的输入之一；映射规则仍归 Adapter。
- **`format_version` 必填**，未来 loader 可据此拒绝不支持的版本。
- **不得**在 payload 内嵌 Echo 的 `RichMessage` / `ChatMessage`，也不得内嵌 GUI / 分析字段。

Adapter 负责解释这些原始字段，并产生 conversation、sender、timestamp、message type、text / expression / relation 等消息语义（边界见 4.2 / 4.3）。

#### 5.1 已观察到的 source-specific 标识（spike 实证，非 Provider 契约）

`40030 / 40033 / 40050 / 40800 / 45002 / 45101` 仅是 **feasibility spike 受控样本中的 source-specific 实证观察**：

- 它们**不属于** Provider 对外稳定 schema，也不构成本文冻结的接口、字段或取值承诺。
- 本阶段**不解释**这些标识的具体语义，也不推断其完整含义或取值域。
- Adapter 对它们的依赖只允许存在于 Adapter 内部实现；不得泄漏到 payload 契约、seam 契约、`RichMessage` / `ChatMessage` 或 Analysis Core。

可扩展性预留（Phase 0 **不实现**，只保证格式放得下）：

- QQ 小表情（unicode face）、QQ 表情包 / market face。
- 回复 / 引用；@ 提及。
- 戳一戳等互动事件。
- 图片 / 文件 / 语音等内容消息；私聊会话。
- 多账号。

扩展方式：新增 / 更丰富的 `fields` 与 `message_blob` 内容；私聊会话由 record 的 DB 原生字段体现（`conversation_type` 由 Adapter 推导）；消息间关系（回复目标等）先放入 `message_blob`，日后可选增加独立 raw relation 块。以上均为未来设计，本阶段不实现。

---

## 6. Direct DB v0 capability boundary（第一条 vertical slice）

第一条 vertical slice **只支持**：

- QQ 群聊（`conversation_type == "group"`）
- 普通纯文本
- sender
- conversation
- timestamp
- message / text recovery
- 转成现有 source-neutral model（`RichMessage` → `ChatMessage`，沿 `legacy_projection`）

一律不包括第 8 节列出的非目标。任何超出该边界的字段都必须以“可跳过、不崩溃”的方式处理。

---

## 7. Phase 1 RED（第一颗失败测试，精确定义）

### 7.1 目的

使用**完全虚构**的 `qq-db` source-specific raw record，证明独立 adapter 能从 raw record 推导出正确的 `RichMessage` / `ChatMessage`。

### 7.2 测试文件

- 新增：`tests/test_qq_db_adapter.py`
- 被测模块（Phase 1 创建）：`src/qq_chat_analyzer/qq_db_adapter.py`
- 概念 API（与现有 `qq_chat_exporter_adapter.py` / `wechat_db_adapter.py` 同形）：
  - `is_qq_db_export(path) -> bool`
  - `load_qq_db_json(path) -> dict | None`
  - `parse_qq_db_rich_messages(payload, ...) -> tuple[list[RichMessage], tuple[str, ...]]`
  - `parse_qq_db_messages(payload, ...) -> tuple[list[ChatMessage], tuple[str, ...]]`（经 `project_legacy_messages`）

### 7.3 测试数据

- 在测试内**内联构造**一条**完全虚构的 source-specific raw record**（第 5 节 v0 格式：`record_id` + DB 原生 `fields` + opaque `message_blob`），写入 `tmp_path` 后走 `load_qq_db_json` / `parse_qq_db_rich_messages`。
- 输入**不得**包含任何已归一化的 Echo 语义字段：不得直接提供 `conversation_id`、`sender_id`、归一化 `timestamp`、归一化 `message_type` 或 `text`。测试只提供虚构的 DB 原生字段与虚构 blob，`RichMessage` / `ChatMessage` 必须由 `qq_db_adapter` 推导。
- 全部字段为虚构字面量（虚构 record id、虚构 DB 原生字段值、虚构 blob 内容）。
- 不提交任何真实 JSON / JSONL 数据，不使用真实群号 / 昵称 / 账号。

### 7.4 断言（至少）

对 `RichMessage`（`rich`，由 `qq_db_adapter` 从 raw record 推导）：

- `rich.conversation_id == "<虚构会话标识>"`（Adapter 从 raw record 推导）
- `rich.sender.identity_id == "<虚构发送者标识>"`
- `rich.timestamp == <冻结的固定值>`（Adapter 已归一化时间语义）
- `rich.conversation_type == "group"`
- `rich.source == "qq"`
- `rich.source_type` 明确标识 qq-db，且与第 5 节冻结值一致：`"qq-db-json"`
- `rich.message_id` 映射自 record 的 `record_id`（或 Adapter 从 raw record 推导出的消息标识）
- `rich.contents` 恰为单个 `TextContent`，其 `text` 等于期望文本

对 `ChatMessage`（`chat`，来自 `project_legacy_messages`）：

- `chat.text` 与期望文本**逐字符相等**（exact text）
- `chat.platform == "qq"`
- `chat.source_type == "qq-db-json"`
- `chat.conversation_id` / `chat.sender_id` / `chat.timestamp` 与 rich 一致
- `chat.conversation_type == "group"`

边界守卫（建议同批加入）：

- DB 原生字段名（record `fields` 的键名）不得作为语义标识泄漏进 `RichMessage` / `ChatMessage` 的字段值。
- 无法解释的 record 被跳过并返回 warning，不抛异常。

### 7.5 RED 期望失败原因

`src/qq_chat_analyzer/qq_db_adapter.py` 在 Phase 1 前不存在，测试必须以 `ModuleNotFoundError`（模块缺失）失败，而不是断言失败。

### 7.6 运行命令（按 `AGENTS.md`）

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_qq_db_adapter.py -q
```

注：当前环境未发现 `.venv`（见第 10 节），Phase 1 执行前必须先恢复虚拟环境；否则该次结果不构成有效 RED 证据。

---

## 8. Non-goals（明确不做）

- SQLite Provider 实现
- GUI 修改
- QCE fallback
- 私聊
- 表情
- 回复
- 戳一戳
- 图片 / 文件 / 语音
- 多账号
- QQ 版本兼容框架
- 完整 protobuf schema 逆向
- Analysis Core 修改

---

## 9. 尚未决定的问题（Open Questions）

1. `source_type` / `format` 最终字符串是否用 `"qq-db-json"`（本文冻结值，镜像 QCE 的 `"qce-json"` 约定），还是 `"qq-db"` / 其它写法；`DATA_SEMANTICS.md` 是否为该标识的权威约定。
2. seam 的时间范围语义：包含还是半开、返回秒还是毫秒、由谁转换。
3. payload 物化边界：Provider 直接产出 payload 文件（v0 假设），还是先返回内存 rows、由 acquisition 层统一物化；大会话是否需要流式路径。
4. Direct DB readiness / 健康检查如何接入现有 QQ 连接体验：QQ 是否在运行、DB 是否可读、密钥如何处理；是否复用 `QQConnectionService`，还是需要新的 source-neutral readiness 概念。
5. 多账号下 session 身份如何作用域化（影响 `conversation_id` 唯一性）。
6. snapshot 复用（`force_refresh` / `chat_data_snapshot`）是否适用于 Direct DB，还是 QCE 专有；当前 Facade 路径每次都是 fresh acquisition。
7. `list_sessions` 的会话类型判定（group/private）由 Provider 还是 Adapter 负责。
8. Windows 下 DB 文件锁 / 只读打开（WAL、正在运行的 QQ）约束如何满足。
9. seam 落地形式与命名（新 Protocol 放在 `application/` 的哪个模块、QCE 实现是包装现有服务还是改写 Facade 调用点）。
10. `ImportService` 是否必须识别 `qq-db-json` 格式（v0 payload 若是落盘 JSON 并走 path-based 分发，则需要；Phase 1 的 adapter 单测不依赖它）。本阶段不实现。

以上问题在后续阶段由人工确认，本阶段不追踪、不实现。

---

## 10. 环境与验证记录（Phase 0 交付时）

- 环境观察：仓库根目录下**未发现** `.venv`（`Test-Path .\.venv\Scripts\python.exe` → False）。本阶段为纯文档交付，未运行 Python / pytest；Phase 1 开始前必须先恢复虚拟环境。
- `git diff --check`：通过（exit 0，无输出）。
- `git diff --name-only`：无输出（未修改任何已跟踪文件）。
- `git status --short`：仅新增本文档
  `?? docs/superpowers/plans/2026-09-24-qq-direct-db-provider-phase0.md`。
- 未修改任何 Python 产品代码，未修改 `ARCHITECTURE.md` 的已实现事实。