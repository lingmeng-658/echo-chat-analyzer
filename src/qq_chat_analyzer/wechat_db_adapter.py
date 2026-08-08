"""Convert WCDB query exports of WeChat 4.x databases into ChatMessage.

The matching provider (``providers.wechat_database_provider``) writes a JSON
document that keeps the database rows exactly as ``wcdb_cli`` returned them,
plus the conversation the rows were read from:

    {
      "source": "wechat-db",
      "conversation": {"username": "wxid_example", "display_name": "..."},
      "messages": [
        {
          "local_id": 1,
          "server_id": 900001,
          "local_type": 1,
          "create_time": 1753412807,
          "message_content": "hello",
          "user_name": "wxid_sender"
        }
      ]
    }

This module never opens a database, never touches WCDB, and never decides
whether a message is worth analyzing. It only maps rows onto the shared
:class:`~qq_chat_analyzer.message.ChatMessage` model.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .message import ChatMessage


WECHAT_PLATFORM = "wechat"
DB_JSON_FORMAT = "wechat-db-json"
SOURCE_MARKER = "wechat-db"

TEXT_LOCAL_TYPE = 1
_TEXT_TYPE = "text"

# Only ``local_type = 1`` carries plain analyzable text. Every other local type
# (image, voice, video, system, revoke, app message) is skipped here rather
# than filtered later, matching wechat_parser and wechat_cli_adapter.
_SUPPORTED_LOCAL_TYPES = {TEXT_LOCAL_TYPE: _TEXT_TYPE}

_JSON_SUFFIX = ".json"


def is_wechat_db_export(path: str | Path) -> bool:
    """Return whether ``path`` is a provider-written WCDB export document."""
    payload = _load_json_object(path)
    if payload is None:
        return False
    return _looks_like_db_export(payload)


def load_messages(path: str | Path) -> list[Any]:
    """Load raw database rows from a WCDB export document."""
    payload = _load_json_object(path)
    if payload is None or not _looks_like_db_export(payload):
        return []

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []

    conversation_id = _conversation_id(payload)
    if conversation_id is None:
        return messages

    rows: list[Any] = []
    for row in messages:
        if isinstance(row, Mapping) and "username" not in row:
            merged = dict(row)
            merged["username"] = conversation_id
            rows.append(merged)
        else:
            rows.append(row)
    return rows


def parse_messages(raw_messages: Iterable[Any]) -> list[ChatMessage]:
    """Normalize supported database rows, isolating malformed entries."""
    parsed_messages: list[ChatMessage] = []

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages

    for raw_message in iterator:
        parsed_message = parse_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)

    return parsed_messages


def parse_message(raw_message: Any) -> ChatMessage | None:
    """Convert one database row into a ChatMessage, or ``None`` if unusable."""
    if not isinstance(raw_message, Mapping):
        return None

    local_type = raw_message.get("local_type")
    message_type = _normalize_local_type(local_type)
    if message_type is None:
        return None

    timestamp = raw_message.get("create_time")
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float, str)):
        return None

    text = raw_message.get("message_content")
    if not isinstance(text, str):
        return None

    sender = _clean_string(raw_message.get("user_name"))
    if sender is None:
        return None

    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type=message_type,
        text=text,
        platform=WECHAT_PLATFORM,
        source_type=local_type,
        message_id=_stringify_id(raw_message.get("server_id"))
        or _stringify_id(raw_message.get("local_id")),
        sender_id=sender,
        conversation_id=_clean_string(raw_message.get("username")),
        is_system=False,
        recalled=False,
    )


def _normalize_local_type(local_type: Any) -> str | None:
    if isinstance(local_type, bool) or not isinstance(local_type, int):
        return None
    return _SUPPORTED_LOCAL_TYPES.get(local_type)


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _stringify_id(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, str)):
        text = str(value).strip()
        return text or None
    return None


def _conversation_id(payload: Mapping[str, Any]) -> str | None:
    conversation = payload.get("conversation")
    if not isinstance(conversation, Mapping):
        return None
    return _clean_string(conversation.get("username"))


def _load_json_object(path: str | Path) -> Mapping[str, Any] | None:
    try:
        input_path = Path(path)
    except TypeError:
        return None

    if input_path.suffix.lower() != _JSON_SUFFIX:
        return None

    try:
        with input_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _looks_like_db_export(payload: Mapping[str, Any]) -> bool:
    if payload.get("source") != SOURCE_MARKER:
        return False
    return isinstance(payload.get("messages"), list)
