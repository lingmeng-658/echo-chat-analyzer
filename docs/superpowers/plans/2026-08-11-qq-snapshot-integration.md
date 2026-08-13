# QQ Snapshot Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate QQ exports with `ChatDataSnapshotManager` while preserving the existing Provider → ImportService → Parser → ChatMessage → analysis chain.

**Architecture:** `ChatDataSnapshotManager` owns latest-available lookup and validation. `QQExportImportService` orchestrates reuse or Provider export and returns acquisition metadata while its existing `execute()` and `export_only()` entry points remain available. Facade passes snapshot metadata to history and the existing result status without changing WeChat behavior.

**Tech Stack:** Python 3.10+, frozen dataclasses, JSON/JSONL, pathlib, pytest.

## Global Constraints

- Do not modify Provider interfaces or implementations, `ChatMessage`, Parser, Analyzer, Scope Filter, WeChat flow, or QQ connection flow.
- Stop reading the legacy `metadata.json` absolute-path cache; do not migrate or delete it.
- `ChatDataSnapshotManager` is the only snapshot query, creation, validation, and cleanup authority.
- Snapshot failure must not block analysis, and all analysis paths must continue through `ImportService`.
- Do not implement cleanup policy, incremental sync, freshness detection, or complex GUI.

---

### Task 1: Latest available snapshot query

**Files:**
- Modify: `src/qq_chat_analyzer/application/chat_data_snapshot.py`
- Test: `tests/test_chat_data_snapshot.py`

**Interfaces:**
- Produces: `ChatDataSnapshotManager.find_latest_available(*, source, session_id, session_type) -> SnapshotValidation | None`
- Guarantees: newest-first, exact source/session/type match, only `AVAILABLE` validation returned.

- [ ] **Step 1: Write failing tests** for newest matching snapshot, session type mismatch, and invalid payload exclusion.
- [ ] **Step 2: Run** `python -m pytest -q tests/test_chat_data_snapshot.py` and confirm missing-method failures.
- [ ] **Step 3: Implement** the method by composing `list_snapshots()` and `validate_snapshot()`; add no file parsing to the manager.
- [ ] **Step 4: Re-run** the focused tests and confirm green.

### Task 2: Replace legacy QQ cache with Snapshot acquisition

**Files:**
- Modify: `src/qq_chat_analyzer/application/qq_export_import_service.py`
- Modify: `src/qq_chat_analyzer/application/__init__.py`
- Test: `tests/test_qq_export_import_service.py`
- Test: `tests/test_application_public_api.py`

**Interfaces:**
- Produces: `QQExportAcquisition(payload_path, snapshot_id, acquired_at, reused_snapshot)`.
- Produces: `QQExportImportRequest.force_refresh: bool = False`.
- Produces: `QQExportImportService.acquire_export(request) -> QQExportAcquisition`.
- Preserves: `execute(request) -> ImportOutcome` and `export_only(request) -> Path`.

- [ ] **Step 1: Replace legacy-cache expectations with failing tests** for first snapshot creation, second-call reuse, force refresh, missing/corrupt snapshot fallback, metadata extraction, and save-failure fallback.
- [ ] **Step 2: Run** the QQ service tests and verify the new API/behavior fails for the expected reasons.
- [ ] **Step 3: Remove legacy metadata reads/writes** but leave old files untouched.
- [ ] **Step 4: Implement acquisition**: only full-session requests query/save snapshots; validate QCE JSON before save; compute raw message count and UTC coverage; call Provider on cache miss; return original verified export if snapshot save fails.
- [ ] **Step 5: Keep ImportService routing** by making `execute()` import the path returned by `acquire_export()` and `export_only()` return that same path.
- [ ] **Step 6: Export the new result type** from the Application package and run focused tests green.

### Task 3: Facade metadata and force refresh

**Files:**
- Modify: `src/qq_chat_analyzer/application/facade.py`
- Test: `tests/test_facade.py`
- Test: `tests/test_application_dto.py`

**Interfaces:**
- Produces: `AnalysisConfig.force_refresh: bool = False`.
- Produces: optional `AnalysisOutcome.snapshot_id`, `data_acquired_at`, and `snapshot_reused`.
- Consumes: `QQExportImportService.acquire_export()` when available; retains `export_only()` fallback for compatible injected test/services.

- [ ] **Step 1: Write failing tests** proving force refresh reaches only QQ acquisition, snapshot payload reaches AnalysisApplicationService, metadata appears on outcome, and WeChat export request remains unchanged.
- [ ] **Step 2: Run** the focused Facade tests and confirm failures.
- [ ] **Step 3: Add an internal session-export value** carrying path plus optional snapshot metadata.
- [ ] **Step 4: Thread metadata through `_analyze_path()`** without changing analysis request semantics.
- [ ] **Step 5: Re-run Facade and DTO tests green.**

### Task 4: History snapshot association and old-row compatibility

**Files:**
- Modify: `src/qq_chat_analyzer/application/report_history.py`
- Modify: `src/qq_chat_analyzer/application/facade.py`
- Test: `tests/test_report_history.py`
- Test: `tests/test_facade.py`

**Interfaces:**
- Produces: `AnalysisHistoryRecord.snapshot_id: str | None = None`.
- Extends: `ReportHistoryManager.save_analysis(..., snapshot_id=None)`.
- Compatibility: old records without `snapshot_id` remain readable.

- [ ] **Step 1: Write failing tests** for new-row snapshot ID, old-row compatibility, QQ Facade association, and WeChat `None` association.
- [ ] **Step 2: Run** history/Facade tests and confirm failures.
- [ ] **Step 3: Accept exactly old or new JSONL field sets** and serialize `snapshot_id` for new rows.
- [ ] **Step 4: Pass QQ snapshot ID from Facade history save** and run focused tests green.

### Task 5: Minimal acquisition-time display

**Files:**
- Modify: `src/qq_chat_analyzer/gui/main_window.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `AnalysisOutcome.data_acquired_at`.
- Preserves: existing outcome page transition and history success/failure status behavior.

- [ ] **Step 1: Write a failing GUI test** that a QQ outcome with acquisition time appends a localized timestamp to the existing status message, while an outcome without it keeps the exact old text.
- [ ] **Step 2: Run** the targeted GUI test and confirm failure.
- [ ] **Step 3: Add display-only formatting** in `show_outcome()` with no new widgets, scans, or state transitions.
- [ ] **Step 4: Re-run GUI tests green.**

### Task 6: Regression and scope verification

**Files:**
- No production changes expected.

- [ ] **Step 1: Run focused regression** for Snapshot, QQ service, Facade, History, GUI, ImportService, Scope Filter, and WeChat services.
- [ ] **Step 2: Run full** `python -m pytest -p no:cacheprovider --basetemp=<workspace-temp>`.
- [ ] **Step 3: Run** `git diff --check`.
- [ ] **Step 4: Audit changed paths** and confirm no forbidden module was modified.

