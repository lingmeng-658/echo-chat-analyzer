"""Behavioral tests for the CipherTalk CLI (miyu) WeChat data source."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import wechat_cli_adapter
from qq_chat_analyzer.application import ImportRequest, ImportService
from qq_chat_analyzer.providers.wechat_cli_provider import (
    CliNotInstalled,
    DatabaseNotFound,
    ExportFailed,
    KeyUnavailable,
    SessionNotFound,
    WeChatCliProvider,
    WeChatNotRunning,
)


CLI_TEXT_TYPE = 1
CLI_IMAGE_TYPE = 3


def _cli_row(
    content: str = "Hello from the CLI",
    message_type: object = CLI_TEXT_TYPE,
    create_time: object = 1753412807,
    direction: str = "in",
    sender_username: str | None = "wxid_fictional_sender",
    server_id: object = 900001,
) -> dict[str, object]:
    row: dict[str, object] = {
        "localId": 11,
        "serverId": server_id,
        "createTime": create_time,
        "sortSeq": 22,
        "direction": direction,
        "type": message_type,
        "content": content,
    }
    if sender_username is not None:
        row["senderUsername"] = sender_username
    return row


def _write_cli_export(path: Path, rows: list[object]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def _envelope_ok(data: object) -> str:
    return json.dumps({"ok": True, "data": data, "meta": {"took_ms": 5}})


def _envelope_error(code: str, message: str) -> str:
    return json.dumps({"ok": False, "error": {"code": code, "message": message}})


def _provider(
    runner,
    monkeypatch: pytest.MonkeyPatch,
    installed: bool = True,
) -> WeChatCliProvider:
    monkeypatch.setattr(
        "qq_chat_analyzer.providers.wechat_cli_provider.shutil.which",
        lambda _name: "/usr/local/bin/miyu" if installed else None,
    )
    return WeChatCliProvider(runner=runner)


# --------------------------------------------------------------- adapter tests


def test_cli_export_is_detected(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(export_path, [_cli_row()])

    assert wechat_cli_adapter.is_cli_export(export_path) is True


def test_detailed_json_is_not_detected_as_cli_export(tmp_path: Path) -> None:
    export_path = tmp_path / "detailed.json"
    export_path.write_text(
        json.dumps(
            {
                "exportInfo": {"format": "detailed-json"},
                "session": {"platform": "wechat"},
                "messages": [],
            }
        ),
        encoding="utf-8",
    )

    assert wechat_cli_adapter.is_cli_export(export_path) is False


def test_empty_array_is_not_detected_as_cli_export(tmp_path: Path) -> None:
    export_path = tmp_path / "empty.json"
    _write_cli_export(export_path, [])

    assert wechat_cli_adapter.is_cli_export(export_path) is False


def test_cli_row_is_parsed_into_chat_message(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(export_path, [_cli_row()])

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert len(parsed) == 1
    message = parsed[0]
    assert message.text == "Hello from the CLI"
    assert message.message_type == "text"
    assert message.platform == "wechat"
    assert message.sender == "wxid_fictional_sender"
    assert message.sender_id == "wxid_fictional_sender"
    assert message.message_id == "900001"
    assert message.timestamp == 1753412807


def test_string_type_rows_are_parsed(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(
        export_path,
        [_cli_row(message_type="text"), _cli_row(message_type="reply")],
    )

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert [message.message_type for message in parsed] == ["text", "reply"]


def test_non_text_cli_rows_are_ignored(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(
        export_path,
        [
            _cli_row(message_type=CLI_IMAGE_TYPE, content="[image]"),
            _cli_row(message_type="voice", content="[voice]"),
            _cli_row(content="Only text survives"),
        ],
    )

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert [message.text for message in parsed] == ["Only text survives"]


def test_missing_sender_falls_back_to_direction(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(
        export_path,
        [
            _cli_row(sender_username=None, direction="out", content="Mine"),
            _cli_row(sender_username=None, direction="in", content="Theirs"),
        ],
    )

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert [message.sender for message in parsed] == ["\u6211", "\u5bf9\u65b9"]


def test_unknown_direction_without_sender_is_skipped(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(
        export_path,
        [_cli_row(sender_username=None, direction="unknown")],
    )

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert parsed == []


def test_malformed_rows_do_not_drop_valid_messages(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(
        export_path,
        [
            _cli_row(content="Before"),
            "not-an-object",
            _cli_row(create_time=None, content="No timestamp"),
            _cli_row(content="After"),
        ],
    )

    parsed = wechat_cli_adapter.parse_messages(
        wechat_cli_adapter.load_messages(export_path)
    )

    assert [message.text for message in parsed] == ["Before", "After"]


# ------------------------------------------------------------ ImportService


def test_import_service_routes_cli_export_to_wechat(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(export_path, [_cli_row(), _cli_row(content="Second")])

    outcome = ImportService().execute(ImportRequest(input_path=export_path))

    assert outcome.result.platform == "wechat"
    assert outcome.result.format == "cli-json"
    assert outcome.result.message_count == 2


def test_import_service_honors_wechat_hint_for_cli_export(tmp_path: Path) -> None:
    export_path = tmp_path / "session.json"
    _write_cli_export(export_path, [_cli_row()])

    outcome = ImportService().execute(
        ImportRequest(input_path=export_path, platform="wechat")
    )

    assert outcome.result.platform == "wechat"
    assert outcome.result.message_count == 1


def test_import_service_still_supports_detailed_json(tmp_path: Path) -> None:
    export_path = tmp_path / "detailed.json"
    export_path.write_text(
        json.dumps(
            {
                "exportInfo": {"format": "detailed-json"},
                "session": {"platform": "wechat"},
                "messages": [
                    {
                        "type": "\u6587\u672c\u6d88\u606f",
                        "createTime": 1753412807,
                        "senderDisplayName": "Fictional Alice",
                        "senderUsername": "wxid_fictional_sender",
                        "content": "Manual import still works",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    outcome = ImportService().execute(ImportRequest(input_path=export_path))

    assert outcome.result.platform == "wechat"
    assert outcome.result.format == "detailed-json"
    assert outcome.result.message_count == 1


def test_import_service_reads_cli_export_directory(tmp_path: Path) -> None:
    _write_cli_export(tmp_path / "chat-a.json", [_cli_row(content="A")])
    _write_cli_export(tmp_path / "chat-b.json", [_cli_row(content="B")])

    outcome = ImportService().execute(ImportRequest(input_path=tmp_path))

    assert outcome.result.platform == "wechat"
    assert outcome.result.message_count == 2


# ----------------------------------------------------------------- provider


def test_status_reports_unavailable_when_cli_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(
        lambda command, timeout: _FakeCompleted(),
        monkeypatch,
        installed=False,
    )

    status = provider.get_status()

    assert status.available is False
    assert status.connected is False


def test_status_parses_connected_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _envelope_ok(
        {
            "configured": True,
            "databaseFiles": 7,
            "connection": {"attempted": True, "ok": True, "sessionCount": 12},
        }
    )
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stdout=payload),
        monkeypatch,
    )

    status = provider.get_status()

    assert status.available is True
    assert status.configured is True
    assert status.connected is True
    assert status.database_files == 7
    assert status.session_count == 12


def test_status_uses_json_and_quiet_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def runner(command, timeout):
        seen.append(list(command))
        return _FakeCompleted(stdout=_envelope_ok({"configured": True}))

    _provider(runner, monkeypatch).get_status()

    assert seen[0][1:4] == ["--format", "json", "--quiet"]
    assert seen[0][-1] == "status"


def test_list_sessions_returns_descriptors(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _envelope_ok(
        {
            "sessions": [
                {
                    "sessionId": "fictional-chatroom",
                    "displayName": "Fictional Group",
                    "type": "group",
                    "messageCount": 42,
                },
                {"sessionId": "wxid_fictional_friend", "type": "private"},
            ]
        }
    )
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stdout=payload),
        monkeypatch,
    )

    sessions = provider.list_sessions()

    assert [session.session_id for session in sessions] == [
        "fictional-chatroom",
        "wxid_fictional_friend",
    ]
    assert sessions[0].display_name == "Fictional Group"
    assert sessions[1].display_name == "wxid_fictional_friend"


def test_export_session_passes_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []

    def runner(command, timeout):
        seen.append(list(command))
        return _FakeCompleted(stdout=_envelope_ok({"path": "out.json", "count": 3}))

    provider = _provider(runner, monkeypatch)
    output_path = tmp_path / "out.json"

    count = provider.export_session("fictional-chatroom", output_path)

    assert count == 3
    assert "export" in seen[0]
    assert "fictional-chatroom" in seen[0]
    assert "--output" in seen[0]
    assert str(output_path) in seen[0]


def test_load_session_messages_parses_exported_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def runner(command, timeout):
        output_path = Path(command[command.index("--output") + 1])
        _write_cli_export(output_path, [_cli_row(content="From temp file")])
        return _FakeCompleted(
            stdout=_envelope_ok({"path": str(output_path), "count": 1})
        )

    provider = _provider(runner, monkeypatch)

    messages = provider.load_session_messages("fictional-chatroom")

    assert len(messages) == 1
    assert messages[0].text == "From temp file"
    assert messages[0].platform == "wechat"


def test_temp_file_is_cleaned_up(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Path] = []

    def runner(command, timeout):
        output_path = Path(command[command.index("--output") + 1])
        captured.append(output_path)
        _write_cli_export(output_path, [_cli_row()])
        return _FakeCompleted(
            stdout=_envelope_ok({"path": str(output_path), "count": 1})
        )

    _provider(runner, monkeypatch).load_session_messages("fictional-chatroom")

    assert captured and not captured[0].exists()


# ------------------------------------------------------------ error mapping


def test_missing_cli_raises_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(
        lambda command, timeout: _FakeCompleted(),
        monkeypatch,
        installed=False,
    )

    with pytest.raises(CliNotInstalled) as error:
        provider.list_sessions()

    assert "ciphertalk-cli" in error.value.public_message


def test_wechat_not_running_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _envelope_error(
        "INTERNAL_ERROR",
        "\u5fae\u4fe1 (Weixin.exe) \u672a\u8fd0\u884c\u3002",
    )
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stderr=payload),
        monkeypatch,
    )

    with pytest.raises(WeChatNotRunning):
        provider.acquire_key()


def test_key_failure_is_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _envelope_error("INTERNAL_ERROR", "Hook failed after timeout")
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stderr=payload),
        monkeypatch,
    )

    with pytest.raises(KeyUnavailable):
        provider.acquire_key()


def test_config_missing_is_mapped_to_database_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _envelope_error("CONFIG_MISSING", "missing db-path")
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stderr=payload),
        monkeypatch,
    )

    with pytest.raises(DatabaseNotFound):
        provider.list_sessions()


def test_invalid_argument_is_mapped_to_session_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _envelope_error("INVALID_ARGUMENT", "unknown session")
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stderr=payload),
        monkeypatch,
    )

    with pytest.raises(SessionNotFound):
        provider.export_session("missing-session", tmp_path / "out.json")


def test_unparsable_output_raises_export_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stderr="segmentation fault"),
        monkeypatch,
    )

    with pytest.raises(ExportFailed):
        provider.list_sessions()


def test_timeout_raises_export_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def runner(command, timeout):
        raise subprocess.TimeoutExpired(cmd="miyu", timeout=timeout)

    provider = _provider(runner, monkeypatch)

    with pytest.raises(ExportFailed):
        provider.list_sessions()


def test_envelope_with_banner_prefix_is_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    noisy = "loading native modules...\n" + _envelope_ok({"configured": True})
    provider = _provider(
        lambda command, timeout: _FakeCompleted(stdout=noisy),
        monkeypatch,
    )

    status = provider.get_status()

    assert status.configured is True
