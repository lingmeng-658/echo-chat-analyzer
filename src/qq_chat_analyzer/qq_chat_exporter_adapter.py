"""Adapter for QQChatExporter single-file JSON exports."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .legacy_projection import project_legacy_messages
from .message import ChatMessage
from .rich_message import (
    MentionRelation,
    MessageRelation,
    RecallState,
    ReplyRelation,
    RichMessage,
    SenderIdentity,
    TextContent,
)


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


def qce_conversation_id(payload: Mapping[str, Any] | None) -> str | None:
    """Return a stable conversation identifier when QCE exported one."""
    if not isinstance(payload, Mapping):
        return None
    chat_info = payload.get("chatInfo")
    if not isinstance(chat_info, Mapping):
        return None
    return _first_identifier(
        chat_info,
        "groupCode",
        "peerUid",
        "conversationId",
        "id",
        "uin",
        "uid",
    )


def parse_qce_messages(
    raw_messages: Iterable[Any],
    conversation_id: str | None = None,
) -> tuple[list[ChatMessage], tuple[str, ...]]:
    """Project QCE rich messages for the existing analysis pipeline."""
    rich_messages, warnings = parse_qce_rich_messages(
        raw_messages,
        conversation_id=conversation_id,
    )
    return project_legacy_messages(rich_messages), warnings


def parse_qce_rich_messages(
    raw_messages: Iterable[Any],
    conversation_id: str | None = None,
) -> tuple[list[RichMessage], tuple[str, ...]]:
    """Convert QCE messages to P0 source-neutral semantic facts."""
    parsed_messages: list[RichMessage] = []
    skipped_non_text = False

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages, ()

    for raw_message in iterator:
        parsed_message = _parse_rich_message(
            raw_message,
            conversation_id=conversation_id,
        )
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


def _parse_rich_message(
    raw_message: Any,
    conversation_id: str | None,
) -> RichMessage | None:
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

    recalled = raw_message.get("recalled")
    recall_state = (
        RecallState(is_recalled=recalled)
        if isinstance(recalled, bool)
        else None
    )
    return RichMessage(
        message_id=_stringify_identifier(raw_message.get("id")),
        source="qq",
        source_type="qce-json",
        conversation_id=conversation_id,
        sender=SenderIdentity(
            identity_id=_stringify_identifier(
                sender_data.get("uid") or sender_data.get("uin")
            ),
            display_name=_resolve_sender_name(sender_data),
            remark=_first_text(sender_data, "remark"),
            nickname=_first_text(sender_data, "nickname", "name"),
            contextual_name=_first_text(sender_data, "groupCard"),
        ),
        timestamp=timestamp,
        message_type=message_type,
        contents=(TextContent(text=text),),
        relations=_extract_relations(content),
        recall_state=recall_state,
        is_system=bool(raw_message.get("system", False)),
    )


def _extract_relations(content: Mapping[Any, Any]) -> tuple[MessageRelation, ...]:
    relations: list[MessageRelation] = []
    elements = content.get("elements")
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, Mapping):
                continue
            element_type = element.get("type")
            if element_type == "reply" or element.get("elementType") == 7:
                target = _reply_target(element)
                if target:
                    relations.append(ReplyRelation(target_message_id=target))
            mention = _mention_relation(element)
            if mention is not None:
                relations.append(mention)

    mentions = content.get("mentions")
    if isinstance(mentions, list):
        for mention_data in mentions:
            if not isinstance(mention_data, Mapping):
                continue
            target = _first_identifier(
                mention_data,
                "uid",
                "uin",
                "targetUid",
                "targetUin",
                "id",
            )
            if target:
                relations.append(
                    MentionRelation(
                        target_identity_id=target,
                        display_text=_first_text(
                            mention_data,
                            "text",
                            "name",
                            "displayName",
                        ),
                    )
                )
    return tuple(relations)


def _reply_target(element: Mapping[Any, Any]) -> str | None:
    for key in ("replyElement", "data"):
        block = element.get(key)
        if isinstance(block, Mapping):
            target = _first_identifier(
                block,
                "sourceMsgIdInRecords",
                "replayMsgId",
                "messageId",
                "message_id",
                "id",
            )
            if target:
                return target
    return _first_identifier(
        element,
        "sourceMsgIdInRecords",
        "replayMsgId",
        "messageId",
        "message_id",
        "id",
    )


def _mention_relation(element: Mapping[Any, Any]) -> MentionRelation | None:
    element_type = element.get("type")
    if element_type not in ("text", "at") and element.get("elementType") != 1:
        return None
    block: Mapping[Any, Any] = element
    for key in ("textElement", "data"):
        candidate = element.get(key)
        if isinstance(candidate, Mapping):
            block = candidate
            break
    at_type = block.get("atType")
    target = _first_identifier(block, "atNtUid", "atUid", "uid", "uin")
    if not target or at_type in (None, 0, "0"):
        return None
    return MentionRelation(
        target_identity_id=target,
        display_text=_first_text(block, "content", "text", "name"),
    )


def _first_identifier(data: Mapping[Any, Any], *keys: str) -> str | None:
    for key in keys:
        value = _stringify_identifier(data.get(key))
        if value:
            return value
    return None


def _first_text(data: Mapping[Any, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _stringify_identifier(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


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
