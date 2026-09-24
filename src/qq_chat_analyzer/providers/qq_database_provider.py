"""Materialize raw QQ Direct DB records without interpreting message semantics."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from typing import Any


QQ_DB_JSON_FORMAT = "qq-db-json"
_GROUP_MESSAGE_TABLE = "group_msg_table"


class QQDatabaseProvider:
    """Read a supported QQ group-message database into a raw payload v0."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def materialize_group_payload(
        self,
        group_selector: str,
        payload_path: str | Path,
        *,
        start_time: int | float | str | None = None,
        end_time: int | float | str | None = None,
    ) -> Path:
        """Write source-specific group records as a ``qq-db-json`` payload."""
        records = self._read_group_records(group_selector, start_time, end_time)
        output_path = Path(payload_path)
        payload = {
            "format": QQ_DB_JSON_FORMAT,
            "format_version": 0,
            "source": "qq",
            "source_type": QQ_DB_JSON_FORMAT,
            "query": {
                "requested_session": group_selector,
                "time_range": _time_range(start_time, end_time),
            },
            "records": records,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return output_path

    def _read_group_records(
        self,
        group_selector: str,
        start_time: int | float | str | None,
        end_time: int | float | str | None,
    ) -> list[dict[str, Any]]:
        conditions = ['"40030" = ?']
        parameters: list[Any] = [group_selector]
        if start_time is not None:
            conditions.append('"40050" >= ?')
            parameters.append(start_time)
        if end_time is not None:
            conditions.append('"40050" <= ?')
            parameters.append(end_time)

        query = (
            'SELECT row_id, "40030", "40033", "40050", "40800" '
            f'FROM {_GROUP_MESSAGE_TABLE} '
            f"WHERE {' AND '.join(conditions)} "
            "ORDER BY row_id"
        )
        connection = sqlite3.connect(self._read_only_uri(), uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()

        return [_raw_record(row) for row in rows]

    def _read_only_uri(self) -> str:
        return f"{self._database_path.resolve().as_uri()}?mode=ro"


def _raw_record(row: sqlite3.Row) -> dict[str, Any]:
    # These field numbers only describe the feasibility-supported source
    # shape; they are not stable across QQ versions.
    blob = row["40800"]
    if not isinstance(blob, bytes):
        raise ValueError("QQ DB message blob must be bytes")
    return {
        "record_id": str(row["row_id"]),
        "fields": {
            "40030": row["40030"],
            "40033": row["40033"],
            "40050": row["40050"],
        },
        "message_blob": base64.b64encode(blob).decode("ascii"),
        "blob_encoding": "base64",
        "source_meta": {"table": _GROUP_MESSAGE_TABLE},
    }


def _time_range(
    start_time: int | float | str | None,
    end_time: int | float | str | None,
) -> dict[str, int | float | str | None] | None:
    if start_time is None and end_time is None:
        return None
    return {"start": start_time, "end": end_time}
