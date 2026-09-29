"""Minimal adapter for the Phase 1 QQ DB JSON payload slice.

This module only interprets an already-materialized raw payload.  It does not
open a QQ database or otherwise acquire source data.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .legacy_projection import project_legacy_messages
from .identity_names import first_identity_name, resolve_member_names
from .message import ChatMessage
from .qq_db_identity import QQ_DB_SELF_NAMESPACE, canonical_qq_uin
from .rich_message import RichMessage, SenderIdentity, TextContent


QQ_DB_JSON_FORMAT = "qq-db-json"
WARNING_QQ_DB_RECORD_SKIPPED = "qq_db_record_skipped"


def is_qq_db_export(path: str | Path) -> bool:
    """Return whether a file is a v0 QQ DB JSON payload."""
    return _is_qq_db_payload(load_qq_db_json(path))


def load_qq_db_json(path: str | Path) -> dict[str, Any] | None:
    """Load an already-materialized QQ DB JSON payload, if valid JSON."""
    try:
        input_path = Path(path)
        with input_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def parse_qq_db_messages(
    payload: Mapping[str, Any] | None,
) -> tuple[list[ChatMessage], tuple[str, ...]]:
    """Project supported QQ DB records for legacy analysis consumers."""
    rich_messages, warnings = parse_qq_db_rich_messages(payload)
    return project_legacy_messages(rich_messages), warnings


def parse_qq_db_rich_messages(
    payload: Mapping[str, Any] | None,
) -> tuple[list[RichMessage], tuple[str, ...]]:
    """Interpret the Phase 1 group-text records into source-neutral facts."""
    if not _is_qq_db_payload(payload):
        return [], ()

    parsed_messages: list[RichMessage] = []
    skipped_record = False
    records = payload["records"]
    session_context = _session_context(payload)
    if session_context is None:
        return [], (WARNING_QQ_DB_RECORD_SKIPPED,) if records else ()
    self_uin = _self_uin(payload)
    for record in records:
        parsed_message = _parse_text_record(record, session_context, self_uin)
        if parsed_message is None:
            skipped_record = True
        else:
            parsed_messages.append(parsed_message)

    warnings = (WARNING_QQ_DB_RECORD_SKIPPED,) if skipped_record else ()
    return parsed_messages, warnings


def _is_qq_db_payload(payload: Mapping[str, Any] | None) -> bool:
    return (
        isinstance(payload, Mapping)
        and payload.get("format") == QQ_DB_JSON_FORMAT
        and payload.get("format_version") == 0
        and payload.get("source") == "qq"
        and payload.get("source_type") == QQ_DB_JSON_FORMAT
        and isinstance(payload.get("records"), list)
    )


def _parse_text_record(
    record: Any,
    session_context: tuple[str, str],
    self_uin: Any,
) -> RichMessage | None:
    if not isinstance(record, Mapping):
        return None
    fields = record.get("fields")
    if not isinstance(fields, Mapping):
        return None

    # These field numbers only describe the feasibility-supported Adapter v0
    # slice; they are not stable across QQ versions.
    sender_id = _stringify_identifier(fields.get("40033"))
    timestamp = fields.get("40050")
    if (
        sender_id is None
        or not isinstance(timestamp, (int, float, str))
        or isinstance(timestamp, bool)
    ):
        return None

    text = _extract_text(record)
    if text is None:
        return None

    conversation_type, conversation_id = session_context
    sender_data = record.get("sender")
    if not isinstance(sender_data, Mapping):
        sender_data = {}
    remark = (
        first_identity_name(sender_data.get("remark"))
        if conversation_type == "private"
        else None
    )
    nickname = first_identity_name(sender_data.get("nickname"), sender_data.get("name"))
    contextual_name = first_identity_name(sender_data.get("groupCard"))
    is_self = _resolve_is_self(fields.get("40033"), self_uin)
    display_name, _, _ = resolve_member_names(
        remark=remark,
        contextual_name=contextual_name,
        nickname=nickname,
        safe_display_fallback=(
            first_identity_name(sender_data.get("displayName"))
            or ("我" if is_self else "未知成员")
        ),
        conversation_kind=conversation_type,
    )
    return RichMessage(
        message_id=_stringify_identifier(record.get("record_id")),
        source="qq",
        source_type=QQ_DB_JSON_FORMAT,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        sender=SenderIdentity(
            identity_id=sender_id,
            display_name=display_name,
            remark=remark,
            nickname=nickname,
            contextual_name=contextual_name,
        ),
        timestamp=timestamp,
        message_type="text",
        contents=(TextContent(text=text),),
        is_self=is_self,
    )


def _self_uin(payload: Mapping[str, Any]) -> Any:
    """Return the payload's bound self value, or ``None`` when absent.

    The namespace must match the Direct DB ``qq_uin`` namespace exactly; a
    mismatched or missing context is treated as unknown rather than guessed.
    """
    self_context = payload.get("self")
    if not isinstance(self_context, Mapping):
        return None
    if self_context.get("namespace") != QQ_DB_SELF_NAMESPACE:
        return None
    return self_context.get("value")


def _resolve_is_self(sender_value: Any, self_uin: Any) -> bool | None:
    """Compare canonical sender (40033) against canonical self identity.

    ``None`` means the source cannot reliably judge the sender; it is never
    collapsed to peer (``False``).  A zero / NULL / invalid sender or an
    unreliable self identity both yield ``None``.
    """
    canonical_sender = canonical_qq_uin(sender_value)
    canonical_self = canonical_qq_uin(self_uin)
    if canonical_sender is None or canonical_self is None:
        return None
    return canonical_sender == canonical_self


def _session_context(payload: Mapping[str, Any]) -> tuple[str, str] | None:
    query = payload.get("query")
    if not isinstance(query, Mapping):
        return None
    session_type = query.get("session_type")
    if session_type not in {"group", "private"}:
        return None
    session_object = _nonzero_identifier(query.get("session_object"))
    if session_object is not None:
        return session_type, session_object
    internal_key = _stringify_identifier(query.get("internal_key"))
    if internal_key is None:
        return None
    return session_type, f"{session_type}:{internal_key}"


def _extract_text(record: Mapping[str, Any]) -> str | None:
    if record.get("blob_encoding") != "base64":
        return None
    blob = record.get("message_blob")
    if not isinstance(blob, str):
        return None
    try:
        decoded = base64.b64decode(blob, validate=True)
    except binascii.Error:
        return None

    # These field numbers only describe the feasibility-supported Adapter v0
    # slice; they are not stable across QQ versions.
    for field_number, wire_type, value in _protobuf_fields(decoded):
        if field_number != 40800 or wire_type != 2:
            continue
        text = _text_from_segment(value)
        if text is not None:
            return text
    return None


def _text_from_segment(segment: bytes) -> str | None:
    message_type: int | None = None
    text_bytes: bytes | None = None
    for field_number, wire_type, value in _protobuf_fields(segment):
        if field_number == 45002 and wire_type == 0:
            message_type = value
        elif field_number == 45101 and wire_type == 2:
            text_bytes = value

    if message_type != 1 or text_bytes is None:
        return None
    try:
        return text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _protobuf_fields(data: bytes) -> tuple[tuple[int, int, int | bytes], ...]:
    fields: list[tuple[int, int, int | bytes]] = []
    offset = 0
    while offset < len(data):
        tag = _read_varint(data, offset)
        if tag is None:
            return ()
        tag_value, offset = tag
        field_number = tag_value >> 3
        wire_type = tag_value & 0x07
        if field_number == 0:
            return ()
        if wire_type == 0:
            value = _read_varint(data, offset)
            if value is None:
                return ()
            scalar, offset = value
            fields.append((field_number, wire_type, scalar))
        elif wire_type == 2:
            length = _read_varint(data, offset)
            if length is None:
                return ()
            size, offset = length
            end = offset + size
            if end > len(data):
                return ()
            fields.append((field_number, wire_type, data[offset:end]))
            offset = end
        else:
            return ()
    return tuple(fields)


def _read_varint(data: bytes, offset: int) -> tuple[int, int] | None:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            return None
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
    return None


def _nonzero_identifier(value: Any) -> str | None:
    identifier = _stringify_identifier(value)
    return identifier if identifier not in {None, "0"} else None


def _stringify_identifier(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None
