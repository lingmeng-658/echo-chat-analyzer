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

282694a

当前工作区状态：

-   Phase 5.2A Application Service 已完成
-   Phase 5.2B ChatMessage 中性消息模型已完成
-   微信 detailed JSON 第一版支持已完成
-   多来源分析流程验证已完成
-   微信接入相关改动尚未提交到 main

最近完整 pytest：

196 passed

1 failed

失败项：

test_cli.py::test_console_script_and_module_help_are_consistent

原因：当前 .venv 的 editable 安装指向 D:\Word cloud，qqchat.exe 运行的是旧包；与微信接入无关。

当前版本目标：

v0.6.0 Multi-Source v1

------------------------------------------------------------------------

# Architecture Overview

当前架构：

QQ JSON/JSONL          WeChat detailed JSON

↓

QQ Parser / WeChat Parser

↓

统一消息模型 ChatMessage

↓

AnalysisApplicationService

↓

Core Analysis Pipeline

↓

Exporter

依赖方向：

CLI ↓ Application ↓ Parser / Cleaner / Tokenizer / Analyzer / Exporter

输入方向：

来源 Parser ↓ ChatMessage ↓ Application ↓ Core Analysis

原则：

-   Core 模块不能依赖 CLI；
-   Core 模块不能依赖 Application；
-   Application 负责业务流程编排；
-   CLI 只负责用户交互和参数转换。
-   来源 Parser 只负责把来源消息转换为 ChatMessage；
-   核心分析层不关心 QQ、微信或其他来源的具体结构。

------------------------------------------------------------------------

# Completed Work

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

# Current Task

## 当前状态

当前没有进行中的实现任务。

最近完成：

-   Phase 5.2A Application Service；
-   Phase 5.2B ChatMessage；
-   微信 detailed JSON 第一版；
-   多来源分析流程验证。

待办（不纳入当前实现范围）：

-   微信 JSONL 支持：未实现，后续另行设计；
-   其他聊天来源格式：待真实样例确认后再决定。

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

-   微信 detailed JSON 第一版已完成；
-   微信 JSONL 待后续；
-   其他来源格式待调研。

设计原则：

-   不同来源只负责转换成统一消息模型；
-   分析核心不关心 QQ、微信或其他来源；
-   新增来源使用独立 parser；
-   不复制 QQ parser；
-   不引入微信专用模型到核心分析层。

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
