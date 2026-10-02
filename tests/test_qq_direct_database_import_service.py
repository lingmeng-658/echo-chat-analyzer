"""TDD coverage for the Direct DB QQ acquisition orchestration.

Every database and message in this module is fictional.  The production
service consumes a plaintext snapshot already produced locally by NapCat's
``DatabaseApi.decryptDatabase`` helper; it never receives a passphrase.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from qq_chat_analyzer.application.import_request import ImportRequest
from qq_chat_analyzer.application.import_service import ImportService
from qq_chat_analyzer.application.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
)

from qq_direct_db_testing import FakeSnapshotRuntime


def _encode_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _field(field_number: int, value: bytes) -> bytes:
    return (
        _encode_varint((field_number << 3) | 2)
        + _encode_varint(len(value))
        + value
    )


def _text_message_blob(text: str) -> bytes:
    segment = (
        _encode_varint((45002 << 3) | 0)
        + _encode_varint(1)
        + _field(45101, text.encode("utf-8"))
    )
    return _field(40800, segment)


def _create_plaintext_snapshot(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        for table_name in ("group_msg_table", "c2c_msg_table"):
            connection.execute(
                f'''CREATE TABLE {table_name} (
                    "40001" INTEGER PRIMARY KEY,
                    "40027" TEXT NOT NULL,
                    "40030" TEXT NOT NULL,
                    "40033" TEXT NOT NULL,
                    "40050" INTEGER NOT NULL,
                    "40800" BLOB NOT NULL
                )'''
            )
        connection.execute(
            '''INSERT INTO group_msg_table
                ("40001", "40027", "40030", "40033", "40050", "40800")
                VALUES (?, ?, ?, ?, ?, ?)''',
            (101, "group-partition", "fictional-group", "fictional-group-sender", 1760000001, _text_message_blob("fictional group message")),
        )
        connection.execute(
            '''INSERT INTO c2c_msg_table
                ("40001", "40027", "40030", "40033", "40050", "40800")
                VALUES (?, ?, ?, ?, ?, ?)''',
            (201, "private-partition", "fictional-peer", "fictional-private-sender", 1760000002, _text_message_blob("fictional private message")),
        )


def test_direct_db_acquisition_materializes_group_and_private_through_import_service(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "plaintext-qq.db"
    _create_plaintext_snapshot(snapshot_path)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot_path)
    service = QQDirectDatabaseImportService(runtime_client=runtime)

    sessions = {session.session_type: session for session in service.list_sessions()}

    for session_type, expected_text in (
        ("group", "fictional group message"),
        ("private", "fictional private message"),
    ):
        with service.acquired_session(sessions[session_type].session_id) as acquisition:
            assert acquisition.payload_path.is_file()
            outcome = ImportService().execute(
                ImportRequest(input_path=acquisition.payload_path)
            )

        assert outcome.messages[0].conversation_type == session_type
        assert outcome.messages[0].text == expected_text
