# Smart Profile Candidate Detection 设计

## 目标与范围

Smart Profile Phase 1 建立候选发现（Candidate Detection）的基础领域模型。
本阶段只定义“发现结果如何表达”，不实现机器人识别、模板聚类、过滤、
AI 判断、GUI 或 CLI 接入。

## Candidate 的定位

**Candidate 不等于 FilterDecision。**

Candidate 表示系统根据统计发现的疑似低价值对象。它描述：

- 哪个对象值得进一步检查；
- 系统怀疑它属于哪种候选类型；
- 当前怀疑程度；
- 形成怀疑的原因；
- 供后续判断使用的派生统计信息。

Candidate 不是最终过滤结论，也不会直接删除、隐藏或修改消息。统计规则可以
产生 Candidate，但只有未来的 FilterDecision 才能决定如何处理该对象。

## 第一阶段支持的 Candidate 类型

### SenderCandidate

SenderCandidate 表示疑似机器人发送者。第一阶段把它作为 Candidate 的语义
类别，不创建只改名字但没有独立行为的 Python 子类。

领域展示示例：

```json
{
  "sender": "警卫犬",
  "candidate_type": "robot_sender",
  "score": 0.95,
  "reasons": [
    "high_message_ratio",
    "high_repeat_rate"
  ]
}
```

规范 Python 模型中，`sender` 映射到通用字段 `target`：

```python
Candidate(
    target="警卫犬",
    candidate_type="robot_sender",
    score=0.95,
    reasons=["high_message_ratio", "high_repeat_rate"],
)
```

### TemplateCandidate

TemplateCandidate 表示疑似重复消息模板。它同样是 Candidate 的语义类别，
模板表达式映射到通用字段 `target`。

领域展示示例：

```json
{
  "template": "欢迎.*加入群聊",
  "candidate_type": "welcome_template",
  "score": 0.98,
  "reasons": [
    "high_frequency",
    "high_similarity"
  ]
}
```

规范 Python 模型中：

```python
Candidate(
    target="欢迎.*加入群聊",
    candidate_type="welcome_template",
    score=0.98,
    reasons=["high_frequency", "high_similarity"],
)
```

## Python 数据模型

模型位于 `src/qq_chat_analyzer/candidates.py`：

```python
@dataclass(slots=True)
class Candidate:
    target: str
    candidate_type: str
    score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

字段语义：

| 字段 | 含义 |
| --- | --- |
| `target` | 被怀疑的发送者、模板或未来其他对象的稳定表示 |
| `candidate_type` | 候选类别，例如 `robot_sender`、`welcome_template` |
| `score` | 检测器给出的怀疑程度，约定使用 0 到 1 的数值 |
| `reasons` | 可组合的机器可读原因代码，不是最终判断 |
| `metadata` | 可选的派生统计和展示辅助信息 |

Phase 1 不在模型中校验 score，也不把 candidate_type 固定为枚举。分数校准和
类别扩展属于未来检测器的职责。`metadata` 应优先保存派生统计，不应复制完整
原始消息。

## 与未来 FilterDecision 的关系

Candidate 负责发现问题，FilterDecision 负责决定如何处理。

```text
messages
   ↓
candidate detector
   ↓
candidate
   ↓
(optional AI/user judgement)
   ↓
FilterDecision
   ↓
FilterPipeline
```

未来 AI 或用户判断是可选步骤。Candidate 模型不依赖 AI、GUI 或任何在线服务；
FilterDecision 和 FilterPipeline 也不在 Phase 1 中定义。

## 模块边界

- `candidates.py`：只保存 Candidate 数据结构。
- 未来 candidate detector：读取统计或规范化消息，返回 Candidate 列表。
- 未来 FilterDecision：消费 Candidate 和可选判断结果，表达处理决定。
- parser、cleaner、tokenizer、analyzer、exporters 和 CLI 在本阶段均不修改。

这个边界允许未来机器人检测和模板检测独立演进，也允许 GUI 展示 Candidate
而不触发过滤。

## 测试与隐私

- 测试只构造虚构发送者、虚构模板和虚构统计 metadata。
- 测试验证字段保存、多原因保存及默认可变容器互不共享。
- 不读取真实 JSON/JSONL，不运行真实聊天分析。
- 不调用网络、AI API 或本地大模型。

## 已知设计取舍

`candidate_type` 和 `metadata` 当前保持开放，便于探索阶段扩展，但静态约束较弱。
当检测类型和 metadata 字段稳定后，可以再引入枚举、TypedDict 或专用子类；
Phase 1 不提前承担这些复杂度。
