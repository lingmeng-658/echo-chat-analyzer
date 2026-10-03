"""Fictional regression cases for Direct DB identity display semantics."""

from __future__ import annotations

import base64
import json
import sqlite3
from types import SimpleNamespace

import pytest

from qq_chat_analyzer.providers.qq_database_provider import QQDatabaseProvider
from qq_chat_analyzer.qq_db_adapter import parse_qq_db_rich_messages
from qq_chat_analyzer.application.qq.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
    _group_member_data,
    _identity_coverage_counts,
    _attach_sender_names,
    _log_group_member_shape,
)
from qq_chat_analyzer.providers.qq_database_provider import QQSession
from test_qq_db_import_integration import _synthetic_text_message_blob


def test_zero_partition_is_not_a_user_session(tmp_path) -> None:
    database = tmp_path / "fictional.db"
    with sqlite3.connect(database) as connection:
        for table in ("group_msg_table", "c2c_msg_table"):
            connection.execute(
                f'CREATE TABLE {table} ("40027" TEXT, "40030" TEXT, '
                '"40050" INTEGER)'
            )
        connection.executemany(
            'INSERT INTO c2c_msg_table VALUES (?, ?, ?)',
            [("0", "0", 1)] * 82 + [("valid-key", "valid-peer", 2)],
        )
    sessions = QQDatabaseProvider(database).list_sessions()
    assert [(session.internal_key, session.message_count) for session in sessions] == [
        ("valid-key", 1)
    ]


def test_direct_db_sender_uses_source_neutral_identity_fields() -> None:
    payload = {
        "format": "qq-db-json",
        "format_version": 0,
        "source": "qq",
        "source_type": "qq-db-json",
        "query": {"session_type": "group", "session_object": "fictional-group"},
        "records": [
            {
                "record_id": str(index + 1),
                "fields": {"40033": f"fictional-member-{index}", "40050": index + 1},
                "sender": sender,
                "blob_encoding": "base64",
                "message_blob": base64.b64encode(
                    _synthetic_text_message_blob("Fictional text")
                ).decode("ascii"),
            }
            for index, sender in enumerate((
                {"remark": "Fictional Remark", "groupCard": "Fictional Card", "nickname": "Fictional Nick"},
                {"remark": "Fictional Remark", "groupCard": "", "nickname": "Fictional Nick Only"},
                {"remark": "Fictional Remark", "groupCard": "", "nickname": ""},
            ))
        ],
    }
    messages, _ = parse_qq_db_rich_messages(payload)
    assert [message.sender.display_name for message in messages] == [
        "Fictional Card", "Fictional Nick Only", "\u672a\u77e5\u6210\u5458"
    ]
    assert messages[0].sender.contextual_name == "Fictional Card"
    assert messages[0].sender.nickname == "Fictional Nick"
    assert messages[0].sender.remark is None


def test_group_member_names_use_info_uin_not_serialized_map_key(tmp_path) -> None:
    response = json.loads(json.dumps({
        "result": {"infos": {
            9001: {"uin": 123456789, "cardName": "Fictional Card", "nick": "Fictional Nick"},
            "opaque-member-key": {"uin": "234567890", "cardName": "", "nick": "Fictional Nick Only"},
            "no-name-key": {"uin": "345678901", "cardName": "", "nick": ""},
        }}
    }))

    result = _group_member_data(response)

    assert result["names"] == {
        "123456789": "Fictional Card",
        "234567890": "Fictional Nick Only",
    }
    assert result["uins"] == {"123456789", "234567890", "345678901"}
    assert _identity_coverage_counts(
        {"123456789", "234567890", "345678901", "456789012"}, result
    ) == {
        "distinct_sender_count": 4,
        "rpc_member_count": 3,
        "matched_sender_count": 3,
        "unmatched_sender_count": 1,
        "matched_with_card_count": 1,
        "matched_without_card_with_nick_count": 1,
        "matched_without_card_or_nick_count": 1,
        "rpc_member_with_card_count": 1,
        "rpc_member_with_nick_count": 2,
    }

    payload_path = tmp_path / "fictional-group-payload.json"
    payload_path.write_text(json.dumps({
        "records": [{"fields": {"40033": "123456789"}}]
    }), encoding="utf-8")
    _attach_sender_names(payload_path, result["names"], "fictional-self")
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["records"][0]["sender"] == {"displayName": "Fictional Card"}


@pytest.mark.parametrize("card_name,nick,expected", [
    (" Fictional Card ", "Fictional Nick", "Fictional Card"),
    ("", " Fictional Nick ", "Fictional Nick"),
    (None, "Fictional Nick", "Fictional Nick"),
    (42, "Fictional Nick", "Fictional Nick"),
    (" ", "", None),
    (None, None, None),
])
def test_group_member_contract_ignores_friend_remark_and_legacy_card(
    card_name, nick, expected,
) -> None:
    result = _group_member_data({"result": {"infos": {"opaque-key": {
        "uin": "123456789", "cardName": card_name, "nick": nick,
        "card": "Incorrect Legacy Card", "remark": "Fictional Friend Remark",
        "displayName": "Untrusted Display Name",
    }}}})
    assert result["names"] == ({"123456789": expected} if expected else {})
    assert result["uins"] == {"123456789"}


def test_group_member_shape_logs_only_anonymous_field_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger_name = "qq_chat_analyzer.desktop.qq_direct_database"
    caplog.set_level("INFO", logger=logger_name)
    response = {"result": {"infos": {
        "fictional-uin-one": {
            "uin": "fictional-uin-one", "cardName": "Fictional Group Card",
            "card": "", "nick": "Fictional Nick", "remark": "Fictional Remark",
        },
        "fictional-uin-two": {
            "uin": "fictional-uin-two", "cardName": " ", "card": "Fictional Legacy Card",
            "nickname": None, "displayName": 42,
        },
        "fictional-uin-three": {
            "uin": "fictional-uin-three", "cardName": None,
            "card": None, "nick": "", "nickname": "Fictional Alias",
            "displayName": "Fictional Display",
        },
        "fictional-uin-four": {"uin": "fictional-uin-four"},
    }}}

    _log_group_member_shape(response)

    assert "[qq-direct-member-shape]" not in caplog.text
    caplog.set_level("DEBUG", logger=logger_name)
    _log_group_member_shape(response)

    shape_record = next(
        record for record in caplog.records
        if "[qq-direct-member-shape]" in record.getMessage()
    )
    assert shape_record.levelname == "DEBUG"
    line = shape_record.getMessage()
    assert "member_count=4" in line
    assert "cardName_present_count=3 cardName_nonempty_string_count=1" in line
    assert "card_present_count=3 card_nonempty_string_count=1" in line
    assert "nick_present_count=2 nick_nonempty_string_count=1" in line
    assert "nickname_present_count=2 nickname_nonempty_string_count=1" in line
    assert "remark_present_count=1 remark_nonempty_string_count=1" in line
    assert "displayName_present_count=2 displayName_nonempty_string_count=1" in line
    assert "cardName_string_count=2 cardName_null_count=1 cardName_other_type_count=0" in line
    assert "nickname_string_count=1 nickname_null_count=1 nickname_other_type_count=0" in line
    assert "displayName_string_count=1 displayName_null_count=0 displayName_other_type_count=1" in line
    for private_value in (
        "fictional-uin-one", "fictional-uin-two", "fictional-uin-three",
        "fictional-uin-four", "Fictional Group Card", "Fictional Legacy Card",
        "Fictional Nick", "Fictional Remark", "Fictional Alias", "Fictional Display",
    ):
        assert private_value not in line


def test_private_peer_is_the_only_non_self_sender(tmp_path) -> None:
    database = tmp_path / "fictional.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            'CREATE TABLE group_msg_table ("40027" TEXT, "40030" TEXT, '
            '"40033" TEXT, "40050" INTEGER)'
        )
        connection.execute(
            'CREATE TABLE c2c_msg_table ("40027" TEXT, "40030" TEXT, '
            '"40033" TEXT, "40050" INTEGER)'
        )
        connection.executemany(
            'INSERT INTO c2c_msg_table VALUES (?, ?, ?, ?)',
            [
                ("partition", "self", "self", 1),
                ("partition", "peer", "peer", 2),
            ],
        )
    session = QQDatabaseProvider(database).list_sessions(self_uin="self")[0]
    assert session.peer_uin == "peer"


def test_session_names_join_existing_qq_group_and_friend_metadata() -> None:
    class FakeProvider:
        def list_groups(self):
            return [SimpleNamespace(group_code="group-1", group_name="Fictional Group")]

        def list_friends(self):
            return [SimpleNamespace(uin="peer-1", display_name="Fictional Friend")]

    factory = SimpleNamespace(create=lambda: FakeProvider())
    service = QQDirectDatabaseImportService(provider_factory=factory)
    sessions = service._named_sessions([
        QQSession("group-key", "group-1", "group-1", "group"),
        QQSession("private-key", "self", "self", "private", peer_uin="peer-1"),
        QQSession("missing-key", "123456", "123456", "group"),
    ])
    assert [session.display_name for session in sessions] == [
        "Fictional Group", "Fictional Friend", "未知群聊"
    ]


def test_friend_name_and_self_reach_the_shared_message_model(tmp_path) -> None:
    payload = {
        "format": "qq-db-json", "format_version": 0,
        "source": "qq", "source_type": "qq-db-json",
        "self": {"namespace": "qq_uin", "value": "self"},
        "query": {"session_type": "private", "session_object": "peer"},
        "records": [],
    }
    blob = base64.b64encode(_synthetic_text_message_blob("Fictional text")).decode("ascii")
    for index, sender in enumerate(("self", "peer", "stranger")):
        payload["records"].append({
            "record_id": str(index + 1),
            "fields": {"40033": sender, "40050": index + 1},
            "blob_encoding": "base64", "message_blob": blob,
        })
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    _attach_sender_names(path, {"peer": "Fictional Friend"}, "self")
    messages, _ = parse_qq_db_rich_messages(json.loads(path.read_text(encoding="utf-8")))
    assert [(message.sender.display_name, message.is_self) for message in messages] == [
        ("我", True), ("Fictional Friend", False), ("未知成员", False)
    ]
