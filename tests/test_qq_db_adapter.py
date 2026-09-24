"""Regression coverage for the QQ DB adapter's Phase 1 text-only slice."""

from __future__ import annotations

import base64
import json

from qq_chat_analyzer.legacy_projection import project_legacy_messages
from qq_chat_analyzer.qq_db_adapter import (
    WARNING_QQ_DB_RECORD_SKIPPED,
    load_qq_db_json,
    parse_qq_db_rich_messages,
)
from qq_chat_analyzer.rich_message import TextContent


def _encode_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _length_delimited_field(field_number: int, value: bytes) -> bytes:
    return (
        _encode_varint((field_number << 3) | 2)
        + _encode_varint(len(value))
        + value
    )


def _synthetic_text_message_blob(text: str) -> bytes:
    segment = (
        _encode_varint((45002 << 3) | 0)
        + _encode_varint(1)
        + _length_delimited_field(45101, text.encode("utf-8"))
    )
    return _length_delimited_field(40800, segment)


def test_qq_db_payload_projects_one_fictional_group_text_record(tmp_path) -> None:
    expected_text = "A fictional QQ group message."
    message_blob = base64.b64encode(
        _synthetic_text_message_blob(expected_text)
    ).decode("ascii")
    payload = {
        "format": "qq-db-json",
        "format_version": 0,
        "source": "qq",
        "source_type": "qq-db-json",
        "query": {"requested_session": "fictional-room-77", "time_range": None},
        "records": [
            {
                "record_id": "fictional-row-001",
                "fields": {
                    "40030": "fictional-room-77",
                    "40033": "fictional-member-12",
                    "40050": 1760000000,
                },
                "message_blob": message_blob,
                "blob_encoding": "base64",
            }
        ],
    }
    payload_path = tmp_path / "fictional-qq-db.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded_payload = load_qq_db_json(payload_path)
    rich_messages, warnings = parse_qq_db_rich_messages(loaded_payload)

    assert warnings == ()
    assert len(rich_messages) == 1
    rich = rich_messages[0]
    assert rich.conversation_id == "fictional-room-77"
    assert rich.sender.identity_id == "fictional-member-12"
    assert rich.timestamp == 1760000000
    assert rich.conversation_type == "group"
    assert rich.contents == (TextContent(text=expected_text),)
    assert rich.source == "qq"
    assert rich.source_type == "qq-db-json"

    chat = project_legacy_messages(rich_messages)[0]
    assert chat.platform == "qq"
    assert chat.source_type == "qq-db-json"
    assert chat.text == expected_text


def test_qq_db_adapter_skips_uninterpretable_record_with_stable_warning() -> None:
    payload = {
        "format": "qq-db-json",
        "format_version": 0,
        "source": "qq",
        "source_type": "qq-db-json",
        "query": {"requested_session": "fictional-room-77", "time_range": None},
        "records": [
            {
                "record_id": "fictional-row-unreadable",
                "fields": {"40030": "fictional-room-77"},
                "message_blob": "not-base64",
                "blob_encoding": "base64",
            }
        ],
    }

    rich_messages, warnings = parse_qq_db_rich_messages(payload)

    assert rich_messages == []
    assert warnings == (WARNING_QQ_DB_RECORD_SKIPPED,)
