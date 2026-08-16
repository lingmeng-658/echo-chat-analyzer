"""End-to-end tests for the WeChat provider -> adapter -> ChatMessage seam.

No real WeChat database is opened. The provider is a stub that writes a
fictional export document, mirroring test_qq_export_import_service.py.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ApplicationServiceError,
    ImportService,
    WeChatExportFileMissing,
    WeChatExportImportRequest,
    WeChatExportImportService,
    WeChatExportProvider,
    WeChatExportUnavailable,
)
from qq_chat_analyzer.application.import_service import WECHAT_DB_FORMAT
from qq_chat_analyzer.providers.wechat_database_provider import (
    DatabaseNotFound,
    KeyUnavailable,
    WeChatSession,
)


FICTIONAL_SESSION = "wxid_fictional_room@chatroom"
TEXT_LOCAL_TYPE = 1
IMAGE_LOCAL_TYPE = 3


# --------------------------------------------------------------------- fixtures


def _db_row(
    message_content: str = "Fictional wechat line",
    local_type: int = TEXT_LOCAL_TYPE,
    create_time: int = 1753412807,
    user_name: str = "wxid_fictional_sender",
    server_id: int = 900001,
) -> dict:
    return {
        "local_id": 11,
        "server_id": server_id,
        "local_type": local_type,
        "create_time": create_time,
        "message_content": message_content,
        "user_name": user_name,
    }


def _write_fake_export(path: Path, rows: list | None = None) -> Path:
    """Write a fictional WeChat database export document."""
    document = {
        "source": "wechat-db",
        "conversation": {"username": FICTIONAL_SESSION},
        "messages": rows
        if rows is not None
        else [
            _db_row(message_content="Fictional wechat line", server_id=900001),
            _db_row(message_content="Second fictional line", server_id=900002),
            _db_row(local_type=IMAGE_LOCAL_TYPE, server_id=900003),
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


class _StubProvider:
    """Stand-in for WeChatDatabaseProvider that never touches a database."""

    def __init__(
        self,
        rows: list | None = None,
        result: object = "write",
        error: Exception | None = None,
        sessions: list | None = None,
    ) -> None:
        self._rows = rows
        self._result = result
        self._error = error
        self._sessions = sessions or []
        self.calls: list[dict] = []

    def list_sessions(self) -> list:
        if self._error is not None:
            raise self._error
        return self._sessions

    def export_session_json(
        self,
        session_id,
        output_path,
        start_time=None,
        end_time=None,
    ):
        self.calls.append(
            {
                "session_id": session_id,
                "output_path": output_path,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        if self._error is not None:
            raise self._error
        if self._result == "write":
            return _write_fake_export(Path(output_path), self._rows)
        return self._result


def _request(tmp_path: Path, **kwargs) -> WeChatExportImportRequest:
    return WeChatExportImportRequest(
        session_id=kwargs.pop("session_id", FICTIONAL_SESSION),
        output_path=kwargs.pop("output_path", tmp_path / "export.json"),
        **kwargs,
    )


# ------------------------------------------------------------------- contract


def test_stub_provider_satisfies_the_protocol() -> None:
    assert isinstance(_StubProvider(), WeChatExportProvider)


def test_request_is_frozen(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(Exception):
        request.session_id = "changed"  # type: ignore[misc]


def test_service_errors_are_application_errors() -> None:
    assert issubclass(WeChatExportUnavailable, ApplicationServiceError)
    assert issubclass(WeChatExportFileMissing, ApplicationServiceError)
    assert WeChatExportUnavailable().public_message
    assert WeChatExportFileMissing().public_message
    assert WeChatExportUnavailable.code == "wechat_export_unavailable"
    assert WeChatExportFileMissing.code == "wechat_export_file_missing"


# -------------------------------------------------------------------- execute


def test_execute_exports_then_imports_into_chat_messages(tmp_path: Path) -> None:
    provider = _StubProvider()
    service = WeChatExportImportService(provider)

    outcome = service.execute(_request(tmp_path))

    assert outcome.result.platform == "wechat"
    assert outcome.result.format == WECHAT_DB_FORMAT
    assert outcome.result.message_count == 2
    assert outcome.result.valid_text_count == 2
    assert [message.text for message in outcome.messages] == [
        "Fictional wechat line",
        "Second fictional line",
    ]
    assert {message.platform for message in outcome.messages} == {"wechat"}
    assert {message.conversation_id for message in outcome.messages} == {
        FICTIONAL_SESSION
    }


def test_execute_passes_session_and_time_window_to_provider(tmp_path: Path) -> None:
    provider = _StubProvider()
    service = WeChatExportImportService(provider)
    output_path = tmp_path / "windowed.json"

    service.execute(
        _request(
            tmp_path,
            output_path=output_path,
            start_time=1753400000,
            end_time=1753500000,
        )
    )

    assert provider.calls == [
        {
            "session_id": FICTIONAL_SESSION,
            "output_path": output_path,
            "start_time": 1753400000,
            "end_time": 1753500000,
        }
    ]


def test_execute_accepts_a_string_path_from_the_provider(tmp_path: Path) -> None:
    export_path = tmp_path / "as-string.json"
    _write_fake_export(export_path)
    provider = _StubProvider(result=str(export_path))
    service = WeChatExportImportService(provider)

    outcome = service.execute(_request(tmp_path))

    assert outcome.result.message_count == 2


def test_execute_reuses_the_injected_import_service(tmp_path: Path) -> None:
    class _RecordingImportService(ImportService):
        def __init__(self) -> None:
            self.requests: list = []

        def execute(self, request):
            self.requests.append(request)
            return super().execute(request)

    import_service = _RecordingImportService()
    service = WeChatExportImportService(_StubProvider(), import_service)

    service.execute(_request(tmp_path))

    assert len(import_service.requests) == 1
    assert import_service.requests[0].platform == "wechat"


def test_execute_logs_import_failure_without_exception_message(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class _FailingImportService(ImportService):
        def execute(self, request):
            raise RuntimeError("fictional secret import detail")

    service = WeChatExportImportService(
        _StubProvider(),
        _FailingImportService(),
    )

    with caplog.at_level(
        logging.WARNING,
        logger="qq_chat_analyzer.desktop.wechat_export_import_service",
    ):
        with pytest.raises(RuntimeError):
            service.execute(_request(tmp_path))

    assert "wechat.import.failed error_type=RuntimeError" in caplog.text
    assert "fictional secret import detail" not in caplog.text


def test_empty_conversation_imports_without_messages(tmp_path: Path) -> None:
    service = WeChatExportImportService(_StubProvider(rows=[]))

    outcome = service.execute(_request(tmp_path))

    assert outcome.result.message_count == 0
    assert outcome.messages == ()


# ---------------------------------------------------------------- export_only


def test_export_only_returns_path_without_importing(tmp_path: Path) -> None:
    provider = _StubProvider()
    service = WeChatExportImportService(provider)
    output_path = tmp_path / "only.json"

    result = service.export_only(_request(tmp_path, output_path=output_path))

    assert result == output_path
    assert result.exists()


def test_missing_file_raises_export_file_missing(tmp_path: Path) -> None:
    provider = _StubProvider(result=tmp_path / "never-written.json")
    service = WeChatExportImportService(provider)

    with pytest.raises(WeChatExportFileMissing):
        service.execute(_request(tmp_path))


@pytest.mark.parametrize("bad_result", [None, "", "   ", 42, object()])
def test_unusable_provider_result_raises_export_unavailable(
    tmp_path: Path,
    bad_result: object,
) -> None:
    service = WeChatExportImportService(_StubProvider(result=bad_result))

    with pytest.raises(WeChatExportUnavailable):
        service.execute(_request(tmp_path))


def test_provider_errors_propagate_unchanged(tmp_path: Path) -> None:
    for error in (DatabaseNotFound(), KeyUnavailable()):
        service = WeChatExportImportService(_StubProvider(error=error))

        with pytest.raises(type(error)) as excinfo:
            service.execute(_request(tmp_path))

        assert excinfo.value.public_message == error.public_message


# -------------------------------------------------------------- list_sessions


def test_list_sessions_delegates_to_the_provider() -> None:
    sessions = [
        WeChatSession(
            session_id=FICTIONAL_SESSION,
            display_name=FICTIONAL_SESSION,
            session_type="group",
        )
    ]
    service = WeChatExportImportService(_StubProvider(sessions=sessions))

    assert service.list_sessions() == sessions


def test_list_sessions_propagates_provider_errors() -> None:
    service = WeChatExportImportService(_StubProvider(error=DatabaseNotFound()))

    with pytest.raises(DatabaseNotFound):
        service.list_sessions()
