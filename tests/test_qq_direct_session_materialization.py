"""RED-GREEN tests: QQ Direct DB session materialization via 40001.

Covers:
- group acquisition via materialize_session_payload
- private acquisition via materialize_session_payload
- same 40027 in group vs private does not cross-contaminate
- time range filtering (start_time, end_time)
- unrelated session not mixed into output
- DB read-only access (mode=ro)
- 40001 used as record_id (source-native message identity)
- qq-db-json format structure validation
"""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import pytest

from qq_chat_analyzer.providers.qq_database_provider import (
    QQDatabaseProvider,
    QQSession,
)


def _create_materialize_db(path: Path) -> None:
    """Create a synthetic DB with group + c2c tables for materialization tests."""
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE group_msg_table (
                row_id    INTEGER PRIMARY KEY,
                "40001"   INTEGER NOT NULL,
                "40027"   TEXT NOT NULL,
                "40030"   TEXT NOT NULL,
                "40033"   TEXT NOT NULL,
                "40050"   INTEGER NOT NULL,
                "40800"   BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE c2c_msg_table (
                row_id    INTEGER PRIMARY KEY,
                "40001"   INTEGER NOT NULL,
                "40027"   TEXT NOT NULL,
                "40030"   TEXT NOT NULL,
                "40033"   TEXT NOT NULL,
                "40050"   INTEGER NOT NULL,
                "40800"   BLOB NOT NULL
            )
            """
        )
        # Group session A: 3 messages
        conn.executemany(
            """
            INSERT INTO group_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1001, "group-key-a", "ext-group-100", "sender-1", 1000, b"blob-a1"),
                (2, 1002, "group-key-a", "ext-group-100", "sender-2", 2000, b"blob-a2"),
                (3, 1003, "group-key-a", "ext-group-100", "sender-3", 3000, b"blob-a3"),
            ],
        )
        # Group session B: 2 messages
        conn.executemany(
            """
            INSERT INTO group_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (4, 2001, "group-key-b", "ext-group-200", "sender-4", 4000, b"blob-b1"),
                (5, 2002, "group-key-b", "ext-group-200", "sender-5", 5000, b"blob-b2"),
            ],
        )
        # Private session X: 2 messages
        conn.executemany(
            """
            INSERT INTO c2c_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 3001, "private-key-x", "ext-uin-1000", "sender-self", 1500, b"blob-x1"),
                (2, 3002, "private-key-x", "ext-uin-1000", "sender-peer", 2500, b"blob-x2"),
            ],
        )
        # Private session Y: 1 message
        conn.execute(
            """
            INSERT INTO c2c_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (3, 4001, "private-key-y", "ext-uin-2000", "sender-peer", 6000, b"blob-y1"),
        )


def _load_payload(path: Path) -> dict:
    """Load and parse a qq-db-json payload file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Test: group acquisition with 40001
# ---------------------------------------------------------------------------

def test_materialize_group_session(tmp_path: Path) -> None:
    """materialize_session_payload on a group session returns correct records with 40001."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "group-a.json"
    result_path = provider.materialize_session_payload(session, output)

    assert result_path == output
    payload = _load_payload(output)
    assert payload["format"] == "qq-db-json"
    assert payload["format_version"] == 0
    assert payload["source"] == "qq"
    assert payload["source_type"] == "qq-db-json"
    assert payload["query"]["requested_session"] == "group-key-a"
    assert payload["query"]["session_type"] == "group"
    assert payload["query"]["time_range"] is None
    assert len(payload["records"]) == 3

    for i, record in enumerate(payload["records"], 1):
        assert record["record_id"] == str(1000 + i)
        assert record["fields"]["40001"] == 1000 + i
        assert record["fields"]["40027"] == "group-key-a"
        assert record["fields"]["40030"] == "ext-group-100"
        assert record["fields"]["40050"] == i * 1000
        assert base64.b64decode(record["message_blob"]).decode("ascii") == f"blob-a{i}"
        assert record["source_meta"]["table"] == "group_msg_table"


# ---------------------------------------------------------------------------
# Test: private acquisition with 40001
# ---------------------------------------------------------------------------

def test_materialize_private_session(tmp_path: Path) -> None:
    """materialize_session_payload on a private session returns correct records with 40001."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="private-key-x",
        session_object="ext-uin-1000",
        display_name="ext-uin-1000",
        session_type="private",
    )
    output = tmp_path / "private-x.json"
    result_path = provider.materialize_session_payload(session, output)

    assert result_path == output
    payload = _load_payload(output)
    assert payload["query"]["session_type"] == "private"
    assert payload["query"]["requested_session"] == "private-key-x"
    assert len(payload["records"]) == 2

    for i, record in enumerate(payload["records"], 1):
        assert record["record_id"] == str(3000 + i)
        assert record["fields"]["40001"] == 3000 + i
        assert record["fields"]["40027"] == "private-key-x"
        assert record["fields"]["40030"] == "ext-uin-1000"
        assert record["source_meta"]["table"] == "c2c_msg_table"


# ---------------------------------------------------------------------------
# Test: same 40027 in group vs private does not cross-contaminate
# ---------------------------------------------------------------------------

def test_same_40027_group_vs_private_no_cross(tmp_path: Path) -> None:
    """Same 40027 value in group and private tables must not mix records."""
    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE group_msg_table (
                row_id    INTEGER PRIMARY KEY,
                "40001"   INTEGER NOT NULL,
                "40027"   TEXT NOT NULL,
                "40030"   TEXT NOT NULL,
                "40033"   TEXT NOT NULL,
                "40050"   INTEGER NOT NULL,
                "40800"   BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE c2c_msg_table (
                row_id    INTEGER PRIMARY KEY,
                "40001"   INTEGER NOT NULL,
                "40027"   TEXT NOT NULL,
                "40030"   TEXT NOT NULL,
                "40033"   TEXT NOT NULL,
                "40050"   INTEGER NOT NULL,
                "40800"   BLOB NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO group_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 5001, "shared-key", "ext-g", "gs", 1000, b"group-blob"),
        )
        conn.execute(
            """
            INSERT INTO c2c_msg_table
                (row_id, "40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 5002, "shared-key", "ext-p", "ps", 2000, b"private-blob"),
        )

    provider = QQDatabaseProvider(db_path)

    group_session = QQSession(
        internal_key="shared-key",
        session_object="ext-g",
        display_name="ext-g",
        session_type="group",
    )
    group_output = tmp_path / "shared-group.json"
    provider.materialize_session_payload(group_session, group_output)
    group_payload = _load_payload(group_output)

    private_session = QQSession(
        internal_key="shared-key",
        session_object="ext-p",
        display_name="ext-p",
        session_type="private",
    )
    private_output = tmp_path / "shared-private.json"
    provider.materialize_session_payload(private_session, private_output)
    private_payload = _load_payload(private_output)

    assert len(group_payload["records"]) == 1
    assert group_payload["records"][0]["record_id"] == "5001"
    assert group_payload["records"][0]["fields"]["40001"] == 5001
    assert group_payload["records"][0]["fields"]["40030"] == "ext-g"
    assert group_payload["records"][0]["source_meta"]["table"] == "group_msg_table"

    assert len(private_payload["records"]) == 1
    assert private_payload["records"][0]["record_id"] == "5002"
    assert private_payload["records"][0]["fields"]["40001"] == 5002
    assert private_payload["records"][0]["fields"]["40030"] == "ext-p"
    assert private_payload["records"][0]["source_meta"]["table"] == "c2c_msg_table"


# ---------------------------------------------------------------------------
# Test: time range filtering
# ---------------------------------------------------------------------------

def test_materialize_with_time_range(tmp_path: Path) -> None:
    """start_time and end_time filter records by 40050 (Unix seconds)."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "group-a-timed.json"
    provider.materialize_session_payload(
        session, output, start_time=1500, end_time=2500,
    )

    payload = _load_payload(output)
    assert payload["query"]["time_range"] == {"start": 1500, "end": 2500}
    assert len(payload["records"]) == 1
    assert payload["records"][0]["fields"]["40050"] == 2000
    assert payload["records"][0]["fields"]["40001"] == 1002


def test_materialize_with_start_time_only(tmp_path: Path) -> None:
    """Only start_time specified: filters >= start_time."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "group-a-start.json"
    provider.materialize_session_payload(
        session, output, start_time=2500,
    )

    payload = _load_payload(output)
    assert payload["query"]["time_range"] == {"start": 2500, "end": None}
    assert len(payload["records"]) == 1
    assert payload["records"][0]["fields"]["40050"] == 3000
    assert payload["records"][0]["fields"]["40001"] == 1003


def test_materialize_with_end_time_only(tmp_path: Path) -> None:
    """Only end_time specified: filters <= end_time."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "group-a-end.json"
    provider.materialize_session_payload(
        session, output, end_time=1500,
    )

    payload = _load_payload(output)
    assert payload["query"]["time_range"] == {"start": None, "end": 1500}
    assert len(payload["records"]) == 1
    assert payload["records"][0]["fields"]["40050"] == 1000
    assert payload["records"][0]["fields"]["40001"] == 1001


# ---------------------------------------------------------------------------
# Test: unrelated session not mixed in
# ---------------------------------------------------------------------------

def test_unrelated_session_not_mixed(tmp_path: Path) -> None:
    """Materializing session A must not return records from session B."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session_a = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "group-a-only.json"
    provider.materialize_session_payload(session_a, output)

    payload = _load_payload(output)
    for record in payload["records"]:
        assert record["fields"]["40027"] == "group-key-a"
        assert record["fields"]["40030"] == "ext-group-100"
        assert record["fields"]["40001"] >= 1001 and record["fields"]["40001"] <= 1003

    session_b = QQSession(
        internal_key="group-key-b",
        session_object="ext-group-200",
        display_name="ext-group-200",
        session_type="group",
    )
    output_b = tmp_path / "group-b-only.json"
    provider.materialize_session_payload(session_b, output_b)

    payload_b = _load_payload(output_b)
    for record in payload_b["records"]:
        assert record["fields"]["40027"] == "group-key-b"
        assert record["fields"]["40030"] == "ext-group-200"
        assert record["fields"]["40001"] >= 2001 and record["fields"]["40001"] <= 2002


# ---------------------------------------------------------------------------
# Test: DB read-only access
# ---------------------------------------------------------------------------

def test_db_read_only_mode(tmp_path: Path) -> None:
    """The provider must open the DB in read-only mode."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    uri = provider._read_only_uri()
    assert "mode=ro" in uri

    with pytest.raises(Exception):
        connection = sqlite3.connect(provider._read_only_uri(), uri=True)
        try:
            connection.execute("CREATE TABLE foo (id INTEGER)")
        finally:
            connection.close()


# ---------------------------------------------------------------------------
# Test: empty session returns empty records
# ---------------------------------------------------------------------------

def test_materialize_nonexistent_session(tmp_path: Path) -> None:
    """Materializing a session key that does not exist returns empty records."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="nonexistent-key",
        session_object="",
        display_name="nonexistent-key",
        session_type="group",
    )
    output = tmp_path / "empty.json"
    result_path = provider.materialize_session_payload(session, output)

    assert result_path == output
    payload = _load_payload(output)
    assert len(payload["records"]) == 0


# ---------------------------------------------------------------------------
# Test: format structure validation
# ---------------------------------------------------------------------------

def test_qq_db_json_format_structure(tmp_path: Path) -> None:
    """The output payload must conform to qq-db-json v0 structure with 40001."""
    db_path = tmp_path / "test.db"
    _create_materialize_db(db_path)
    provider = QQDatabaseProvider(db_path)

    session = QQSession(
        internal_key="group-key-a",
        session_object="ext-group-100",
        display_name="ext-group-100",
        session_type="group",
    )
    output = tmp_path / "format-check.json"
    provider.materialize_session_payload(session, output)

    payload = _load_payload(output)

    assert set(payload.keys()) == {
        "format", "format_version", "source", "source_type", "self", "query", "records",
    }
    assert payload["self"] is None
    assert payload["format"] == "qq-db-json"
    assert payload["format_version"] == 0
    assert payload["source"] == "qq"
    assert payload["source_type"] == "qq-db-json"

    query = payload["query"]
    assert "requested_session" in query
    assert "session_type" in query
    assert "time_range" in query

    record = payload["records"][0]
    assert set(record.keys()) == {
        "record_id", "fields", "message_blob", "blob_encoding", "source_meta",
    }
    assert record["blob_encoding"] == "base64"
    assert set(record["fields"].keys()) == {"40001", "40027", "40030", "40033", "40050"}
    assert set(record["source_meta"].keys()) == {"table"}
    assert isinstance(record["record_id"], str)
    assert isinstance(record["fields"]["40001"], int)
