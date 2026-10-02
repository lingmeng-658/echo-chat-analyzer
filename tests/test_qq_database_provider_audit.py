"""Audit regressions for QQ Direct DB acquisition."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from qq_chat_analyzer.providers.qq_database_provider import (
    QQDatabaseProvider,
    QQSession,
)


def _create_group_database_with_blob(path: Path, invalid_blob: object) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            '''
            CREATE TABLE group_msg_table (
                "40001" INTEGER PRIMARY KEY,
                "40027" TEXT NOT NULL,
                "40030" TEXT NOT NULL,
                "40033" TEXT NOT NULL,
                "40050" INTEGER NOT NULL,
                "40800"
            )
            '''
        )
        connection.executemany(
            '''
            INSERT INTO group_msg_table
                ("40001", "40027", "40030", "40033", "40050", "40800")
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                (1, "group-key", "external-group", "sender", 1000, invalid_blob),
                (2, "group-key", "external-group", "sender", 2000, b"valid-blob"),
            ],
        )


@pytest.mark.parametrize("invalid_blob", [None, "sensitive-content", b""])
def test_materialize_session_skips_invalid_40800_rows(
    tmp_path: Path,
    invalid_blob: object,
) -> None:
    """NULL, TEXT, and empty BLOB 40800 values do not abort acquisition."""
    db_path = tmp_path / "invalid-blob.db"
    _create_group_database_with_blob(db_path, invalid_blob)
    session = QQSession(
        internal_key="group-key",
        session_object="external-group",
        display_name="external-group",
        session_type="group",
    )
    payload_path = tmp_path / "payload.json"

    with pytest.warns(RuntimeWarning, match="Skipped QQ DB record with invalid 40800"):
        QQDatabaseProvider(db_path).materialize_session_payload(session, payload_path)

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert [record["record_id"] for record in payload["records"]] == ["2"]
    assert "sensitive-content" not in payload_path.read_text(encoding="utf-8")


def test_materialize_session_rejects_unknown_session_type(tmp_path: Path) -> None:
    """Unknown session types must not be silently routed to the c2c table."""
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path):
        pass
    session = QQSession(
        internal_key="key",
        session_object="object",
        display_name="object",
        session_type="other",
    )

    with pytest.raises(ValueError, match="Unsupported QQ session type: other"):
        QQDatabaseProvider(db_path).materialize_session_payload(
            session,
            tmp_path / "payload.json",
        )


def test_sqlite_failure_logs_privacy_safe_file_and_quick_check_diagnostics(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One failed read identifies the query point and snapshot health."""
    db_path = tmp_path / "snapshot.db"
    db_path.write_bytes(b"fictional-not-a-sqlite-database")
    (tmp_path / "snapshot.db-wal").write_bytes(b"fictional-wal")
    (tmp_path / "snapshot.db-shm").write_bytes(b"fictional-shm")

    with caplog.at_level(
        "WARNING",
        logger="qq_chat_analyzer.desktop.qq_database",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            QQDatabaseProvider(db_path).list_sessions()

    diagnostic = caplog.text
    assert "operation=list_sessions" in diagnostic
    assert "table=group_msg_table" in diagnostic
    assert "stage=query" in diagnostic
    assert "database_name=snapshot.db" in diagnostic
    assert "header_valid=false" in diagnostic
    assert "wal_present=true" in diagnostic
    assert "shm_present=true" in diagnostic
    assert "quick_check=error" in diagnostic
    assert str(tmp_path) not in diagnostic
    assert "fictional-not-a-sqlite-database" not in diagnostic


def test_first_successful_query_logs_snapshot_structure_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A healthy generation leaves a cheap structural baseline before cleanup."""
    db_path = tmp_path / "snapshot.db"
    with sqlite3.connect(db_path) as connection:
        for table_name in ("group_msg_table", "c2c_msg_table"):
            connection.execute(
                f'''CREATE TABLE {table_name} (
                    "40001" INTEGER PRIMARY KEY,
                    "40027" TEXT NOT NULL,
                    "40030" TEXT NOT NULL,
                    "40050" INTEGER NOT NULL
                )'''
            )

    provider = QQDatabaseProvider(db_path)
    with caplog.at_level("INFO", logger="qq_chat_analyzer.desktop.qq_database"):
        assert provider.list_sessions() == []

    records = [
        record.message for record in caplog.records
        if "QQ Direct DB sqlite read succeeded" in record.message
    ]
    assert len(records) == 1
    diagnostic = records[0]
    assert "operation=list_sessions" in diagnostic
    assert "table=group_msg_table" in diagnostic
    assert "database_name=snapshot.db" in diagnostic
    assert "header_valid=true" in diagnostic
    assert "page_size=" in diagnostic
    assert "header_page_count=" in diagnostic
    assert "size_page_aligned=true" in diagnostic
    assert "wal_present=false" in diagnostic
    assert "shm_present=false" in diagnostic
    assert "quick_check=" not in diagnostic
    assert str(tmp_path) not in diagnostic
