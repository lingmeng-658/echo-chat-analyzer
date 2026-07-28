"""Parse QQChatExporter JSON messages into a small normalized model."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_MESSAGE_TYPES = frozenset({"text", "reply"})


@dataclass(frozen=True, slots=True)
class ParsedMessage:
    """A text-bearing chat message normalized for later processing."""

    timestamp: int | float | str
    sender: str
    message_type: str
    text: str


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


def parse_messages(raw_messages: Iterable[Any]) -> list[ParsedMessage]:
    """Normalize supported messages while isolating malformed entries."""
    parsed_messages: list[ParsedMessage] = []

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages

    for raw_message in iterator:
        parsed_message = _parse_message(raw_message)
        if parsed_message is not None:
            parsed_messages.append(parsed_message)

    return parsed_messages


def _parse_message(raw_message: Any) -> ParsedMessage | None:
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

    sender = sender_data.get("nickname")
    if not isinstance(sender, str):
        return None

    content = raw_message.get("content")
    if not isinstance(content, Mapping):
        return None

    # For both text and reply messages, only the current message's text is
    # considered. Quoted/reference nodes are intentionally never traversed.
    text = content.get("text")
    if not isinstance(text, str):
        return None

    return ParsedMessage(
        timestamp=timestamp,
        sender=sender,
        message_type=message_type,
        text=text,
    )
