"""Materialize raw QQ Direct DB records without interpreting message semantics."""

from __future__ import annotations

import base64
import json
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..qq_db_identity import QQ_DB_SELF_NAMESPACE, canonical_qq_uin


QQ_DB_JSON_FORMAT = "qq-db-json"
_GROUP_MESSAGE_TABLE = "group_msg_table"
_C2C_MESSAGE_TABLE = "c2c_msg_table"
_PARTITION_KEY_FIELD = "40027"
_SESSION_OBJECT_FIELD = "40030"
_TIMESTAMP_FIELD = "40050"


@dataclass(frozen=True, slots=True)
class QQSession:
    """Privacy-safe descriptor for one QQ conversation discovered from the DB.

    The session is identified by the local partition key (column `40027`),
    not by the external session object identifier (column `40030`).
    This means a single logical session may carry different external
    identifiers across QQ versions or after account migration.

    Fields:
    - `internal_key`   -> column `40027` (local session partition key)
    - `session_object` -> column `40030` (external/session object ID)
    - `display_name`   -> best-effort label; falls back to `session_object`
    - `session_type`   -> `"group"` or `"private"`
    - `message_count`  -> total rows for this partition key
    - `last_message_time` -> max `40050` (Unix seconds)
    """

    internal_key: str
    session_object: str
    display_name: str
    session_type: str = "other"
    message_count: int | None = None
    last_message_time: int | None = None

    @property
    def session_id(self) -> str:
        """Return the selection identifier scoped by the QQ session type."""
        return f"{self.session_type}:{self.internal_key}"

class QQDatabaseProvider:
    """Read a supported QQ group-message database into a raw payload v0."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def list_sessions(self) -> list[QQSession]:
        """Return all conversations (groups + private) in the database."""
        groups = self._discover_sessions_from_table(_GROUP_MESSAGE_TABLE, "group")
        c2c = self._discover_sessions_from_table(_C2C_MESSAGE_TABLE, "private")
        return groups + c2c

    def _discover_sessions_from_table(
        self,
        table_name: str,
        session_type: str,
    ) -> list[QQSession]:
        """Query one message table and return per-session aggregates."""
        query = (
            f'SELECT "{_PARTITION_KEY_FIELD}" AS internal_key, '
            f'MAX(CASE WHEN TRIM(CAST("{_SESSION_OBJECT_FIELD}" AS TEXT)) '
            f"NOT IN ('', '0') THEN \"{_SESSION_OBJECT_FIELD}\" END) "
            f'AS session_object, '
            f'COUNT(*) AS message_count, '
            f'MAX("40050") AS last_message_time '
            f'FROM "{table_name}" '
            f'GROUP BY "{_PARTITION_KEY_FIELD}" '
            f'ORDER BY last_message_time DESC'
        )
        connection = sqlite3.connect(self._read_only_uri(), uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(query).fetchall()
        finally:
            connection.close()

        sessions: list[QQSession] = []
        for row in rows:
            internal_key_raw = row["internal_key"]
            internal_key = str(internal_key_raw) if internal_key_raw is not None else ""
            if not internal_key.strip():
                continue
            session_object = _nonzero_identifier(row["session_object"]) or ""
            display_name = session_object if session_object.strip() else internal_key
            sessions.append(
                QQSession(
                    internal_key=internal_key,
                    session_object=session_object,
                    display_name=display_name,
                    session_type=session_type,
                    message_count=row["message_count"],
                    last_message_time=row["last_message_time"],
                )
            )
        return sessions

    def materialize_group_payload(
        self,
        group_selector: str,
        payload_path: str | Path,
        *,
        start_time: int | float | str | None = None,
        end_time: int | float | str | None = None,
        self_uin: str | None = None,
    ) -> Path:
        """Write source-specific group records as a ``qq-db-json`` payload."""
        records = self._read_group_records(group_selector, start_time, end_time)
        output_path = Path(payload_path)
        payload = {
            "format": QQ_DB_JSON_FORMAT,
            "format_version": 0,
            "source": "qq",
            "source_type": QQ_DB_JSON_FORMAT,
            "self": _self_context(self_uin),
            "query": {
                "requested_session": group_selector,
                "session_type": "group",
                "internal_key": None,
                "session_object": _nonzero_identifier(group_selector),
                "time_range": _time_range(start_time, end_time),
            },
            "records": records,
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return output_path

    def materialize_session_payload(
        self,
        session: QQSession,
        payload_path: str | Path,
        *,
        start_time: int | float | str | None = None,
        end_time: int | float | str | None = None,
        self_uin: str | None = None,
    ) -> Path:
        """Write source-specific records for one session as a qq-db-json payload.

        Uses the session internal_key (column 40027) as the query
        predicate, and routes to the correct table based on session_type.

        ``self_uin`` is the acquisition-time self identity bound to the same
        plaintext snapshot (``core.selfInfo.uin``), or ``None`` when unknown.
        It is passed through verbatim as source metadata; the adapter decides
        how to use it.

        Output is raw / source-specific: no sender/conversation/text
        interpretation is performed here.
        """
        if session.session_type == "group":
            table_name = _GROUP_MESSAGE_TABLE
        elif session.session_type == "private":
            table_name = _C2C_MESSAGE_TABLE
        else:
            raise ValueError(f"Unsupported QQ session type: {session.session_type}")
        records = self._read_session_records(session, table_name, start_time, end_time)
        output_path = Path(payload_path)
        payload = {
            "format": QQ_DB_JSON_FORMAT,
            "format_version": 0,
            "source": "qq",
            "source_type": QQ_DB_JSON_FORMAT,
            "self": _self_context(self_uin),
            "query": {
                "requested_session": session.internal_key,
                "session_type": session.session_type,
                "internal_key": session.internal_key,
                "session_object": _nonzero_identifier(session.session_object),
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
            'SELECT "40001", "40030", "40033", "40050", "40800" '
            f'FROM {_GROUP_MESSAGE_TABLE} '
            f"WHERE {' AND '.join(conditions)} "
            'ORDER BY "40001"'
        )
        connection = sqlite3.connect(self._read_only_uri(), uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()

        records = []
        for row in rows:
            record = _raw_record(row)
            if record is not None:
                records.append(record)
        return records

    def _read_session_records(
        self,
        session: QQSession,
        table_name: str,
        start_time: int | float | str | None,
        end_time: int | float | str | None,
    ) -> list[dict[str, Any]]:
        """Query one table by the session internal_key (40027)."""
        conditions = ['"40027" = ?']
        parameters: list[Any] = [session.internal_key]
        if start_time is not None:
            conditions.append('"40050" >= ?')
            parameters.append(start_time)
        if end_time is not None:
            conditions.append('"40050" <= ?')
            parameters.append(end_time)

        query = (
            'SELECT "40001", "40027", "40030", "40033", "40050", "40800" '
            f'FROM "{table_name}" '
            f"WHERE {' AND '.join(conditions)} "
            'ORDER BY "40001"'
        )
        connection = sqlite3.connect(self._read_only_uri(), uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(query, parameters).fetchall()
        finally:
            connection.close()

        records = []
        for row in rows:
            record = _session_record(row, table_name)
            if record is not None:
                records.append(record)
        return records

    def _read_only_uri(self) -> str:
        return f"{self._database_path.resolve().as_uri()}?mode=ro"


def _nonzero_identifier(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    identifier = str(value).strip()
    return identifier if identifier and identifier != "0" else None


def _raw_record(row: sqlite3.Row) -> dict[str, Any] | None:
    # These field numbers only describe the feasibility-supported source
    # shape; they are not stable across QQ versions.
    blob = _message_blob_or_warn(row)
    if blob is None:
        return None
    return {
        "record_id": str(row["40001"]),
        "fields": {
            "40030": row["40030"],
            "40033": row["40033"],
            "40001": row["40001"],
            "40050": row["40050"],
        },
        "message_blob": base64.b64encode(blob).decode("ascii"),
        "blob_encoding": "base64",
        "source_meta": {"table": _GROUP_MESSAGE_TABLE},
    }


def _session_record(row: sqlite3.Row, table_name: str) -> dict[str, Any] | None:
    """Build a raw session record dict (no semantic interpretation).

    Uses column 40001 (source-native message unique ID) as record_id.
    """
    blob = _message_blob_or_warn(row)
    if blob is None:
        return None
    return {
        "record_id": str(row["40001"]),
        "fields": {
            "40001": row["40001"],
            "40027": row["40027"],
            "40030": row["40030"],
            "40033": row["40033"],
            "40050": row["40050"],
        },
        "message_blob": base64.b64encode(blob).decode("ascii"),
        "blob_encoding": "base64",
        "source_meta": {"table": table_name},
    }


def _time_range(
    start_time: int | float | str | None,
    end_time: int | float | str | None,
) -> dict[str, int | float | str | None] | None:
    if start_time is None and end_time is None:
        return None
    return {"start": start_time, "end": end_time}


def _self_context(self_uin: str | None) -> dict[str, str] | None:
    """Return the payload ``self`` context, or ``None`` when unreliable.

    The provider canonicalizes the incoming self value so an invalid/zero
    value never reaches the adapter as a real identity.  The resulting
    structure carries the namespace and canonical value explicitly.
    """
    canonical = canonical_qq_uin(self_uin)
    if canonical is None:
        return None
    return {"namespace": QQ_DB_SELF_NAMESPACE, "value": canonical}

def _message_blob_or_warn(row: sqlite3.Row) -> bytes | None:
    """Return a usable raw blob without exposing malformed data."""
    blob = row["40800"]
    if isinstance(blob, bytes) and blob:
        return blob
    warnings.warn(
        "Skipped QQ DB record with invalid 40800.",
        RuntimeWarning,
        stacklevel=2,
    )
    return None
