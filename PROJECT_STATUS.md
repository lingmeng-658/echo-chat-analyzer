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

当前 commit：

36b314a

测试状态：

176 passed

当前版本目标：

v0.5.0 Analysis Core Complete

------------------------------------------------------------------------

# Architecture Overview

当前架构：

CLI

↓

Application Service

↓

Core Analysis Modules

↓

Exporter

依赖方向：

CLI ↓ Application ↓ Parser / Cleaner / Tokenizer / Analyzer / Exporter

原则：

-   Core 模块不能依赖 CLI；
-   Core 模块不能依赖 Application；
-   Application 负责业务流程编排；
-   CLI 只负责用户交互和参数转换。

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

# Current Task

## Phase 5.2A Application Public Entry

目标：

让 Application Service 成为稳定公开入口。

当前希望：

从：

from qq_chat_analyzer.application.analysis_service import
AnalysisApplicationService

变为：

from qq_chat_analyzer.application import AnalysisApplicationService

计划修改：

-   application/**init**.py
-   tests/test_application_public_api.py

禁止扩大范围：

不要修改：

-   CLI
-   AnalysisApplicationService 实现
-   DTO
-   Errors
-   Core modules

------------------------------------------------------------------------

# Roadmap

## Phase 5.2 Architecture Stabilization

目标：

完善 Application 边界。

包括：

-   Public Service Entry
-   Message Model 中性化
-   文档和 metadata 整理

## Phase 6 Multi-source Support

目标：

支持新的聊天来源。

重点：

微信聊天记录读取。

设计原则：

不同来源只负责转换成统一消息模型。

分析核心不关心：

-   QQ
-   微信
-   其他来源

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

微信接入前：

需要先完成：

1.  Application Public Entry
2.  Message Model 中性化

不要直接复制 QQ Parser 到微信 Parser。

目标架构：

QQ Reader\
\
Unified Message Model \| \| AnalysisApplicationService \| \| Analysis
Core \| \| Result DTO

WeChat Reader
