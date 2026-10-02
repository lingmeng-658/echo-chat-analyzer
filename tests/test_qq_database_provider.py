"""Coverage for the QQ Direct DB Phase 2 raw-payload provider."""

from __future__ import annotations

import base64
import json
import sqlite3

from qq_chat_analyzer.providers.qq_database_provider import QQDatabaseProvider


def _create_synthetic_group_database(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            '''
            CREATE TABLE group_msg_table (
                "40001" INTEGER PRIMARY KEY,
                "40030" TEXT NOT NULL,
                "40033" TEXT NOT NULL,
                "40050" INTEGER NOT NULL,
                "40800" BLOB NOT NULL
            ) WITHOUT ROWID
            '''
        )
        connection.executemany(
            '''
            INSERT INTO group_msg_table
                ("40001", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?)
            ''',
            [
                (101, "fictional-group-a", "fictional-sender-1", 100, b"blob-a"),
                (202, "fictional-group-a", "fictional-sender-2", 200, b"blob-b"),
                (303, "fictional-group-b", "fictional-sender-3", 200, b"blob-c"),
            ],
        )


def test_legacy_group_path_uses_40001_without_row_id_dependency(
    tmp_path,
) -> None:
    database_path = tmp_path / "fictional-qq.db"
    _create_synthetic_group_database(database_path)
    database_before = database_path.read_bytes()
    payload_path = tmp_path / "qq-db-payload.json"

    result_path = QQDatabaseProvider(database_path).materialize_group_payload(
        "fictional-group-a",
        payload_path,
        start_time=150,
        end_time=200,
    )

    assert result_path == payload_path
    assert database_path.read_bytes() == database_before
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["format"] == "qq-db-json"
    assert payload["format_version"] == 0
    assert payload["source"] == "qq"
    assert payload["source_type"] == "qq-db-json"
    assert payload["query"] == {
        "requested_session": "fictional-group-a",
        "session_type": "group",
        "internal_key": None,
        "session_object": "fictional-group-a",
        "time_range": {"start": 150, "end": 200},
    }
    assert payload["records"] == [
        {
            "record_id": "202",
            "fields": {
                "40001": 202,
                "40030": "fictional-group-a",
                "40033": "fictional-sender-2",
                "40050": 200,
            },
            "message_blob": base64.b64encode(b"blob-b").decode("ascii"),
            "blob_encoding": "base64",
            "source_meta": {"table": "group_msg_table"},
        }
    ]
    raw_record = payload["records"][0]
    for forbidden_key in (
        "conversation_id",
        "sender_id",
        "timestamp",
        "message_type",
        "text",
    ):
        assert forbidden_key not in raw_record
        assert forbidden_key not in raw_record["fields"]


def test_provider_omits_time_range_when_not_requested(tmp_path) -> None:
    database_path = tmp_path / "fictional-qq.db"
    _create_synthetic_group_database(database_path)
    payload_path = tmp_path / "qq-db-payload.json"

    QQDatabaseProvider(database_path).materialize_group_payload(
        "fictional-group-a",
        payload_path,
    )

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["query"]["time_range"] is None
    assert [record["record_id"] for record in payload["records"]] == ["101", "202"]
