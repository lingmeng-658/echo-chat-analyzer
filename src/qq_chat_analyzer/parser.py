"""Parse QQChatExporter JSON messages into a small normalized model."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .legacy_projection import project_legacy_messages
from .message import ChatMessage
from .rich_message import (
    RecallState,
    ReplyRelation,
    RichMessage,
    SenderIdentity,
    TextContent,
)


SUPPORTED_MESSAGE_TYPES = frozenset({"text", "reply"})

ParsedMessage = ChatMessage


def load_messages(path: str | Path) -> list[Any]:
    """Load raw messages from a JSON export or line-delimited JSON export."""
    try:
        input_path = Path(path)
    except TypeError:
        return []

    if input_path.suffix.lower() == ".jsonl":
        return _load_jsonl_messages(input_path)

    return _load_json_messages(input_path)


def _load_json_messages(path: Path) -> list[Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []

    if not isinstance(payload, dict):
        return []

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []

    return messages


def _load_jsonl_messages(path: Path) -> list[Any]:
    messages: list[Any] = []

    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue

                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(message, dict):
                    messages.append(message)
    except (OSError, UnicodeDecodeError):
        return messages

    return messages


def parse_messages(raw_messages: Iterable[Any]) -> list[ChatMessage]:
    """Project normalized QQ rich messages for existing analysis."""
    return project_legacy_messages(parse_rich_messages(raw_messages))


def parse_rich_messages(raw_messages: Iterable[Any]) -> list[RichMessage]:
    """Normalize supported legacy QQ exports into P0 semantic facts."""
    parsed_messages: list[RichMessage] = []

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages

    for raw_message in iterator:
        parsed_message = _parse_rich_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)

    return parsed_messages


def _parse_rich_message(raw_message: Any) -> RichMessage | None:
    if not isinstance(raw_message, Mapping):
        return None

    message_type = raw_message.get("type")
    if message_type not in SUPPORTED_MESSAGE_TYPES:
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

    # For both text and reply messages, only the current message's text is
    # considered. Quoted/reference nodes are intentionally never traversed.
    text = content.get("text")
    if not isinstance(text, str):
        return None

    message_id = raw_message.get("messageId") or raw_message.get("id")
    sender_id = sender_data.get("uid") or sender_data.get("uin")
    recalled = raw_message.get("recalled")
    relations: tuple[ReplyRelation, ...] = ()
    for key in ("replyTo", "quote", "source"):
        reference = content.get(key)
        if not isinstance(reference, Mapping):
            continue
        target = reference.get("messageId") or reference.get("id")
        if isinstance(target, (str, int)) and not isinstance(target, bool):
            relations = (ReplyRelation(target_message_id=str(target)),)
            break
    return RichMessage(
        message_id=(str(message_id) if message_id is not None else None),
        source="qq",
        conversation_id=None,
        sender=SenderIdentity(
            identity_id=(str(sender_id) if sender_id is not None else None),
            display_name=_resolve_sender_name(sender_data),
        ),
        timestamp=timestamp,
        message_type=message_type,
        contents=(TextContent(text=text),),
        relations=relations,
        recall_state=(
            RecallState(is_recalled=recalled)
            if isinstance(recalled, bool)
            else None
        ),
        is_system=raw_message.get("system", False),
    )


def _resolve_sender_name(sender_data: Mapping[Any, Any]) -> str:
    for key in ("nickname", "name", "groupCard", "remark", "uin", "uid"):
        value = sender_data.get(key)
        if isinstance(value, str) and value:
            return value
    return "\u672a\u77e5\u7528\u6237"
