# Development Guide

## 1. Project Overview

Local Chat Analyzer is a privacy-first local chat analysis tool.

Current supported source: - QQChatExporter exported JSON/JSONL files

The project is designed to: - run locally; - keep chat data on the
user's machine; - separate analysis core from user interfaces; - support
future additional chat sources.

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

    CLI Adapter

        ↓

    Application Service

        ↓

    Core Analysis Modules

        ↓

    Exporters

CLI handles: - command arguments; - user interaction; - displaying
results; - exit codes.

CLI should not contain analysis workflow.

Application Service handles: - analysis workflow; - calling core
modules; - DTO conversion; - application-level errors.

Future API/Desktop interfaces should call Application Service instead of
core modules directly.

Core modules should implement analysis logic and avoid depending on
CLI/Application layers.

------------------------------------------------------------------------

## 8. Privacy Rules

Never commit: - real chat JSON/JSONL files; - QQ group numbers; -
usernames/nicknames; - API keys; - tokens; - local paths.

Tests must use fictional data only.

------------------------------------------------------------------------

Current stable main branch:
- Architecture: Phase 5.2A completed
- Tests: 177 passed

for current progress and next steps.

## Source Structure

src/qq_chat_analyzer/
    application/    # application contracts and service
    parser.py       # message parsing
    cleaner.py      # text cleaning
    tokenizer.py    # tokenization
    analyzer.py     # analysis algorithms
    exporters.py    # local artifact generation
    cli.py          # command line adapter