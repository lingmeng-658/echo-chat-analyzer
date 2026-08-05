"""Behavioral tests for the WeChat detailed JSON parser."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.wechat_parser import (
    is_wechat_export,
    load_messages,
    parse_messages,
)


TEXT_TYPE = "\u6587\u672c\u6d88\u606f"
REPLY_TYPE = "\u5f15\u7528\u6d88\u606f"
IMAGE_TYPE = "\u56fe\u7247\u6d88\u606f"
SYSTEM_TYPE = "\u7cfb\u7edf\u6d88\u606f"


def _write_wechat_export(path: Path, messages: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "exportInfo": {
                    "version": "0.0.2",
                    "exportedAt": 1785895813,
                    "generator": "CipherTalk",
                    "format": "detailed-json",
                },
                "session": {
                    "wxid": "fictional-chatroom",
                    "nickname": "Fictional Group",
                    "platform": "wechat",
                    "isGroup": True,
                },
                "messages": messages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _text_message(text: str = "Hello from WeChat") -> dict[str, object]:
    return {
        "localId": 1,
        "platformMessageId": "fictional-wechat-message-001",
        "createTime": 1783223281,
        "formattedTime": "2026-07-05 11:48:01",
        "type": TEXT_TYPE,
        "localType": 1,
        "chatLabType": 0,
        "content": text,
        "rawContent": text,
        "isSend": 1,
        "senderUsername": "wxid_fictional_sender",
        "senderDisplayName": "Fictional Alice",
        "senderAvatar": "",
        "source": "",
    }


def test_load_messages_returns_the_top_level_messages_array(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "wechat.json"
    image_message = _text_message("[image]")
    image_message["type"] = IMAGE_TYPE
    _write_wechat_export(
        input_path,
        [_text_message(), image_message],
    )

    messages = load_messages(input_path)

    assert len(messages) == 2
    assert messages[0]["platformMessageId"] == "fictional-wechat-message-001"


def test_is_wechat_export_recognizes_detailed_json(tmp_path: Path) -> None:
    input_path = tmp_path / "wechat.json"
    _write_wechat_export(input_path, [_text_message()])

    assert is_wechat_export(input_path) is True


def test_is_wechat_export_rejects_qq_shaped_json(tmp_path: Path) -> None:
    input_path = tmp_path / "qq.json"
    input_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "id": "fictional-qq-message",
                        "timestamp": 1767315600,
                        "sender": {"nickname": "Fictional QQ"},
                        "type": "text",
                        "content": {"text": "Hello from QQ"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert is_wechat_export(input_path) is False
    assert load_messages(input_path) == []


def test_load_messages_returns_empty_for_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "broken.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    assert load_messages(input_path) == []


def test_text_message_maps_to_chat_message() -> None:
    parsed = parse_messages([_text_message()])

    assert parsed == [
        ChatMessage(
            timestamp=1783223281,
            sender="Fictional Alice",
            message_type="text",
            text="Hello from WeChat",
            platform="wechat",
            source_type=TEXT_TYPE,
            message_id="fictional-wechat-message-001",
            sender_id="wxid_fictional_sender",
            conversation_id=None,
            is_system=False,
            recalled=False,
        )
    ]


def test_text_message_maps_v2_metadata_fields() -> None:
    raw_message = _text_message()
    raw_message["platformMessageId"] = "fictional-wechat-v2-message"
    raw_message["senderUsername"] = "wxid_v2_sender"

    parsed = parse_messages([raw_message])

    assert parsed[0].message_id == "fictional-wechat-v2-message"
    assert parsed[0].sender_id == "wxid_v2_sender"
    assert parsed[0].conversation_id is None
    assert parsed[0].is_system is False
    assert parsed[0].recalled is False


def test_reply_message_uses_only_current_text() -> None:
    raw_reply = _text_message("Current reply only")
    raw_reply["type"] = REPLY_TYPE
    raw_reply["chatLabType"] = 25
    raw_reply["rawContent"] = "quoted original should never be counted"

    parsed = parse_messages([raw_reply])

    assert parsed[0].message_type == "reply"
    assert parsed[0].text == "Current reply only"
    assert "quoted original" not in parsed[0].text


def test_non_textual_message_types_are_filtered() -> None:
    image_message = _text_message("[image]")
    image_message["type"] = IMAGE_TYPE
    system_message = _text_message("System notice")
    system_message["type"] = SYSTEM_TYPE

    parsed = parse_messages(
        [_text_message(), image_message, system_message]
    )

    assert [message.message_type for message in parsed] == ["text"]


def test_unknown_message_type_is_safely_skipped() -> None:
    unknown_message = _text_message("Unknown type text")
    unknown_message["type"] = "fictional-unknown-type"

    assert parse_messages([unknown_message]) == []


def test_malformed_message_does_not_abort_the_remaining_messages() -> None:
    malformed_message = {
        "localId": 2,
        "type": TEXT_TYPE,
        "createTime": 1783223290,
        "content": None,
    }
    valid_message = _text_message("Still parses")

    parsed = parse_messages([malformed_message, valid_message])

    assert len(parsed) == 1
    assert parsed[0].text == "Still parses"


def test_sender_falls_back_to_username_when_display_name_is_missing() -> None:
    raw_message = _text_message()
    raw_message.pop("senderDisplayName")

    parsed = parse_messages([raw_message])

    assert parsed[0].sender == "wxid_fictional_sender"
