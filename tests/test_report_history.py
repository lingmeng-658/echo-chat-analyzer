from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

import pytest

from qq_chat_analyzer.application.report_history import (
    InputIdentitySummary,
    ReportHistoryManager,
    ReportHistoryWriteError,
)


def _save_record(
    manager: ReportHistoryManager,
    *,
    source: str = "qq",
    session_name: str | None = "虚构会话",
    session_id: str | None = "fictional-session",
    message_count: int = 42,
    analysis_scope: str = "custom",
    scope_start: date | None = date(2026, 1, 1),
    scope_end: date | None = date(2026, 6, 30),
    report_generated_at: datetime = datetime(
        2026,
        8,
        11,
        12,
        30,
        tzinfo=timezone.utc,
    ),
    snapshot_id: str | None = None,
    session_type: str | None = None,
    input_identity_summary: InputIdentitySummary | None = None,
    raw_message_count: int | None = None,
    imported_message_count: int | None = None,
    scope_message_count: int | None = None,
    filtered_message_count: int | None = None,
    analyzed_message_count: int | None = None,
):
    return manager.save_analysis(
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


def test_missing_history_file_returns_empty_history(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")

    assert manager.list_records() == ()
    assert manager.get_record("missing") is None


def test_empty_history_file_returns_empty_history(tmp_path):
    history_path = tmp_path / "history.jsonl"
    history_path.touch()
    manager = ReportHistoryManager(history_path)

    assert manager.list_records() == ()


def test_default_storage_path_is_under_the_echo_user_data_directory(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "qq_chat_analyzer.application.report_history.user_data_dir",
        lambda: tmp_path,
    )
    manager = ReportHistoryManager()

    _save_record(manager)

    assert (tmp_path / "history" / "analysis_history.jsonl").is_file()


def test_save_analysis_can_be_read_and_retrieved_by_id(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")

    saved = _save_record(manager)

    assert saved.analysis_id
    assert saved.created_at.tzinfo is not None
    assert saved.source == "qq"
    assert saved.session_name == "虚构会话"
    assert saved.session_id == "fictional-session"
    assert saved.message_count == 42
    assert saved.analysis_scope == "custom"
    assert saved.scope_start == date(2026, 1, 1)
    assert saved.scope_end == date(2026, 6, 30)
    assert saved.report_generated_at == datetime(
        2026,
        8,
        11,
        12,
        30,
        tzinfo=timezone.utc,
    )
    assert manager.list_records() == (saved,)
    assert manager.get_record(saved.analysis_id) == saved


def test_multiple_records_append_and_list_newest_first(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")
    first = _save_record(manager, session_id="first")
    second = _save_record(
        manager,
        source="wechat",
        session_name="虚构联系人",
        session_id="second",
        message_count=7,
        analysis_scope="all",
        scope_start=None,
        scope_end=None,
    )

    assert manager.list_records() == (second, first)


def test_jsonl_serialization_uses_metadata_allowlist_only(tmp_path):
    history_path = tmp_path / "history.jsonl"
    manager = ReportHistoryManager(history_path)

    _save_record(manager)

    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert set(payload) == {
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
        "snapshot_id",
        "session_type",
        "input_identity_summary",
        "raw_message_count",
        "imported_message_count",
        "scope_message_count",
        "filtered_message_count",
        "analyzed_message_count",
    }
    serialized = history_path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "messages",
        "text",
        "content",
        "reports",
        "top_words",
        "input_path",
        "output_directory",
    ):
        assert forbidden not in serialized


def test_record_repr_does_not_expose_session_identifiers(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")

    saved = _save_record(manager)

    assert "虚构会话" not in repr(saved)
    assert "fictional-session" not in repr(saved)


def test_new_history_record_persists_optional_snapshot_id(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")

    saved = _save_record(
        manager,
        snapshot_id="11111111-1111-1111-1111-111111111111",
    )

    assert saved.snapshot_id == "11111111-1111-1111-1111-111111111111"
    assert manager.list_records()[0].snapshot_id == saved.snapshot_id


def test_new_history_record_persists_diagnostic_metadata(tmp_path):
    manager = ReportHistoryManager(tmp_path / "history.jsonl")
    summary = InputIdentitySummary(
        snapshot_reused=True,
        capture_mode="snapshot",
    )

    saved = _save_record(
        manager,
        session_type="group",
        input_identity_summary=summary,
        raw_message_count=166,
        imported_message_count=109,
        scope_message_count=100,
        filtered_message_count=95,
        analyzed_message_count=95,
    )

    assert saved.session_type == "group"
    assert saved.input_identity_summary == summary
    assert saved.raw_message_count == 166
    assert saved.imported_message_count == 109
    assert saved.scope_message_count == 100
    assert saved.filtered_message_count == 95
    assert saved.analyzed_message_count == 95
    assert manager.list_records() == (saved,)


def test_legacy_history_row_without_snapshot_id_remains_readable(tmp_path):
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        json.dumps(
            {
                "analysis_id": "legacy-analysis",
                "created_at": "2026-08-11T12:00:00+00:00",
                "source": "qq",
                "session_name": "Fictional Legacy Group",
                "session_id": "legacy-session",
                "message_count": 12,
                "analysis_scope": "all",
                "scope_start": None,
                "scope_end": None,
                "report_generated_at": "2026-08-11T12:01:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    records = ReportHistoryManager(history_path).list_records()

    assert len(records) == 1
    assert records[0].analysis_id == "legacy-analysis"
    assert records[0].snapshot_id is None
    assert records[0].session_type is None
    assert records[0].input_identity_summary is None
    assert records[0].raw_message_count is None
    assert records[0].imported_message_count is None
    assert records[0].scope_message_count is None
    assert records[0].filtered_message_count is None
    assert records[0].analyzed_message_count is None


@pytest.mark.parametrize("invalid_count", [-1, True])
def test_invalid_diagnostic_count_refuses_append(tmp_path, invalid_count):
    history_path = tmp_path / "history.jsonl"
    manager = ReportHistoryManager(history_path)

    with pytest.raises(ReportHistoryWriteError):
        _save_record(manager, raw_message_count=invalid_count)

    assert not history_path.exists()


@pytest.mark.parametrize("capture_mode", ["file", "", "snapshot/path"])
def test_invalid_capture_mode_refuses_append(tmp_path, capture_mode):
    history_path = tmp_path / "history.jsonl"
    manager = ReportHistoryManager(history_path)

    with pytest.raises(ReportHistoryWriteError):
        _save_record(
            manager,
            input_identity_summary=InputIdentitySummary(
                snapshot_reused=False,
                capture_mode=capture_mode,
            ),
        )

    assert not history_path.exists()


def test_malformed_json_returns_empty_history_and_logs_warning(
    tmp_path,
    caplog,
):
    history_path = tmp_path / "history.jsonl"
    history_path.write_text("{not-json}\n", encoding="utf-8")
    manager = ReportHistoryManager(history_path)

    with caplog.at_level(
        logging.WARNING,
        logger="qq_chat_analyzer.desktop.report_history",
    ):
        records = manager.list_records()

    assert records == ()
    assert any(
        record.name == "qq_chat_analyzer.desktop.report_history"
        and record.levelno == logging.WARNING
        for record in caplog.records
    )


def test_invalid_record_shape_returns_empty_history_and_logs_warning(
    tmp_path,
    caplog,
):
    history_path = tmp_path / "history.jsonl"
    history_path.write_text('{"analysis_id":"only-one-field"}\n', encoding="utf-8")
    manager = ReportHistoryManager(history_path)

    with caplog.at_level(
        logging.WARNING,
        logger="qq_chat_analyzer.desktop.report_history",
    ):
        records = manager.list_records()

    assert records == ()
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_save_refuses_to_append_to_corrupted_history(tmp_path):
    history_path = tmp_path / "history.jsonl"
    original = "{not-json}\n"
    history_path.write_text(original, encoding="utf-8")
    manager = ReportHistoryManager(history_path)

    with pytest.raises(ReportHistoryWriteError):
        _save_record(manager)

    assert history_path.read_text(encoding="utf-8") == original


def test_save_wraps_io_failure_as_history_write_error(tmp_path):
    history_path = tmp_path / "history.jsonl"
    history_path.mkdir()
    manager = ReportHistoryManager(history_path)

    with pytest.raises(ReportHistoryWriteError):
        _save_record(manager)
