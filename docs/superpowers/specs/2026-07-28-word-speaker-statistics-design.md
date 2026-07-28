# 高频词主要发送者统计设计

## 功能目标

在现有离线 QQ 群聊分析流程中，对清洗、分词后的 token 保留发送者关系，并统计：

- 每个词的总出现次数；
- 每个发送者使用该词的次数；
- 使用该词最多的发送者；
- 该发送者使用次数占该词总次数的比例。

该功能在现有词频 CSV、词云和终端 Top N 输出之外，新增两份 CSV 和一张统计图。所有计算和导出继续在本机完成。

## 方案比较与选择

### 方案一：analyzer 中使用稀疏嵌套计数结构

CLI 逐条完成解析、清洗和分词，并向 analyzer 传递按输入顺序排列的“发送者及其 token”记录。analyzer 使用 `word -> sender -> count` 的稀疏结构计数，同时记录词和“词—发送者”组合首次出现的位置。

优点是统计语义集中、内存随实际出现的组合增长、并列规则可稳定实现，且可以独立进行单元测试。此方案为最终采用方案。

### 方案二：在 CLI 中直接维护多个字典

该方案改动表面较少，但会把计数、排序、并列决胜和百分比计算堆入流程编排层，导致 CLI 难以理解和测试，因此不采用。

### 方案三：构造 pandas 用户与词语矩阵

完整矩阵便于表格运算，但会提前创建大量实际不存在的“词 × 用户”组合，在大规模聊天记录上浪费内存，也违反稀疏数据约束，因此不采用。

## 统计语义

- 一条消息中同一个词出现多次时，每次出现都累计一次，不按消息去重。
- 使用所有有效消息产生的 token 计算整体总词频，再按总词频选出 Top 25。
- 整体词频相同时，沿用现有 `top_words` 的稳定语义：输入数据中首次出现更早的词排在前面。
- 柱状图和两个新增 CSV 只涉及这组整体 Top 25 词。
- 同一个词有多个发送者并列最高次数时，选择在输入数据中最早使用该词的发送者作为 `top_speaker`。
- 发送者明细中，每个词内部按 `count` 降序排列；次数相同时，按该发送者首次使用该词的顺序排列。
- 输入顺序定义为 CLI 扫描文件后的确定性文件顺序、文件内消息顺序以及单条消息内 tokenizer 返回的 token 顺序。
- 统计必须使用现有 cleaner 和 tokenizer 的完整结果，包括停用词、单字中文、单个 ASCII 字母、短数字、卡组数量标记、纯标点和其他既有低信息 token 过滤规则。
- 新增统计固定使用最多 25 个词，不受现有 `--top` 参数影响。`--top` 仍只控制原有终端 Top N、`word_frequency.csv` 和词云输入。
- 有效词不足 25 个时使用全部有效词，不创建占位词或空数据行。

## 数据流与数据结构

### CLI 保留消息级发送者关系

现有 CLI 把所有 token 直接扩展到一个全局列表。实现阶段应在保留该列表供原有输出使用的同时，为每条有效消息保留一条按输入顺序排列的“发送者及该消息 token 列表”记录。消息没有产生 token 时不进入发送者统计，但仍沿用现有有效文本计数语义。

流程为：

1. parser 返回规范化消息及其 `sender`；
2. cleaner 清洗当前消息正文；
3. tokenizer 使用现有停用词和过滤规则生成 token；
4. CLI 将 token 继续加入原有全局词频输入，并同时把发送者与 token 交给 analyzer；
5. analyzer 生成 Top 25 摘要和发送者明细；
6. exporters 写入两个 CSV 并绘制统计图。

### analyzer 的稀疏统计

在 `analyzer.py` 增加独立的发送者统计函数和简单、明确的结果结构。结果结构至少表达：

- 摘要行：`word`、`total_count`、`top_speaker`、`top_speaker_count`、`top_speaker_share_percent`；
- 明细行：`word`、`speaker`、`count`。

内部使用等价于 `word -> sender -> count` 的稀疏嵌套映射，并额外记录：

- 每个词的首次出现序号，用于整体词频并列排序；
- 每个“词—发送者”组合的首次出现序号，用于选择并列的主要发送者以及明细并列排序。

不得创建“所有词 × 所有用户”的完整矩阵。统计函数只接收已经完成清洗和分词的数据，不读取 JSON、不调用 cleaner 或 tokenizer，也不负责写文件。

百分比按 `top_speaker_count / total_count * 100` 计算，范围为 0 到 100。摘要结果保存数值语义，CSV 输出时固定保留两位小数，例如 `100.00`。

## 输出文件

所有新增文件继续写入 `--output-dir` 指定的目录。

### `word_speaker_summary.csv`

使用 UTF-8 with BOM 编码。表头和顺序固定为：

1. `word`
2. `total_count`
3. `top_speaker`
4. `top_speaker_count`
5. `top_speaker_share_percent`

行顺序与整体 Top 25 词排名一致。`top_speaker_share_percent` 输出为 0 到 100 的数值文本，并固定保留两位小数。

### `word_speaker_frequency.csv`

使用 UTF-8 with BOM 编码。表头和顺序固定为：

1. `word`
2. `speaker`
3. `count`

只输出整体 Top 25 词的发送者明细。词与词之间按整体 Top 25 排名排列；每个词内部按 `count` 降序排列，并列时按该发送者首次使用该词的顺序排列。

### `word_top_speakers.png`

使用 matplotlib 生成横向柱状图：

- 每个整体 Top 25 词对应一根柱子；
- 纵轴标签格式固定为“词语 — 发送者”；
- 横轴表示该主要发送者使用此词的次数；
- 每根柱子旁标注 `top_speaker_count / total_count (share%)`，其中比例显示两位小数；
- 按整体 Top 25 排名从上到下展示；
- 有效词少于 25 个时按实际数量调整，不补空柱子；
- 使用 `exporters.py` 现有的本地中文字体解析逻辑，并通过 matplotlib 字体属性应用于标题、坐标轴、刻度和标注；
- 不下载字体，不访问在线服务；
- 字体不可用时沿用现有明确的字体错误，并由 CLI 的输出错误处理返回非零状态；
- 图片保存后关闭 figure，避免重复调用 CLI 时累积绘图资源。

## CLI 行为

原有行为必须保持：

- 继续生成 `word_frequency.csv`；
- 继续生成 `wordcloud.png`；
- 继续在终端显示处理消息数量、有效文本数量和 Top N 词频；
- 继续由 `--top` 控制原有 Top N 行为；
- 不增加新的必填参数。

当存在有效 token 时，CLI 额外生成：

- `word_speaker_summary.csv`；
- `word_speaker_frequency.csv`；
- `word_top_speakers.png`。

五个输出使用同一个 `--output-dir`。新增统计图固定展示最多 25 个词，不随 `--top` 增减。CLI 只负责收集消息级 token、调用 analyzer 和 exporters、确定输出路径及处理现有错误；统计、排序、百分比和绘图细节不得放入 CLI。

## 模块边界

### `analyzer.py`

负责稀疏计数、整体 Top 25 排名、主要发送者选择、明细排序和百分比计算。它不读取输入文件、不清洗文本、不分词、不导出文件。

### `exporters.py`

负责新增两个 CSV 和横向柱状图的文件输出，复用 `_resolve_font_path` 或等价的现有本地字体检测入口。它接受 analyzer 已经排好序的结果，不重新定义统计或并列规则。

### `cli.py`

负责保持发送者与当前消息 token 的关联，继续构造原有全局 token 列表，调用 analyzer 和 exporters，并将三个新文件放入 `--output-dir`。CLI 不打印新增发送者统计，也不打印完整消息正文。

### 保持不变的输入与文本处理模块

`parser.py`、`cleaner.py`、`tokenizer.py` 和 stopwords 文件原则上不修改。parser 已经为有效消息提供发送者字段，cleaner 和 tokenizer 已经定义本功能必须复用的文本语义。

## 隐私约束

- 不在终端或日志中打印完整聊天正文。
- 不在终端或日志中打印真实发送者信息。
- CSV 和图片中的发送者统计只写入本机 `output/` 或用户通过 `--output-dir` 指定的位置。
- 项目默认 `output/` 保持被 Git 忽略。
- 测试只能使用虚构昵称、虚构消息和临时输出目录。
- 测试和实现过程不读取、不运行真实 JSON 或 JSONL。
- 不使用网络请求、在线 API 或大模型 API。

## 错误与边界情况

- 没有有效 token：沿用当前“不生成输出文件”的行为，五个文件均不生成。
- 只有一个发送者：正常生成两个 CSV 和统计图。
- 一个词只有一个使用者：该发送者为 `top_speaker`，比例输出为 `100.00`。
- 多个发送者次数并列：选择输入数据中最早使用该词的发送者；明细排序也以首次使用顺序打破并列。
- 昵称为空或消息解析失败：沿用 parser 当前过滤行为，不进入统计。
- 中文字体不可用：exporters 给出清晰错误，CLI 沿用现有“生成输出失败”错误路径并返回非零状态，不在错误信息中加入发送者或正文。
- Top 25 实际不足 25 个：输出全部有效词，不补空数据。
- 非正数或空的统计输入：analyzer 返回空结果，CLI 走现有无可输出词频分支。

## 预计修改范围

实现阶段预计修改：

- `src/qq_chat_analyzer/analyzer.py`
- `src/qq_chat_analyzer/exporters.py`
- `src/qq_chat_analyzer/cli.py`
- `tests/test_analyzer.py`
- `tests/test_exporters.py`
- `tests/test_cli.py`

`pyproject.toml` 已声明 matplotlib，因此不需要修改依赖。只有未来核对发现依赖声明缺失时，才允许修改 `requirements.txt` 或 `pyproject.toml`。

README 在功能实现完成后更新，本设计阶段不修改。

以下文件原则上不修改：

- `src/qq_chat_analyzer/parser.py`
- `src/qq_chat_analyzer/cleaner.py`
- `src/qq_chat_analyzer/tokenizer.py`
- `stopwords.txt`
- `stopwords_topic.txt`
- `stopwords_culture.txt`

## 测试策略

### analyzer 单元测试

- 一个词由多个虚构发送者使用时，正确计算总次数、各发送者次数和主要发送者。
- 一条消息内重复出现同一词时，按实际出现次数累计。
- 多个发送者次数相同时，选择最早使用该词者。
- 整体词数超过 25 时只返回 Top 25，并沿用首次出现顺序打破总词频并列。
- 整体词数少于 25 时返回全部词，不补数据。
- 百分比计算正确，摘要导出所需值可稳定格式化为两位小数。
- 只有一个发送者和一个词只有一个使用者时正常返回 `100.00` 语义。
- 空输入返回空摘要和空明细。

### exporters 单元测试

- `word_speaker_summary.csv` 使用 UTF-8 with BOM，表头完全匹配设计字段，行顺序与整体排名一致，百分比固定两位小数。
- `word_speaker_frequency.csv` 使用 UTF-8 with BOM，表头完全匹配设计字段，词按整体排名、发送者按次数降序及首次出现顺序排列。
- `word_top_speakers.png` 成功生成，可由 Pillow 打开，包含非零尺寸。
- 显式字体和自动字体检测路径均可用于统计图。
- 字体缺失时产生清晰异常。

### CLI 集成测试

- 原有 `word_frequency.csv` 和 `wordcloud.png` 继续生成。
- 三个新增文件同时生成。
- `--top` 小于或大于 25 时，新增统计仍固定最多 25 个词。
- 无有效 token 时五个输出均不生成。
- 终端仍输出原有计数和 Top N，但不包含虚构完整聊天正文，也不新增发送者明细输出。
- JSON 与 JSONL 的虚构输入均能保留发送者关系并完成新增导出。

## 验收标准

- 原有输出和 CLI 参数保持兼容。
- 新增 CSV 的文件名、表头、排序和百分比格式与本设计完全一致。
- 新增 PNG 只展示整体 Top 25 词，中文标签可读，标注格式一致。
- 统计逻辑位于 analyzer，文件生成位于 exporters，CLI 只进行流程编排。
- 全部测试仅使用虚构数据并通过完整 pytest。
- 实现不读取真实聊天数据、不调用网络、不泄露正文或发送者到终端和日志。
