"""Adapter for QQChatExporter single-file JSON exports."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .message import ChatMessage


WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED = "qce_non_text_messages_skipped"

_SUPPORTED_MESSAGE_TYPES = frozenset({"text", "reply"})


def is_qce_export(path: str | Path) -> bool:
    """Return whether a file looks like a QQChatExporter single JSON export."""
    return _is_qce_payload(load_qce_json(path))


def load_qce_json(path: str | Path) -> dict[str, Any] | None:
    """Load the top-level QCE JSON object, returning None for invalid files."""
    try:
        input_path = Path(path)
    except TypeError:
        return None

    try:
        with input_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def parse_qce_messages(
    raw_messages: Iterable[Any],
) -> tuple[list[ChatMessage], tuple[str, ...]]:
    """Convert QCE messages to ChatMessage and report skipped non-text rows."""
    parsed_messages: list[ChatMessage] = []
    skipped_non_text = False

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages, ()

    for raw_message in iterator:
        parsed_message = _parse_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)
        elif _is_skipped_non_text_message(raw_message):
            skipped_non_text = True

    warnings = (
        (WARNING_QCE_NON_TEXT_MESSAGE_SKIPPED,)
        if skipped_non_text
        else ()
    )
    return parsed_messages, warnings


def _is_qce_payload(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    return isinstance(payload.get("chatInfo"), dict) and isinstance(
        payload.get("messages"),
        list,
    )


def _parse_message(raw_message: Any) -> ChatMessage | None:
    if not isinstance(raw_message, Mapping):
        return None

    message_type = raw_message.get("type")
    if message_type not in _SUPPORTED_MESSAGE_TYPES:
        return None

    timestamp = raw_message.get("timestamp")
    if not isinstance(timestamp, (int, float, str)):
        return None

    sender_data = raw_message.get("sender")
    if not isinstance(sender_data, Mapping):
        return None

    content = raw_message.get("content")
    if not isinstance(content, Mapping):
        return None

    text = content.get("text")
    if not isinstance(text, str):
        return None

    return ChatMessage(
        timestamp=timestamp,
        sender=_resolve_sender_name(sender_data),
        message_type=message_type,
        text=text,
        platform="qq",
        source_type="qce-json",
        message_id=raw_message.get("id"),
        sender_id=sender_data.get("uid") or sender_data.get("uin"),
        is_system=bool(raw_message.get("system", False)),
        recalled=bool(raw_message.get("recalled", False)),
    )


def _resolve_sender_name(sender_data: Mapping[Any, Any]) -> str:
    for key in ("nickname", "name", "groupCard", "remark", "uin", "uid"):
        value = sender_data.get(key)
        if isinstance(value, str) and value:
            return value
    return "未知用户"


def _is_skipped_non_text_message(raw_message: Any) -> bool:
    if not isinstance(raw_message, Mapping):
        return False
    message_type = raw_message.get("type")
    return isinstance(message_type, str) and message_type not in _SUPPORTED_MESSAGE_TYPES
