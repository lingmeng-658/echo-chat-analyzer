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
from qq_chat_analyzer.legacy_projection import project_legacy_message
from qq_chat_analyzer.rich_message import TextContent
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
from qq_chat_analyzer.providers import wechat_database_provider


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


def test_wcdb_subprocess_hides_console_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return _FakeCompleted()

    monkeypatch.setattr(wechat_database_provider.os, "name", "nt")
    monkeypatch.setattr(
        wechat_database_provider.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    monkeypatch.setattr(wechat_database_provider.subprocess, "run", run)

    command = ["wcdb_cli.exe", "--wcdb", "WCDB.dll"]
    wechat_database_provider._run_subprocess(command, 30, {"WX_DB_KEY": "x"})

    assert calls[0][0] == command
    assert calls[0][1]["creationflags"] == 0x08000000
    assert calls[0][1]["timeout"] == 30
    assert calls[0][1]["env"] == {"WX_DB_KEY": "x"}


def test_wcdb_subprocess_omits_windows_creation_flags_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return _FakeCompleted()

    monkeypatch.setattr(wechat_database_provider.os, "name", "posix")
    monkeypatch.setattr(wechat_database_provider.subprocess, "run", run)

    command = ["wcdb_cli.exe", "--wcdb", "WCDB.dll"]
    wechat_database_provider._run_subprocess(command, 30, {"WX_DB_KEY": "x"})

    assert calls[0][0] == command
    assert "creationflags" not in calls[0][1]


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


def test_text_row_becomes_rich_message_then_projects_to_legacy(
    tmp_path: Path,
) -> None:
    export = tmp_path / "session.json"
    row = _db_row()
    row["sender_name"] = "Fictional Alice"
    _write_db_export(export, [row])

    rich_messages = wechat_db_adapter.parse_rich_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert len(rich_messages) == 1
    rich_message = rich_messages[0]
    assert rich_message.source == "wechat"
    assert rich_message.message_id == "900001"
    assert rich_message.conversation_id == FICTIONAL_SESSION
    assert rich_message.sender.identity_id == "wxid_fictional_sender"
    assert rich_message.sender.display_name == "Fictional Alice"
    assert rich_message.timestamp == 1753412807
    assert rich_message.message_type == "text"
    assert rich_message.contents == (
        TextContent(text="\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u4e0d\u9519"),
    )
    assert rich_message.relations == ()
    assert rich_message.recall_state is None

    legacy_message = project_legacy_message(rich_message)
    assert legacy_message.sender == "Fictional Alice"
    assert legacy_message.text == "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u4e0d\u9519"
    assert legacy_message.timestamp == 1753412807


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


def test_db_row_uses_resolved_sender_name(tmp_path: Path) -> None:
    export = tmp_path / "session.json"
    row = _db_row()
    row["sender_name"] = "\u5907\u6ce8\u540d"
    _write_db_export(export, [row])

    messages = wechat_db_adapter.parse_messages(
        wechat_db_adapter.load_messages(export)
    )

    assert messages[0].sender == "\u5907\u6ce8\u540d"
    assert messages[0].sender_id == "wxid_fictional_sender"


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
        {"username": "   ", "last_timestamp": 1},
        "junk",
    ]

    def runner(command, timeout, environment):
        sql = " ".join(command)
        if "SessionTable" in sql:
            return _FakeCompleted(stdout=_helper_result(rows))
        if "sqlite_master" in sql:
            return _FakeCompleted(
                stdout=_helper_result([], columns=["name"])
            )
        raise AssertionError(f"unexpected query: {sql}")

    sessions = _provider(tmp_path, runner).list_sessions()

    assert [session.session_id for session in sessions] == [
        FICTIONAL_SESSION,
        "wxid_friend",
    ]
    assert [session.session_type for session in sessions] == [
        "group",
        "private",
    ]


def test_list_sessions_marks_missing_msg_tables_unavailable(
    tmp_path: Path,
) -> None:
    available_session = "wxid_has_messages"
    missing_session = "wxid_no_messages"
    available_table = message_table_name(available_session)
    session_rows = [
        {"username": available_session, "last_timestamp": 1753412900},
        {"username": missing_session, "last_timestamp": 1753412800},
    ]

    def runner(command, timeout, environment):
        sql = " ".join(command)
        if "SessionTable" in sql:
            return _FakeCompleted(stdout=_helper_result(session_rows))
        if "sqlite_master" in sql:
            return _FakeCompleted(
                stdout=_helper_result(
                    [{"name": available_table}],
                    columns=["name"],
                )
            )
        raise AssertionError(f"unexpected query: {sql}")

    sessions = _provider(tmp_path, runner).list_sessions()

    assert len(sessions) == 2
    assert sessions[0].message_available is True
    assert sessions[0].unavailable_reason is None
    assert sessions[1].message_available is False
    assert sessions[1].unavailable_reason


def test_list_sessions_resolves_contact_display_names(tmp_path: Path) -> None:
    private_session = "wxid_friend"
    no_contact_session = "wxid_no_contact"
    group_session = "room@chatroom"
    session_rows = [
        {"username": private_session, "last_timestamp": 1753412900},
        {"username": no_contact_session, "last_timestamp": 1753412800},
        {"username": group_session, "last_timestamp": 1753412700},
    ]
    contact_rows = [
        {
            "username": private_session,
            "remark": "\u5907\u6ce8\u540d",
            "nick_name": "\u6635\u79f0",
        },
        {
            "username": group_session,
            "remark": "",
            "nick_name": "\u7fa4\u804a\u540d",
        },
    ]

    def runner(command, timeout, environment):
        sql = " ".join(command)
        if "SessionTable" in sql:
            return _FakeCompleted(stdout=_helper_result(session_rows))
        if "FROM contact" in sql:
            return _FakeCompleted(
                stdout=_helper_result(
                    contact_rows,
                    columns=["username", "remark", "nick_name"],
                )
            )
        if "sqlite_master" in sql:
            return _FakeCompleted(
                stdout=_helper_result([], columns=["name"])
            )
        raise AssertionError(f"unexpected query: {sql}")

    provider = _provider(tmp_path, runner)
    contact_dir = (
        tmp_path
        / "xwechat_files"
        / "wxid_owner"
        / "db_storage"
        / "contact"
    )
    contact_dir.mkdir(parents=True, exist_ok=True)
    (contact_dir / "contact.db").write_bytes(b"fake")

    sessions = provider.list_sessions()

    assert [session.display_name for session in sessions] == [
        "\u5907\u6ce8\u540d",
        no_contact_session,
        "\u7fa4\u804a\u540d",
    ]


def test_list_sessions_filters_official_and_system_sessions(
    tmp_path: Path,
) -> None:
    private_session = "wxid_friend"
    group_session = "room@chatroom"
    session_rows = [
        {"username": private_session, "last_timestamp": 1753412900},
        {"username": group_session, "last_timestamp": 1753412800},
        {"username": "gh_official", "last_timestamp": 1753412700},
        {"username": "notify", "last_timestamp": 1753412600},
        {"username": "unknown-system-account", "last_timestamp": 1753412500},
    ]

    def runner(command, timeout, environment):
        sql = " ".join(command)
        if "SessionTable" in sql:
            return _FakeCompleted(stdout=_helper_result(session_rows))
        if "sqlite_master" in sql:
            return _FakeCompleted(
                stdout=_helper_result([], columns=["name"])
            )
        raise AssertionError(f"unexpected query: {sql}")

    sessions = _provider(tmp_path, runner).list_sessions()

    assert [session.session_id for session in sessions] == [
        private_session,
        group_session,
    ]
    assert [session.session_type for session in sessions] == [
        "private",
        "group",
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


def test_export_session_json_resolves_sender_display_names(
    tmp_path: Path,
) -> None:
    table = message_table_name(FICTIONAL_SESSION)
    sender = "wxid_fictional_sender"
    contact_rows = [
        {
            "username": sender,
            "remark": "\u5907\u6ce8\u540d",
            "nick_name": "\u6635\u79f0",
        }
    ]

    def runner(command, timeout, environment):
        sql = command[command.index("--sql") + 1]
        if "FROM contact" in sql:
            return _FakeCompleted(
                stdout=_helper_result(
                    contact_rows,
                    columns=["username", "remark", "nick_name"],
                )
            )
        if "sqlite_master" in sql:
            return _FakeCompleted(stdout=_helper_result([{"name": table}]))
        return _FakeCompleted(stdout=_helper_result([_db_row(user_name=sender)]))

    provider = _provider(tmp_path, runner)
    contact_dir = (
        tmp_path
        / "xwechat_files"
        / "wxid_owner"
        / "db_storage"
        / "contact"
    )
    contact_dir.mkdir(parents=True, exist_ok=True)
    (contact_dir / "contact.db").write_bytes(b"fake")
    output = tmp_path / "out" / "session.json"

    provider.export_session_json(FICTIONAL_SESSION, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["messages"][0]["sender_name"] == "\u5907\u6ce8\u540d"


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
