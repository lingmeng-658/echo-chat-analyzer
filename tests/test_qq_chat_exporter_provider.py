"""Behavioral tests for the QQChatExporter (QCE) HTTP provider.

Every test uses a stub transport. Nothing here contacts a real QCE service,
starts a process, or touches real chat data.
"""

from __future__ import annotations

import json
import sys
import urllib.error
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.providers.qq_chat_exporter_provider import (
    DEFAULT_BASE_URL,
    ExportTaskCancelled,
    ExportTaskFailed,
    ExportTaskLimitReached,
    ExportTimeout,
    QQChatExporterProvider,
    RequestFailed,
    ServiceUnavailable,
    TaskNotFound,
    TokenUnavailable,
    read_token,
    resolve_security_candidates,
    resolve_security_path,
)


FAKE_TOKEN = "fictional-token-0000"


def _envelope(data: object) -> str:
    return json.dumps({"success": True, "data": data, "requestId": "req-1"})


def _error_envelope(code: str, message: str) -> str:
    return json.dumps(
        {"success": False, "error": {"code": code, "message": message}, "requestId": "req-1"}
    )


class _StubTransport:
    """Records calls and replays queued ``(status, body)`` responses."""

    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, method, url, payload, headers, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "payload": json.loads(payload.decode("utf-8")) if payload else None,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError(f"unexpected extra request: {method} {url}")
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class _RaisingTransport:
    def __init__(self, error: BaseException) -> None:
        self._error = error
        self.calls = 0

    def __call__(self, method, url, payload, headers, timeout):
        self.calls += 1
        raise self._error


def _provider(responses, **kwargs):
    transport = _StubTransport(responses)
    provider = QQChatExporterProvider(
        token=FAKE_TOKEN,
        transport=transport,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return provider, transport


# ------------------------------------------------------------------ health check


def test_health_check_reports_available_service():
    provider, transport = _provider([(200, _envelope({"status": "healthy", "version": "4.1.0"}))])

    health = provider.health_check()

    assert health.available is True
    assert health.status == "healthy"
    assert health.version == "4.1.0"
    assert transport.calls[0]["url"] == f"{DEFAULT_BASE_URL}/api/health"


def test_health_check_does_not_send_authorization_header():
    provider, transport = _provider([(200, _envelope({"status": "healthy"}))])

    provider.health_check()

    assert "Authorization" not in transport.calls[0]["headers"]


def test_health_check_returns_unavailable_when_connection_refused():
    transport = _RaisingTransport(urllib.error.URLError("connection refused"))
    provider = QQChatExporterProvider(token=FAKE_TOKEN, transport=transport)

    health = provider.health_check()

    assert health.available is False
    assert provider.is_available() is False


def test_health_check_survives_error_envelope():
    provider, _ = _provider([(500, _error_envelope("INTERNAL", "boom"))])

    assert provider.health_check().available is False


# ------------------------------------------------------------------------ token


def test_read_token_reads_access_token(tmp_path):
    target = tmp_path / "security.json"
    target.write_text(json.dumps({"accessToken": FAKE_TOKEN}), encoding="utf-8")

    assert read_token(target) == FAKE_TOKEN


def test_read_token_returns_none_for_missing_file(tmp_path):
    assert read_token(tmp_path / "absent.json") is None


def test_read_token_returns_none_for_malformed_json(tmp_path):
    target = tmp_path / "security.json"
    target.write_text("{not json", encoding="utf-8")

    assert read_token(target) is None


def test_read_token_returns_none_when_token_blank(tmp_path):
    target = tmp_path / "security.json"
    target.write_text(json.dumps({"accessToken": "   "}), encoding="utf-8")

    assert read_token(target) is None


def test_resolve_security_path_honours_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("QCE_CONFIG_DIR", str(tmp_path))

    assert resolve_security_path() == tmp_path / "security.json"


def test_resolve_security_candidates_config_dir_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("QCE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    candidates = resolve_security_candidates()

    assert candidates == (tmp_path / "security.json",)


def test_resolve_security_path_prefers_windows_desktop_path(monkeypatch, tmp_path):
    monkeypatch.delenv("QCE_CONFIG_DIR", raising=False)
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    resolved = resolve_security_path()

    assert resolved == local / "QQChatExporter" / ".qce-config" / "security.json"


def test_resolve_security_candidates_includes_windows_desktop_path(monkeypatch, tmp_path):
    monkeypatch.delenv("QCE_CONFIG_DIR", raising=False)
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    candidates = resolve_security_candidates()

    expected = local / "QQChatExporter" / ".qce-config" / "security.json"
    assert candidates[0] == expected
    assert expected in candidates


def test_resolve_security_candidates_keeps_home_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("QCE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    candidates = resolve_security_candidates()

    assert candidates[-1] == tmp_path / ".qq-chat-exporter" / "security.json"


def test_read_token_falls_back_to_home_when_windows_path_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("QCE_CONFIG_DIR", raising=False)
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    home = tmp_path / "Home"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))

    home_path = home / ".qq-chat-exporter" / "security.json"
    home_path.parent.mkdir(parents=True)
    home_path.write_text(json.dumps({"accessToken": FAKE_TOKEN}), encoding="utf-8")

    assert read_token() == FAKE_TOKEN


def test_authenticated_request_sends_bearer_token(tmp_path):
    target = tmp_path / "security.json"
    target.write_text(json.dumps({"accessToken": FAKE_TOKEN}), encoding="utf-8")
    transport = _StubTransport([(200, _envelope({"groups": []}))])
    provider = QQChatExporterProvider(transport=transport, security_path=target)

    provider.list_groups()

    assert transport.calls[0]["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"


def test_missing_token_raises_token_unavailable(tmp_path):
    transport = _StubTransport([(200, _envelope({"groups": []}))])
    provider = QQChatExporterProvider(
        transport=transport, security_path=tmp_path / "absent.json"
    )

    with pytest.raises(TokenUnavailable):
        provider.list_groups()

    assert transport.calls == []


def test_unauthorized_response_raises_token_unavailable():
    provider, _ = _provider([(401, _error_envelope("UNAUTHORIZED", "bad token"))])

    with pytest.raises(TokenUnavailable):
        provider.list_groups()


# ----------------------------------------------------------------------- groups


def test_list_groups_maps_rows():
    payload = {
        "groups": [
            {"groupCode": "100001", "groupName": "\u865a\u6784\u7fa4 A", "memberCount": 42},
            {"groupCode": "100002", "groupName": "\u865a\u6784\u7fa4 B", "memberCount": None},
        ],
        "totalCount": 2,
    }
    provider, transport = _provider([(200, _envelope(payload))])

    groups = provider.list_groups()

    assert [g.group_code for g in groups] == ["100001", "100002"]
    assert groups[0].group_name == "\u865a\u6784\u7fa4 A"
    assert groups[0].member_count == 42
    assert groups[1].member_count is None
    assert "page=1" in transport.calls[0]["url"]


def test_list_groups_passes_force_refresh():
    provider, transport = _provider([(200, _envelope({"groups": []}))])

    provider.list_groups(page=2, limit=10, force_refresh=True)

    url = transport.calls[0]["url"]
    assert "forceRefresh=true" in url
    assert "page=2" in url
    assert "limit=10" in url


def test_list_groups_skips_rows_without_group_code():
    payload = {"groups": [{"groupName": "no code"}, "not-a-mapping", {"groupCode": "100003"}]}
    provider, _ = _provider([(200, _envelope(payload))])

    groups = provider.list_groups()

    assert [g.group_code for g in groups] == ["100003"]


def test_list_groups_returns_empty_for_unexpected_shape():
    provider, _ = _provider([(200, _envelope({"unexpected": True}))])

    assert provider.list_groups() == []


# ----------------------------------------------------------------- create export


def test_create_export_task_builds_group_json_request():
    data = {
        "taskId": "export_1",
        "status": "running",
        "fileName": "group.json",
        "filePath": "D:/exports/group.json",
        "messageCount": 0,
    }
    provider, transport = _provider([(200, _envelope(data))])

    task = provider.create_export_task("100001", start_time=1700000000, end_time=1700003600)

    body = transport.calls[0]["payload"]
    assert transport.calls[0]["method"] == "POST"
    assert transport.calls[0]["url"].endswith("/api/messages/export")
    assert body["peer"] == {"chatType": 2, "peerUid": "100001"}
    assert body["format"] == "JSON"
    assert body["filter"] == {"startTime": 1700000000, "endTime": 1700003600}
    assert task.task_id == "export_1"
    assert task.status == "running"
    assert task.is_terminal is False


def test_create_export_task_omits_empty_filter():
    provider, transport = _provider(
        [(200, _envelope({"taskId": "export_2", "status": "running"}))]
    )

    provider.create_export_task("100001")

    assert "filter" not in transport.calls[0]["payload"]


def test_create_export_task_rejects_blank_group_code():
    provider, transport = _provider([(200, _envelope({}))])

    with pytest.raises(RequestFailed):
        provider.create_export_task("   ")

    assert transport.calls == []


def test_create_export_task_raises_on_task_limit():
    provider, _ = _provider(
        [(429, _error_envelope("EXPORT_TASK_LIMIT_REACHED", "too many tasks"))]
    )

    with pytest.raises(ExportTaskLimitReached):
        provider.create_export_task("100001")


def test_create_export_task_raises_when_service_down():
    transport = _RaisingTransport(urllib.error.URLError("refused"))
    provider = QQChatExporterProvider(token=FAKE_TOKEN, transport=transport)

    with pytest.raises(ServiceUnavailable):
        provider.create_export_task("100001")


# -------------------------------------------------------------------- polling


def test_wait_export_task_returns_completed_file_path():
    responses = [
        (200, _envelope({"taskId": "export_3", "status": "running", "progress": 60})),
        (
            200,
            _envelope(
                {
                    "taskId": "export_3",
                    "status": "completed",
                    "progress": 100,
                    "messageCount": 128,
                    "filePath": "D:/exports/group.json",
                    "fileName": "group.json",
                }
            ),
        ),
    ]
    provider, transport = _provider(responses)

    result = provider.wait_export_task("export_3", poll_interval=0)

    assert result == Path("D:/exports/group.json")
    assert len(transport.calls) == 2
    assert transport.calls[0]["url"].endswith("/api/tasks/export_3")


def test_wait_export_task_raises_with_error_text_on_failure():
    responses = [
        (
            200,
            _envelope(
                {
                    "taskId": "export_4",
                    "status": "failed",
                    "progress": 70,
                    "error": "napcat connection lost",
                }
            ),
        )
    ]
    provider, _ = _provider(responses)

    with pytest.raises(ExportTaskFailed) as excinfo:
        provider.wait_export_task("export_4", poll_interval=0)

    assert excinfo.value.error == "napcat connection lost"
    assert "napcat connection lost" in excinfo.value.public_message


def test_wait_export_task_raises_on_cancelled():
    provider, _ = _provider(
        [(200, _envelope({"taskId": "export_5", "status": "cancelled", "progress": 42}))]
    )

    with pytest.raises(ExportTaskCancelled):
        provider.wait_export_task("export_5", poll_interval=0)


def test_wait_export_task_ignores_progress_as_completion_signal():
    """progress may reach 100 before status settles; status alone decides."""
    responses = [
        (200, _envelope({"taskId": "export_6", "status": "running", "progress": 100})),
        (
            200,
            _envelope(
                {"taskId": "export_6", "status": "completed", "filePath": "D:/exports/g.json"}
            ),
        ),
    ]
    provider, transport = _provider(responses)

    assert provider.wait_export_task("export_6", poll_interval=0) == Path("D:/exports/g.json")
    assert len(transport.calls) == 2


def test_wait_export_task_treats_unknown_status_as_pending():
    responses = [
        (200, _envelope({"taskId": "export_7", "status": "pending"})),
        (200, _envelope({"taskId": "export_7", "status": "completed", "filePath": "D:/g.json"})),
    ]
    provider, transport = _provider(responses)

    provider.wait_export_task("export_7", poll_interval=0)

    assert len(transport.calls) == 2


def test_wait_export_task_times_out():
    clock = iter([0.0, 0.0, 10.0, 20.0, 30.0, 40.0])
    transport = _StubTransport([(200, _envelope({"taskId": "export_8", "status": "running"}))])
    provider = QQChatExporterProvider(
        token=FAKE_TOKEN,
        transport=transport,
        sleep=lambda _seconds: None,
        monotonic=lambda: next(clock),
    )

    with pytest.raises(ExportTimeout):
        provider.wait_export_task("export_8", timeout=5, poll_interval=0)


def test_wait_export_task_raises_task_not_found():
    provider, _ = _provider([(404, _error_envelope("TASK_NOT_FOUND", "\u4efb\u52a1\u4e0d\u5b58\u5728"))])

    with pytest.raises(TaskNotFound):
        provider.wait_export_task("missing", poll_interval=0)


def test_wait_export_task_rejects_completed_without_file_path():
    provider, _ = _provider(
        [(200, _envelope({"taskId": "export_9", "status": "completed", "progress": 100}))]
    )

    with pytest.raises(ExportTaskFailed):
        provider.wait_export_task("export_9", poll_interval=0)


def test_get_export_task_reads_flattened_id():
    provider, _ = _provider([(200, _envelope({"id": "export_10", "status": "running"}))])

    task = provider.get_export_task("export_10")

    assert task.task_id == "export_10"


def test_export_group_json_creates_then_waits():
    responses = [
        (200, _envelope({"taskId": "export_11", "status": "running"})),
        (200, _envelope({"taskId": "export_11", "status": "completed", "filePath": "D:/g.json"})),
    ]
    provider, transport = _provider(responses)

    result = provider.export_group_json("100001", poll_interval=0)

    assert result == Path("D:/g.json")
    assert transport.calls[0]["method"] == "POST"
    assert transport.calls[1]["method"] == "GET"


# ------------------------------------------------------------------ http errors


def test_server_error_raises_request_failed():
    provider, _ = _provider([(500, _error_envelope("INTERNAL", "boom"))])

    with pytest.raises(RequestFailed):
        provider.list_groups()


def test_unsuccessful_envelope_raises_request_failed():
    provider, _ = _provider([(200, _error_envelope("GET_GROUPS_FAILED", "napcat offline"))])

    with pytest.raises(RequestFailed) as excinfo:
        provider.list_groups()

    assert "napcat offline" in excinfo.value.public_message


def test_non_json_body_raises_request_failed():
    provider, _ = _provider([(200, "<html>not json</html>")])

    with pytest.raises(RequestFailed):
        provider.list_groups()


def test_os_error_is_reported_as_service_unavailable():
    transport = _RaisingTransport(OSError("socket closed"))
    provider = QQChatExporterProvider(token=FAKE_TOKEN, transport=transport)

    with pytest.raises(ServiceUnavailable):
        provider.list_groups()
