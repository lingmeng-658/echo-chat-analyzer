from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qq_chat_analyzer.application.chat_data_snapshot import (
    ChatDataSnapshotManager,
    ChatDataSource,
    SnapshotPayloadState,
    SnapshotSaveError,
    SnapshotStatus,
)


_COVERAGE_START = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
_COVERAGE_END = datetime(2026, 8, 11, 20, 30, tzinfo=timezone.utc)


def _write_payload(path: Path, content: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        content
        if content is not None
        else (
            b'{"timestamp":"2026-01-01T08:00:00Z",'
            b'"text":"Fictional hello"}\n'
        )
    )
    return path


def _save_snapshot(
    manager: ChatDataSnapshotManager,
    payload_path: Path,
    *,
    session_id: str = "fictional-session",
    session_name: str | None = "Fictional Group",
    session_type: str = "group",
):
    return manager.save_snapshot(
        payload_path,
        source=ChatDataSource.QQ,
        session_id=session_id,
        session_name=session_name,
        session_type=session_type,
        coverage_start=_COVERAGE_START,
        coverage_end=_COVERAGE_END,
        message_count=42,
        storage_format="qce_json",
    )


def _snapshot_directory(user_data: Path, snapshot_id: str) -> Path:
    return user_data / "data" / "snapshots" / "qq" / snapshot_id


def test_save_snapshot_copies_raw_payload_and_writes_relative_manifest(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    original_bytes = (
        b'{"raw":"Fictional original bytes"}\n'
        b'{"raw":"Second fictional row"}\n'
    )
    source_payload = _write_payload(
        tmp_path / "source" / "fictional.jsonl",
        original_bytes,
    )
    manager = ChatDataSnapshotManager(user_data)

    snapshot = _save_snapshot(manager, source_payload)

    snapshot_directory = (
        user_data / "data" / "snapshots" / "qq" / snapshot.id
    )
    stored_payload = snapshot_directory / "export.jsonl"
    manifest_path = snapshot_directory / "manifest.json"
    assert stored_payload.read_bytes() == original_bytes
    assert source_payload.read_bytes() == original_bytes
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["id"] == snapshot.id
    assert manifest["source"] == "qq"
    assert manifest["session_id"] == "fictional-session"
    assert manifest["session_name"] == "Fictional Group"
    assert manifest["session_type"] == "group"
    assert manifest["coverage_start"] == "2026-01-01T08:00:00+00:00"
    assert manifest["coverage_end"] == "2026-08-11T20:30:00+00:00"
    assert manifest["message_count"] == 42
    assert manifest["data_size_bytes"] == len(original_bytes)
    assert manifest["storage_format"] == "qce_json"
    assert manifest["storage_path"] == (
        f"data/snapshots/qq/{snapshot.id}/export.jsonl"
    )
    assert not Path(manifest["storage_path"]).is_absolute()
    assert manifest["payload_state"] == "available"

    assert snapshot.source is ChatDataSource.QQ
    assert snapshot.session_id == "fictional-session"
    assert snapshot.session_name == "Fictional Group"
    assert snapshot.acquired_at.tzinfo is not None
    assert snapshot.capture_scope == "all_available"
    assert snapshot.payload_state is SnapshotPayloadState.AVAILABLE


def test_saved_snapshot_can_be_read_and_payload_resolved(tmp_path: Path) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "fictional.json"),
    )

    reloaded_manager = ChatDataSnapshotManager(user_data)
    loaded = reloaded_manager.get_snapshot(saved.id)

    assert loaded == saved
    assert reloaded_manager.resolve_payload_path(saved.id) == (
        user_data
        / "data"
        / "snapshots"
        / "qq"
        / saved.id
        / "export.json"
    )


def test_default_snapshot_storage_uses_echo_user_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "qq_chat_analyzer.application.chat_data_snapshot.user_data_dir",
        lambda: tmp_path,
    )
    manager = ChatDataSnapshotManager()

    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "fictional.jsonl"),
    )

    assert (
        tmp_path
        / "data"
        / "snapshots"
        / "qq"
        / saved.id
        / "manifest.json"
    ).is_file()


def test_missing_source_payload_fails_without_partial_snapshot(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)

    with pytest.raises(SnapshotSaveError):
        _save_snapshot(manager, tmp_path / "missing.jsonl")

    snapshots_root = user_data / "data" / "snapshots"
    assert list(snapshots_root.rglob("manifest.json")) == []


def test_list_snapshots_returns_newest_first_and_filters_by_session(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    first = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "first.jsonl"),
        session_id="session-a",
    )
    second = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "second.jsonl"),
        session_id="session-a",
    )
    _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "other.jsonl"),
        session_id="session-b",
    )

    assert manager.list_snapshots(
        source=ChatDataSource.QQ,
        session_id="session-a",
    ) == (second, first)
    assert manager.list_snapshots(source=ChatDataSource.WECHAT) == ()


def test_validate_snapshot_reports_available_payload(tmp_path: Path) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "available.jsonl"),
    )

    validation = manager.validate_snapshot(saved.id)

    assert validation.status is SnapshotStatus.AVAILABLE
    assert validation.available is True
    assert validation.snapshot == saved
    assert validation.payload_path == manager.resolve_payload_path(saved.id)


def test_validate_snapshot_reports_unknown_id_as_not_found(tmp_path: Path) -> None:
    validation = ChatDataSnapshotManager(
        tmp_path / "LocalChatAnalyzer"
    ).validate_snapshot("00000000-0000-0000-0000-000000000000")

    assert validation.status is SnapshotStatus.NOT_FOUND
    assert validation.available is False
    assert validation.snapshot is None


def test_validate_snapshot_distinguishes_missing_manifest(tmp_path: Path) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "missing-manifest.jsonl"),
    )
    (_snapshot_directory(user_data, saved.id) / "manifest.json").unlink()

    validation = manager.validate_snapshot(saved.id)

    assert validation.status is SnapshotStatus.MANIFEST_MISSING
    assert manager.get_snapshot(saved.id) is None


def test_corrupted_manifest_returns_none_and_logs_warning(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "corrupt.jsonl"),
    )
    manifest_path = _snapshot_directory(user_data, saved.id) / "manifest.json"
    manifest_path.write_text("{not-json}\n", encoding="utf-8")

    with caplog.at_level(
        logging.WARNING,
        logger="qq_chat_analyzer.desktop.chat_data_snapshot",
    ):
        loaded = manager.get_snapshot(saved.id)

    assert loaded is None
    assert manager.validate_snapshot(saved.id).status is (
        SnapshotStatus.MANIFEST_CORRUPTED
    )
    assert any(
        record.name == "qq_chat_analyzer.desktop.chat_data_snapshot"
        and record.levelno == logging.WARNING
        for record in caplog.records
    )


def test_absolute_storage_path_marks_manifest_as_corrupted(tmp_path: Path) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "unsafe.jsonl"),
    )
    manifest_path = _snapshot_directory(user_data, saved.id) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["storage_path"] = str((tmp_path / "outside.jsonl").resolve())
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert manager.get_snapshot(saved.id) is None
    assert manager.validate_snapshot(saved.id).status is (
        SnapshotStatus.MANIFEST_CORRUPTED
    )


def test_validate_snapshot_reports_missing_payload(tmp_path: Path) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "missing-payload.jsonl"),
    )
    payload_path = manager.resolve_payload_path(saved.id)
    assert payload_path is not None
    payload_path.unlink()

    validation = manager.validate_snapshot(saved.id)

    assert manager.get_snapshot(saved.id) == saved
    assert manager.resolve_payload_path(saved.id) is None
    assert validation.status is SnapshotStatus.PAYLOAD_MISSING
    assert validation.snapshot == saved


def test_validate_snapshot_reports_payload_size_mismatch(tmp_path: Path) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "changed.jsonl"),
    )
    payload_path = manager.resolve_payload_path(saved.id)
    assert payload_path is not None
    payload_path.write_bytes(payload_path.read_bytes() + b"changed")

    validation = manager.validate_snapshot(saved.id)

    assert validation.status is SnapshotStatus.PAYLOAD_SIZE_MISMATCH
    assert validation.available is False
    assert manager.resolve_payload_path(saved.id) is None


def test_remove_payload_preserves_manifest_and_marks_snapshot_removed(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    manager = ChatDataSnapshotManager(user_data)
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "to-remove.jsonl"),
    )
    payload_path = manager.resolve_payload_path(saved.id)
    manifest_path = _snapshot_directory(user_data, saved.id) / "manifest.json"
    assert payload_path is not None

    validation = manager.remove_payload(saved.id)

    assert payload_path.exists() is False
    assert manifest_path.is_file()
    loaded = manager.get_snapshot(saved.id)
    assert loaded is not None
    assert loaded.payload_state is SnapshotPayloadState.REMOVED
    assert validation.status is SnapshotStatus.REMOVED
    assert validation.snapshot == loaded
    assert validation.available is False
    assert manager.resolve_payload_path(saved.id) is None


def test_remove_payload_is_idempotent(tmp_path: Path) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    saved = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "remove-twice.jsonl"),
    )

    first = manager.remove_payload(saved.id)
    second = manager.remove_payload(saved.id)

    assert first.status is SnapshotStatus.REMOVED
    assert second.status is SnapshotStatus.REMOVED
    assert manager.get_snapshot(saved.id) == second.snapshot


def test_remove_payload_reports_unknown_snapshot_without_creating_files(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    validation = ChatDataSnapshotManager(user_data).remove_payload(
        "00000000-0000-0000-0000-000000000000"
    )

    assert validation.status is SnapshotStatus.NOT_FOUND
    assert user_data.exists() is False


def test_find_latest_available_returns_newest_matching_snapshot(
    tmp_path: Path,
) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    first = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "first-match.jsonl"),
        session_id="session-a",
    )
    second = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "second-match.jsonl"),
        session_id="session-a",
    )

    validation = manager.find_latest_available(
        source=ChatDataSource.QQ,
        session_id="session-a",
        session_type="group",
    )

    assert validation is not None
    assert validation.snapshot == second
    assert validation.snapshot != first
    assert validation.status is SnapshotStatus.AVAILABLE


def test_find_latest_available_requires_matching_session_type(
    tmp_path: Path,
) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "private.jsonl"),
        session_id="same-session",
        session_type="private",
    )

    validation = manager.find_latest_available(
        source=ChatDataSource.QQ,
        session_id="same-session",
        session_type="group",
    )

    assert validation is None


def test_find_latest_available_skips_invalid_newer_payload(
    tmp_path: Path,
) -> None:
    manager = ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer")
    older = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "older-valid.jsonl"),
        session_id="session-a",
    )
    newer = _save_snapshot(
        manager,
        _write_payload(tmp_path / "source" / "newer-invalid.jsonl"),
        session_id="session-a",
    )
    newer_payload = manager.resolve_payload_path(newer.id)
    assert newer_payload is not None
    newer_payload.unlink()

    validation = manager.find_latest_available(
        source=ChatDataSource.QQ,
        session_id="session-a",
        session_type="group",
    )

    assert validation is not None
    assert validation.snapshot == older
    assert validation.status is SnapshotStatus.AVAILABLE
