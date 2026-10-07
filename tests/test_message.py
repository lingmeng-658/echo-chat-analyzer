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
    assert message.sender_remark is None
    assert message.sender_nickname is None
    assert message.sender_contextual_name is None
