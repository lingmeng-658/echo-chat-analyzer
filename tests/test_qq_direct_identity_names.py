"""Fictional regression cases for Direct DB identity display semantics."""

from __future__ import annotations

import base64
import json
import sqlite3
from types import SimpleNamespace

from qq_chat_analyzer.providers.qq_database_provider import QQDatabaseProvider
from qq_chat_analyzer.qq_db_adapter import parse_qq_db_rich_messages
from qq_chat_analyzer.application.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
    _group_member_data,
    _identity_coverage_counts,
    _attach_sender_names,
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
            9001: {"uin": 123456789, "card": "Fictional Card", "nick": "Fictional Nick"},
            "opaque-member-key": {"uin": "234567890", "card": "", "nick": "Fictional Nick Only"},
            "no-name-key": {"uin": "345678901", "card": "", "nick": ""},
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
        def list_groups(self, *, page=1, limit=200):
            return [SimpleNamespace(group_code="group-1", group_name="Fictional Group")]

        def list_friends(self, *, page=1, limit=200):
            return [SimpleNamespace(peer_uin="peer-1", display_name="Fictional Friend")]

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
