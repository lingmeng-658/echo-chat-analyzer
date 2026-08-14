"""Read WeChat 4.x databases through the bundled read-only ``wcdb_cli`` helper.

This provider only *acquires* data. It locates the WeChat data directory, runs
the already-built ``wcdb_cli`` executable against ``session.db`` and the right
``message_N.db`` shard, and writes the rows to a JSON document. Turning those
rows into :class:`~qq_chat_analyzer.message.ChatMessage` objects is the job of
``wechat_db_adapter``; orchestration is the job of the application layer.

Schema facts confirmed against a real WeChat 4.x install:

* ``session.db``   -> ``SessionTable.username`` identifies a conversation
* ``md5(username)`` -> the ``Msg_<md5>`` table inside a ``message_N.db`` shard
* ``Msg_<md5>.local_type = 1`` marks a plain text message
* ``Msg_<md5>.real_sender_id`` -> ``Name2Id.rowid`` -> ``user_name``

The database key is only ever held in memory and passed to the helper through
the ``WX_DB_KEY`` environment variable, never written to disk or logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from .wechat_wcdb_diagnostic import maybe_launch_wcdb_diagnostic


DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_SESSION_LIMIT = 200
DEFAULT_MESSAGE_LIMIT = 100000
DB_KEY_ENVIRONMENT_VARIABLE = "WX_DB_KEY"

SESSION_DB_NAME = "session.db"
MESSAGE_DB_GLOB = "message_*.db"
CONTACT_DB_NAME = "contact.db"
WCDB_DLL_NAME = "WCDB.dll"
MESSAGE_AVAILABILITY_REASON = (
    "\u8be5\u4f1a\u8bdd\u6ca1\u6709\u53ef\u5206\u6790\u6d88\u606f"
)

_DB_STORAGE_DIR_NAMES = ("db_storage",)
_SESSION_TABLE = "SessionTable"
_ACCOUNT_DIRECTORY_SUFFIX_PATTERN = re.compile(
    r"^(?P<username>.+)_[0-9a-fA-F]{4,}$"
)
_LOGGER = logging.getLogger(
    "qq_chat_analyzer.providers.wechat_database_provider"
)


class WeChatDatabaseError(Exception):
    """Base error for WeChat database access failures."""

    code = "wechat_database_error"
    public_message = "\u5fae\u4fe1\u6570\u636e\u5e93\u8bfb\u53d6\u5931\u8d25\u3002"

    def __init__(self, public_message: str | None = None) -> None:
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class WcdbHelperNotFound(WeChatDatabaseError):
    """Raised when the ``wcdb_cli`` helper executable is unavailable."""

    code = "wcdb_helper_not_found"
    public_message = (
        "\u672a\u627e\u5230 wcdb_cli \u8f85\u52a9\u7a0b\u5e8f\u3002"
        "\u8bf7\u5148\u6784\u5efa src/qq_chat_analyzer/native/wcdb_cli\u3002"
    )


class WcdbLibraryNotFound(WeChatDatabaseError):
    """Raised when ``WCDB.dll`` cannot be located."""

    code = "wcdb_library_not_found"
    public_message = (
        "\u672a\u627e\u5230 WCDB.dll\u3002"
        "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u5b89\u88c5\uff0c"
        "\u6216\u624b\u52a8\u6307\u5b9a WCDB.dll \u8def\u5f84\u3002"
    )


class DatabaseNotFound(WeChatDatabaseError):
    """Raised when the WeChat data directory or its databases are missing."""

    code = "database_not_found"
    public_message = (
        "\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3002"
        "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u5728\u672c\u673a\u767b\u5f55\u8fc7\uff0c"
        "\u6216\u624b\u52a8\u6307\u5b9a\u6570\u636e\u76ee\u5f55\u3002"
    )


class KeyUnavailable(WeChatDatabaseError):
    """Raised when no database key was supplied."""

    code = "key_unavailable"
    public_message = (
        "\u7f3a\u5c11\u5fae\u4fe1\u6570\u636e\u5e93\u5bc6\u94a5\u3002"
        "\u8bf7\u5148\u83b7\u53d6 DbKey \u540e\u91cd\u8bd5\u3002"
    )


class QueryFailed(WeChatDatabaseError):
    """Raised when the helper could not run a query."""

    code = "query_failed"
    public_message = (
        "\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002"
    )


class SessionNotFound(WeChatDatabaseError):
    """Raised when a session has no message table in any shard."""

    code = "session_not_found"
    public_message = (
        "\u672a\u627e\u5230\u8be5\u804a\u5929\uff0c"
        "\u6216\u6240\u9009\u65f6\u95f4\u8303\u56f4\u5185\u6ca1\u6709\u6d88\u606f\u3002"
    )


@dataclass(frozen=True, slots=True)
class WeChatSession:
    """Privacy-safe descriptor for one WeChat conversation."""

    session_id: str
    display_name: str
    session_type: str = "other"
    message_count: int | None = None
    message_available: bool = True
    unavailable_reason: str | None = None


def message_table_name(username: str) -> str:
    """Return the ``Msg_<md5>`` table name WeChat uses for ``username``."""
    digest = hashlib.md5(username.encode("utf-8")).hexdigest()
    return f"Msg_{digest}"


def default_data_root() -> Path | None:
    """Best-effort guess of the local WeChat 4.x data directory."""
    candidates = [
        Path.home() / "Documents" / "xwechat_files",
        Path.home() / "Documents" / "WeChat Files",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


class WeChatDatabaseProvider:
    """Acquire raw WeChat rows from local databases via ``wcdb_cli``."""

    def __init__(
        self,
        data_root: str | Path | None = None,
        db_key: str | None = None,
        wcdb_cli_path: str | Path | None = None,
        wcdb_dll_path: str | Path | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        runner: Callable[..., Any] | None = None,
        diagnostic_spawner: Callable[..., Any] | None = None,
    ) -> None:
        self._data_root = Path(data_root) if data_root is not None else None
        self._db_key = db_key
        self._wcdb_cli_path = (
            Path(wcdb_cli_path) if wcdb_cli_path is not None else None
        )
        self._wcdb_dll_path = (
            Path(wcdb_dll_path) if wcdb_dll_path is not None else None
        )
        self._timeout = timeout
        self._runner = runner or _run_subprocess
        self._diagnostic_spawner = diagnostic_spawner

    # ---------------------------------------------------------------- listing

    def list_sessions(self, limit: int = DEFAULT_SESSION_LIMIT) -> list[WeChatSession]:
        """List conversations found in ``session.db``."""
        session_db = self._session_db_path()
        self._maybe_launch_wcdb_diagnostic(session_db)
        sql = (
            "SELECT username, summary, last_timestamp "
            f"FROM {_SESSION_TABLE} ORDER BY last_timestamp DESC"
        )
        rows = self._query(
            session_db,
            sql,
            limit=limit,
            query_stage="session_list",
        )
        available_tables = self._message_table_names()
        contact_names = self._contact_display_names()

        sessions: list[WeChatSession] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            username = row.get("username")
            if not isinstance(username, str) or not username.strip():
                continue
            if not _is_conversation_username(username):
                continue
            message_available = message_table_name(username) in available_tables
            sessions.append(
                WeChatSession(
                    session_id=username,
                    display_name=contact_names.get(username) or username,
                    session_type=_session_type(username),
                    message_available=message_available,
                    unavailable_reason=(
                        None
                        if message_available
                        else MESSAGE_AVAILABILITY_REASON
                    ),
                )
            )
        return sessions

    def _maybe_launch_wcdb_diagnostic(self, session_db: Path) -> None:
        """Start the standalone WCDB diagnostic runner when the env gate is on.

        Fire-and-forget and fully isolated: any failure (missing key, missing
        script, subprocess error) is swallowed so the WeChat connection flow
        and its return values are never disturbed. The DbKey is only passed
        through the child environment.
        """
        try:
            key = self._resolve_key()
        except Exception:
            return
        try:
            maybe_launch_wcdb_diagnostic(
                session_db, key, runner=self._diagnostic_spawner
            )
        except Exception:
            _LOGGER.debug("wcdb diagnostic launch skipped", exc_info=True)

    # -------------------------------------------------------------- exporting

    def export_session_json(
        self,
        session_id: str,
        output_path: str | Path,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = DEFAULT_MESSAGE_LIMIT,
    ) -> Path:
        """Write one conversation's raw rows to ``output_path`` as JSON."""
        rows = self.read_session_rows(
            session_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        contact_names = self._contact_display_names()
        resolved_rows: list[Any] = []
        for row in rows:
            if isinstance(row, Mapping):
                merged = dict(row)
                sender_id = row.get("user_name")
                if isinstance(sender_id, str) and sender_id.strip():
                    merged["sender_name"] = (
                        contact_names.get(sender_id.strip())
                        or sender_id.strip()
                    )
                resolved_rows.append(merged)
            else:
                resolved_rows.append(row)
        document = {
            "source": "wechat-db",
            "conversation": {
                "username": session_id,
                "session_type": _session_type(session_id),
                "display_name": (
                    contact_names.get(session_id) or session_id
                ),
            },
            "messages": resolved_rows,
        }
        try:
            self_username = self._resolve_self_username()
        except Exception:
            self_username = None
        if self_username:
            document["conversation"]["self_username"] = self_username
        destination.write_text(
            json.dumps(document, ensure_ascii=False),
            encoding="utf-8",
        )
        return destination

    def read_session_rows(
        self,
        session_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = DEFAULT_MESSAGE_LIMIT,
    ) -> list[Any]:
        """Return raw message rows for one conversation, sender names resolved."""
        cleaned_session = (session_id or "").strip()
        if not cleaned_session:
            raise SessionNotFound()

        table = message_table_name(cleaned_session)
        message_db = self._find_message_db(table)
        conditions = ["(m.local_type & 0xFFFFFFFF) IN (1, 47)"]
        if isinstance(start_time, int) and not isinstance(start_time, bool):
            conditions.append(f"m.create_time >= {start_time}")
        if isinstance(end_time, int) and not isinstance(end_time, bool):
            conditions.append(f"m.create_time <= {end_time}")
        where_clause = " AND ".join(conditions)

        sql = (
            "SELECT m.local_id, m.server_id, m.local_type, m.create_time, "
            "m.message_content, m.WCDB_CT_message_content, n.user_name "
            f"FROM {table} AS m "
            "LEFT JOIN Name2Id AS n ON n.rowid = m.real_sender_id "
            f"WHERE {where_clause} ORDER BY m.create_time ASC"
        )
        return self._query(
            message_db,
            sql,
            limit=limit,
            query_stage="message_rows",
        )

    # --------------------------------------------------------------- internals

    def _query(
        self,
        db_path: Path,
        sql: str,
        limit: int,
        query_stage: str = "query",
    ) -> list[Any]:
        command = [
            str(self._resolve_helper()),
            "--wcdb",
            str(self._resolve_library()),
            "--db",
            str(db_path),
            "--sql",
            sql,
        ]
        if limit > 0:
            command.extend(["--limit", str(limit)])

        environment = dict(os.environ)
        environment[DB_KEY_ENVIRONMENT_VARIABLE] = self._resolve_key()
        database_type = _database_type(db_path)
        _LOGGER.info(
            "[wechat db] query started database_type=%s database_file=%s "
            "database_path=%s query_stage=%s wcdb_stage=invoke",
            database_type,
            db_path.name,
            db_path,
            query_stage,
        )

        try:
            completed = self._runner(command, self._timeout, environment)
        except FileNotFoundError as error:
            _log_query_exception(db_path, query_stage, error)
            raise WcdbHelperNotFound() from error
        except subprocess.TimeoutExpired as error:
            _log_query_exception(db_path, query_stage, error)
            raise QueryFailed(
                "\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u8d85\u65f6\uff0c\u8bf7\u91cd\u8bd5\u3002"
            ) from error
        except Exception as error:
            _log_query_exception(db_path, query_stage, error)
            raise QueryFailed() from error

        stdout = getattr(completed, "stdout", "") or ""
        stderr = _safe_diagnostic_text(
            getattr(completed, "stderr", ""),
            secrets=(environment[DB_KEY_ENVIRONMENT_VARIABLE],),
        )
        returncode = getattr(completed, "returncode", None)
        payload = _parse_result(stdout)
        if payload is None:
            _log_query_failure(
                db_path,
                query_stage,
                wcdb_stage="parse_result",
                returncode=returncode,
                stderr=stderr,
                error_type="QueryFailed",
                helper_error="invalid helper output",
            )
            raise QueryFailed()
        if payload.get("ok") is not True:
            _log_query_failure(
                db_path,
                query_stage,
                wcdb_stage=_safe_stage(payload.get("stage")),
                returncode=returncode,
                stderr=stderr,
                error_type="QueryFailed",
                helper_error=_safe_diagnostic_text(
                    payload.get("error"),
                    secrets=(environment[DB_KEY_ENVIRONMENT_VARIABLE],),
                ),
            )
            raise QueryFailed()

        rows = payload.get("rows")
        return rows if isinstance(rows, list) else []

    def _resolve_key(self) -> str:
        key = self._db_key or os.environ.get(DB_KEY_ENVIRONMENT_VARIABLE)
        if not key or not key.strip():
            raise KeyUnavailable()
        return key.strip()

    def _resolve_helper(self) -> Path:
        if self._wcdb_cli_path is not None:
            if not self._wcdb_cli_path.exists():
                raise WcdbHelperNotFound()
            return self._wcdb_cli_path

        for candidate in _helper_candidates():
            if candidate.exists():
                self._wcdb_cli_path = candidate
                return candidate
        raise WcdbHelperNotFound()

    def _resolve_library(self) -> Path:
        if self._wcdb_dll_path is not None:
            if not self._wcdb_dll_path.exists():
                raise WcdbLibraryNotFound()
            return self._wcdb_dll_path
        raise WcdbLibraryNotFound()

    def _resolve_data_root(self) -> Path:
        root = self._data_root or default_data_root()
        if root is None or not root.is_dir():
            raise DatabaseNotFound()
        return root

    def _resolve_self_username(self) -> str | None:
        """Return the account identity used by WeChat database rows."""
        root = self._resolve_data_root()
        candidates = _account_directory_names(root)
        if len(candidates) != 1:
            return None

        account_directory = candidates[0]
        match = _ACCOUNT_DIRECTORY_SUFFIX_PATTERN.fullmatch(
            account_directory
        )
        if match is None:
            return account_directory

        canonical_username = match.group("username")
        for directory in _iter_db_directories(root):
            contact_db = directory / CONTACT_DB_NAME
            if not contact_db.is_file():
                continue
            try:
                rows = self._query(
                    contact_db,
                    "SELECT username FROM contact",
                    limit=DEFAULT_MESSAGE_LIMIT,
                    query_stage="self_username",
                )
            except WeChatDatabaseError:
                continue
            if any(
                isinstance(row, Mapping)
                and row.get("username") == canonical_username
                for row in rows
            ):
                return canonical_username
        return account_directory

    def _session_db_path(self) -> Path:
        root = self._resolve_data_root()
        for candidate in _iter_db_directories(root):
            session_db = candidate / SESSION_DB_NAME
            if session_db.is_file():
                return session_db
        raise DatabaseNotFound()

    def _find_message_db(self, table: str) -> Path:
        root = self._resolve_data_root()
        shards = [
            shard
            for directory in _iter_db_directories(root)
            for shard in sorted(directory.glob(MESSAGE_DB_GLOB))
        ]
        if not shards:
            raise DatabaseNotFound()

        for shard in shards:
            if self._table_exists(shard, table):
                return shard
        raise SessionNotFound()

    def _table_exists(self, db_path: Path, table: str) -> bool:
        escaped = table.replace("'", "''")
        sql = (
            "SELECT name FROM sqlite_master "
            f"WHERE type = 'table' AND name = '{escaped}'"
        )
        try:
            rows = self._query(
                db_path,
                sql,
                limit=1,
                query_stage="message_table_lookup",
            )
        except WeChatDatabaseError:
            return False
        return bool(rows)

    def _message_table_names(self) -> set[str]:
        """Return every ``Msg_<md5>`` table name found in message shards."""
        root = self._resolve_data_root()
        shards = [
            shard
            for directory in _iter_db_directories(root)
            for shard in sorted(directory.glob(MESSAGE_DB_GLOB))
        ]
        names: set[str] = set()
        for shard in shards:
            try:
                rows = self._query(
                    shard,
                    (
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'table' AND name LIKE 'Msg_%'"
                    ),
                    limit=DEFAULT_MESSAGE_LIMIT,
                    query_stage="message_table_inventory",
                )
            except WeChatDatabaseError:
                continue
            for row in rows:
                if (
                    isinstance(row, Mapping)
                    and isinstance(row.get("name"), str)
                ):
                    names.add(row["name"])
        return names

    def _contact_display_names(self) -> dict[str, str]:
        """Return username -> resolved display name from contact.db."""
        root = self._resolve_data_root()
        names: dict[str, str] = {}
        for directory in _iter_db_directories(root):
            contact_db = directory / CONTACT_DB_NAME
            if not contact_db.is_file():
                continue
            try:
                rows = self._query(
                    contact_db,
                    (
                        "SELECT username, remark, nick_name "
                        "FROM contact"
                    ),
                    limit=DEFAULT_MESSAGE_LIMIT,
                    query_stage="contact_names",
                )
            except WeChatDatabaseError:
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                username = row.get("username")
                if not isinstance(username, str) or not username.strip():
                    continue
                display_name = _first_display_name(
                    row.get("remark"),
                    row.get("nick_name"),
                )
                if display_name:
                    names[username] = display_name
        return names


def _helper_candidates() -> list[Path]:
    package_root = Path(__file__).resolve().parents[1]
    project_root = package_root.parents[1]
    return [
        package_root / "native" / "wcdb_cli" / "wcdb_cli.exe",
        project_root / "build" / "wcdb_cli" / "Release" / "wcdb_cli.exe",
        project_root / "build" / "wcdb_cli" / "Debug" / "wcdb_cli.exe",
    ]


def _iter_db_directories(root: Path) -> list[Path]:
    directories: list[Path] = []
    if (root / SESSION_DB_NAME).is_file() or list(root.glob(MESSAGE_DB_GLOB)):
        directories.append(root)

    for name in _DB_STORAGE_DIR_NAMES:
        for candidate in sorted(root.rglob(name)):
            if candidate.is_dir():
                directories.append(candidate)
                directories.extend(
                    child for child in sorted(candidate.iterdir()) if child.is_dir()
                )
    return directories


def _session_type(username: str) -> str:
    if username.endswith("@chatroom"):
        return "group"
    if username.startswith("gh_"):
        return "official"
    return "private"


def _account_directory_names(root: Path) -> list[str]:
    """Return account-style directory names directly under ``root``."""
    candidates: list[str] = []
    if _is_account_directory_name(root.name):
        candidates.append(root.name)
    try:
        children = sorted(root.iterdir())
    except OSError:
        return candidates
    for child in children:
        if child.is_dir() and _is_account_directory_name(child.name):
            candidates.append(child.name)
    return candidates


def _is_account_directory_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(("wxid_", "wx_"))


def _is_conversation_username(username: str) -> bool:
    """Return whether a session is a real private or group conversation."""
    return username.endswith("@chatroom") or username.startswith(
        ("wxid_", "wx_")
    )


def _first_display_name(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _database_type(path: Path) -> str:
    if path.name == SESSION_DB_NAME:
        return "session"
    if path.name == CONTACT_DB_NAME:
        return "contact"
    if path.match(MESSAGE_DB_GLOB):
        return "message"
    return "unknown"


def _safe_stage(value: Any) -> str:
    text = str(value or "unknown").strip()
    return text[:80] or "unknown"


def _safe_diagnostic_text(
    value: Any,
    limit: int = 2000,
    *,
    secrets: Sequence[str] = (),
) -> str:
    """Normalize native diagnostics without logging commands or environment."""
    text = str(value or "").strip().replace("\r", " ").replace("\n", " | ")
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:limit]


def _log_query_failure(
    db_path: Path,
    query_stage: str,
    *,
    wcdb_stage: str,
    returncode: Any,
    stderr: str,
    error_type: str,
    helper_error: str,
) -> None:
    _LOGGER.error(
        "[wechat db] query failed database_type=%s database_file=%s "
        "database_path=%s query_stage=%s wcdb_stage=%s returncode=%s "
        "stderr=%s error_type=%s helper_error=%s",
        _database_type(db_path),
        db_path.name,
        db_path,
        query_stage,
        wcdb_stage,
        returncode,
        stderr,
        error_type,
        helper_error,
    )


def _log_query_exception(
    db_path: Path,
    query_stage: str,
    error: Exception,
) -> None:
    # Do not attach ``exc_info``: third-party/native exception messages may
    # echo environment values. The exception class is sufficient diagnosis
    # and cannot expose the database key.
    _LOGGER.error(
        "[wechat db] query invocation failed database_type=%s "
        "database_file=%s database_path=%s query_stage=%s "
        "wcdb_stage=invoke original_error_type=%s",
        _database_type(db_path),
        db_path.name,
        db_path,
        query_stage,
        type(error).__name__,
    )


def _parse_result(stdout: str) -> Mapping[str, Any] | None:
    for line in reversed(stdout.strip().splitlines()):
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _run_subprocess(
    command: Sequence[str],
    timeout: int,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess:
    process_options: dict[str, Any] = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(  # noqa: S603 - resolved executable, list form, no shell
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
        env=dict(environment),
        **process_options,
    )
