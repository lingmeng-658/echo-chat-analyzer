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
    ImportRequest,
    ImportService,
    QQExportFileMissing,
    QQExportImportRequest,
    QQExportImportService,
    QQExportUnavailable,
)
from qq_chat_analyzer.qq_chat_exporter_adapter import (
    WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED,
)


# --------------------------------------------------------------------- fixtures


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

    assert calls == [export_path]
    assert outcome.result.message_count == 3


# --------------------------------------------------- export_only (path only)


def test_export_only_returns_provider_path(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    provider = _StubProvider(export_path)
    service = QQExportImportService(provider)

    returned = service.export_only(QQExportImportRequest(group_code="700000001"))

    assert returned == export_path
    assert provider.calls == [("700000001", None, None)]


def test_export_only_accepts_string_path(tmp_path: Path) -> None:
    export_path = _write_fake_export(tmp_path / "fake_export.json")
    service = QQExportImportService(_StubProvider(str(export_path)))

    returned = service.export_only(QQExportImportRequest(group_code="700000001"))

    assert returned == export_path


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

    assert returned == export_path
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
