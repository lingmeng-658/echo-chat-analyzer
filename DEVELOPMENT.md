# Development Guide

## 1. Project Overview

Local Chat Analyzer is a privacy-first local chat analysis tool.

Current supported sources:
- QQChatExporter exported JSON/JSONL files
- WeChat CipherTalk detailed JSON exports (first version)

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

Current architecture:

    Input sources (QQ JSON/JSONL, WeChat detailed JSON)

        ↓

    Source parsers (QQ parser / WeChat parser)

        ↓

    ChatMessage

        ↓

    ImportService

        ↓

    Application Service

        ↓

    Core Analysis Modules

        ↓

    Exporters

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
- WeChat parser converts WeChat detailed JSON into ChatMessage;
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
- WeChat JSONL is not supported in the current version.

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

- Research QQChatExporter and CipherTalk data import integration.
- Analyze export flows and output formats.
- Design Export Adapter boundaries.
- Design user-facing selection flow: QQ/WeChat, group/private, time range, and privacy options.

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
- Architecture: Phase 6.2 Import Pipeline integrated into AnalysisApplicationService
- Models: AnalysisTask, ExportConfig, ImportResult, ImportRequest, ImportOutcome, ImportService
- ChatMessage: v2 fields added and populated by QQ/WeChat parsers
- Tests: 221 passed
- Next phase: QQChatExporter / CipherTalk import adapter research and design

See PROJECT_STATUS.md for current progress and next steps.

## Source Structure

src/qq_chat_analyzer/
    application/       # application contracts and service
    message.py         # source-neutral ChatMessage model
    parser.py          # QQChatExporter message parsing
    wechat_parser.py   # WeChat detailed JSON parsing
    smart_profile.py   # Smart Profile orchestration
    detectors/         # robot/template/interactive bot detectors
    cleaner.py         # text cleaning
    tokenizer.py       # tokenization
    analyzer.py        # analysis algorithms
    exporters.py       # local artifact generation
    cli.py             # command line adapter
