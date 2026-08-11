"""End-to-end tests for the QCE provider -> adapter -> ChatMessage seam.

No real QCE service is contacted. The provider is a stub that returns a path to
a fictional export file written by the test itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ApplicationServiceError,
    ChatDataSnapshotManager,
    ChatDataSource,
    ImportRequest,
    ImportService,
    QQExportFileMissing,
    QQExportImportRequest,
    QQExportImportService,
    QQExportUnavailable,
    SnapshotSaveError,
    SnapshotStatus,
)
from qq_chat_analyzer.qq_chat_exporter_adapter import (
    WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED,
)


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))


def _qce_message(
    message_id: str,
    message_type: str = "text",
    text: str = "Fictional line",
    nickname: str = "Fictional Alice",
    timestamp: int = 1750000000000,
) -> dict:
    return {
        "id": message_id,
        "seq": message_id,
        "timestamp": timestamp,
        "time": "2025-06-15 12:00:00",
        "sender": {
            "uid": "user-1001",
            "uin": "1001",
            "name": nickname,
            "nickname": nickname,
        },
        "type": message_type,
        "content": {"text": text, "elements": [], "resources": [], "mentions": []},
        "recalled": False,
        "system": False,
    }


def _write_fake_export(path: Path) -> Path:
    """Write a fictional QCE single-file export with mixed message types."""
    payload = {
        "metadata": {"exportedAt": "2025-06-15T12:00:00Z", "version": "4.0.0"},
        "chatInfo": {
            "chatType": 2,
            "peerUid": "700000001",
            "name": "Fictional Test Group",
        },
        "statistics": {"totalMessages": 4},
        "messages": [
            _qce_message("fake-1", "text", "Fictional hello"),
            _qce_message("fake-2", "reply", "Fictional reply", nickname="Fictional Bob"),
            _qce_message("fake-3", "file", "attachment.bin"),
            _qce_message("fake-4", "text", "Fictional goodbye"),
        ],
        "avatars": {},
        "exportOptions": {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class _StubProvider:
    """Stand in for the real QCE HTTP provider."""

    def __init__(self, export_path: object) -> None:
        self._export_path = export_path
        self.calls: list[tuple[str, object, object]] = []

    def export_group_json(
        self,
        group_code: str,
        start_time: object = None,
        end_time: object = None,
    ) -> object:
        self.calls.append((group_code, start_time, end_time))
        return self._export_path


class _FailingProvider:
    """Provider whose export fails with a domain error."""

    class _Boom(ApplicationServiceError):
        code = "qce_service_unreachable"
        public_message = "QCE service unreachable."

    def export_group_json(
        self,
        group_code: str,
        start_time: object = None,
        end_time: object = None,
    ) -> object:
        raise self._Boom()


class _TaskStubProvider:
    """Provider used to test task-list delegation only."""

    def __init__(self, tasks: list[object] | None = None, error: Exception | None = None):
        self._tasks = tasks
        self._error = error
        self.calls = 0

    def list_tasks(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._tasks


class _SessionStubProvider:
    def __init__(self, groups=(), friends=(), export_path=None):
        self.groups = list(groups)
        self.friends = list(friends)
        self.export_path = export_path
        self.export_calls: list[dict[str, object]] = []

    def list_groups(self):
        return self.groups

    def list_friends(self):
        return self.friends

    def export_chat_json(self, peer_uid, **kwargs):
        self.export_calls.append({"peer_uid": peer_uid, **kwargs})
        return self.export_path


# ------------------------------------------------------ 1. provider -> adapter


def test_provider_path_flows_into_adapter(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _StubProvider(export_path)
    service = QQExportImportService(provider)

    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    assert provider.calls == [("700000001", None, None)]
    assert outcome.result.platform == "qq"
    assert outcome.result.format == "qce-json"


def test_provider_accepts_string_path(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(str(export_path)))

    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    assert outcome.result.message_count == 3


def test_time_window_is_forwarded_to_provider(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _StubProvider(export_path)
    service = QQExportImportService(provider)

    service.execute(
        QQExportImportRequest(
            group_code="700000001",
            start_time=1700000000,
            end_time=1800000000,
        )
    )

    assert provider.calls == [("700000001", 1700000000, 1800000000)]


# ----------------------------------------------------- 2. ChatMessage creation


def test_qce_json_produces_chat_messages(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(export_path))

    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    texts = [message.text for message in outcome.messages]
    assert texts == ["Fictional hello", "Fictional reply", "Fictional goodbye"]
    senders = {message.sender for message in outcome.messages}
    assert senders == {"Fictional Alice", "Fictional Bob"}
    assert outcome.result.valid_text_count == 3


def test_message_ids_and_timestamps_survive(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(export_path))

    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    assert [m.message_id for m in outcome.messages] == ["fake-1", "fake-2", "fake-4"]
    assert all(m.timestamp is not None for m in outcome.messages)


# --------------------------------------------- 3. non-text filtering unchanged


def test_non_text_messages_are_skipped_with_warning(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(export_path))

    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    assert WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED in outcome.result.warnings
    assert outcome.result.message_count == 3
    assert outcome.processed_message_count == 4


# ------------------------------------------------------- 4. error propagation


def test_provider_error_propagates_unchanged(tmp_path: Path) -> None:
    service = QQExportImportService(_FailingProvider())

    with pytest.raises(ApplicationServiceError) as excinfo:
        service.execute(QQExportImportRequest(group_code="700000001"))

    assert excinfo.value.code == "qce_service_unreachable"


def test_list_tasks_delegates_to_provider() -> None:
    tasks = [
        {"taskId": "export_1", "status": "running", "progress": 42},
        {"taskId": "export_2", "status": "completed", "progress": 100},
    ]
    provider = _TaskStubProvider(tasks=tasks)
    service = QQExportImportService(provider)

    result = service.list_tasks()

    assert result == tasks
    assert provider.calls == 1


def test_list_sessions_keeps_groups_and_private_friends() -> None:
    group = object()
    friend = object()
    service = QQExportImportService(
        _SessionStubProvider(groups=[group], friends=[friend])
    )

    assert service.list_sessions() == [group, friend]


def test_private_session_export_uses_private_chat_type(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "private.json")
    provider = _SessionStubProvider(export_path=export_path)
    service = QQExportImportService(provider, cache_directory=tmp_path / "cache")

    service.export_only(
        QQExportImportRequest(
            group_code="u_fictional_1",
            chat_type=1,
            peer_uin="200001",
            session_name="Fictional Alice",
        )
    )

    assert provider.export_calls == [
        {
            "peer_uid": "u_fictional_1",
            "chat_type": 1,
            "peer_uin": "200001",
            "session_name": "Fictional Alice",
            "start_time": None,
            "end_time": None,
        }
    ]


def test_list_tasks_propagates_provider_error() -> None:
    service = QQExportImportService(
        _TaskStubProvider(error=_FailingProvider._Boom())
    )

    with pytest.raises(ApplicationServiceError) as excinfo:
        service.list_tasks()

    assert excinfo.value.code == "qce_service_unreachable"


def test_missing_export_file_raises_domain_error(tmp_path: Path) -> None:
    missing = tmp_path / "never_written.json"
    service = QQExportImportService(_StubProvider(missing))

    with pytest.raises(QQExportFileMissing):
        service.execute(QQExportImportRequest(group_code="700000001"))


def test_provider_returning_none_raises_unavailable() -> None:
    service = QQExportImportService(_StubProvider(None))

    with pytest.raises(QQExportUnavailable):
        service.execute(QQExportImportRequest(group_code="700000001"))


def test_provider_returning_blank_string_raises_unavailable() -> None:
    service = QQExportImportService(_StubProvider("   "))

    with pytest.raises(QQExportUnavailable):
        service.execute(QQExportImportRequest(group_code="700000001"))


# ------------------------------------------- 5. legacy QQ import is unaffected


def test_legacy_qq_json_import_still_works() -> None:
    legacy = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.json"
    outcome = ImportService().execute(ImportRequest(input_path=legacy))

    assert outcome.result.platform == "qq"
    assert outcome.result.format != "qce-json"
    assert outcome.result.message_count > 0
    assert WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED not in outcome.result.warnings


def test_orchestrator_reuses_injected_import_service(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    calls: list[Path] = []

    class _RecordingImportService(ImportService):
        def execute(self, request: ImportRequest):
            calls.append(request.input_path)
            return super().execute(request)

    service = QQExportImportService(
        _StubProvider(export_path),
        import_service=_RecordingImportService(),
    )
    outcome = service.execute(QQExportImportRequest(group_code="700000001"))

    assert len(calls) == 1
    assert calls[0] != export_path
    assert calls[0].read_bytes() == export_path.read_bytes()
    assert outcome.result.message_count == 3


# --------------------------------------------------- export_only (path only)


def test_export_only_returns_persisted_snapshot_payload(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _StubProvider(export_path)
    service = QQExportImportService(provider)

    returned = service.export_only(QQExportImportRequest(group_code="700000001"))

    assert returned != export_path
    assert returned.read_bytes() == export_path.read_bytes()
    assert provider.calls == [("700000001", None, None)]


def test_acquire_export_creates_snapshot_after_verified_provider_export(
    tmp_path: Path,
) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _StubProvider(export_path)
    snapshot_manager = ChatDataSnapshotManager(tmp_path / "user-data")
    service = QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
    )
    request = QQExportImportRequest(
        group_code="700000001",
        session_name="Fictional Test Group",
    )

    acquisition = service.acquire_export(request)

    assert provider.calls == [("700000001", None, None)]
    assert acquisition.payload_path != export_path
    assert acquisition.payload_path.read_bytes() == export_path.read_bytes()
    assert acquisition.snapshot_id is not None
    assert acquisition.reused_snapshot is False
    snapshot = snapshot_manager.get_snapshot(acquisition.snapshot_id)
    assert snapshot is not None
    assert snapshot.source is ChatDataSource.QQ
    assert snapshot.session_id == "700000001"
    assert snapshot.session_name == "Fictional Test Group"
    assert snapshot.session_type == "group"
    assert snapshot.message_count == 4
    assert snapshot.coverage_start is not None
    assert snapshot.coverage_start.timestamp() == 1750000000
    assert snapshot.coverage_end == snapshot.coverage_start
    assert acquisition.acquired_at == snapshot.acquired_at
    assert snapshot_manager.validate_snapshot(snapshot.id).status is (
        SnapshotStatus.AVAILABLE
    )


def test_acquire_export_reuses_latest_available_snapshot(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    snapshot_manager = ChatDataSnapshotManager(tmp_path / "user-data")
    request = QQExportImportRequest(group_code="700000001")
    first_provider = _StubProvider(export_path)
    first = QQExportImportService(
        first_provider,
        snapshot_manager=snapshot_manager,
    ).acquire_export(request)
    second_provider = _StubProvider(tmp_path / "must-not-be-used.json")

    second = QQExportImportService(
        second_provider,
        snapshot_manager=snapshot_manager,
    ).acquire_export(request)

    assert second.payload_path == first.payload_path
    assert second.snapshot_id == first.snapshot_id
    assert second.acquired_at == first.acquired_at
    assert second.reused_snapshot is True
    assert second_provider.calls == []


def test_force_refresh_exports_and_creates_a_new_snapshot(tmp_path: Path) -> None:
    old_export = _write_fake_export(tmp_path / "old_export.json")
    new_export = _write_fake_export(tmp_path / "new_export.json")
    snapshot_manager = ChatDataSnapshotManager(tmp_path / "user-data")
    request = QQExportImportRequest(group_code="700000001")
    first = QQExportImportService(
        _StubProvider(old_export),
        snapshot_manager=snapshot_manager,
    ).acquire_export(request)
    provider = _StubProvider(new_export)

    refreshed = QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
    ).acquire_export(
        QQExportImportRequest(
            group_code="700000001",
            force_refresh=True,
        )
    )

    assert refreshed.snapshot_id != first.snapshot_id
    assert refreshed.reused_snapshot is False
    assert refreshed.payload_path.read_bytes() == new_export.read_bytes()
    assert provider.calls == [("700000001", None, None)]


def test_invalid_snapshot_payload_causes_a_fresh_export(
    tmp_path: Path,
) -> None:
    old_export = _write_fake_export(tmp_path / "old_export.json")
    new_export = _write_fake_export(tmp_path / "new_export.json")
    snapshot_manager = ChatDataSnapshotManager(tmp_path / "user-data")
    first = QQExportImportService(
        _StubProvider(old_export),
        snapshot_manager=snapshot_manager,
    ).acquire_export(QQExportImportRequest(group_code="700000001"))
    first.payload_path.write_bytes(first.payload_path.read_bytes() + b"broken")
    provider = _StubProvider(new_export)

    replacement = QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
    ).acquire_export(QQExportImportRequest(group_code="700000001"))

    assert replacement.snapshot_id != first.snapshot_id
    assert replacement.reused_snapshot is False
    assert provider.calls == [("700000001", None, None)]


def test_legacy_absolute_path_cache_is_ignored_and_left_untouched(
    tmp_path: Path,
) -> None:
    legacy_directory = tmp_path / "legacy-cache"
    legacy_directory.mkdir()
    legacy_export = _write_fake_export(tmp_path / "legacy-export.json")
    legacy_metadata = legacy_directory / "metadata.json"
    original_metadata = json.dumps(
        {
            "entries": [
                {
                    "source": "qq",
                    "conversation_id": "700000001",
                    "export_file_path": str(legacy_export.resolve()),
                }
            ]
        }
    )
    legacy_metadata.write_text(original_metadata, encoding="utf-8")
    new_export = _write_fake_export(tmp_path / "new-export.json")
    provider = _StubProvider(new_export)

    acquisition = QQExportImportService(
        provider,
        cache_directory=legacy_directory,
        snapshot_manager=ChatDataSnapshotManager(tmp_path / "user-data"),
    ).acquire_export(QQExportImportRequest(group_code="700000001"))

    assert acquisition.payload_path.read_bytes() == new_export.read_bytes()
    assert provider.calls == [("700000001", None, None)]
    assert legacy_metadata.read_text(encoding="utf-8") == original_metadata


def test_snapshot_save_failure_returns_verified_provider_export(
    tmp_path: Path,
) -> None:
    class _FailingSnapshotManager(ChatDataSnapshotManager):
        def save_snapshot(self, *args, **kwargs):
            raise SnapshotSaveError("fictional write failure")

    export_path = _write_fake_export(tmp_path / "fallback-export.json")
    provider = _StubProvider(export_path)

    acquisition = QQExportImportService(
        provider,
        snapshot_manager=_FailingSnapshotManager(tmp_path / "user-data"),
    ).acquire_export(QQExportImportRequest(group_code="700000001"))

    assert acquisition.payload_path == export_path
    assert acquisition.snapshot_id is None
    assert acquisition.acquired_at is None
    assert acquisition.reused_snapshot is False
    assert provider.calls == [("700000001", None, None)]


def test_export_only_accepts_string_path(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(str(export_path)))

    returned = service.export_only(QQExportImportRequest(group_code="700000001"))

    assert returned != export_path
    assert returned.read_bytes() == export_path.read_bytes()


def test_export_only_does_not_import_messages(tmp_path: Path) -> None:
    """export_only stops at the file; it must not run the import pipeline."""
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    calls: list[Path] = []

    class _RecordingImportService(ImportService):
        def execute(self, request: ImportRequest):
            calls.append(request.input_path)
            return super().execute(request)

    service = QQExportImportService(
        _StubProvider(export_path),
        import_service=_RecordingImportService(),
    )
    returned = service.export_only(QQExportImportRequest(group_code="700000001"))

    assert returned != export_path
    assert returned.read_bytes() == export_path.read_bytes()
    assert calls == []


def test_get_session_message_range_uses_real_message_timestamps(
    tmp_path: Path,
) -> None:
    export_path = tmp_path / "range_export.json"
    payload = {
        "chatInfo": {"chatType": 2, "peerUid": "700000002", "name": "Fictional"},
        "messages": [
            _qce_message("fake-1", timestamp=1700000000),
            _qce_message("fake-2", "image", timestamp=1700007200),
            {"id": "fake-3", "timestamp": None},
        ],
    }
    export_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    provider = _StubProvider(export_path)
    service = QQExportImportService(provider)

    message_range = service.get_session_message_range("700000002")

    assert message_range == (1700000000, 1700007200)
    assert provider.calls == [("700000002", None, None)]


def test_export_only_returning_none_raises_unavailable() -> None:
    service = QQExportImportService(_StubProvider(None))

    with pytest.raises(QQExportUnavailable):
        service.export_only(QQExportImportRequest(group_code="700000001"))


def test_export_only_returning_blank_string_raises_unavailable() -> None:
    service = QQExportImportService(_StubProvider("   "))

    with pytest.raises(QQExportUnavailable):
        service.export_only(QQExportImportRequest(group_code="700000001"))


def test_export_only_missing_file_raises_file_missing(tmp_path: Path) -> None:
    absent = tmp_path / "not_created.json"
    service = QQExportImportService(_StubProvider(absent))

    with pytest.raises(QQExportFileMissing):
        service.export_only(QQExportImportRequest(group_code="700000001"))


def test_export_only_propagates_provider_error() -> None:
    service = QQExportImportService(_FailingProvider())

    with pytest.raises(ApplicationServiceError) as excinfo:
        service.export_only(QQExportImportRequest(group_code="700000001"))

    assert excinfo.value.code == "qce_service_unreachable"
