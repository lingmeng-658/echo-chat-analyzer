# 余音 Echo

> 隐私优先、完全本地运行的 QQ / 微信聊天分析工具。  
> 把散落在聊天记录里的时间、语言与互动，重新整理成一份可以回看的 Echo Report。

## 现在能看到什么

- 会话概览：消息规模、时间跨度、活跃时段
- 聊天轮次：谁更常开启聊天、一次通常聊多久、聊天纪录
- 节奏：一天与一周中的活跃分布
- 语言画像：
  - 群聊成员特色词
  - 私聊双方常用表达
- QQ / 微信统一分析
- 自包含 Echo HTML 报告，可直接在浏览器打开

> 仍在持续开发中：Emoji / 表情行为、互动关系、私聊专属洞察等。

## 隐私优先

Echo 的设计前提是：真实聊天数据属于用户自己。

- QQ / 微信聊天数据在本机读取和分析
- 不上传完整聊天记录
- 不将聊天正文、身份信息、群号或本地路径写入 Git
- 测试只使用虚构数据
- Echo 报告可以在本地生成并查看
- 需要 AI 扩展时优先使用本地模型；云端能力只允许发送最少量、匿名化信息

## 支持的数据来源

### QQ

当前主要通过 QQChatExporter / 本地 QQ 接入链路读取并统一为内部 ChatMessage 模型。

### 微信

已打通 Windows 微信数据库读取链路，并统一进入同一套分析核心。

QQ 与微信最终共享：

数据源
→ Import / Adapter
→ ChatMessage
→ Analysis Core
→ Presentation
→ Echo Report

## Echo Report

Echo 不希望成为另一张 Dashboard。

它更接近一份数字聊天杂志：

- 用编辑式排版组织数据
- 保留适量音乐意象
- 重点展示“这段聊天留下了什么”
- 前端不重新计算业务统计，所有核心语义来自 Analysis Core

## Desktop

Windows 桌面端目前负责：

- QQ / 微信连接
- 会话选择
- 分析范围
- 启动分析
- 打开 Echo Report

Desktop Shell 正在继续重构，最终会逐步加入：

- QQ / 微信独立入口
- 本地数据 / 历史报告管理
- Echo 历史
- 缓存和存储管理

## 开发运行

项目使用 Python `src` layout。

```powershell
cd D:\ChatAnalyzerWorkspace\local-chat-analyzer
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m qq_chat_analyzer.gui
