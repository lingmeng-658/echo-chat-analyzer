"""Behavioral tests for the WeChat database source (WCDB provider chain).

All fixtures are fictional. No real WeChat data, key, or account appears here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import wechat_db_adapter
from qq_chat_analyzer.application import ImportRequest, ImportService
from qq_chat_analyzer.application.import_service import WECHAT_DB_FORMAT
from qq_chat_analyzer.providers.wechat_database_provider import (
    DatabaseNotFound,
    KeyUnavailable,
    QueryFailed,
    SessionNotFound,
    WcdbHelperNotFound,
    WcdbLibraryNotFound,
    WeChatDatabaseProvider,
    message_table_name,
)


TEXT_LOCAL_TYPE = 1
IMAGE_LOCAL_TYPE = 3
FICTIONAL_KEY = "a" * 64
FICTIONAL_SESSION = "wxid_fictional_room@chatroom"


def _db_row(
    message_content: str = "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u4e0d\u9519",
    local_type: object = TEXT_LOCAL_TYPE,
    create_time: object = 1753412807,
    user_name: object = "wxid_fictional_sender",
    server_id: object = 900001,
    local_id: object = 11,
) -> dict[str, object]:
    return {
        "local_id": local_id,
        "server_id": server_id,
        "local_type": local_type,
        "create_time": create_time,
        "message_content": message_content,
        "user_name": user_name,
    }


def _write_db_export(
    path: Path,
    rows: list[object],
    username: str = FICTIONAL_SESSION,
) -> None:
    document = {
        "source": "wechat-db",
        "conversation": {"username": username},
        "messages": rows,
    }
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def _helper_result(rows: list[object], columns: list[str] | None = None) -> str:
    return json.dumps(
        {
            "ok": True,
            "columns": columns or ["local_id"],
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
        }
    )


def _make_data_root(tmp_path: Path, table: str | None = None) -> Path:
    """Build a fictional WeChat data directory layout."""
    storage = tmp_path / "xwechat_files" / "wxid_owner" / "db_storage"
    message_dir = storage / "message"
    message_dir.mkdir(parents=True, exist_ok=True)
    (message_dir / "session.db").write_bytes(b"fake")
    (message_dir / "message_0.db").write_bytes(b"fake")
    return tmp_path / "xwechat_files"


def _provider(tmp_path: Path, runner) -> WeChatDatabaseProvider:
    helper = tmp_path / "wcdb_cli.exe"
    helper.write_bytes(b"fake")
    library = tmp_path / "WCDB.dll"
    library.write_bytes(b"fake")
    return WeChatDatabaseProvider(
        data_root=_make_data_root(tmp_path),
        db_key=FICTIONAL_KEY,
        wcdb_cli_path=helper,
        wcdb_dll_path=library,
        runner=runner,
    )


# ------------------------------------------------------------------ adapter


def test_text_row_becomes_chat_message_with_mapped_fields(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row()])

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert len(messages) == 1
    message = messages[0]
    assert message.timestamp == 1753412807
    assert message.sender == "wxid_fictional_sender"
    assert message.sender_id == "wxid_fictional_sender"
    assert message.text == "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u4e0d\u9519"
    assert message.platform == "wechat"
    assert message.conversation_id == FICTIONAL_SESSION
    assert message.message_type == "text"
    assert message.source_type == TEXT_LOCAL_TYPE
    assert message.message_id == "900001"
    assert message.is_system is False
    assert message.recalled is False


def test_non_text_local_types_are_skipped(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(
        export,
        [_db_row(local_type=IMAGE_LOCAL_TYPE), _db_row(local_type=49)],
    )

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert messages == []


@pytest.mark.parametrize(
    "row",
    [
        _db_row(create_time=None),
        _db_row(create_time=True),
        _db_row(message_content=None),
        _db_row(user_name=None),
        _db_row(user_name="   "),
        _db_row(local_type="text"),
        _db_row(local_type=True),
        "not-a-mapping",
        None,
    ],
)
def test_malformed_rows_are_isolated(row: object) -> None:
    assert wechat_db_adapter.parse_message(row) is None


def test_malformed_rows_do_not_drop_valid_neighbours(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row(create_time=None), _db_row(), "junk"])

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert len(messages) == 1


def test_row_username_takes_precedence_over_conversation(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    row = _db_row()
    row["username"] = "wxid_explicit_conversation"
    _write_db_export(export, [row])

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert messages[0].conversation_id == "wxid_explicit_conversation"


def test_falls_back_to_local_id_when_server_id_missing(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row(server_id=None, local_id=42)])

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert messages[0].message_id == "42"


def test_detects_db_export_and_rejects_other_shapes(tmp_path: Path) -> None:
    db_export = tmp_path / "db.json"
    _write_db_export(db_export, [_db_row()])
    assert wechat_db_adapter.is_wechat_db_export(db_export) is True

    other = tmp_path / "other.json"
    other.write_text(json.dumps({"messages": []}), encoding="utf-8")
    assert wechat_db_adapter.is_wechat_db_export(other) is False

    cli_array = tmp_path / "cli.json"
    cli_array.write_text(json.dumps([{"content": "hi"}]), encoding="utf-8")
    assert wechat_db_adapter.is_wechat_db_export(cli_array) is False


def test_unreadable_and_invalid_inputs_return_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert wechat_db_adapter.load_messages(missing) == []
    assert wechat_db_adapter.is_wechat_db_export(missing) is False

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert wechat_db_adapter.load_messages(broken) == []

    assert wechat_db_adapter.parse_messages(None) == []


# ----------------------------------------------------------------- provider


def test_message_table_name_uses_md5_of_username() -> None:
    assert message_table_name("wxid_test") == (
        "Msg_57afd0237934cda01feecbee3168a6b2"
    )


def test_list_sessions_returns_privacy_safe_descriptors(tmp_path: Path) -> None:
    rows = [
        {"username": FICTIONAL_SESSION, "last_timestamp": 1753412900},
        {"username": "wxid_friend", "last_timestamp": 1753412800},
        {"username": "gh_official", "last_timestamp": 1753412700},
        {"username": "   ", "last_timestamp": 1},
        "junk",
    ]

    def runner(command, timeout, environment):
        assert "SessionTable" in " ".join(command)
        return _FakeCompleted(stdout=_helper_result(rows))

    sessions = _provider(tmp_path, runner).list_sessions()

    assert [session.session_id for session in sessions] == [
        FICTIONAL_SESSION,
        "wxid_friend",
        "gh_official",
    ]
    assert [session.session_type for session in sessions] == [
        "group",
        "private",
        "official",
    ]


def test_export_session_json_writes_provider_document(tmp_path: Path) -> None:
    table = message_table_name(FICTIONAL_SESSION)
    seen_sql: list[str] = []

    def runner(command, timeout, environment):
        sql = command[command.index("--sql") + 1]
        seen_sql.append(sql)
        assert environment["WX_DB_KEY"] == FICTIONAL_KEY
        if "sqlite_master" in sql:
            return _FakeCompleted(stdout=_helper_result([{"name": table}]))
        return _FakeCompleted(stdout=_helper_result([_db_row()]))

    provider = _provider(tmp_path, runner)
    output = tmp_path / "out" / "session.json"

    result = provider.export_session_json(FICTIONAL_SESSION, output)

    assert result == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "wechat-db"
    assert payload["conversation"]["username"] == FICTIONAL_SESSION
    assert len(payload["messages"]) == 1
    message_sql = seen_sql[-1]
    assert table in message_sql
    assert "local_type = 1" in message_sql
    assert "Name2Id" in message_sql


def test_time_window_is_pushed_into_the_query(tmp_path: Path) -> None:
    table = message_table_name(FICTIONAL_SESSION)
    seen_sql: list[str] = []

    def runner(command, timeout, environment):
        sql = command[command.index("--sql") + 1]
        seen_sql.append(sql)
        if "sqlite_master" in sql:
            return _FakeCompleted(stdout=_helper_result([{"name": table}]))
        return _FakeCompleted(stdout=_helper_result([]))

    provider = _provider(tmp_path, runner)
    provider.read_session_rows(
        FICTIONAL_SESSION,
        start_time=1753400000,
        end_time=1753500000,
    )

    message_sql = seen_sql[-1]
    assert "create_time >= 1753400000" in message_sql
    assert "create_time <= 1753500000" in message_sql


def test_key_is_never_placed_on_the_command_line(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def runner(command, timeout, environment):
        captured.append(list(command))
        return _FakeCompleted(stdout=_helper_result([]))

    _provider(tmp_path, runner).list_sessions()

    assert FICTIONAL_KEY not in " ".join(captured[0])


def test_missing_key_raises_key_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WX_DB_KEY", raising=False)
    helper = tmp_path / "wcdb_cli.exe"
    helper.write_bytes(b"fake")
    library = tmp_path / "WCDB.dll"
    library.write_bytes(b"fake")
    provider = WeChatDatabaseProvider(
        data_root=_make_data_root(tmp_path),
        db_key=None,
        wcdb_cli_path=helper,
        wcdb_dll_path=library,
        runner=lambda *args: _FakeCompleted(stdout=_helper_result([])),
    )

    with pytest.raises(KeyUnavailable):
        provider.list_sessions()


def test_missing_helper_and_library_are_reported(tmp_path: Path) -> None:
    data_root = _make_data_root(tmp_path)
    runner = lambda *args: _FakeCompleted(stdout=_helper_result([]))

    with pytest.raises(WcdbHelperNotFound):
        WeChatDatabaseProvider(
            data_root=data_root,
            db_key=FICTIONAL_KEY,
            wcdb_cli_path=tmp_path / "absent.exe",
            wcdb_dll_path=tmp_path / "WCDB.dll",
            runner=runner,
        ).list_sessions()

    helper = tmp_path / "wcdb_cli.exe"
    helper.write_bytes(b"fake")
    with pytest.raises(WcdbLibraryNotFound):
        WeChatDatabaseProvider(
            data_root=data_root,
            db_key=FICTIONAL_KEY,
            wcdb_cli_path=helper,
            wcdb_dll_path=tmp_path / "absent.dll",
            runner=runner,
        ).list_sessions()


def test_missing_data_root_raises_database_not_found(tmp_path: Path) -> None:
    helper = tmp_path / "wcdb_cli.exe"
    helper.write_bytes(b"fake")
    library = tmp_path / "WCDB.dll"
    library.write_bytes(b"fake")
    provider = WeChatDatabaseProvider(
        data_root=tmp_path / "absent",
        db_key=FICTIONAL_KEY,
        wcdb_cli_path=helper,
        wcdb_dll_path=library,
        runner=lambda *args: _FakeCompleted(stdout=_helper_result([])),
    )

    with pytest.raises(DatabaseNotFound):
        provider.list_sessions()


def test_unknown_session_raises_session_not_found(tmp_path: Path) -> None:
    def runner(command, timeout, environment):
        return _FakeCompleted(stdout=_helper_result([]))

    with pytest.raises(SessionNotFound):
        _provider(tmp_path, runner).read_session_rows(FICTIONAL_SESSION)


def test_blank_session_id_raises_session_not_found(tmp_path: Path) -> None:
    provider = _provider(
        tmp_path,
        lambda *args: _FakeCompleted(stdout=_helper_result([])),
    )

    with pytest.raises(SessionNotFound):
        provider.read_session_rows("   ")


def test_helper_failure_and_timeout_become_query_failed(tmp_path: Path) -> None:
    def failing(command, timeout, environment):
        return _FakeCompleted(
            stdout=json.dumps({"ok": False, "stage": "open", "error": "bad key"})
        )

    with pytest.raises(QueryFailed):
        _provider(tmp_path, failing).list_sessions()

    def timing_out(command, timeout, environment):
        raise subprocess.TimeoutExpired(cmd="wcdb_cli", timeout=1)

    with pytest.raises(QueryFailed):
        _provider(tmp_path, timing_out).list_sessions()

    def garbage(command, timeout, environment):
        return _FakeCompleted(stdout="not json at all")

    with pytest.raises(QueryFailed):
        _provider(tmp_path, garbage).list_sessions()


def test_helper_absent_at_runtime_becomes_helper_not_found(tmp_path: Path) -> None:
    def missing(command, timeout, environment):
        raise FileNotFoundError("gone")

    with pytest.raises(WcdbHelperNotFound):
        _provider(tmp_path, missing).list_sessions()


def test_provider_errors_carry_user_facing_messages(tmp_path: Path) -> None:
    for error in (
        DatabaseNotFound(),
        KeyUnavailable(),
        QueryFailed(),
        SessionNotFound(),
        WcdbHelperNotFound(),
        WcdbLibraryNotFound(),
    ):
        assert error.public_message
        assert error.code


# ----------------------------------------------------------- import service


def test_import_service_routes_db_export_to_the_db_adapter(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row(), _db_row(local_type=IMAGE_LOCAL_TYPE)])

    outcome = ImportService().execute(ImportRequest(input_path=export))

    assert outcome.result.platform == "wechat"
    assert outcome.result.format == WECHAT_DB_FORMAT
    assert outcome.result.message_count == 1
    assert outcome.result.valid_text_count == 1
    assert outcome.messages[0].platform == "wechat"
    assert outcome.messages[0].conversation_id == FICTIONAL_SESSION


def test_import_service_honours_explicit_wechat_platform_hint(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row()])

    outcome = ImportService().execute(
        ImportRequest(input_path=export, platform="wechat")
    )

    assert outcome.result.format == WECHAT_DB_FORMAT
    assert outcome.result.message_count == 1


def test_import_service_reports_empty_db_export(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [])

    outcome = ImportService().execute(ImportRequest(input_path=export))

    assert outcome.result.message_count == 0
    assert "no_messages_loaded" in outcome.result.warnings


def test_db_export_does_not_leak_into_qq_detection(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    _write_db_export(export, [_db_row()])

    outcome = ImportService().execute(
        ImportRequest(input_path=export, platform="qq")
    )

    assert outcome.result.message_count == 0
