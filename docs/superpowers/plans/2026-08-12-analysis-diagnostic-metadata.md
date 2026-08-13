# Analysis Diagnostic Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist privacy-safe input identity state and per-stage message counts for every completed analysis while preserving old history records.

**Architecture:** `AnalysisApplicationService` captures counts from objects already present in its single execution pass and returns them in a focused DTO. `ChatAnalyzerFacade` combines those counts with acquisition context and forwards them to the existing `ReportHistoryManager`, which performs lightweight allowlist validation and JSONL persistence.

**Tech Stack:** Python 3.13, frozen dataclasses, JSONL, pytest.

## Global Constraints

- Do not add a generic metadata framework.
- Do not change analysis behavior or repeat import/filter work.
- Do not modify Provider, Parser, ChatMessage, Analyzer, GUI flow, Snapshot validation, or QQ incident logic.
- Never persist content, display names in diagnostic summary, paths, payloads, SQL, keys, or tokens.
- Keep legacy JSONL records fully readable with new fields set to `None`.

---

### Task 1: Capture stage counts in the application result

**Files:**
- Modify: `src/qq_chat_analyzer/application/dto.py`
- Modify: `src/qq_chat_analyzer/application/analysis_service.py`
- Modify: `src/qq_chat_analyzer/application/__init__.py`
- Test: `tests/test_application_service.py`
- Test: `tests/test_application_dto.py`

**Interfaces:**
- Produces: `AnalysisDiagnosticCounts(raw_message_count: int | None, imported_message_count: int | None, scope_message_count: int | None, filtered_message_count: int | None, analyzed_message_count: int | None)`.
- Produces: `AnalysisResultDTO.diagnostic_counts: AnalysisDiagnosticCounts | None = None`.

- [ ] **Step 1: Write failing tests for exact counts and early successful outcomes**

Add assertions showing a normal execution reports raw/imported/scope/filtered/analyzed counts from the existing collections. Extend the no-valid-text and no-token tests to require the same count object. Add a DTO test proving the optional default remains `None` for alternate callers.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest -q tests/test_application_dto.py tests/test_application_service.py`

Expected: failures because `AnalysisDiagnosticCounts` and `diagnostic_counts` do not exist.

- [ ] **Step 3: Implement the minimal count DTO and single-pass capture**

Create the frozen count dataclass in `dto.py`, export it through the application public API, and construct it after smart filtering from:

```python
AnalysisDiagnosticCounts(
    raw_message_count=outcome.processed_message_count,
    imported_message_count=len(parsed_messages),
    scope_message_count=len(scoped_messages),
    filtered_message_count=len(kept_messages),
    analyzed_message_count=len(kept_messages),
)
```

Attach the same object to every successful `AnalysisResultDTO` return path. Do not call import or either filter again.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `pytest -q tests/test_application_dto.py tests/test_application_service.py`

Expected: all selected tests pass.

### Task 2: Persist identity state and counts in history

**Files:**
- Modify: `src/qq_chat_analyzer/application/report_history.py`
- Modify: `src/qq_chat_analyzer/application/facade.py`
- Test: `tests/test_report_history.py`
- Test: `tests/test_facade.py`

**Interfaces:**
- Produces: `InputIdentitySummary(snapshot_reused: bool, capture_mode: str)` in the history persistence module.
- Extends: `AnalysisHistoryRecord` and `ReportHistoryManager.save_analysis` with optional `session_type`, `input_identity_summary`, and five optional counts.
- Consumes: `AnalysisResultDTO.diagnostic_counts` from Task 1.

- [ ] **Step 1: Write failing history compatibility and validation tests**

Require new records to serialize exactly the existing allowlist plus the seven new fields. Require round-trip of a valid summary/count set, legacy rows to load with every new property `None`, negative/bool counts to fail without append, and summaries with extra keys or invalid capture modes to fail.

- [ ] **Step 2: Run history tests and verify RED**

Run: `pytest -q tests/test_report_history.py`

Expected: failures because the new persistence fields and validation do not exist.

- [ ] **Step 3: Implement lightweight persistence validation**

Add optional dataclass fields and explicit JSON keys. Replace exact two-shape acceptance with required legacy keys plus an allowlisted set of optional fields, while still rejecting unknown keys. Parse absent optional fields with `.get()`. Validate counts as null or non-negative non-bool integers. Validate summary as null or exactly:

```json
{"snapshot_reused": true, "capture_mode": "snapshot"}
```

with capture mode in `snapshot`, `provider_export`, `live_database`.

- [ ] **Step 4: Run history tests and verify GREEN**

Run: `pytest -q tests/test_report_history.py`

Expected: all history tests pass.

- [ ] **Step 5: Write failing Facade forwarding tests**

Extend QQ Snapshot history coverage to require `session_type`, `snapshot_reused`, `capture_mode=snapshot`, and diagnostic counts. Extend WeChat history coverage to require `capture_mode=live_database`. Add local-file coverage proving identity summary is absent. Use stub result DTOs; do not exercise GUI.

- [ ] **Step 6: Run Facade tests and verify RED**

Run: `pytest -q tests/test_facade.py -k "history or snapshot"`

Expected: new metadata assertions fail.

- [ ] **Step 7: Forward existing context from Facade**

Pass `session.session_type` when present. Derive capture mode without inspecting input: Snapshot ID present → `snapshot`; QQ session without Snapshot → `provider_export`; WeChat session → `live_database`; local file → no summary. Forward counts from `result.diagnostic_counts`, leaving each absent when alternate result implementations do not provide them.

- [ ] **Step 8: Run focused integration tests and verify GREEN**

Run: `pytest -q tests/test_report_history.py tests/test_facade.py -k "history or snapshot"`

Expected: all selected tests pass.

### Task 3: Regression verification

**Files:**
- Review only: all modified source and test files.

- [ ] **Step 1: Run all directly affected tests**

Run: `pytest -q tests/test_application_dto.py tests/test_application_service.py tests/test_report_history.py tests/test_facade.py`

Expected: all pass.

- [ ] **Step 2: Run the complete suite**

Run: `pytest`

Expected: exit code 0 with no failures.

- [ ] **Step 3: Inspect scope and whitespace**

Run: `git diff --check`

Expected: exit code 0. Review `git diff --stat` and `git diff` to confirm no Provider, Parser, ChatMessage, Analyzer, GUI, or unrelated files changed.
