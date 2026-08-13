# Analysis Diagnostic Metadata Design

## Goal

Persist a minimal, privacy-safe diagnostic trace for each completed analysis so
future data-chain incidents can be localized without retaining chat content or
input paths.

## Scope and constraints

This change is limited to application-layer result metadata and analysis
history persistence. It does not change providers, parsers, `ChatMessage`,
analyzers, GUI control flow, filtering behavior, or analysis output semantics.

Persisted diagnostics must never include message content, sender or conversation
display names, paths, payload documents, SQL, database keys, tokens, or other
credentials.

## Data model

`AnalysisResultDTO` will expose a small diagnostic-count value object populated
by `AnalysisApplicationService` at the existing stage boundaries:

- `raw_message_count`: raw rows reported by `ImportService`.
- `imported_message_count`: `ChatMessage` objects returned by import.
- `scope_message_count`: messages remaining after scope filtering.
- `filtered_message_count`: messages retained by smart filtering.
- `analyzed_message_count`: messages passed to the existing report analyzers.

Each count is optional so callers or alternate analysis-service implementations
that cannot provide a stage may leave it unset. The normal application service
can provide all five without re-reading input or duplicating processing.

`AnalysisHistoryRecord` will add the same optional counts, plus:

- `session_type`: the existing stable session category when known.
- `input_identity_summary`: an optional structured object containing only:
  - `snapshot_reused`: boolean.
  - `capture_mode`: `snapshot`, `provider_export`, or `live_database`.

Identity remains represented only by the existing `source`, `session_id`, and
`snapshot_id` fields plus the new `session_type`. The summary does not repeat
identity.

## Data flow

`AnalysisApplicationService` records counts using objects already present in its
execution flow. `ChatAnalyzerFacade` reads those counts from the result and
passes them to `ReportHistoryManager.save_analysis` together with session and
snapshot acquisition metadata already available at that boundary.

Capture mode is derived without inspecting the payload:

- Any analysis backed by an acquired Snapshot: `snapshot`.
- QQ direct export without a Snapshot: `provider_export`.
- WeChat session acquisition: `live_database`.
- Local-file or indeterminate inputs: absent.

No second import, scope pass, or smart-filter pass is introduced.

## Compatibility and validation

New history fields are optional. Existing JSONL records that contain the legacy
field sets remain readable and produce `None` for every new field. New records
use an explicit metadata allowlist.

Counts must be non-negative integers or null. `session_type` must be a string or
null. The identity summary must be null or an object containing exactly the two
approved keys with a boolean `snapshot_reused` and an approved `capture_mode`.
No arbitrary extra keys are accepted.

## Testing

Tests will be written first and will cover:

- Exact stage counts from the normal analysis application service.
- Count availability on early successful outcomes such as no valid text or no
  tokens.
- Facade forwarding of session type, capture mode, reuse state, and counts.
- History serialization using only the approved keys.
- Reading legacy records with all diagnostic fields defaulting to `None`.
- Rejection of invalid counts or identity-summary shapes without appending a
  corrupted record.

Completion requires focused tests, the full `pytest` suite, and
`git diff --check`.
