"""Behavioral tests for the future QQChatExporter parser."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.json"
JSONL_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.jsonl"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.parser import load_messages, parse_messages


@pytest.fixture
def fixture_messages() -> list[dict]:
    """Load the committed, completely fictional QQChatExporter fixture."""
    return load_messages(FIXTURE_PATH)


def test_load_messages_returns_the_top_level_messages_array(
    fixture_messages: list[dict],
) -> None:
    assert isinstance(fixture_messages, list)
    assert len(fixture_messages) == 7
    assert fixture_messages[0]["messageId"] == "fictional-message-001"


def test_load_messages_reads_independent_jsonl_objects() -> None:
    messages = load_messages(JSONL_FIXTURE_PATH)

    assert len(messages) == 4
    assert [message["type"] for message in messages] == [
        "text",
        "reply",
        "image",
        "system",
    ]
    assert messages[0]["id"] == "fictional-jsonl-message-001"


def test_load_messages_skips_blank_jsonl_lines(tmp_path: Path) -> None:
    input_path = tmp_path / "blank-lines.jsonl"
    message = {
        "id": "fictional-jsonl-blank-check",
        "timestamp": 1767403000,
        "sender": {"nickname": "虚构空行测试用户"},
        "type": "text",
        "content": {"text": "空行不会产生额外消息"},
    }
    input_path.write_text(
        f"\n{json.dumps(message, ensure_ascii=False)}\n\n",
        encoding="utf-8",
    )

    assert load_messages(input_path) == [message]


def test_load_messages_skips_bad_jsonl_line_and_continues(tmp_path: Path) -> None:
    input_path = tmp_path / "one-bad-line.jsonl"
    first = {
        "id": "fictional-jsonl-before-bad-line",
        "timestamp": 1767403100,
        "sender": {"nickname": "虚构前序用户"},
        "type": "text",
        "content": {"text": "错误行之前的虚构消息"},
    }
    second = {
        "id": "fictional-jsonl-after-bad-line",
        "timestamp": 1767403200,
        "sender": {"nickname": "虚构后序用户"},
        "type": "reply",
        "content": {"text": "错误行之后仍可读取"},
    }
    input_path.write_text(
        "\n".join(
            [
                json.dumps(first, ensure_ascii=False),
                "{this is intentionally invalid json",
                json.dumps(second, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )

    messages = load_messages(input_path)

    assert [message["id"] for message in messages] == [
        "fictional-jsonl-before-bad-line",
        "fictional-jsonl-after-bad-line",
    ]


def test_text_message_extracts_the_normalized_fields(
    fixture_messages: list[dict],
) -> None:
    parsed = parse_messages(fixture_messages)

    message = parsed[0]
    assert message.timestamp == 1767315600
    assert message.message_id == "fictional-message-001"
    assert message.sender_id == "100000001"
    assert message.is_system is False
    assert message.recalled is False
    assert message.conversation_id is None
    assert message.sender == "虚构用户甲"
    assert message.message_type == "text"
    assert message.text == "今天一起学习 Python 数据分析"


def test_text_message_maps_v2_metadata_fields() -> None:
    raw_message = {
        "messageId": "fictional-message-v2",
        "timestamp": 1767316300,
        "sender": {
            "uid": "u_fictional_sender",
            "uin": "100000020",
            "nickname": "Fictional V2 Sender",
        },
        "type": "text",
        "content": {"text": "V2 fields"},
        "system": True,
        "recalled": True,
    }

    parsed = parse_messages([raw_message])

    assert parsed[0].message_id == "fictional-message-v2"
    assert parsed[0].sender_id == "u_fictional_sender"
    assert parsed[0].is_system is True
    assert parsed[0].recalled is True
    assert parsed[0].conversation_id is None


def test_text_message_falls_back_to_id_and_sender_uin() -> None:
    raw_message = {
        "id": "fictional-jsonl-v2-message",
        "timestamp": 1767316320,
        "sender": {
            "uin": "100000021",
            "nickname": "Fictional Fallback Sender",
        },
        "type": "text",
        "content": {"text": "Fallback id fields"},
    }

    parsed = parse_messages([raw_message])

    assert parsed[0].message_id == "fictional-jsonl-v2-message"
    assert parsed[0].sender_id == "100000021"
    assert parsed[0].is_system is False
    assert parsed[0].recalled is False


def test_text_message_uses_sender_name_when_nickname_is_missing() -> None:
    raw_message = {
        "id": "fictional-message-name-only",
        "timestamp": 1767316340,
        "sender": {
            "uid": "u_fictional",
            "uin": "100000022",
            "name": "Fictional Name Sender",
            "nickname": "",
        },
        "type": "text",
        "content": {"text": "nickname missing but name present"},
    }

    parsed = parse_messages([raw_message])

    assert len(parsed) == 1
    assert parsed[0].sender == "Fictional Name Sender"
    assert parsed[0].platform == "qq"


def test_text_message_falls_back_to_uin_and_unknown_user() -> None:
    uin_only = {
        "id": "fictional-message-uin-only",
        "timestamp": 1767316360,
        "sender": {"uid": "u_fictional", "uin": "100000023"},
        "type": "text",
        "content": {"text": "uin fallback"},
    }
    empty_sender = {
        "id": "fictional-message-empty-sender",
        "timestamp": 1767316380,
        "sender": {},
        "type": "text",
        "content": {"text": "unknown user fallback"},
    }

    parsed = parse_messages([uin_only, empty_sender])

    assert parsed[0].sender == "100000023"
    assert parsed[1].sender == "\u672a\u77e5\u7528\u6237"


def test_reply_extracts_only_the_repliers_new_text(
    fixture_messages: list[dict],
) -> None:
    parsed = parse_messages(fixture_messages)

    reply = parsed[1]
    assert reply.message_type == "reply"
    assert reply.text == "好呀，下午两点开始吧"
    assert "今天一起学习 Python 数据分析" not in reply.text


@pytest.mark.parametrize("reference_key", ["replyTo", "quote", "source"])
def test_reply_never_reads_nested_reference_fields(reference_key: str) -> None:
    raw_reply = {
        "messageId": f"fictional-reply-{reference_key}",
        "timestamp": 1767316000,
        "sender": {
            "uin": "100000010",
            "nickname": "虚构回复者",
        },
        "type": "reply",
        "content": {
            "text": "只统计回复者新增的这句话",
            reference_key: {
                "content": {
                    "text": "这是一段绝不能被统计的虚构引用原文",
                }
            },
        },
    }

    parsed = parse_messages([raw_reply])

    assert len(parsed) == 1
    assert parsed[0].text == "只统计回复者新增的这句话"
    assert "绝不能被统计" not in parsed[0].text


def test_non_textual_message_types_are_filtered(
    fixture_messages: list[dict],
) -> None:
    parsed = parse_messages(fixture_messages)

    assert [message.message_type for message in parsed] == [
        "text",
        "reply",
        "text",
    ]


def test_unknown_message_type_is_safely_skipped() -> None:
    unknown_message = {
        "messageId": "fictional-message-unknown",
        "timestamp": 1767316060,
        "sender": {
            "uin": "100000011",
            "nickname": "虚构未知用户",
        },
        "type": "fictional-unknown-type",
        "content": {
            "text": "未知类型中的文本不应进入结果",
        },
    }

    assert parse_messages([unknown_message]) == []


def test_one_malformed_message_does_not_abort_the_remaining_messages() -> None:
    malformed_message = {
        "messageId": "fictional-message-malformed",
        "timestamp": 1767316120,
        "sender": None,
        "type": "text",
        "content": None,
    }
    valid_message = {
        "messageId": "fictional-message-valid-after-malformed",
        "timestamp": 1767316180,
        "sender": {
            "uin": "100000012",
            "nickname": "虚构健全用户",
        },
        "type": "text",
        "content": {
            "text": "异常消息之后仍然可以解析",
        },
    }

    parsed = parse_messages([malformed_message, valid_message])

    assert len(parsed) == 1
    assert parsed[0].timestamp == 1767316180
    assert parsed[0].sender == "虚构健全用户"
    assert parsed[0].text == "异常消息之后仍然可以解析"
