# Local Chat Analyzer Project Status

## 项目定位

Local Chat Analyzer 是一个隐私优先、本地运行的聊天记录分析工具。

目标：

-   读取本地导出的聊天记录；
-   完成本地文本分析；
-   生成词频、词云、发送者关联等统计结果；
-   未来支持更多聊天来源、API、桌面界面和 AI 辅助分析。

隐私原则：

-   原始聊天记录只在用户本机处理；
-   测试禁止使用真实聊天数据；
-   不上传完整聊天内容到云端服务。

------------------------------------------------------------------------

# Current Baseline

当前稳定分支：

main

当前基线 commit：

04782b1

当前工作区状态：

- Phase 5.2A Application Service 已完成
- Phase 5.2B ChatMessage 中性消息模型已完成
- ChatMessage v2 基础字段已完成
- 微信 detailed JSON 第一版支持已完成
- 微信 CipherTalk chatlab JSONL 支持已完成
- ImportService 已支持 chatlab JSONL 自动路由到微信 parser
- 多来源分析流程验证已完成
- Phase 6.2 Import Pipeline 基础架构已完成
- AnalysisApplicationService 已接入 ImportService
- QQChatExporter Provider 已完成
- QQChatExporter Adapter 已完成
- QQ 导出→分析闭环已完成
- CLI qce 入口已完成
- QQChatExporter 集成真实环境验收已完成
- v0.7.0 Desktop MVP Foundation 已完成
- QQ / 微信多来源支持
- 微信数据库 Provider
- Analysis Core v2/v3 与 Analysis Reports
- Presentation Layer
- ChatAnalyzerFacade
- PySide6 GUI（Dashboard 展示）

最近完整 pytest：

528 tests passing

历史状态：Phase 5.2 阶段曾出现 196 passed + 1 个与 .venv editable 安装指向相关的环境失败。

当前版本目标：

v0.7.0 Desktop MVP Foundation

------------------------------------------------------------------------

# Current User Flow

QQ 导出→分析闭环已可通过 CLI 使用：

qqchat qce list

↓

选择 group_code

↓

qqchat qce analyze --group <group_code>

↓

自动导出并进入已有分析流程

------------------------------------------------------------------------

# Real Acceptance

QQChatExporter 集成已在真实环境完成验收：

- QQChatExporter 桌面版正常运行；
- Provider 成功读取真实 security.json token；
- qqchat qce list 成功获取真实 QQ 群列表；
- qqchat qce analyze --group <group_code> 成功完成：
  QQ 导出 → QCE JSON → Adapter → ChatMessage → 分析核心 → 输出文件；
- 真实群聊数据测试成功；
- 当前测试基线：528 tests passing。

------------------------------------------------------------------------

# Current Limitations

当前已知限制：

- 不自动启动 QCE，需要用户先启动并登录 QQChatExporter 桌面版；
- 不支持分片 manifest/chunks；
- 只支持群聊；
- 只支持 JSON；
- 非文本消息暂未进入分析；

------------------------------------------------------------------------

# Architecture Overview

当前系统架构详见 ARCHITECTURE.md。

本文档不再复制架构图与分层职责副本，以 ARCHITECTURE.md 作为唯一架构事实来源。

------------------------------------------------------------------------

# Completed Work# Completed Work

## Analysis Core

已完成：

-   QQChatExporter JSON/JSONL parsing
-   Message cleaning
-   Tokenization
-   Word frequency analysis
-   Word cloud generation
-   Speaker statistics

## Smart Filtering

已完成：

-   Robot Detector
-   Interactive Bot Detector
-   Template Detector
-   Template fingerprint:
    -   {number}
    -   {id}
    -   {user}
    -   {url}
-   FilterPipeline
-   Decision Engine
-   Stopword profile

## Phase 5.1 Application Architecture

已完成：

### DTO Contract

建立：

-   AnalysisRequestDTO
-   AnalysisResultDTO
-   AnalysisStatus
-   ArtifactDTO
-   WordFrequencyDTO

### Application Service

建立：

AnalysisApplicationService

负责：

-   输入校验
-   文件发现
-   Parser 调用
-   Smart Profile 调用
-   Cleaner/Tokenizer 调用
-   Analyzer 调用
-   Exporter 调用
-   DTO 转换

### CLI Adapter

完成：

CLI 不再直接负责分析流程。

当前：

CLI ↓ AnalysisApplicationService ↓ Analysis Core

## Phase 5.2A-0 Exporter Import Safety

已完成：

解决 matplotlib 全局 backend 副作用。

修改：

-   使用 Figure + FigureCanvasAgg；
-   不在 import 时修改 matplotlib backend；
-   移除 pyplot 依赖。

------------------------------------------------------------------------

## Phase 5.2A Application Public Entry

已完成：

-   Application Service 已成为稳定公开入口；
-   可直接使用：

from qq_chat_analyzer.application import AnalysisApplicationService

-   CLI 与核心分析逻辑解耦；
-   原有 analysis_service 导入路径仍可用。

------------------------------------------------------------------------

## Phase 5.2B ChatMessage 中性消息模型

已完成：

新增：

-   src/qq_chat_analyzer/message.py

统一模型：

-   ChatMessage

说明：

-   timestamp、sender、message_type、text 是分析必需字段；
-   platform、source_type 保留来源信息；
-   已有 QQ parser 兼容旧入口 ParsedMessage。

------------------------------------------------------------------------

## WeChat detailed JSON 第一版支持

已完成：

新增：

-   src/qq_chat_analyzer/wechat_parser.py

能力：

-   识别微信 detailed JSON 导出；
-   将“文本消息”“引用消息”转换为 ChatMessage；
-   设置 platform="wechat"；
-   保留 source_type 原始类型；
-   接入 AnalysisApplicationService；
-   进入现有 smart_profile、cleaner、tokenizer、analyzer 流程；
-   不修改 analyzer.py、tokenizer.py、cleaner.py；
-   新增测试：
    -   tests/test_wechat_parser.py
    -   tests/test_wechat_application_service.py

------------------------------------------------------------------------

## 多来源分析流程验证

已完成：

-   QQ 输入 → ChatMessage；
-   微信 detailed JSON → ChatMessage；
-   两者进入同一个 AnalysisApplicationService；
-   输出 AnalysisResultDTO、CSV 导出、PNG 导出的格式保持一致。

------------------------------------------------------------------------

## ChatMessage v2 基础字段

已完成：

-   新增字段：message_id、sender_id、conversation_id、is_system、recalled；
-   所有新增字段带默认值；
-   ChatMessage 保持 frozen=True、slots=True；
-   QQ parser 与微信 parser 已填充 message_id、sender_id、is_system、recalled；
-   conversation_id 保持 None，待会话上下文接入。

------------------------------------------------------------------------

## Phase 6.1 Application 产品模型

已完成：

-   AnalysisTask：表达一次用户分析任务；
-   ExportConfig：隐私优先的导出范围配置；
-   ImportResult：公开的导入摘要，不保存聊天正文和消息列表。

------------------------------------------------------------------------

## Phase 6.2 Import Pipeline

已完成：

-   ImportRequest：输入路径 + 可选平台，平台为 None 时自动检测；
-   ImportOutcome：内部管道对象，携带 ImportResult、ChatMessage 和原始消息数；
-   ImportService：负责路径校验、文件发现、来源识别、调用现有 parser；
-   AnalysisApplicationService 已接入 ImportService；
-   已移除 AnalysisApplicationService 中旧的文件发现与解析 helper；
-   未修改 parser.py、wechat_parser.py、ChatMessage、CLI。

------------------------------------------------------------------------

## QQChatExporter 集成

已完成：

-   QQChatExporter Provider：HTTP 客户端，负责健康检查、token 读取、群列表、导出任务创建与轮询；
-   QQChatExporter Adapter：识别 QCE 单文件 JSON，转换为 ChatMessage；
-   QQExportImportService：导出→导入编排层，提供 export_only() 与 list_groups()；
-   CLI qce 入口：qqchat qce list / qqchat qce analyze --group <group_code>；
-   CLI 通过 Application 层调用，不直接依赖 Provider；
-   未修改 parser.py、Provider 内部逻辑、ImportService 核心路径。

------------------------------------------------------------------------

# Current Task

## 当前状态

当前没有进行中的实现任务。

最近完成：

-   v0.7.0 Desktop MVP Foundation；
-   QQ / 微信多来源支持与微信数据库 Provider；
-   Analysis Core v2/v3 与 Analysis Reports；
-   Presentation Layer；
-   ChatAnalyzerFacade；
-   PySide6 GUI（Dashboard 展示）；
-   全量测试 528 tests passing。

下一阶段：后续产品化方向（不提前展开实现细节）。

-   Windows 可执行打包；
-   普通用户安装流程；
-   依赖封装；
-   报告展示增强。

待办（不纳入当前实现范围）：

-   QCE 自动启动：未实现；
-   分片 manifest/chunks 支持：未实现；
-   AI、API 接入：未实现。

------------------------------------------------------------------------

# Roadmap

## Phase 5.2 Architecture Stabilization

目标：

完善 Application 边界。

状态：

-   Public Service Entry 已完成；
-   Message Model 中性化已完成；
-   文档和 metadata 整理：本次更新。

## Phase 6 Multi-source Support

目标：

支持新的聊天来源。

状态：

- 微信 detailed JSON 第一版已完成；
- 微信 CipherTalk chatlab JSONL 已完成；
- ImportService 已支持多格式来源识别和 parser 路由；
- 其他来源格式待调研。

设计原则：

- 不同来源只负责转换成统一消息模型；
- 分析核心不关心 QQ、微信或其他来源；
- 新增来源使用独立 parser；
- 不复制 QQ parser；
- 不引入微信专用模型到核心分析层。

## Phase 7 Productization

目标：

让普通用户无需 Python/CLI。

可能方向：

-   API
-   Desktop UI
-   Web Interface

## Phase 8 AI Analysis

目标：

基于本地统计结果提供智能分析。

原则：

-   AI 不直接读取完整聊天记录；
-   优先本地模型；
-   云端服务只接收最小必要信息。

------------------------------------------------------------------------

# Development Rules

## 开发流程

所有重要功能：

Design ↓ RED Test ↓ GREEN Implementation ↓ Full Test ↓ Review ↓ PR

## 不提前设计

除非真实需求出现，否则不要提前引入：

-   DI Container
-   Factory System
-   Ports and Adapters
-   Repository Layer

## 测试原则

-   使用虚构数据；
-   不读取真实聊天记录；
-   不上传聊天内容。

## Git原则

-   小范围提交；
-   明确文件列表；
-   不使用 git add .；
-   功能完成后再合并。

------------------------------------------------------------------------

# Future Notes

微信接入现状：

-   微信 detailed JSON 已支持；
-   微信 JSONL 未支持，不纳入本次范围。

后续新增来源时：

1.  继续使用 ChatMessage 作为统一消息模型；
2.  为每个来源建立独立 parser；
3.  不要直接复制 QQ parser 到微信 parser；
4.  不要在 analyzer、tokenizer、cleaner 中引入平台判断；
5.  先按真实样例确认字段，再决定第一版支持格式。
