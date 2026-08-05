"""Contract tests for the source-neutral chat message model."""

from __future__ import annotations

import importlib
import sys
from dataclasses import FrozenInstanceError, is_dataclass
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _chat_message_class():
    message_module = importlib.import_module("qq_chat_analyzer.message")
    return message_module.ChatMessage


def test_chat_message_can_be_imported() -> None:
    ChatMessage = _chat_message_class()

    assert ChatMessage.__name__ == "ChatMessage"


def test_chat_message_can_be_created_as_a_dataclass() -> None:
    ChatMessage = _chat_message_class()

    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="Hello",
    )

    assert is_dataclass(message)


def test_chat_message_preserves_explicit_field_values() -> None:
    ChatMessage = _chat_message_class()

    message = ChatMessage(
        timestamp="1767315600",
        sender="Fictional Bob",
        message_type="reply",
        text="Current reply only",
        platform="wechat",
        source_type=57,
    )

    assert message.timestamp == "1767315600"
    assert message.sender == "Fictional Bob"
    assert message.message_type == "reply"
    assert message.text == "Current reply only"
    assert message.platform == "wechat"
    assert message.source_type == 57


def test_chat_message_is_frozen() -> None:
    ChatMessage = _chat_message_class()
    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="Original text",
    )

    with pytest.raises(FrozenInstanceError):
        message.text = "Changed text"


def test_chat_message_uses_slots() -> None:
    ChatMessage = _chat_message_class()
    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="Hello",
    )

    assert not hasattr(message, "__dict__")


def test_chat_message_has_source_neutral_defaults() -> None:
    ChatMessage = _chat_message_class()
    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="Hello",
    )

    assert message.platform == "unknown"
    assert message.source_type is None


def test_chat_message_new_fields_have_defaults() -> None:
    ChatMessage = _chat_message_class()
    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="Hello",
    )

    assert message.message_id is None
    assert message.sender_id is None
    assert message.conversation_id is None
    assert message.is_system is False
    assert message.recalled is False
