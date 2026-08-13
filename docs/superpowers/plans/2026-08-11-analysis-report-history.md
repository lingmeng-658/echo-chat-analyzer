# Analysis Report History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and read metadata-only analysis history without changing the existing analysis chain or storing reports/messages.

**Architecture:** Add a focused JSONL `ReportHistoryManager` in the application result layer. Inject it into `ChatAnalyzerFacade`, save after successful result/view construction, expose list/get through the Facade, and surface only save status in the existing result UI.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, json, uuid, logging, pytest, PySide6.

## Global Constraints

- Do not modify Provider, Adapter/Parser, `ChatMessage`, Scope Filter, Analyzer core, QQ/WeChat connection flows, or stable GUI connection-state logic.
- Do not persist raw messages, message bodies, report details, or full Dashboard snapshots.
- Do not add a database, cache, synchronization, history page, report management, search, deletion, export, or version system.
- Reuse `resources.user_data_dir()` and keep history outside the code/install directory.
- A history failure must never cause a successful analysis to fail.
- Use artificial test data only.
- Follow RED -> GREEN for every production behavior.

---

### Task 1: JSONL history manager

**Files:**
- Create: `src/qq_chat_analyzer/application/report_history.py`
- Modify: `src/qq_chat_analyzer/application/__init__.py`
- Create: `tests/test_report_history.py`

**Interfaces:**
- Produces: `AnalysisHistoryRecord`, `ReportHistoryManager`, and `ReportHistoryWriteError`.
- `ReportHistoryManager.save_analysis(...) -> AnalysisHistoryRecord`
- `ReportHistoryManager.list_records() -> tuple[AnalysisHistoryRecord, ...]`
- `ReportHistoryManager.get_record(analysis_id: str) -> AnalysisHistoryRecord | None`

- [ ] **Step 1: Write failing persistence tests**

  Add real temporary-file tests for missing/empty reads, one save/read/get,
  multiple appends in newest-first order, and exact serialized keys. Construct
  no message/report objects; assert forbidden keys such as `messages`, `text`,
  `content`, `reports`, `top_words`, and filesystem paths are absent.

- [ ] **Step 2: Verify RED**

  Run `pytest -q tests/test_report_history.py` and confirm import/API failures
  occur because the manager does not exist.

- [ ] **Step 3: Implement the minimal valid JSONL path**

  Implement a frozen record with private log representation for session fields,
  lazy default path `<user_data_dir>/history/analysis_history.jsonl`, explicit
  allowlist serialization, UUID generation, UTC ISO timestamps, append, reverse
  reading, and ID lookup.

- [ ] **Step 4: Verify GREEN**

  Run `pytest -q tests/test_report_history.py` and confirm the valid-path tests
  pass.

- [ ] **Step 5: Add failing corruption/error tests**

  Add tests for malformed JSON, invalid required fields, save against a corrupt
  file, and an unwritable target. Assert reads return empty and log; assert
  unsafe writes raise `ReportHistoryWriteError` without altering the file.

- [ ] **Step 6: Implement corruption containment**

  Add strict internal decoding/validation. Catch read-side parse/I/O failures in
  `list_records()` and return `()`, while `save_analysis()` wraps validation and
  I/O failures in `ReportHistoryWriteError`.

- [ ] **Step 7: Verify manager tests**

  Run `pytest -q tests/test_report_history.py`.

### Task 2: Facade result-layer integration and history reads

**Files:**
- Modify: `src/qq_chat_analyzer/application/facade.py`
- Modify: `tests/test_facade.py`

**Interfaces:**
- Consumes: `ReportHistoryManager.save_analysis`, `.list_records`, `.get_record`.
- Extends `AnalysisOutcome` with backward-compatible defaults:
  `history_saved: bool | None = None` and
  `history_record_id: str | None = None`.
- Produces: `ChatAnalyzerFacade.list_analysis_history()` and
  `ChatAnalyzerFacade.get_analysis_history(analysis_id)`.

- [ ] **Step 1: Write failing Facade integration tests**

  Run successful QQ and WeChat analyses with a real temporary history manager.
  Assert one record contains the source/session, processed message count, scope
  mode/dates, and no report/message data. Assert the returned view/result stay
  the existing objects and `history_saved` is true.

- [ ] **Step 2: Verify RED**

  Run only the new `tests/test_facade.py` history cases and confirm failure due
  to missing injection/outcome fields.

- [ ] **Step 3: Implement post-result saving**

  Add optional constructor injection. After `_build_view()` succeeds, capture
  `report_generated_at`, save allowlisted metadata, and return the existing
  outcome plus status/ID. Do not alter request construction, analysis execution,
  source export, scope resolution, or progress/cancellation logic.

- [ ] **Step 4: Verify GREEN**

  Run the new successful-save Facade cases.

- [ ] **Step 5: Write failing non-fatal and read API tests**

  Add a failing saver and assert analysis still returns its view/result with
  `history_saved=False`. Assert an analysis exception never writes. Assert
  no-manager callers retain `None`. Assert Facade list/get return manager data
  and absent IDs return `None`.

- [ ] **Step 6: Implement failure isolation and read delegation**

  Catch/log history save exceptions outside translated analysis errors; return
  the outcome normally. Add list/get delegation with empty/`None` behavior when
  no manager is injected.

- [ ] **Step 7: Verify Facade regressions**

  Run `pytest -q tests/test_facade.py tests/test_facade_wechat_setup.py`.

### Task 3: Desktop wiring and minimal GUI status

**Files:**
- Modify: `src/qq_chat_analyzer/gui/app.py`
- Modify: `src/qq_chat_analyzer/gui/main_window.py`
- Modify: `tests/test_gui.py`
- Modify: `tests/test_desktop_runtime.py` only if the composition-root contract is already tested there.

**Interfaces:**
- Consumes: `AnalysisOutcome.history_saved`.
- Production Facade receives `ReportHistoryManager()` with lazy path resolution.

- [ ] **Step 1: Write failing GUI status tests**

  Extend real `MainWindow.show_outcome()` tests to assert: saved -> `分析已保存`;
  failed save -> `分析完成，但历史记录保存失败。`; absent status -> old
  `分析完成`. In every branch assert the Dashboard is selected/rendered.

- [ ] **Step 2: Verify RED**

  Run the new GUI cases and confirm the saved/failed branches show the old text.

- [ ] **Step 3: Implement minimal status selection**

  Keep the existing rendering/page transition unchanged, then select one of the
  three status strings from the outcome field. Add no widget or history page.

- [ ] **Step 4: Wire the manager**

  Construct `ReportHistoryManager()` in `gui.app.build_facade()` and inject it.
  The constructor must perform no filesystem I/O so desktop startup behavior is
  unchanged.

- [ ] **Step 5: Verify GUI/application regressions**

  Run `pytest -q tests/test_gui.py tests/test_desktop_runtime.py`.

### Task 4: Full verification and scope audit

**Files:**
- Modify: `ARCHITECTURE.md` only after all implementation/tests pass, with a
  small result-layer history note and the metadata-only boundary.

- [ ] **Step 1: Run focused Phase 2 suite**

  Run `pytest -q tests/test_report_history.py tests/test_facade.py tests/test_gui.py tests/test_desktop_runtime.py`.

- [ ] **Step 2: Run source/scope regressions**

  Run `pytest -q tests/test_application_service.py tests/test_scope_filter.py tests/test_wechat_application_service.py`.

- [ ] **Step 3: Run full suite**

  Run `pytest` and record exact pass/fail counts, including any demonstrably
  pre-existing failure without changing forbidden Analyzer code.

- [ ] **Step 4: Validate patch formatting**

  Run `git diff --check` and require exit code 0.

- [ ] **Step 5: Audit forbidden paths and privacy**

  Inspect `git status --short` and `git diff --name-only`; separate pre-existing
  Phase 1 edits from Phase 2 edits, confirm no prohibited module changed in
  Phase 2, and inspect history serialization for raw message/report fields.

- [ ] **Step 6: Report without committing**

  Report modified/new files, storage format/path, test results,
  `git diff --check`, any pre-existing unrelated failure, and explicit
  confirmation of untouched prohibited modules. Do not stage or commit the
  user's existing uncommitted Phase 1 work.

