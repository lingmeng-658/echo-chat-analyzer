"""Adapter for QQChatExporter single-file JSON exports."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from .legacy_projection import project_legacy_messages
from .message import ChatMessage
from .rich_message import (
    EXPRESSION_KIND_PLATFORM_FACE,
    EXPRESSION_KIND_STICKER,
    ExpressionContent,
    MentionRelation,
    MessageRelation,
    RichContent,
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


def qce_conversation_type(payload: Mapping[str, Any] | None) -> str:
    """Return private/group/unknown from the QCE chat info block."""
    if not isinstance(payload, Mapping):
        return "unknown"
    chat_info = payload.get("chatInfo")
    if not isinstance(chat_info, Mapping):
        return "unknown"

    chat_type = chat_info.get("chatType")
    if isinstance(chat_type, int) and not isinstance(chat_type, bool):
        if chat_type == 1:
            return "private"
        if chat_type == 2:
            return "group"
        return "unknown"

    for key in ("type", "sessionType", "conversationType"):
        raw_type = chat_info.get(key)
        if isinstance(raw_type, str):
            normalized = _normalize_conversation_type(raw_type)
            if normalized != "unknown":
                return normalized
    return "unknown"


def qce_self_identity(payload: Mapping[str, Any] | None) -> str | None:
    """Return the QCE export's reliable self stable ID, when present."""
    identities = qce_self_identities(payload)
    return identities[0] if identities else None


def qce_self_identities(payload: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Return every reliable self ID alias exported by QCE."""
    if not isinstance(payload, Mapping):
        return ()
    chat_info = payload.get("chatInfo")
    if not isinstance(chat_info, Mapping):
        return ()
    identities: list[str] = []
    for key in ("selfUid", "self_uid", "selfUin", "self_uin"):
        identity = _stringify_identifier(chat_info.get(key))
        if identity and identity not in identities:
            identities.append(identity)
    return tuple(identities)


def _normalize_conversation_type(raw_type: str) -> str:
    normalized = raw_type.strip().lower()
    if normalized in {"private", "friend", "c2c"}:
        return "private"
    if normalized in {"group", "chatroom"}:
        return "group"
    return "unknown"


def parse_qce_messages(
    raw_messages: Iterable[Any],
    conversation_id: str | None = None,
    conversation_type: str = "unknown",
    self_identity: str | Iterable[str] | None = None,
) -> tuple[list[ChatMessage], tuple[str, ...]]:
    """Project QCE rich messages for the existing analysis pipeline."""
    rich_messages, warnings = parse_qce_rich_messages(
        raw_messages,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        self_identity=self_identity,
    )
    return project_legacy_messages(rich_messages), warnings


def parse_qce_rich_messages(
    raw_messages: Iterable[Any],
    conversation_id: str | None = None,
    conversation_type: str = "unknown",
    self_identity: str | Iterable[str] | None = None,
) -> tuple[list[RichMessage], tuple[str, ...]]:
    """Convert QCE messages to P0 source-neutral semantic facts."""
    parsed_messages: list[RichMessage] = []
    skipped_non_text = False
    self_identities = _normalize_self_identities(self_identity)

    try:
        iterator = iter(raw_messages)
    except TypeError:
        return parsed_messages, ()

    for raw_message in iterator:
        parsed_message = _parse_rich_message(
            raw_message,
            conversation_id=conversation_id,
            conversation_type=conversation_type,
            self_identities=self_identities,
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
    conversation_type: str,
    self_identities: frozenset[str],
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

    contents = _build_rich_contents(content)
    if not contents:
        return None

    recalled = raw_message.get("recalled")
    recall_state = (
        RecallState(is_recalled=recalled)
        if isinstance(recalled, bool)
        else None
    )
    identity_id = _stringify_identifier(
        sender_data.get("uid") or sender_data.get("uin")
    )
    is_self = None
    if self_identities:
        uid_value = _stringify_identifier(sender_data.get("uid"))
        uin_value = _stringify_identifier(sender_data.get("uin"))
        if identity_id or uid_value or uin_value:
            sender_identities = {identity_id, uid_value, uin_value} - {None}
            is_self = bool(self_identities.intersection(sender_identities))

    return RichMessage(
        message_id=_stringify_identifier(raw_message.get("id")),
        source="qq",
        source_type="qce-json",
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        sender=SenderIdentity(
            identity_id=identity_id,
            display_name=_resolve_sender_name(sender_data),
            remark=_first_text(sender_data, "remark"),
            nickname=_first_text(sender_data, "nickname", "name"),
            contextual_name=_first_text(sender_data, "groupCard"),
        ),
        is_self=is_self,
        timestamp=timestamp,
        message_type=message_type,
        contents=tuple(contents),
        relations=_extract_relations(content),
        recall_state=recall_state,
        is_system=bool(raw_message.get("system", False)),
    )


def _normalize_self_identities(
    value: str | Iterable[str] | None,
) -> frozenset[str]:
    if isinstance(value, str):
        values: Iterable[str] = (value,)
    elif value is None:
        values = ()
    else:
        values = value
    return frozenset(
        identity.strip()
        for identity in values
        if isinstance(identity, str) and identity.strip()
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


def _extract_expression_contents(
    content: Mapping[Any, Any],
) -> tuple[ExpressionContent, ...]:
    """Extract source-neutral expression content from QCE elements."""
    expressions: list[ExpressionContent] = []
    elements = content.get("elements")
    if isinstance(elements, list):
        for element in elements:
            if not isinstance(element, Mapping):
                continue
            expression = _expression_from_element(element)
            if expression is not None:
                expressions.append(expression)
    return tuple(expressions)


def _build_rich_contents(content: Mapping[Any, Any]) -> tuple[RichContent, ...]:
    """Build ordered contents, falling back to the legacy text projection."""
    ordered = _ordered_content_parts(content)
    if ordered is not None:
        return ordered

    text = content.get("text")
    contents: list[RichContent] = []
    if isinstance(text, str) and text:
        contents.append(TextContent(text=text))
    contents.extend(_extract_expression_contents(content))
    return tuple(contents)


def _ordered_content_parts(
    content: Mapping[Any, Any],
) -> tuple[RichContent, ...] | None:
    """Reconstruct QCE element order when it matches the exported text."""
    elements = content.get("elements")
    if not isinstance(elements, list):
        return None

    parts: list[RichContent] = []
    text_parts: list[str] = []
    for element in elements:
        if not isinstance(element, Mapping):
            continue
        text_value = _text_element_content(element)
        if text_value is not None:
            parts.append(TextContent(text=text_value))
            text_parts.append(text_value)
            continue
        expression = _expression_from_element(element)
        if expression is not None:
            parts.append(expression)

    has_expression = any(
        isinstance(part, ExpressionContent) for part in parts
    )
    if not has_expression or not text_parts:
        return None
    exported_text = content.get("text")
    if not isinstance(exported_text, str):
        return None
    if "".join(text_parts) != exported_text:
        return None

    expression_index = 0
    resolved: list[RichContent] = []
    for index, part in enumerate(parts):
        if not isinstance(part, ExpressionContent):
            resolved.append(part)
            continue
        resolved.append(
            replace(
                part,
                position=expression_index,
                text_before=_adjacent_text_before(parts, index),
                text_after=_adjacent_text_after(parts, index),
            )
        )
        expression_index += 1
    return tuple(resolved)


def _text_element_content(element: Mapping[Any, Any]) -> str | None:
    element_type = element.get("type")
    if element_type != "text" and element.get("elementType") != 1:
        return None
    block = element.get("textElement")
    if not isinstance(block, Mapping):
        block = element.get("data")
    if not isinstance(block, Mapping):
        return None
    text = _first_text(block, "content", "text")
    return text


def _expression_from_element(element: Mapping[Any, Any]) -> ExpressionContent | None:
    element_type = element.get("type")
    element_code = element.get("elementType")
    if element_type == "face" or element_code == 6:
        return _face_expression(element)
    if element_type == "market_face" or element_code == 37:
        return _market_face_expression(element)
    return None


def _adjacent_text_before(
    parts: list[RichContent],
    index: int,
) -> str | None:
    for candidate in range(index - 1, -1, -1):
        part = parts[candidate]
        if isinstance(part, TextContent):
            return part.text[-40:]
    return None


def _adjacent_text_after(
    parts: list[RichContent],
    index: int,
) -> str | None:
    for candidate in range(index + 1, len(parts)):
        part = parts[candidate]
        if isinstance(part, TextContent):
            return part.text[:40]
    return None


def _face_expression(element: Mapping[Any, Any]) -> ExpressionContent | None:
    block = element.get("data")
    if not isinstance(block, Mapping):
        block = element.get("faceElement")
    if not isinstance(block, Mapping):
        return None
    face_id = (
        _stringify_identifier(block.get("id"))
        or _stringify_identifier(block.get("faceIndex"))
        or _first_text(block, "id", "faceId")
    )
    if face_id is None:
        return None
    face_name = _first_text(block, "name", "faceText")
    return ExpressionContent(
        expression_kind=EXPRESSION_KIND_PLATFORM_FACE,
        expression_key=face_id,
        display_text=face_name or f"[QQ表情 {face_id}]",
        source="qq",
    )


def _market_face_expression(element: Mapping[Any, Any]) -> ExpressionContent | None:
    block = element.get("data")
    if not isinstance(block, Mapping):
        block = element.get("marketFaceElement")
    if not isinstance(block, Mapping):
        return None
    expression_key = (
        _stringify_identifier(block.get("emojiId"))
        or _stringify_identifier(block.get("key"))
        or _first_text(block, "faceName", "name")
    )
    if expression_key is None:
        return None
    face_name = _first_text(block, "faceName", "name")
    return ExpressionContent(
        expression_kind=EXPRESSION_KIND_STICKER,
        expression_key=expression_key,
        display_text=face_name or "[贴图]",
        source="qq",
    )


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
