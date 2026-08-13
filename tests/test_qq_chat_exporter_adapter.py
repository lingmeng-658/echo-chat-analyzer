"""Behavior tests for the QQChatExporter JSON adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.qq_chat_exporter_adapter import (
    WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED,
    is_qce_export,
    load_qce_json,
    parse_qce_messages,
    parse_qce_rich_messages,
)
from qq_chat_analyzer.rich_message import MentionRelation, ReplyRelation, TextContent


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _qce_message(
    message_type: str = "text",
    sender: dict | None = None,
    text: str = "Fictional text",
    timestamp: object = 1750000000000,
    message_id: str = "fake-1",
    recalled: bool = False,
    system: bool = False,
) -> dict:
    return {
        "id": message_id,
        "seq": "1",
        "timestamp": timestamp,
        "time": "2025-06-15 12:00:00",
        "sender": (
            sender
            if sender is not None
            else {
                "uid": "user-1001",
                "uin": "1001",
                "name": "Fictional Alice",
                "nickname": "Fictional Alice",
            }
        ),
        "type": message_type,
        "content": {"text": text, "elements": [], "resources": [], "mentions": []},
        "recalled": recalled,
        "system": system,
    }


def test_is_qce_export_recognizes_qce_json(tmp_path: Path) -> None:
    path = tmp_path / "qce.json"
    _write_json(
        path,
        {
            "metadata": {"name": "QQChatExporter", "version": "0.0.0"},
            "chatInfo": {"name": "Fictional Group", "type": "group"},
            "messages": [],
        },
    )

    assert is_qce_export(path) is True


def test_is_qce_export_rejects_legacy_qq_json(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    _write_json(path, {"messages": []})

    assert is_qce_export(path) is False


def test_is_qce_export_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not valid json", encoding="utf-8")

    assert is_qce_export(path) is False


def test_load_qce_json_returns_payload(tmp_path: Path) -> None:
    path = tmp_path / "qce.json"
    payload = {"chatInfo": {}, "messages": []}
    _write_json(path, payload)

    assert load_qce_json(path) == payload


def test_load_qce_json_returns_none_for_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("not json", encoding="utf-8")

    assert load_qce_json(path) is None


def test_parse_qce_messages_maps_text_and_reply() -> None:
    raw_messages = [
        _qce_message(message_id="fake-text", text="Hello"),
        _qce_message(message_type="reply", message_id="fake-reply", text="Reply"),
    ]

    messages, warnings = parse_qce_messages(raw_messages)

    assert warnings == ()
    assert len(messages) == 2
    assert all(isinstance(message, ChatMessage) for message in messages)
    assert messages[0].message_type == "text"
    assert messages[0].text == "Hello"
    assert messages[0].message_id == "fake-text"
    assert messages[0].sender == "Fictional Alice"
    assert messages[0].sender_id == "user-1001"
    assert messages[0].platform == "qq"
    assert messages[0].source_type == "qce-json"
    assert messages[1].message_type == "reply"


def test_parse_qce_rich_messages_maps_p0_message_relations_and_recall() -> None:
    raw_message = _qce_message(
        message_type="reply",
        message_id="fictional-rich-reply",
        text="Replying to Bob",
        recalled=True,
    )
    raw_message["content"]["elements"] = [
        {
            "type": "reply",
            "replyElement": {
                "replayMsgId": "fictional-target-message",
            },
        },
        {
            "type": "text",
            "textElement": {
                "content": "@Fictional Bob",
                "atType": 2,
                "atUid": "2002",
                "atNtUid": "fictional-user-2002",
            },
        },
    ]

    messages, warnings = parse_qce_rich_messages(
        [raw_message],
        conversation_id="fictional-group-1",
    )

    assert warnings == ()
    assert len(messages) == 1
    message = messages[0]
    assert message.message_id == "fictional-rich-reply"
    assert message.source == "qq"
    assert message.source_type == "qce-json"
    assert message.conversation_id == "fictional-group-1"
    assert message.sender.identity_id == "user-1001"
    assert message.sender.display_name == "Fictional Alice"
    assert message.contents == (TextContent(text="Replying to Bob"),)
    assert message.relations == (
        ReplyRelation(target_message_id="fictional-target-message"),
        MentionRelation(
            target_identity_id="fictional-user-2002",
            display_text="@Fictional Bob",
        ),
    )
    assert message.recall_state is not None
    assert message.recall_state.is_recalled is True
    assert message.recall_event is None


def test_parse_qce_rich_messages_preserves_qq_identity_fields() -> None:
    sender = {
        "uid": "user-1001",
        "uin": "1001",
        "name": "Nick Name",
        "nickname": "Nickname",
        "remark": "老王",
        "groupCard": "达拉崩吧",
    }

    messages, warnings = parse_qce_rich_messages(
        [_qce_message(sender=sender)]
    )

    assert warnings == ()
    identity = messages[0].sender
    assert identity.identity_id == "user-1001"
    assert identity.remark == "老王"
    assert identity.nickname == "Nickname"
    assert identity.contextual_name == "达拉崩吧"


def test_parse_qce_rich_messages_uses_name_as_nickname_fallback() -> None:
    sender = {"uid": "user-1001", "name": "Nick Name"}

    messages, warnings = parse_qce_rich_messages(
        [_qce_message(sender=sender)]
    )

    assert warnings == ()
    identity = messages[0].sender
    assert identity.nickname == "Nick Name"
    assert identity.contextual_name is None
    assert identity.remark is None


def test_parse_qce_messages_projects_identity_fields_into_chat_message() -> None:
    sender = {
        "uid": "user-1001",
        "uin": "1001",
        "nickname": "Nickname",
        "remark": "老王",
        "groupCard": "达拉崩吧",
    }

    messages, warnings = parse_qce_messages([_qce_message(sender=sender)])

    assert warnings == ()
    message = messages[0]
    assert message.sender_id == "user-1001"
    assert message.sender_remark == "老王"
    assert message.sender_nickname == "Nickname"
    assert message.sender_contextual_name == "达拉崩吧"


def test_parse_qce_messages_preserves_metadata_flags() -> None:
    raw_messages = [
        _qce_message(
            message_id="fake-system",
            recalled=True,
            system=True,
        )
    ]

    messages, warnings = parse_qce_messages(raw_messages)

    assert warnings == ()
    assert messages[0].recalled is True
    assert messages[0].is_system is True


@pytest.mark.parametrize(
    ("sender", "expected"),
    [
        (
            {
                "uid": "uid",
                "uin": "uin",
                "name": "name",
                "nickname": "nickname",
            },
            "nickname",
        ),
        (
            {"uid": "uid", "uin": "uin", "name": "name", "nickname": ""},
            "name",
        ),
        (
            {"uid": "uid", "uin": "uin", "groupCard": "card"},
            "card",
        ),
        (
            {"uid": "uid", "uin": "uin", "remark": "remark"},
            "remark",
        ),
        (
            {"uid": "uid", "uin": "uin"},
            "uin",
        ),
        (
            {"uid": "uid"},
            "uid",
        ),
        ({}, "未知用户"),
    ],
)
def test_parse_qce_messages_uses_sender_fallback_order(
    sender: dict,
    expected: str,
) -> None:
    raw_messages = [_qce_message(sender=sender)]

    messages, warnings = parse_qce_messages(raw_messages)

    assert warnings == ()
    assert messages[0].sender == expected


def test_parse_qce_messages_skips_non_text_and_reports_warning() -> None:
    raw_messages = [
        _qce_message(message_id="fake-text"),
        _qce_message(message_type="file", message_id="fake-file"),
        _qce_message(message_type="system", message_id="fake-system"),
    ]

    messages, warnings = parse_qce_messages(raw_messages)

    assert len(messages) == 1
    assert warnings == (WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED,)


def test_parse_qce_messages_ignores_malformed_rows_without_warning() -> None:
    raw_messages = [
        _qce_message(message_id="fake-text"),
        {"type": "text"},
        _qce_message(message_type="reply", message_id="fake-reply"),
    ]

    messages, warnings = parse_qce_messages(raw_messages)

    assert warnings == ()
    assert [message.message_id for message in messages] == [
        "fake-text",
        "fake-reply",
    ]
