"""Metadata-only history for completed analyses."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..resources import user_data_dir


_HISTORY_RELATIVE_PATH = Path("history") / "analysis_history.jsonl"
_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.report_history")
_LEGACY_RECORD_KEYS = {
    "analysis_id",
    "created_at",
    "source",
    "session_name",
    "session_id",
    "message_count",
    "analysis_scope",
    "scope_start",
    "scope_end",
    "report_generated_at",
}
_SNAPSHOT_RECORD_KEYS = _LEGACY_RECORD_KEYS | {"snapshot_id"}
_DIAGNOSTIC_KEYS = {
    "session_type",
    "input_identity_summary",
    "raw_message_count",
    "imported_message_count",
    "scope_message_count",
    "filtered_message_count",
    "analyzed_message_count",
}
_RECORD_KEYS = _SNAPSHOT_RECORD_KEYS | _DIAGNOSTIC_KEYS
_CAPTURE_MODES = frozenset({"snapshot", "provider_export", "live_database"})


class _HistoryFileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class InputIdentitySummary:
    """Non-identifying state describing how analysis input was acquired."""

    snapshot_reused: bool
    capture_mode: str


@dataclass(frozen=True, slots=True)
class AnalysisHistoryRecord:
    """One completed analysis without messages or report contents."""

    analysis_id: str
    created_at: datetime
    source: str
    session_name: str | None = field(default=None, repr=False)
    session_id: str | None = field(default=None, repr=False)
    message_count: int = 0
    analysis_scope: str = "all"
    scope_start: date | None = None
    scope_end: date | None = None
    report_generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    snapshot_id: str | None = None
    session_type: str | None = None
    input_identity_summary: InputIdentitySummary | None = None
    raw_message_count: int | None = None
    imported_message_count: int | None = None
    scope_message_count: int | None = None
    filtered_message_count: int | None = None
    analyzed_message_count: int | None = None


class ReportHistoryWriteError(RuntimeError):
    """Raised when a history record cannot be saved safely."""


class ReportHistoryManager:
    """Append and read analysis metadata from one local JSONL file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._configured_path = Path(path) if path is not None else None

    def save_analysis(
        self,
        *,
        source: str,
        session_name: str | None,
        session_id: str | None,
        message_count: int,
        analysis_scope: str,
        scope_start: date | None,
        scope_end: date | None,
        report_generated_at: datetime,
        snapshot_id: str | None = None,
        session_type: str | None = None,
        input_identity_summary: InputIdentitySummary | None = None,
        raw_message_count: int | None = None,
        imported_message_count: int | None = None,
        scope_message_count: int | None = None,
        filtered_message_count: int | None = None,
        analyzed_message_count: int | None = None,
    ) -> AnalysisHistoryRecord:
        """Create and append one metadata-only history record."""
        record = AnalysisHistoryRecord(
            analysis_id=str(uuid4()),
            created_at=datetime.now(timezone.utc),
            source=source,
            session_name=session_name,
            session_id=session_id,
            message_count=message_count,
            analysis_scope=analysis_scope,
            scope_start=scope_start,
            scope_end=scope_end,
            report_generated_at=report_generated_at,
            snapshot_id=snapshot_id,
            session_type=session_type,
            input_identity_summary=input_identity_summary,
            raw_message_count=raw_message_count,
            imported_message_count=imported_message_count,
            scope_message_count=scope_message_count,
            filtered_message_count=filtered_message_count,
            analyzed_message_count=analyzed_message_count,
        )
        try:
            payload = _record_to_payload(record)
            _record_from_payload(payload)
            path = self._path()
            if path.exists() and path.stat().st_size:
                _load_records(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as history_file:
                history_file.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                history_file.write("\n")
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            _HistoryFileError,
            TypeError,
        ) as exc:
            raise ReportHistoryWriteError(
                "Analysis history could not be saved."
            ) from exc
        return record

    def list_records(self) -> tuple[AnalysisHistoryRecord, ...]:
        """Return saved records newest first."""
        try:
            records = _load_records(self._path())
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            _HistoryFileError,
            TypeError,
        ) as exc:
            _LOGGER.warning(
                "Analysis history is unavailable or corrupted; "
                "returning empty history (%s).",
                type(exc).__name__,
            )
            return ()
        return tuple(reversed(records))

    def get_record(self, analysis_id: str) -> AnalysisHistoryRecord | None:
        """Return one saved record by ID, if present."""
        return next(
            (
                record
                for record in self.list_records()
                if record.analysis_id == analysis_id
            ),
            None,
        )

    def _path(self) -> Path:
        if self._configured_path is not None:
            return self._configured_path
        return user_data_dir() / _HISTORY_RELATIVE_PATH


def _record_to_payload(record: AnalysisHistoryRecord) -> dict[str, object]:
    return {
        "analysis_id": record.analysis_id,
        "created_at": record.created_at.isoformat(),
        "source": record.source,
        "session_name": record.session_name,
        "session_id": record.session_id,
        "message_count": record.message_count,
        "analysis_scope": record.analysis_scope,
        "scope_start": (
            record.scope_start.isoformat()
            if record.scope_start is not None
            else None
        ),
        "scope_end": (
            record.scope_end.isoformat()
            if record.scope_end is not None
            else None
        ),
        "report_generated_at": record.report_generated_at.isoformat(),
        "snapshot_id": record.snapshot_id,
        "session_type": record.session_type,
        "input_identity_summary": (
            {
                "snapshot_reused": record.input_identity_summary.snapshot_reused,
                "capture_mode": record.input_identity_summary.capture_mode,
            }
            if record.input_identity_summary is not None
            else None
        ),
        "raw_message_count": record.raw_message_count,
        "imported_message_count": record.imported_message_count,
        "scope_message_count": record.scope_message_count,
        "filtered_message_count": record.filtered_message_count,
        "analyzed_message_count": record.analyzed_message_count,
    }


def _record_from_payload(payload: dict[str, object]) -> AnalysisHistoryRecord:
    if not isinstance(payload, dict) or set(payload) not in (
        _LEGACY_RECORD_KEYS,
        _SNAPSHOT_RECORD_KEYS,
        _RECORD_KEYS,
    ):
        raise _HistoryFileError("Unexpected history record fields.")

    scope_start = _optional_date(payload["scope_start"])
    scope_end = _optional_date(payload["scope_end"])
    if (scope_start is None) != (scope_end is None):
        raise _HistoryFileError("Incomplete history scope.")
    if scope_start is not None and scope_start > scope_end:
        raise _HistoryFileError("Invalid history scope order.")

    message_count = payload["message_count"]
    if (
        isinstance(message_count, bool)
        or not isinstance(message_count, int)
        or message_count < 0
    ):
        raise _HistoryFileError("Invalid history message count.")

    diagnostic_counts = {
        key: _optional_count(payload.get(key))
        for key in (
            "raw_message_count",
            "imported_message_count",
            "scope_message_count",
            "filtered_message_count",
            "analyzed_message_count",
        )
    }

    return AnalysisHistoryRecord(
        analysis_id=_required_string(payload["analysis_id"]),
        created_at=_aware_datetime(payload["created_at"]),
        source=_required_string(payload["source"]),
        session_name=_optional_string(payload["session_name"]),
        session_id=_optional_string(payload["session_id"]),
        message_count=message_count,
        analysis_scope=_required_string(payload["analysis_scope"]),
        scope_start=scope_start,
        scope_end=scope_end,
        report_generated_at=_aware_datetime(payload["report_generated_at"]),
        snapshot_id=_optional_string(payload.get("snapshot_id")),
        session_type=_optional_string(payload.get("session_type")),
        input_identity_summary=_identity_summary(
            payload.get("input_identity_summary")
        ),
        **diagnostic_counts,
    )


def _load_records(path: Path) -> tuple[AnalysisHistoryRecord, ...]:
    if not path.exists() or path.stat().st_size == 0:
        return ()
    records: list[AnalysisHistoryRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise _HistoryFileError("History record must be a JSON object.")
        records.append(_record_from_payload(payload))
    return tuple(records)


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _HistoryFileError("Expected a non-empty string.")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _HistoryFileError("Expected a string or null.")
    return value


def _optional_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _HistoryFileError("Invalid diagnostic message count.")
    return value


def _identity_summary(value: object) -> InputIdentitySummary | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "snapshot_reused",
        "capture_mode",
    }:
        raise _HistoryFileError("Invalid input identity summary.")
    snapshot_reused = value["snapshot_reused"]
    capture_mode = value["capture_mode"]
    if not isinstance(snapshot_reused, bool) or capture_mode not in _CAPTURE_MODES:
        raise _HistoryFileError("Invalid input identity summary.")
    return InputIdentitySummary(snapshot_reused, capture_mode)


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _HistoryFileError("Expected an ISO date or null.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _HistoryFileError("Invalid ISO date.") from exc


def _aware_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise _HistoryFileError("Expected an ISO datetime.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _HistoryFileError("Invalid ISO datetime.") from exc
    if parsed.tzinfo is None:
        raise _HistoryFileError("History datetime must include a timezone.")
    return parsed


__all__ = [
    "AnalysisHistoryRecord",
    "InputIdentitySummary",
    "ReportHistoryManager",
    "ReportHistoryWriteError",
]
