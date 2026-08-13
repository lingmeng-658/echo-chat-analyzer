# Analysis Report History Design

**Date:** 2026-08-11

## Goal

Record which analyses a user has completed and expose metadata-only history
reading. This phase does not persist report contents and cannot restore a
Dashboard.

## Confirmed boundaries

- Add the capability after a successful analysis result has been built.
- Do not modify providers, adapters/parsers, `ChatMessage`, scope filtering,
  Analyzer internals, QQ/WeChat connection flows, or GUI connection state.
- Do not store message bodies, raw messages, Analyzer report details, paths,
  report snapshots, caches, synchronization data, deletion policy, search, or
  export functionality.
- A history write failure must not turn a successful analysis into a failure.
- The GUI only reports whether the completed analysis was saved.

## Considered storage approaches

1. **One JSONL file (selected).** Each successful analysis appends one compact
   metadata object. This fits the P0 append/read use case, avoids a database,
   and limits the write surface.
2. One JSON array rewritten on each save. This makes whole-file reading simple
   but rewrites all history for every analysis and increases overwrite risk.
3. One JSON file per analysis. This isolates individual corruption but creates
   file proliferation and starts to resemble future report management.

## Architecture

The existing analysis path remains unchanged through result construction:

```text
Provider -> ChatMessage -> Scope Filter -> Smart Filter -> Analyzer -> Result
                                                                    |
                                                                    v
                                                        ReportHistoryManager
```

`ChatAnalyzerFacade` receives an optional injected `ReportHistoryManager`. It
attempts one metadata save only after the application result and Dashboard view
have both been produced successfully. The manager is therefore a result-layer
side effect, not an analysis dependency.

The Facade also exposes list/get methods so presentation code never reads the
history file directly. The desktop composition root injects the manager; tests
and existing callers that omit it keep their current behavior.

## Record contract

`AnalysisHistoryRecord` contains only:

- `analysis_id`: UUID string generated for this history entry.
- `created_at`: timezone-aware UTC ISO-8601 timestamp for record creation.
- `source`: `qq`, `wechat`, or `local_file`.
- `session_name`: nullable existing display name.
- `session_id`: nullable existing session identifier.
- `message_count`: scoped message count reported by `AnalysisResultDTO`.
- `analysis_scope`: `all`, `last_year`, `last_six_months`, or `custom`.
- `scope_start`: nullable inclusive ISO date.
- `scope_end`: nullable inclusive ISO date.
- `report_generated_at`: timezone-aware UTC ISO-8601 timestamp captured after
  result/view generation.

There is intentionally no schema/version field in this phase. Session name and
ID are excluded from object representations used by logs. Serialization uses
an explicit allowlist so later DTO additions cannot accidentally persist
message or report data.

## Storage and failure behavior

The default path is resolved lazily as:

```text
<Echo user data directory>/history/analysis_history.jsonl
```

The code reuses `resources.user_data_dir()` and does not depend on the source or
installation directory. A supplied path supports isolated tests.

- Missing or empty file: return empty history.
- Any malformed or invalid record: log a warning and return empty history.
- Save against a malformed existing file: raise a manager write error without
  appending another line.
- Permission or I/O error during save: raise a manager write error.
- Facade catches all history-save failures, logs them, and still returns the
  analysis outcome with `history_saved=False`.
- Successful save sets `history_saved=True` and returns the generated ID.
- No injected manager uses `history_saved=None`, preserving old test/caller
  behavior.

History lists are returned newest first. `get` returns a record or `None`.
There is no locking, cleanup, migration, search, deletion, or report loading.

## GUI behavior

`MainWindow.show_outcome()` continues to render and switch to the Dashboard
before setting the status text:

- `history_saved=True`: `分析已保存`
- `history_saved=False`: `分析完成，但历史记录保存失败。`
- `history_saved=None`: existing `分析完成`

No page, button, list, scan, or connection-state transition is added.

## Test strategy

- Manager tests cover save/read/get, multiple appends, missing/empty files,
  malformed JSON, invalid record shape, save against corruption, write errors,
  newest-first ordering, and the serialization allowlist.
- Facade tests use a real temporary manager to prove successful QQ/WeChat
  analyses persist the expected scoped metadata; failure tests prove the same
  view/result are returned and failed analyses are never saved.
- GUI tests prove the three status branches and that the Dashboard is rendered
  for both save success and save failure.
- Existing QQ, WeChat, scope-filter, application, and GUI regression suites
  remain unchanged except for additive assertions where needed.

