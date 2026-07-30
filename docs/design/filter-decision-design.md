# Smart Profile FilterDecision 设计

## 目标与范围

Smart Profile Phase 3.1 建立过滤决定（FilterDecision）的基础领域模型。
本阶段只定义处理决定如何表达，不执行过滤、不修改消息，也不接入 CLI、AI、
GUI 或未来的 FilterPipeline。

## Candidate 与 FilterDecision 的区别

Candidate 表示“系统发现一个疑似对象”。它是检测器根据统计产生的观察结果，
例如：

- 疑似机器人发送者：`虚构机器人`
- 疑似欢迎消息模板：`欢迎 {variable} 加入群聊`

Candidate 不代表对象一定需要被过滤，也不会直接改变任何消息。

FilterDecision 表示“系统或用户对候选做出的处理决定”。它记录目标应被忽略、
保留还是等待复核，以及决定的置信度、原因和来源。FilterDecision 只表达决定，
仍不负责执行决定。

数据流边界为：

```text
Candidate
   ↓
FilterDecision
   ↓
未来 FilterPipeline
```

Candidate Detection 和 FilterDecision 因此可以独立演进：检测器负责发现，决策层
负责表达处理意图，未来 FilterPipeline 才负责执行。

## Python 数据模型

模型位于 `src/qq_chat_analyzer/filter_decisions.py`：

```python
@dataclass(slots=True)
class FilterDecision:
    target: str
    target_type: str
    action: str
    confidence: float
    reason: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
```

字段语义：

| 字段 | 含义 |
| --- | --- |
| `target` | 决定针对的对象，例如发送者名称、模板或 token |
| `target_type` | 目标类别，例如 `sender`、`template`、`token` |
| `action` | 处理意图，例如 `ignore`、`keep`、`review` |
| `confidence` | 决定置信度，约定为 0 到 1 |
| `reason` | 形成决定的机器可读原因，例如 `robot_sender_candidate` |
| `source` | 决定来源，例如 `auto`、`user`、`ai` |
| `metadata` | 可选的额外上下文或派生信息 |

Phase 3.1 延续 Candidate 的开放模型风格，不把 `target_type`、`action` 或
`source` 固定为枚举，也不在 dataclass 中执行范围校验。当前目标是建立稳定、
简单的数据交换结构；当允许值和校验策略稳定后，再考虑枚举或专用构造函数。

`metadata` 使用独立的默认字典，多个 FilterDecision 实例之间不会共享可变状态。
metadata 应保存决策辅助信息，避免复制完整聊天正文。

## 示例

自动生成的发送者忽略决定：

```python
FilterDecision(
    target="虚构机器人",
    target_type="sender",
    action="ignore",
    confidence=0.97,
    reason="robot_sender_candidate",
    source="auto",
)
```

用户覆盖自动判断并保留发送者：

```python
FilterDecision(
    target="虚构助手",
    target_type="sender",
    action="keep",
    confidence=1.0,
    reason="user_override",
    source="user",
)
```

## 模块边界

- `candidates.py`：表达检测器发现的疑似对象。
- `filter_decisions.py`：只表达针对目标的处理决定。
- 未来决策生成层：把 Candidate、用户选择或可选判断结果转换为
  FilterDecision。
- 未来 FilterPipeline：消费 FilterDecision 并执行过滤。

本阶段不创建决策生成器或 FilterPipeline，不修改 parser、cleaner、tokenizer、
analyzer、exporters 或 CLI。

## 测试与隐私

- 测试只使用虚构发送者和虚构模板。
- 测试验证所有字段保存、可选 metadata 以及默认字典互不共享。
- 不读取真实 JSON/JSONL，不运行真实聊天分析。
- 不调用网络、AI API 或本地大模型。

## 已知设计取舍

开放字符串字段便于早期迭代，但静态约束较弱。Phase 3.1 明确把允许值写入字段
语义，而不提前引入枚举和验证框架。数据模型也不保存 Candidate 实例引用，
避免把发现结果和最终决定强耦合；如需追踪来源，可在未来稳定需求中增加明确的
标识字段，而不是把原始消息放入 metadata。
