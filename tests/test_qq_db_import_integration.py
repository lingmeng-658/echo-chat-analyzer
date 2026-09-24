"""Synthetic end-to-end import coverage for the QQ Direct DB slice."""

from __future__ import annotations

import sqlite3

from qq_chat_analyzer.application.import_request import ImportRequest
from qq_chat_analyzer.application.import_service import ImportService
from qq_chat_analyzer.providers.qq_database_provider import QQDatabaseProvider


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


def test_qq_db_payload_imports_one_fictional_group_text_message(tmp_path) -> None:
    database_path = tmp_path / "fictional-qq.db"
    expected_text = "A fictional direct database message."
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            '''
            CREATE TABLE group_msg_table (
                row_id INTEGER PRIMARY KEY,
                "40030" TEXT NOT NULL,
                "40033" TEXT NOT NULL,
                "40050" INTEGER NOT NULL,
                "40800" BLOB NOT NULL
            )
            '''
        )
        connection.execute(
            '''
            INSERT INTO group_msg_table
                (row_id, "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                1,
                "fictional-group-77",
                "fictional-member-12",
                1760000000,
                _synthetic_text_message_blob(expected_text),
            ),
        )

    payload_path = tmp_path / "fictional-qq-db.json"
    QQDatabaseProvider(database_path).materialize_group_payload(
        "fictional-group-77",
        payload_path,
    )

    outcome = ImportService().execute(
        ImportRequest(input_path=payload_path, platform="qq")
    )

    assert outcome.result.platform == "qq"
    assert outcome.result.format == "qq-db-json"
    assert outcome.processed_message_count == 1
    assert len(outcome.messages) == 1
    assert len(outcome.rich_messages) == 1
    message = outcome.messages[0]
    assert message.conversation_id == "fictional-group-77"
    assert message.sender_id == "fictional-member-12"
    assert message.timestamp == 1760000000
    assert message.conversation_type == "group"
    assert message.text == expected_text
    assert message.platform == "qq"
    assert message.source_type == "qq-db-json"
