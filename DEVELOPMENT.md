# 余音 Echo Development Guide

## 1. Project Overview

余音 Echo is a privacy-first local chat analysis tool.

Current GUI / ChatSource product sources:
- QQ Direct DB for desktop session discovery and analysis; bundled QQ / NapCat runtime for connection
- WeChat local database (data directory detection, key acquisition, session analysis)

Current-format JSON / JSONL import capabilities remain in the lower-level pipeline
and the echo-chat local-file CLI, including WeChat detailed JSON / chatlab JSONL.
They are not the removed `LOCAL_FILE` GUI product entry point.

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

### 3.1 Human Initial Setup (new clone)

After cloning the repository, a human developer may create the project
virtual environment:

``` powershell
python -m venv .venv
```

Install the complete development environment from `pyproject.toml`:

``` powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,gui]"
```

All project commands after creation should use the explicit `.venv` interpreter;
shell activation is not required.

Public terminal entrypoints are `echo-chat` (CLI) and `echo-gui` (Desktop).
After installation, developers can launch them without activating the shell:

``` powershell
.\.venv\Scripts\echo-chat.exe --help
.\.venv\Scripts\echo-gui.exe
```

The Python package remains `qq_chat_analyzer`; the distribution name used by
`pip show` remains `qq-chat-analyzer`. No `qqchat` / `qqchat-gui` aliases are registered.

Release version is defined only in `pyproject.toml`. Runtime consumers read the
installed distribution metadata through `qq_chat_analyzer.version`; after a version
change, refresh the editable installation using the setup command above. The
Windows PyInstaller build requires Python 3.11+ to read TOML, rejects stale installed
version metadata, and copies the verified metadata into the frozen application.
It does not require the source checkout to read its version at runtime.

### 3.1.1 Windows Release Build Toolchain

The Windows release build needs the pinned build toolchain, which is not part of
the runtime dependencies. Install it from the same `pyproject.toml` extras:

``` powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,gui,build]"
```

`scripts/build_windows_exe.ps1` runs `<project>\.venv\Scripts\pyinstaller.exe` and
fails closed when it is missing. The versions pinned in the `build` extra are the
toolchain the released frozen artifact is built with, so a release must not be
produced with a different interpreter or an unpinned PyInstaller.

### 3.2 AI Existing Workspace

An AI agent entering an existing working tree must first verify the environment:

``` powershell
Test-Path .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pip --version
```

If `.venv` is missing or dependencies cannot be imported, report an environment
problem. Do not create another environment or install dependencies unless the
task explicitly authorizes environment initialization.

------------------------------------------------------------------------

## 4. Verify Environment

Verify the actual interpreter and pip selected for project commands:

``` powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
.\.venv\Scripts\python.exe -m pip --version
```

If package metadata is needed, query it through the same interpreter:

``` powershell
.\.venv\Scripts\python.exe -m pip show qq-chat-analyzer
```

------------------------------------------------------------------------

## 5. Running Tests

Tests are run in three layers:

- **Focused**: the test file or node directly related to the change;
- **Fast**: daily development regression, excluding `slow_integration` and
  `known_failure`;
- **Full**: complete regression at a phase boundary or before submission.

Run the relevant focused tests first, for example:

``` powershell
.\.venv\Scripts\python.exe -m pytest tests/test_facade.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_facade.py::test_name -q
```

The marker names are defined in `pyproject.toml`; do not replace them with
ad-hoc exclusions. The standard Fast Suite is:

``` powershell
.\.venv\Scripts\python.exe -m pytest -m "not slow_integration and not known_failure" -q
```

The Full Suite is:

``` powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Fast does not replace focused integration tests covered by `slow_integration`.
When a change touches packaging, Chromium rendering, CLI subprocesses,
PowerShell helpers, Windows runtime integration, or a specific WeChat
integration, run the relevant focused integration tests explicitly.

If Windows temporary-directory permission problems appear, pass a local base
directory to the same explicit interpreter:

``` powershell
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-temp
```

Do not commit temporary test directories, test counts, or timing snapshots.

------------------------------------------------------------------------

## 6. Git Workflow

Use feature branches. Before editing, run:

``` powershell
git status --short --branch
```

Identify and preserve existing working-tree changes. Do not use `git restore`,
`git checkout`, or broad cleanup to remove changes whose source is unknown.

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

Do not use `git add .`; stage only explicitly named files. Run
`git diff --check` before completion and confirm the changed-file list stays
within the allowed task scope.

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
- QQ Direct DB adapter converts the transient qq-db-json payload into source-neutral rich messages and ChatMessage;
- WeChat parser converts WeChat detailed JSON/JSONL into ChatMessage;
- parsers must not depend on analysis core or UI layers.

Future API/Desktop interfaces should call Application Service instead of
core modules directly.

Core modules should implement analysis logic and avoid depending on
CLI/Application layers or source-specific types.

## 7.1 Multi-source Input Design Principles

- Use an independent adapter/parser for each supported source format.
- Every parser returns ChatMessage.
- ImportService recognizes the source and routes the file.
- AnalysisApplicationService calls ImportService and keeps the analysis workflow.
- ImportService must reuse existing parsers and must not duplicate parsing logic.
- Core analysis modules only consume ChatMessage.
- Do not duplicate source parsing when adding a new source.
- Do not introduce platform branches in analyzer.py, tokenizer.py, or cleaner.py.
- Confirm real sample fields before choosing the first supported format.

------------------------------------------------------------------------

## 7.2 Current Local Import Pipeline

- ImportRequest describes the input path and optional platform hint.
- ImportOutcome carries ImportResult, ChatMessage, RichMessage and processed_message_count.
- ImportService owns path validation, file discovery, source recognition and adapter/parser routing.
- AnalysisApplicationService obtains messages through ImportService, then applies the final analysis scope.
- Supported formats: qq-db-json, wechat-db-json, detailed-json, chatlab-jsonl,
  and cli-json (a bare array conforming to the WeChat CLI schema).
- echo-chat remains the local-file analysis entry point for these formats. It
  does not provide qce list / qce analyze or import retired QQ file formats.

QQChatExporter / QCE runtime, provider/service, QCE JSON and old QQ JSON/JSONL
compatibility are retired. parser.py and qq_chat_exporter_adapter.py are absent.
Retirement tests and release forbidden checks must remain.

------------------------------------------------------------------------

## 7.3 Current QQ / WeChat Source Integration

The only official QQ product chain is:

```text
NapCat -> Direct DB -> qq_db_adapter -> unified message model -> Analysis
```

- NapCat owns startup/login and local decryption; QQDirectDatabaseImportService
  orchestrates session acquisition and transient cleanup through acquired_session().
- QQDatabaseProvider reads the validated snapshot and materializes qq-db-json;
  qq_db_adapter interprets it into source-neutral RichMessage / ChatMessage.
- QQ acquisition uses epoch seconds. The application scope filter remains the
  final correctness boundary. No QCE export fallback exists.
- WeChat acquisition remains unchanged: epoch-second SQL bounds, all matching
  message shards, global ordering and unlimited acquisition by default.
- CLI delegates local-file analysis to Application services; GUI uses
  ChatAnalyzerFacade. Analysis does not know source formats or runtime tools.

Current architecture and acceptance boundaries are in ARCHITECTURE.md and
docs/HARDENING.md. Earlier QCE integration and acceptance remain historical
records in docs/BUG_JOURNAL.md and docs/superpowers/; their old commands, token
paths and tests are not supported current interfaces.

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


## Source Structure

src/qq_chat_analyzer/
    application/       # application contracts and services
    application/facade.py  # ChatAnalyzerFacade: GUI 唯一业务入口
    analysis/          # Analysis Core v2/v3: reports and analyzers
    presentation/      # view models, formatters, builders
    gui/               # PySide6 GUI MVP
    providers/         # QQ / WeChat data providers
    message.py         # source-neutral ChatMessage model
    wechat_parser.py   # WeChat detailed JSON parsing
    qq_db_adapter.py   # QQ Direct DB payload conversion
    wechat_db_adapter.py         # WeChat DB adapter
    wechat_cli_adapter.py        # WeChat CLI adapter
    smart_profile.py   # Smart Profile orchestration
    detectors/         # robot/template/interactive bot detectors
    cleaner.py         # text cleaning
    tokenizer.py       # tokenization
    analyzer.py        # analysis algorithms
    exporters.py       # local artifact generation
    cli.py             # command line adapter
