# ChatDataSnapshot Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Application-layer manager that stores, reads, queries, validates, and manually removes raw chat snapshot payloads without connecting the capability to any provider or analysis flow.

**Architecture:** A single `ChatDataSnapshotManager` owns per-snapshot manifests and byte-for-byte payload copies beneath the Echo user data directory. Manifests contain only metadata and a user-root-relative payload path; status is derived by validating the manifest and payload on disk.

**Tech Stack:** Python 3.11+, dataclasses, enum, pathlib, json, shutil, tempfile, uuid, logging, pytest.

## Global Constraints

- Do not modify Provider interfaces or implementations.
- Do not modify QQ connection/login/export flows, WeChat flows, `ChatMessage`, Parser/Adapter, Analyzer, or Scope Filter.
- Do not connect snapshots to AnalysisHistory in Phase 3A.
- Store the original payload bytes without parsing or converting chat data.
- Store paths relative to the Echo user data directory; never persist absolute paths.
- Do not upload data or create a message-body index.
- Do not implement automatic refresh, recent-N retention, or policy-driven cleanup.
- Use only fictional test data.
- Follow RED -> GREEN for every production behavior.

---

### Task 1: Snapshot model and successful persistence

**Files:**
- Create: `src/qq_chat_analyzer/application/chat_data_snapshot.py`
- Create: `tests/test_chat_data_snapshot.py`

**Interfaces:**
- Produces `ChatDataSource`, `SnapshotPayloadState`, `SnapshotStatus`, `ChatDataSnapshot`, `SnapshotValidation`, `SnapshotSaveError`, and `ChatDataSnapshotManager`.
- `ChatDataSnapshotManager.save_snapshot(payload_path, *, source, session_id, session_name, session_type, coverage_start, coverage_end, message_count, storage_format="qce_json") -> ChatDataSnapshot`
- `ChatDataSnapshotManager.get_snapshot(snapshot_id) -> ChatDataSnapshot | None`
- `ChatDataSnapshotManager.resolve_payload_path(snapshot_id) -> Path | None`

- [ ] **Step 1: Write failing save/read tests**

  Use a real `tmp_path` user-data root and a fictional `.jsonl` payload. Assert
  the returned model contains the supplied metadata, the stored payload bytes
  are unchanged, the manifest exists under
  `data/snapshots/qq/<id>/manifest.json`, and `storage_path` is relative.

- [ ] **Step 2: Verify RED**

  Run `pytest -q tests/test_chat_data_snapshot.py` and confirm collection fails
  because `application.chat_data_snapshot` does not exist.

- [ ] **Step 3: Implement minimal save/read behavior**

  Add frozen dataclasses/enums, lazy `user_data_dir()` resolution, UUID IDs,
  byte-for-byte copying to an `export` filename that preserves `.json` or
  `.jsonl`, explicit manifest serialization, and strict required-field parsing.
  Stage each snapshot below `data/snapshots/.staging` and rename it into the
  final source directory only after payload and manifest writes succeed.

- [ ] **Step 4: Verify GREEN**

  Run `pytest -q tests/test_chat_data_snapshot.py` and confirm successful
  persistence/read tests pass.

### Task 2: Query and validation states

**Files:**
- Modify: `src/qq_chat_analyzer/application/chat_data_snapshot.py`
- Modify: `tests/test_chat_data_snapshot.py`

**Interfaces:**
- `ChatDataSnapshotManager.list_snapshots(*, source=None, session_id=None) -> tuple[ChatDataSnapshot, ...]`
- `ChatDataSnapshotManager.validate_snapshot(snapshot_id) -> SnapshotValidation`
- Status values: `available`, `not_found`, `manifest_missing`,
  `manifest_corrupted`, `payload_missing`, `payload_size_mismatch`, `removed`.

- [ ] **Step 1: Write failing query/validation tests**

  Add real-file tests for newest-first listing, source/session filtering,
  absent snapshot directory, absent manifest, malformed JSON, invalid manifest
  fields, missing payload, and payload size mismatch. Read-side corruption must
  return `None`/the matching validation state and log instead of raising.

- [ ] **Step 2: Verify RED**

  Run only the new query/validation tests and confirm failure because the APIs
  or status branches are missing.

- [ ] **Step 3: Implement query and validation**

  Scan per-snapshot manifests on demand without a global index. Resolve payload
  paths against the configured user-data root, reject absolute paths and path
  traversal, require the payload to remain inside its snapshot directory, and
  compare its byte size to manifest metadata.

- [ ] **Step 4: Verify GREEN**

  Run `pytest -q tests/test_chat_data_snapshot.py`.

### Task 3: Basic manual cleanup seam and public export

**Files:**
- Modify: `src/qq_chat_analyzer/application/chat_data_snapshot.py`
- Modify: `src/qq_chat_analyzer/application/__init__.py`
- Modify: `tests/test_chat_data_snapshot.py`
- Modify: `tests/test_application_public_api.py`

**Interfaces:**
- `ChatDataSnapshotManager.remove_payload(snapshot_id) -> SnapshotValidation`
- Removing a payload preserves `manifest.json`, changes `payload_state` to
  `removed`, and does not implement any selection/retention policy.

- [ ] **Step 1: Write failing manual-cleanup tests**

  Save a real snapshot, call `remove_payload`, and assert only the payload is
  removed, the manifest remains readable, validation returns `removed`, and a
  second call is idempotent. Add a public-package import assertion.

- [ ] **Step 2: Verify RED**

  Run the new cleanup/public API cases and confirm the method/exports are
  missing.

- [ ] **Step 3: Implement the minimal cleanup seam**

  Validate the resolved payload path before deletion, remove that one file,
  atomically rewrite the same manifest with `payload_state=removed`, and export
  Phase 3A types through `application.__init__`. Do not add recent-N logic.

- [ ] **Step 4: Verify GREEN**

  Run `pytest -q tests/test_chat_data_snapshot.py tests/test_application_public_api.py`.

### Task 4: Verification and forbidden-path audit

**Files:**
- No production changes expected.

- [ ] **Step 1: Run Phase 3A focused tests**

  Run `pytest -q tests/test_chat_data_snapshot.py tests/test_application_public_api.py tests/test_resources.py`.

- [ ] **Step 2: Run Application regressions**

  Run `pytest -q tests/test_qq_export_import_service.py tests/test_facade.py tests/test_application_service.py tests/test_scope_filter.py` to prove Phase 3A did not change export, analysis, or scope behavior.

- [ ] **Step 3: Run the full suite**

  Run `pytest` and report the exact count, preserving the known pre-existing
  Analyzer zero-timestamp failure rather than modifying prohibited code.

- [ ] **Step 4: Check the patch**

  Run `git diff --check`, `git diff --name-only`, and `git status --short`.
  Confirm Phase 3A touched only the new manager/tests, Application public
  exports, and this plan file.

- [ ] **Step 5: Report without committing**

  Report modified files, the new module/API, focused/full test evidence, and
  `git diff --check`. Do not stage or commit the existing Phase 1/2 worktree.

