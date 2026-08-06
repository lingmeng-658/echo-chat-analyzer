"""Parse CipherTalk WeChat detailed JSON and chatlab JSONL exports."""

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

CHATLAB_TEXT_TYPE = 0
CHATLAB_REPLY_TYPE = 25
CHATLAB_JSONL_SUFFIX = ".jsonl"
_CHATLAB_MESSAGE_LINE = "message"
_CHATLAB_HEADER_LINE = "header"
_NORMALIZED_CHATLAB_TYPES = {
    CHATLAB_TEXT_TYPE: "text",
    CHATLAB_REPLY_TYPE: "reply",
}

ParsedMessage = ChatMessage


def is_wechat_export(path: str | Path) -> bool:
    """Return whether the file is a supported WeChat export."""
    if _is_jsonl_path(path):
        return _looks_like_chatlab_export(path)

    payload = _load_json_payload(path)
    if payload is None:
        return False
    return _looks_like_wechat_export(payload)


def load_messages(path: str | Path) -> list[Any]:
    """Load raw messages from a WeChat detailed JSON or chatlab JSONL export."""
    if _is_jsonl_path(path):
        return _load_chatlab_messages(path)

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


def _is_jsonl_path(path: str | Path) -> bool:
    try:
        return Path(path).suffix.lower() == CHATLAB_JSONL_SUFFIX
    except TypeError:
        return False


def _iter_chatlab_lines(path: str | Path) -> list[Mapping[str, Any]]:
    try:
        input_path = Path(path)
    except TypeError:
        return []

    records: list[Mapping[str, Any]] = []
    try:
        with input_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, Mapping):
                    records.append(record)
    except (OSError, UnicodeDecodeError):
        return records

    return records


def _looks_like_chatlab_export(path: str | Path) -> bool:
    for record in _iter_chatlab_lines(path):
        line_type = record.get("_type")
        if line_type == _CHATLAB_HEADER_LINE:
            meta = record.get("meta")
            if (
                isinstance(meta, Mapping)
                and meta.get("platform") == WECHAT_PLATFORM
            ):
                return True
        if line_type == _CHATLAB_MESSAGE_LINE:
            return True
    return False


def _load_chatlab_messages(path: str | Path) -> list[Any]:
    if not _looks_like_chatlab_export(path):
        return []

    return [
        record
        for record in _iter_chatlab_lines(path)
        if record.get("_type") == _CHATLAB_MESSAGE_LINE
    ]


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

    if raw_message.get("_type") == _CHATLAB_MESSAGE_LINE:
        return _parse_chatlab_message(raw_message)

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
        message_id=raw_message.get("platformMessageId"),
        sender_id=raw_message.get("senderUsername"),
        is_system=False,
        recalled=False,
    )


def _parse_chatlab_message(raw_message):
    source_type = raw_message.get("type")
    if isinstance(source_type, bool) or not isinstance(source_type, int):
        return None

    message_type = _NORMALIZED_CHATLAB_TYPES.get(source_type)
    if message_type is None:
        return None

    timestamp = raw_message.get("timestamp")
    if not isinstance(timestamp, (int, float, str)):
        return None

    sender = raw_message.get("accountName")
    if not isinstance(sender, str) or not sender.strip():
        sender = raw_message.get("sender")
    if not isinstance(sender, str) or not sender.strip():
        return None

    text_value = raw_message.get("content")
    if not isinstance(text_value, str):
        return None

    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type=message_type,
        text=text_value,
        platform=WECHAT_PLATFORM,
        source_type=source_type,
        message_id=raw_message.get("platformMessageId"),
        sender_id=raw_message.get("sender"),
        is_system=False,
        recalled=False,
    )
