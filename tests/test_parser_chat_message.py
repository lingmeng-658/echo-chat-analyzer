"""Contract tests for adapting parsed QQ messages to ChatMessage."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.parser import parse_messages


def test_parse_messages_returns_chat_message() -> None:
    parsed = parse_messages([_raw_text_message()])

    assert isinstance(parsed[0], ChatMessage)


def test_parse_messages_preserves_fields_in_chat_message() -> None:
    parsed = parse_messages([_raw_text_message()])

    assert parsed == [
        ChatMessage(
            timestamp=1767315600,
                sender="Fictional Alice",
                message_type="text",
                text="Hello from QQ",
                platform="qq",
                source_type=None,
            message_id=None,
            sender_id=None,
            conversation_id=None,
            is_system=False,
            recalled=False,
        )
    ]


def _raw_text_message() -> dict[str, object]:
    return {
        "timestamp": 1767315600,
        "sender": {"nickname": "Fictional Alice"},
        "type": "text",
        "content": {"text": "Hello from QQ"},
    }
