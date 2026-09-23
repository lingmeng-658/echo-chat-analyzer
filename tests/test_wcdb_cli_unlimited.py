"""Native regression coverage for the wcdb_cli unlimited query contract."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.mark.slow_integration
def test_native_cli_without_positive_limit_returns_more_than_100000_rows(
    tmp_path: Path,
) -> None:
    """No positive --limit must step through the complete SQLite result set."""
    configured_path = os.environ.get("ECHO_NATIVE_WCDB_CLI_PATH")
    if not configured_path:
        pytest.skip("ECHO_NATIVE_WCDB_CLI_PATH is required for the native CLI test")
    native_wcdb_cli_path = Path(configured_path)
    assert native_wcdb_cli_path.is_file()
    wcdb_library_path = native_wcdb_cli_path.with_name("WCDB.dll")
    assert wcdb_library_path.is_file()
    database = tmp_path / "messages.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE message_rows (id INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO message_rows (id) VALUES (?)",
            ((row_id,) for row_id in range(100_001)),
        )

    completed = subprocess.run(
        [
            str(native_wcdb_cli_path),
            "--wcdb",
            str(wcdb_library_path),
            "--no-cipher",
            "--db",
            str(database),
            "--sql",
            "SELECT id FROM message_rows ORDER BY id ASC",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["row_count"] == 100_001
    assert len(result["rows"]) == 100_001
    assert result["truncated"] is False
