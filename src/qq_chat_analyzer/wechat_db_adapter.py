"""Convert WCDB query exports of WeChat 4.x databases into rich messages.

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
whether a message is worth analyzing. It maps rows onto the source-neutral
rich model, then projects that model for legacy analysis callers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .legacy_projection import project_legacy_message, project_legacy_messages
from .message import ChatMessage
from .rich_message import RichMessage, SenderIdentity, TextContent


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

    conversation_type = _conversation_type_from_payload(payload)
    self_username = _self_username(payload)
    rows: list[Any] = []
    for row in messages:
        if isinstance(row, Mapping) and "username" not in row:
            merged = dict(row)
            merged["username"] = conversation_id
            row = merged
        if isinstance(row, Mapping):
            if conversation_type and "conversation_type" not in row:
                row = dict(row)
                row["conversation_type"] = conversation_type
            if self_username and "self_username" not in row:
                row = dict(row)
                row["self_username"] = self_username
        rows.append(row)
    return rows


def parse_messages(raw_messages: Iterable[Any]) -> list[ChatMessage]:
    """Project supported database rows for existing analysis callers."""
    return project_legacy_messages(parse_rich_messages(raw_messages))


def parse_rich_messages(raw_messages: Iterable[Any]) -> list[RichMessage]:
    """Normalize supported database rows into source-neutral facts."""
    parsed_messages: list[RichMessage] = []

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages

    for raw_message in iterator:
        parsed_message = parse_rich_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)

    return parsed_messages


def parse_message(raw_message: Any) -> ChatMessage | None:
    """Project one database row for callers of the legacy adapter API."""
    rich_message = parse_rich_message(raw_message)
    if rich_message is None:
        return None
    return project_legacy_message(rich_message)


def parse_rich_message(raw_message: Any) -> RichMessage | None:
    """Convert one database row into a RichMessage, or ``None`` if unusable."""
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

    sender_id = _clean_string(raw_message.get("user_name"))
    if sender_id is None:
        return None
    sender = _clean_string(raw_message.get("sender_name")) or sender_id
    self_username = _clean_string(raw_message.get("self_username"))
    is_self = None
    if self_username is not None:
        is_self = sender_id == self_username

    return RichMessage(
        message_id=_stringify_id(raw_message.get("server_id"))
        or _stringify_id(raw_message.get("local_id")),
        source=WECHAT_PLATFORM,
        conversation_id=_clean_string(raw_message.get("username")),
        conversation_type=_conversation_type(raw_message),
        sender=SenderIdentity(
            identity_id=sender_id,
            display_name=sender,
        ),
        is_self=is_self,
        timestamp=timestamp,
        message_type=message_type,
        contents=(TextContent(text=text),),
        source_type=local_type,
        is_system=False,
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


def _conversation_type_from_payload(payload: Mapping[str, Any]) -> str:
    conversation = payload.get("conversation")
    if not isinstance(conversation, Mapping):
        return "unknown"
    session_type = conversation.get("session_type")
    if isinstance(session_type, str):
        normalized = _normalize_conversation_type(session_type)
        if normalized != "unknown":
            return normalized
    return "unknown"


def _self_username(payload: Mapping[str, Any]) -> str | None:
    conversation = payload.get("conversation")
    if not isinstance(conversation, Mapping):
        return None
    return _clean_string(conversation.get("self_username"))


def _conversation_type(raw_message: Mapping[str, Any]) -> str:
    explicit = raw_message.get("conversation_type")
    if isinstance(explicit, str):
        normalized = _normalize_conversation_type(explicit)
        if normalized != "unknown":
            return normalized

    username = _clean_string(raw_message.get("username"))
    if not username:
        return "unknown"
    if username.endswith("@chatroom"):
        return "group"
    return "private"


def _normalize_conversation_type(raw_type: str) -> str:
    normalized = raw_type.strip().lower()
    if normalized in {"private", "group"}:
        return normalized
    return "unknown"


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
