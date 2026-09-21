"""End-to-end tests for the QCE provider -> adapter -> ChatMessage seam.

No real QCE service is contacted. The provider is a stub that returns a path to
a fictional export file written by the test itself.
"""

from __future__ import annotations

import json
import shutil
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
from qq_chat_analyzer.providers import ExportTask


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every default (uninjected) path inside ``tmp_path``.

    ``LOCALAPPDATA`` isolates ``user_data_dir``. The QQ transient workspace no
    longer uses it: it now defaults below the QCE Documents exports folder, so
    ``Path.home`` has to be isolated too. Without that, a default-constructed
    service would create real directories in the developer's Documents folder.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "home"))


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
        output_dir: str | None = None,
    ) -> object:
        self.calls.append((group_code, start_time, end_time))
        if (
            output_dir is not None
            and isinstance(self._export_path, (str, Path))
            and Path(self._export_path).is_file()
        ):
            target = Path(output_dir) / Path(self._export_path).name
            shutil.copyfile(self._export_path, target)
            return target
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
        output_dir: str | None = None,
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
        output_dir = kwargs.get("output_dir")
        if output_dir is not None and self.export_path is not None:
            target = Path(output_dir) / Path(self.export_path).name
            shutil.copyfile(self.export_path, target)
            return target
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

    with service.acquired_export(
        QQExportImportRequest(
            group_code="u_fictional_1",
            chat_type=1,
            peer_uin="200001",
            session_name="Fictional Alice",
        )
    ):
        pass

    assert len(provider.export_calls) == 1
    call = provider.export_calls[0]
    output_dir = Path(call.pop("output_dir"))
    assert call == {
        "peer_uid": "u_fictional_1",
        "chat_type": 1,
        "peer_uin": "200001",
        "session_name": "Fictional Alice",
        "start_time": None,
        "end_time": None,
    }
    assert not output_dir.exists()


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


def test_acquired_export_creates_snapshot_after_verified_provider_export(
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

    with service.acquired_export(request) as acquisition:
        assert acquisition.payload_path.is_file()

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


def test_acquired_export_reuses_latest_available_snapshot(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    snapshot_manager = ChatDataSnapshotManager(tmp_path / "user-data")
    request = QQExportImportRequest(group_code="700000001")
    first_provider = _StubProvider(export_path)
    with QQExportImportService(
        first_provider,
        snapshot_manager=snapshot_manager,
    ).acquired_export(request) as first:
        assert first.payload_path.is_file()
    second_provider = _StubProvider(tmp_path / "must-not-be-used.json")

    with QQExportImportService(
        second_provider,
        snapshot_manager=snapshot_manager,
    ).acquired_export(request) as second:
        assert second.payload_path.is_file()

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
    with QQExportImportService(
        _StubProvider(old_export),
        snapshot_manager=snapshot_manager,
    ).acquired_export(request) as first:
        assert first.snapshot_id is not None
    provider = _StubProvider(new_export)

    with QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
    ).acquired_export(
        QQExportImportRequest(
            group_code="700000001",
            force_refresh=True,
        )
    ) as refreshed:
        assert refreshed.payload_path.is_file()

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
    with QQExportImportService(
        _StubProvider(old_export),
        snapshot_manager=snapshot_manager,
    ).acquired_export(QQExportImportRequest(group_code="700000001")) as first:
        assert first.snapshot_id is not None
    first.payload_path.write_bytes(first.payload_path.read_bytes() + b"broken")
    provider = _StubProvider(new_export)

    with QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
    ).acquired_export(
        QQExportImportRequest(group_code="700000001")
    ) as replacement:
        assert replacement.payload_path.is_file()

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

    with QQExportImportService(
        provider,
        cache_directory=legacy_directory,
        snapshot_manager=ChatDataSnapshotManager(tmp_path / "user-data"),
    ).acquired_export(
        QQExportImportRequest(group_code="700000001")
    ) as acquisition:
        assert acquisition.payload_path.is_file()

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

    with QQExportImportService(
        provider,
        snapshot_manager=_FailingSnapshotManager(tmp_path / "user-data"),
    ).acquired_export(
        QQExportImportRequest(group_code="700000001")
    ) as acquisition:
        # A snapshot save failure falls back to the provider's export as
        # it was written into the Echo-owned run, so the payload only
        # exists while the consumer is running.
        payload_bytes = acquisition.payload_path.read_bytes()
        assert acquisition.snapshot_id is None
        assert acquisition.acquired_at is None
        assert acquisition.reused_snapshot is False

    assert payload_bytes == export_path.read_bytes()
    assert provider.calls == [("700000001", None, None)]


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


# -------------------------------- 6. structured export progress contract (REL-01)
#
# ``acquired_export`` must be able to surface the provider's own export progress
# to a caller-supplied callback, without leaking the provider's task type. The
# contract mirrors exactly what QCE reports and can be trusted:
# ``progress``, ``message_count``, ``status`` and ``message``. It carries no
# ``total``: QCE has no reliable totalMessages, so the application layer must
# never invent one. Progress must never change what ``acquired_export`` persists.


def _provider_task(
    status: str,
    *,
    progress: int | None = None,
    message_count: int | None = None,
    message: str = "",
    task_id: str = "export_progress",
) -> ExportTask:
    """Build one provider-side task snapshot, exactly as the provider would."""
    return ExportTask(
        task_id=task_id,
        status=status,
        progress=progress,
        message_count=message_count,
        progress_message=message,
    )


class _ProgressStubProvider:
    """Provider stub that replays scripted task snapshots while exporting.

    It exposes every export style the orchestrator may use (the convenience
    ``export_chat_json`` / ``export_group_json`` wrappers and the lower-level
    ``create_export_task`` / ``wait_export_task`` pair), so the progress callback
    is delivered no matter which route the application layer picks.
    """

    def __init__(
        self,
        export_path: object,
        updates: list[ExportTask] | None = None,
    ) -> None:
        self._export_path = export_path
        self._updates = list(updates or [])
        self.calls: list[tuple[str, object, object]] = []
        self.received_callbacks: list[object] = []

    def export_chat_json(
        self,
        peer_uid: str,
        *,
        chat_type: int = 2,
        peer_uin: object = None,
        session_name: object = None,
        start_time: object = None,
        end_time: object = None,
        output_dir: object = None,
        on_task_update: object = None,
    ) -> object:
        self.calls.append((peer_uid, start_time, end_time))
        self._deliver(on_task_update)
        return self._export_into(output_dir)

    def export_group_json(
        self,
        group_code: str,
        start_time: object = None,
        end_time: object = None,
        output_dir: object = None,
        on_task_update: object = None,
    ) -> object:
        self.calls.append((group_code, start_time, end_time))
        self._deliver(on_task_update)
        return self._export_into(output_dir)

    def create_export_task(
        self,
        peer_uid: str,
        start_time: object = None,
        end_time: object = None,
        session_name: object = None,
        output_dir: object = None,
        chat_type: int = 2,
        peer_uin: object = None,
    ) -> ExportTask:
        self.calls.append((peer_uid, start_time, end_time))
        return _provider_task("running")

    def wait_export_task(
        self,
        task_id: str,
        timeout: float = 900,
        poll_interval: float = 2.0,
        on_task_update: object = None,
    ) -> Path:
        self._deliver(on_task_update)
        return Path(self._export_path)

    def _export_into(self, output_dir: object) -> object:
        """Honour the application-chosen directory, like the real provider."""
        export_path = Path(self._export_path)
        if output_dir is None or not export_path.is_file():
            return self._export_path
        target = Path(output_dir) / export_path.name
        shutil.copyfile(export_path, target)
        return target

    def _deliver(self, on_task_update: object) -> None:
        self.received_callbacks.append(on_task_update)
        if on_task_update is None:
            return
        for update in self._updates:
            on_task_update(update)


def _progress_service(
    tmp_path: Path,
    updates: list[ExportTask],
) -> tuple[QQExportImportService, _ProgressStubProvider]:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _ProgressStubProvider(export_path, updates=updates)
    service = QQExportImportService(
        provider,
        snapshot_manager=ChatDataSnapshotManager(tmp_path / "user-data"),
    )
    return service, provider


def test_acquired_export_forwards_structured_progress_to_callback(
    tmp_path: Path,
) -> None:
    """Every provider export snapshot reaches the caller's ``progress`` callback."""
    updates: list[object] = []
    service, provider = _progress_service(
        tmp_path,
        updates=[
            _provider_task("running", progress=0, message_count=0),
            _provider_task(
                "running",
                progress=42,
                message_count=123,
                message="正在导出",
            ),
            _provider_task("completed", progress=100, message_count=456),
        ],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ) as acquisition:
        assert acquisition.snapshot_id is not None

    assert provider.calls == [("700000001", None, None)]
    assert [update.status for update in updates] == [
        "running",
        "running",
        "completed",
    ]
    assert [update.progress for update in updates] == [0, 42, 100]
    assert [update.message_count for update in updates] == [0, 123, 456]
    assert acquisition.snapshot_id is not None


def test_acquired_export_progress_zero_is_kept(tmp_path: Path) -> None:
    """``progress=0`` must survive as ``0``, never collapse into a missing value."""
    updates: list[object] = []
    service, _ = _progress_service(
        tmp_path,
        updates=[_provider_task("running", progress=0, message_count=0)],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ):
        pass

    assert updates[0].progress == 0
    assert updates[0].progress is not None


def test_acquired_export_missing_progress_stays_none(tmp_path: Path) -> None:
    """A provider that reports no progress stays ``None``, never ``0``."""
    updates: list[object] = []
    service, _ = _progress_service(
        tmp_path,
        updates=[_provider_task("running")],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ):
        pass

    assert updates[0].progress is None


def test_acquired_export_message_count_is_kept(tmp_path: Path) -> None:
    """``message_count`` is forwarded verbatim, including a real ``0``."""
    updates: list[object] = []
    service, _ = _progress_service(
        tmp_path,
        updates=[
            _provider_task("running", progress=10, message_count=0),
            _provider_task("running", progress=20),
        ],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ):
        pass

    assert updates[0].message_count == 0
    assert updates[1].message_count is None


def test_acquired_export_progress_exposes_status_and_message(
    tmp_path: Path,
) -> None:
    """The provider's own ``status`` and progress ``message`` stay observable."""
    updates: list[object] = []
    service, _ = _progress_service(
        tmp_path,
        updates=[_provider_task("running", progress=5, message="正在准备导出")],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ):
        pass

    assert updates[0].status == "running"
    assert updates[0].message == "正在准备导出"


def test_acquired_export_progress_never_fabricates_total(tmp_path: Path) -> None:
    """Progress and message count are real; no ``total`` is ever invented."""
    updates: list[object] = []
    service, _ = _progress_service(
        tmp_path,
        updates=[_provider_task("running", progress=42, message_count=123)],
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ):
        pass

    update = updates[0]
    assert update.progress == 42
    assert getattr(update, "total", None) is None
    assert getattr(update, "total_messages", None) is None


def test_acquired_export_progress_keeps_snapshot_behavior(tmp_path: Path) -> None:
    """Reporting progress must not change what ``acquired_export`` persists."""
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    baseline_manager = ChatDataSnapshotManager(tmp_path / "baseline")
    with QQExportImportService(
        _StubProvider(export_path),
        snapshot_manager=baseline_manager,
    ).acquired_export(
        QQExportImportRequest(group_code="700000001")
    ) as baseline:
        assert baseline.snapshot_id is not None

    provider = _ProgressStubProvider(
        export_path,
        updates=[_provider_task("running", progress=10, message_count=1)],
    )
    progress_manager = ChatDataSnapshotManager(tmp_path / "with-progress")
    updates: list[object] = []
    with QQExportImportService(
        provider,
        snapshot_manager=progress_manager,
    ).acquired_export(
        QQExportImportRequest(group_code="700000001"),
        progress=updates.append,
    ) as with_progress:
        assert with_progress.snapshot_id is not None

    assert updates
    baseline_snapshot = baseline_manager.get_snapshot(baseline.snapshot_id)
    progress_snapshot = progress_manager.get_snapshot(with_progress.snapshot_id)
    assert baseline_snapshot is not None
    assert progress_snapshot is not None
    assert with_progress.reused_snapshot is False
    assert progress_snapshot.message_count == baseline_snapshot.message_count == 4
    assert progress_snapshot.session_id == baseline_snapshot.session_id
    assert progress_snapshot.source is baseline_snapshot.source
    assert progress_snapshot.session_type == baseline_snapshot.session_type
    assert progress_snapshot.coverage_start == baseline_snapshot.coverage_start
    assert progress_snapshot.coverage_end == baseline_snapshot.coverage_end
    assert (
        with_progress.payload_path.read_bytes() == baseline.payload_path.read_bytes()
    )


# ---------------------- Stage 1.2 QCE-accepted transient physical root


def test_default_service_acquires_inside_the_qce_echo_namespace(
    tmp_path: Path,
) -> None:
    """RED before the fix: the default run was allocated under LocalAppData.

    Real QCE refuses any ``outputDir`` outside
    ``Documents\\QQChatExporter\\exports``, so a default-constructed service
    must ask for ``exports\\Echo\\<run-id>`` and must still delete exactly
    that run while keeping the namespace.
    """
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _SessionStubProvider(export_path=export_path)
    service = QQExportImportService(provider)
    expected_namespace = (
        Path.home() / "Documents" / "QQChatExporter" / "exports" / "Echo"
    )

    with service.acquired_export(
        QQExportImportRequest(
            group_code="700000001",
            start_time=1750000000000,
            end_time=1750000001000,
        )
    ) as acquisition:
        run_directory = Path(provider.export_calls[0]["output_dir"])
        payload_path = Path(acquisition.payload_path)
        assert run_directory.is_dir()
        assert run_directory.parent == expected_namespace
        assert payload_path.is_relative_to(run_directory)
        assert payload_path.is_file()

    assert not run_directory.exists()
    assert expected_namespace.is_dir()
