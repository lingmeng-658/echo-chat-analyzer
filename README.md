# QQ 群聊分析

这是一个面向 QQChatExporter JSON 导出文件的本地 Python 分析项目，可完成消息解析、文本清洗、中文分词、词频统计、CSV 导出和中文词云生成。

## 隐私约束

- 工具全程离线运行，所有真实聊天记录只在本机处理。
- 不上传聊天记录。
- 不使用在线 API、大模型 API 或网络服务。
- 真实 JSON/JSONL 应放在被 Git 忽略的 `data/` 中；项目同时通过 `*.json` 和 `*.jsonl` 忽略其他位置的真实导出文件。
- `tests/fixtures/sample_chat.json` 和 `tests/fixtures/sample_chat.jsonl` 是完全虚构的测试数据，也是允许纳入版本控制的例外。
- `output/` 中的 CSV 和词云均被 Git 忽略。
- 程序不会在终端或日志中打印完整聊天正文。

## 目录说明

- `data/`：本地输入数据；整个目录均被 Git 忽略。
- `data/raw/`：建议存放真实聊天导出文件。
- `output/`：生成的 CSV 和词云图片。
- `src/qq_chat_analyzer/`：项目源代码。
- `tests/fixtures/`：完全虚构的测试数据。
- `stopwords.txt`：独立停用词文件。

## 安装

项目使用 `src` 布局。创建虚拟环境并安装依赖后，需要执行 editable 安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## 运行

安装后可使用模块入口运行：

```powershell
python -m qq_chat_analyzer.cli --input data
```

也可以直接使用虚拟环境中的 Python：

```powershell
.\.venv\Scripts\python.exe -m qq_chat_analyzer.cli --input data
```

可通过 `--output-dir`、`--stopwords`、`--font-path` 和 `--top` 调整输出路径、停用词、中文字体和词频数量。
