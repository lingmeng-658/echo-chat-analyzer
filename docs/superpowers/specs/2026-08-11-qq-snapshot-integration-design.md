# QQ Snapshot Integration Design

## Scope

Phase 3B makes `ChatDataSnapshotManager` the only formal QQ export cache.
It stops reading the legacy `metadata.json` absolute-path cache without
migrating or deleting old files. Provider contracts, parsers, `ChatMessage`,
Analyzer, Scope Filter, WeChat acquisition, and QQ connection behavior remain
unchanged.

## Architecture

`QQExportImportService` remains the QQ export orchestrator. It asks
`ChatDataSnapshotManager` for the newest available snapshot matching QQ,
`session_id`, and `session_type`. A cache hit returns the validated payload.
A miss, invalid payload, or force refresh invokes the existing Provider,
validates the completed QCE JSON, saves the raw payload through the manager,
and returns the snapshot payload. `execute()` and Facade analysis continue to
send that path through the existing ImportService-based pipeline.

The manager owns snapshot querying, creation, validation, and cleanup. The QQ
service only supplies source-specific metadata extracted from the raw QCE
export. Full-session exports are cacheable; bounded legacy exports continue to
run directly because v0.1 snapshot identity does not include export bounds.

## Public application behavior

- Default: reuse the newest available matching snapshot.
- Force refresh: `AnalysisConfig.force_refresh=True` and
  `QQExportImportRequest.force_refresh=True` skip reuse and export again.
- Acquisition metadata includes snapshot ID, acquisition time, and reuse flag.
- QQ outcomes expose acquisition time; the existing success status line may
  append it without adding controls or pages.
- Snapshot save failure is logged and analysis continues with the Provider's
  verified export path.
- Snapshot corruption or missing payload causes a normal fresh export.

## History compatibility

New analysis history rows include optional `snapshot_id`. Readers accept both
the old exact field set and the new field set. Old rows load with
`snapshot_id=None`; WeChat and local-file analyses continue to save `None`.

## Testing

Tests cover first export/save, reuse, force refresh, invalid snapshot fallback,
no-snapshot fallback, ImportService routing, save failure fallback, history
association and old history compatibility, minimal acquisition-time display,
and unchanged WeChat dispatch.

