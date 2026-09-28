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
