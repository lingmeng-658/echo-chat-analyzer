"""Parse CipherTalk WeChat detailed JSON exports into ChatMessage."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .message import ChatMessage


TEXT_MESSAGE_TYPE = "\u6587\u672c\u6d88\u606f"
REPLY_MESSAGE_TYPE = "\u5f15\u7528\u6d88\u606f"
WECHAT_PLATFORM = "wechat"
DETAILED_JSON_FORMAT = "detailed-json"

SUPPORTED_MESSAGE_TYPES = frozenset(
    {TEXT_MESSAGE_TYPE, REPLY_MESSAGE_TYPE}
)
_NORMALIZED_MESSAGE_TYPES = {
    TEXT_MESSAGE_TYPE: "text",
    REPLY_MESSAGE_TYPE: "reply",
}

ParsedMessage = ChatMessage


def is_wechat_export(path: str | Path) -> bool:
    """Return whether the JSON file is a WeChat detailed export."""
    payload = _load_json_payload(path)
    if payload is None:
        return False
    return _looks_like_wechat_export(payload)


def load_messages(path: str | Path) -> list[Any]:
    """Load the top-level message array from a WeChat detailed export."""
    payload = _load_json_payload(path)
    if payload is None or not _looks_like_wechat_export(payload):
        return []

    messages = payload.get("messages")
    return messages if isinstance(messages, list) else []


def parse_messages(raw_messages: Iterable[Any]) -> list[ChatMessage]:
    """Normalize supported WeChat messages while isolating malformed entries."""
    parsed_messages: list[ChatMessage] = []

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages

    for raw_message in iterator:
        parsed_message = _parse_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)

    return parsed_messages


def _load_json_payload(path: str | Path) -> Mapping[str, Any] | None:
    try:
        input_path = Path(path)
    except TypeError:
        return None

    if input_path.suffix.lower() != ".json":
        return None

    try:
        with input_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, Mapping) else None


def _looks_like_wechat_export(payload: Mapping[str, Any]) -> bool:
    session = payload.get("session")
    if isinstance(session, Mapping) and session.get("platform") == WECHAT_PLATFORM:
        return True

    export_info = payload.get("exportInfo")
    if (
        isinstance(export_info, Mapping)
        and export_info.get("format") == DETAILED_JSON_FORMAT
    ):
        return True

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False

    for message in messages[:50]:
        if not isinstance(message, Mapping):
            continue
        if message.get("type") in SUPPORTED_MESSAGE_TYPES:
            return True
        if "senderDisplayName" in message and "createTime" in message:
            return True

    return False


def _parse_message(raw_message: Any) -> ChatMessage | None:
    if not isinstance(raw_message, Mapping):
        return None

    source_type = raw_message.get("type")
    message_type = _NORMALIZED_MESSAGE_TYPES.get(source_type)
    if message_type is None:
        return None

    timestamp = raw_message.get("createTime")
    if not isinstance(timestamp, (int, float, str)):
        return None

    sender = raw_message.get("senderDisplayName")
    if not isinstance(sender, str) or not sender.strip():
        sender = raw_message.get("senderUsername")
    if not isinstance(sender, str) or not sender.strip():
        return None

    text = raw_message.get("content")
    if not isinstance(text, str):
        return None

    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type=message_type,
        text=text,
        platform=WECHAT_PLATFORM,
        source_type=source_type,
    )
