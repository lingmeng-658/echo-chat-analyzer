# 余音 Echo Development Guide

## 1. Project Overview

余音 Echo is a privacy-first local chat analysis tool.

Current supported sources:
- QQChatExporter desktop runtime (QQ login, session analysis)
- WeChat local database (data directory detection, key acquisition, session analysis)
- WeChat CipherTalk detailed JSON / chatlab JSONL exports
- Local exported JSON / JSONL files

The project is designed to:
- run locally;
- keep chat data on the user's machine;
- separate analysis core from user interfaces;
- convert each source into ChatMessage;
- support future additional chat sources without changing the analysis core.

------------------------------------------------------------------------

## 2. Development Environment

Requirements: - Windows (primary development platform) - Python 3.x -
Git

The project uses a Python virtual environment:

    .venv/

The virtual environment is local only and should not be committed.

------------------------------------------------------------------------

## 3. Initial Setup

After cloning the repository:

Create virtual environment:

``` powershell
python -m venv .venv
```

Activate environment:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Install project:

``` powershell
pip install -e .
```

Editable installation allows local source changes to be used
immediately.

------------------------------------------------------------------------

## 4. Verify Environment

Check Python:

``` powershell
where python
```

Check pip:

``` powershell
where pip
```

Check installed project:

``` powershell
pip show qq-chat-analyzer
```

------------------------------------------------------------------------

## 5. Running Tests

Run all tests:

``` powershell
pytest
```

If Windows temporary directory permission problems appear:

``` powershell
pytest --basetemp=.pytest-temp
```

Do not commit temporary test directories.

------------------------------------------------------------------------

## 6. Git Workflow

Use feature branches.

Workflow:

    Create branch
        ↓
    Implement small change
        ↓
    Run tests
        ↓
    git diff --check
        ↓
    Commit
        ↓
    Push branch
        ↓
    Create Pull Request
        ↓
    Review
        ↓
    Squash merge

Do not commit: - real chat data; - generated outputs; - local
configuration; - virtual environments.

------------------------------------------------------------------------

## 7. Architecture Rules

完整架构设计见 ARCHITECTURE.md（唯一架构事实来源）。本文档只保留与开发流程相关的规则，不再复制架构图。

CLI handles:
- command arguments;
- user interaction;
- displaying results;
- exit codes.

CLI should not contain analysis workflow.

Application Service handles:
- analysis workflow;
- calling core modules;
- DTO conversion;
- application-level errors.

ImportService handles:
- file discovery and source recognition;
- routing each input file to its source parser;
- returning ChatMessage, ImportResult, and raw message count.

Source parsers:
- QQ parser converts QQChatExporter JSON/JSONL into ChatMessage;
- WeChat parser converts WeChat detailed JSON/JSONL into ChatMessage;
- parsers must not depend on analysis core or UI layers.

Future API/Desktop interfaces should call Application Service instead of
core modules directly.

Core modules should implement analysis logic and avoid depending on
CLI/Application layers or source-specific types.

## 7.1 Multi-source Input Design Principles

- Use one independent parser per chat source.
- Every parser returns ChatMessage.
- ImportService recognizes the source and routes the file.
- AnalysisApplicationService calls ImportService and keeps the analysis workflow.
- ImportService must reuse existing parsers and must not duplicate parsing logic.
- Core analysis modules only consume ChatMessage.
- Do not copy the QQ parser when adding a new source.
- Do not introduce platform branches in analyzer.py, tokenizer.py, or cleaner.py.
- Confirm real sample fields before choosing the first supported format.

------------------------------------------------------------------------

## 7.2 Phase 6.2 Import Pipeline

Completed:

- ImportRequest describes the input path and optional platform hint.
- ImportOutcome is an internal pipeline result carrying ImportResult, ChatMessage, and processed_message_count.
- ImportService owns path validation, file discovery, source recognition, and parser routing.
- AnalysisApplicationService now obtains ChatMessage through ImportService.
- Old file discovery and parsing helpers inside AnalysisApplicationService were removed.
- Parser modules, ChatMessage, and CLI were not modified.

Next phase:

This research phase is complete: the QQChatExporter data source integration
described in section 7.3 is implemented and accepted against the real QCE
desktop application.

------------------------------------------------------------------------

## 7.3 QQChatExporter Data Source Integration

Completed:

- QCE HTTP Provider: health check, security.json token, group list, export task creation and polling.
- QCE JSON Adapter: recognizes single-file QCE JSON exports and converts text/reply messages to ChatMessage.
- QQExportImportService: orchestrates export, then import through the existing ImportService; exposes export_only() and list_groups().
- CLI qce commands: `qqchat qce list` and `qqchat qce analyze --group <group_code>`.
- CLI reaches the QCE flow only through the Application layer; it does not construct a provider directly.

Module responsibilities in the QCE flow:

- Provider: external data acquisition only. Talks to the QCE HTTP API, manages
  export tasks, and returns a local QCE JSON path.
- Adapter: format conversion only. Recognizes QCE single-file JSON and converts
  it to ChatMessage.
- Application layer: business orchestration. QQExportImportService ties
  export, then import together; the CLI never calls Provider or Adapter directly.
- CLI: user interaction only. Parses commands and delegates to Application
  layer services.

Architecture rules for this integration:

- Provider only fetches data from the QCE HTTP service.
- Adapter only converts QCE JSON to ChatMessage.
- Application layer owns orchestration.
- CLI and future GUI call Application layer services.
- parser.py, provider internals, and ImportService core routing were not modified.

Real QCE desktop acceptance:

- QCE desktop app ran normally on the acceptance machine.
- Provider read the real token from the desktop config directory
  `%LOCALAPPDATA%\QQChatExporter\.qce-config\security.json`.
- `qqchat qce list` returned the real QQ group list.
- `qqchat qce analyze --group <group_code>` completed the full flow:
  QQ export -> QCE JSON -> Adapter -> ChatMessage -> analysis -> output files.
- Real group chat data was processed on the user's machine.

Token path compatibility fix:

- `QCE_CONFIG_DIR` keeps the highest priority.
- Windows desktop default path `%LOCALAPPDATA%\QQChatExporter\.qce-config\security.json`
  was added ahead of the legacy fallback.
- The legacy `~/.qq-chat-exporter/security.json` fallback remains supported.
- Candidate resolution is covered by provider tests.

Current limits:

- Desktop QQ flow starts the bundled runtime; the CLI `qce` commands still require a running service.
- Chunked manifest/chunks exports are not supported.
- Group chat only.
- JSON format only.
- Non-text messages are skipped for analysis.
- Desktop GUI MVP is available.


## 7.4 GUI / Facade / Presentation 开发规则

GUI 开发规则：

- GUI 只能通过 ChatAnalyzerFacade 调用业务能力；
- GUI 不得直接调用 Provider、Parser、Adapter 或 Analysis Core；
- GUI 不包含数据解析、分析算法与过滤规则；
- 报告展示控件保持只读（setEditTriggers(NoEditTriggers)），但保留选中与复制。

Facade 规则：

- ChatAnalyzerFacade 是 GUI 的唯一业务入口（application/facade.py）；
- Facade 负责来源分派、配置整理、Service 调度与异常归一（FacadeError）；
- GUI 只展示 FacadeError.public_message，不展示 traceback；
- Facade 通过依赖注入构造，测试可传入 stub。

Presentation 规则：

- Presentation 只负责展示模型转换与格式化，不重新计算分析结果；
- 需要的统计数字必须由 Analysis Core 的 analyzer 产出；
- 展示名称通过 AnalysisRequestDTO.speaker_names / conversation_names 注入，
  不在展示层做来源判断。

------------------------------------------------------------------------

## 8. Privacy Rules

Never commit:
- real QQ/WeChat chat JSON/JSONL files;
- QQ group numbers;
- usernames/nicknames;
- API keys;
- tokens;
- local paths.

Tests must use fictional data only.

------------------------------------------------------------------------

## 9. Adding a New Chat Source

1. Read the real export sample and confirm its field structure.
2. Choose only the first supported format; do not support all variants in advance.
3. Add an independent parser module that returns ChatMessage.
4. Write fictional-data tests before implementation.
5. Route the new parser through AnalysisApplicationService.
6. Run the full test suite.
7. Do not modify analyzer.py, tokenizer.py, or cleaner.py.

------------------------------------------------------------------------

Current working state:
- Architecture: 见 ARCHITECTURE.md（唯一架构事实来源）
- Product: 余音 Echo
- Sources: QQ（QCE Provider / Adapter、登录闭环）、微信（数据库 Provider / CLI Provider）、本地导出文件
- Application: ImportService, AnalysisApplicationService, QQ/WeChatExportImportService, ChatAnalyzerFacade
- Analysis: Analysis Core v2/v3（activity / length / profile / conversation reports）
- Presentation: DashboardBuilder -> DashboardView
- GUI: PySide6 MVP（AnalysisPage / DashboardPage；会话搜索排序、时间范围、QQ 登录引导）
- Tests: 905 passed + 1 个已知失败（ConversationAnalyzer timestamp=0）
- Next phase: Windows packaging, normal-user install flow, report presentation enhancements

See PROJECT_STATUS.md for current progress and next steps.

## Source Structure

src/qq_chat_analyzer/
    application/       # application contracts and services
    application/facade.py  # ChatAnalyzerFacade: GUI 唯一业务入口
    analysis/          # Analysis Core v2/v3: reports and analyzers
    presentation/      # view models, formatters, builders
    gui/               # PySide6 GUI MVP
    providers/         # QQ / WeChat data providers
    message.py         # source-neutral ChatMessage model
    parser.py          # QQChatExporter message parsing
    wechat_parser.py   # WeChat detailed JSON parsing
    qq_chat_exporter_adapter.py  # QCE JSON adapter
    wechat_db_adapter.py         # WeChat DB adapter
    wechat_cli_adapter.py        # WeChat CLI adapter
    smart_profile.py   # Smart Profile orchestration
    detectors/         # robot/template/interactive bot detectors
    cleaner.py         # text cleaning
    tokenizer.py       # tokenization
    analyzer.py        # analysis algorithms
    exporters.py       # local artifact generation
    cli.py             # command line adapter
