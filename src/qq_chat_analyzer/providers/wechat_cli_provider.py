"""Invoke the optional CipherTalk CLI (``miyu``) as a WeChat data source.

This module only shells out to an externally installed ``miyu`` binary. It does
not read WeChat databases, extract keys, or reimplement any CipherTalk logic.

Command surface used (confirmed against CipherTalk-CLI 0.1.x):

* ``miyu --format json --quiet status`` - probe config and DB connectivity
* ``miyu --format json --quiet sessions --limit N`` - list sessions
* ``miyu export <sessionId> --output <file>.json`` - write a bare JSON array

Successful command results arrive on stdout as ``{"ok": true, "data": ...}``;
failures arrive on stderr as ``{"ok": false, "error": {"code", "message"}}``.
``export`` only returns ``{"path", "count"}``; chat content must be read from
the output file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import wechat_cli_adapter
from ..message import ChatMessage


CLI_EXECUTABLE = "miyu"
DEFAULT_SESSION_LIMIT = 200
DEFAULT_TIMEOUT_SECONDS = 120
KEY_TIMEOUT_SECONDS = 90

_JSON_FLAGS = ("--format", "json", "--quiet")


class WeChatCliError(Exception):
    """Base error for CipherTalk CLI integration failures."""

    code = "wechat_cli_error"
    public_message = "The WeChat CLI operation failed."

    def __init__(self, public_message: str | None = None) -> None:
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class CliNotInstalled(WeChatCliError):
    """Raised when the ``miyu`` executable cannot be found."""

    code = "cli_not_installed"
    public_message = (
        "\u672a\u627e\u5230 CipherTalk \u547d\u4ee4\u884c\u5de5\u5177\u3002"
        "\u8bf7\u5148\u5b89\u88c5\uff1anpm install -g ciphertalk-cli"
    )


class WeChatNotRunning(WeChatCliError):
    """Raised when WeChat must be running but is not."""

    code = "wechat_not_running"
    public_message = (
        "\u8bf7\u5148\u6253\u5f00\u5e76\u767b\u5f55\u5fae\u4fe1\uff0c"
        "\u7136\u540e\u91cd\u8bd5\u3002"
    )


class DatabaseNotFound(WeChatCliError):
    """Raised when no local WeChat data directory is configured or found."""

    code = "database_not_found"
    public_message = (
        "\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3002"
        "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u5728\u672c\u673a\u767b\u5f55\u8fc7\uff0c"
        "\u6216\u624b\u52a8\u6307\u5b9a\u6570\u636e\u76ee\u5f55\u3002"
    )


class KeyUnavailable(WeChatCliError):
    """Raised when the database access key cannot be obtained."""

    code = "key_unavailable"
    public_message = (
        "\u65e0\u6cd5\u83b7\u53d6\u5fae\u4fe1\u6570\u636e\u8bbf\u95ee\u51ed\u636e\u3002"
        "\u8bf7\u4fdd\u6301\u5fae\u4fe1\u767b\u5f55\u72b6\u6001\uff0c"
        "\u5e76\u5c1d\u8bd5\u4ee5\u7ba1\u7406\u5458\u8eab\u4efd\u8fd0\u884c\u3002"
    )


class SessionNotFound(WeChatCliError):
    """Raised when the requested session yields no messages."""

    code = "session_not_found"
    public_message = (
        "\u672a\u627e\u5230\u8be5\u804a\u5929\uff0c"
        "\u6216\u6240\u9009\u65f6\u95f4\u8303\u56f4\u5185\u6ca1\u6709\u6d88\u606f\u3002"
    )


class ExportFailed(WeChatCliError):
    """Raised when the export command fails for any other reason."""

    code = "export_failed"
    public_message = (
        "\u5bfc\u51fa\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55\u5931\u8d25\uff0c"
        "\u8bf7\u91cd\u8bd5\u3002"
    )


@dataclass(frozen=True, slots=True)
class CliStatus:
    """Privacy-safe snapshot of ``miyu status``."""

    available: bool
    configured: bool
    connected: bool
    database_files: int = 0
    session_count: int | None = None


@dataclass(frozen=True, slots=True)
class CliSession:
    """Privacy-safe session descriptor from ``miyu sessions``."""

    session_id: str
    display_name: str
    session_type: str
    message_count: int | None = None


def is_available() -> bool:
    """Return whether the ``miyu`` executable is on PATH."""
    return shutil.which(CLI_EXECUTABLE) is not None


class WeChatCliProvider:
    """Read WeChat chat data through an external CipherTalk CLI install."""

    def __init__(
        self,
        executable: str = CLI_EXECUTABLE,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        runner: Any | None = None,
    ) -> None:
        self._executable = executable
        self._timeout = timeout
        self._runner = runner or _run_subprocess

    # ---------------------------------------------------------------- probing

    def get_status(self) -> CliStatus:
        """Probe CLI availability, configuration, and DB connectivity."""
        if not self._resolve_executable():
            return CliStatus(available=False, configured=False, connected=False)

        try:
            data = self._run_json(["status"])
        except WeChatCliError:
            return CliStatus(available=True, configured=False, connected=False)

        if not isinstance(data, Mapping):
            return CliStatus(available=True, configured=False, connected=False)

        connection = data.get("connection")
        connected = bool(
            isinstance(connection, Mapping) and connection.get("ok") is True
        )
        session_count = None
        if isinstance(connection, Mapping):
            raw_count = connection.get("sessionCount")
            if isinstance(raw_count, int) and not isinstance(raw_count, bool):
                session_count = raw_count

        database_files = data.get("databaseFiles")
        if not isinstance(database_files, int) or isinstance(database_files, bool):
            database_files = 0

        return CliStatus(
            available=True,
            configured=bool(data.get("configured")),
            connected=connected,
            database_files=database_files,
            session_count=session_count,
        )

    def list_sessions(self, limit: int = DEFAULT_SESSION_LIMIT) -> list[CliSession]:
        """List available chat sessions."""
        data = self._run_json(["sessions", "--limit", str(limit)])
        rows = _extract_rows(data, "sessions")

        sessions: list[CliSession] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            session_id = row.get("sessionId")
            if not isinstance(session_id, str) or not session_id.strip():
                continue
            display_name = row.get("displayName")
            message_count = row.get("messageCount")
            sessions.append(
                CliSession(
                    session_id=session_id,
                    display_name=(
                        display_name
                        if isinstance(display_name, str) and display_name.strip()
                        else session_id
                    ),
                    session_type=(
                        row.get("type")
                        if isinstance(row.get("type"), str)
                        else "other"
                    ),
                    message_count=(
                        message_count
                        if isinstance(message_count, int)
                        and not isinstance(message_count, bool)
                        else None
                    ),
                )
            )
        return sessions

    def acquire_key(self) -> bool:
        """Ask the CLI to extract and persist the database key.

        Requires a running, logged-in WeChat client.
        """
        self._run_json(
            ["key", "get", "--save"],
            timeout=KEY_TIMEOUT_SECONDS,
            json_flags=False,
        )
        return True

    # --------------------------------------------------------------- exporting

    def export_session(
        self,
        session_id: str,
        output_path: Path,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """Export one session to ``output_path`` and return the message count."""
        arguments = ["export", session_id, "--output", str(output_path)]
        if date_from:
            arguments.extend(["--from", date_from])
        if date_to:
            arguments.extend(["--to", date_to])

        data = self._run_json(arguments, json_flags=False)
        count = data.get("count") if isinstance(data, Mapping) else None
        if isinstance(count, int) and not isinstance(count, bool):
            return count
        return 0

    def load_session_messages(
        self,
        session_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[ChatMessage, ...]:
        """Export one session to a temp file and parse it into ChatMessage."""
        with tempfile.TemporaryDirectory(prefix="wechat-cli-") as temp_dir:
            output_path = Path(temp_dir) / "session.json"
            count = self.export_session(
                session_id,
                output_path,
                date_from=date_from,
                date_to=date_to,
            )
            if count == 0 and not output_path.exists():
                raise SessionNotFound()
            raw_rows = wechat_cli_adapter.load_messages(output_path)
            return tuple(wechat_cli_adapter.parse_messages(raw_rows))

    # ---------------------------------------------------------------- internals

    def _resolve_executable(self) -> str | None:
        return shutil.which(self._executable)

    def _run_json(
        self,
        arguments: Sequence[str],
        timeout: int | None = None,
        json_flags: bool = True,
    ) -> Any:
        executable = self._resolve_executable()
        if executable is None:
            raise CliNotInstalled()

        command = [executable]
        if json_flags:
            command.extend(_JSON_FLAGS)
        else:
            command.extend(("--format", "json"))
        command.extend(arguments)

        try:
            completed = self._runner(command, timeout or self._timeout)
        except FileNotFoundError as error:
            raise CliNotInstalled() from error
        except subprocess.TimeoutExpired as error:
            raise ExportFailed(
                "\u5fae\u4fe1\u6570\u636e\u8bfb\u53d6\u8d85\u65f6\uff0c"
                "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u767b\u5f55\u540e\u91cd\u8bd5\u3002"
            ) from error

        envelope = _parse_envelope(completed.stdout, completed.stderr)
        if envelope is None:
            raise _classify_failure(None, completed.stderr or completed.stdout)

        if envelope.get("ok") is True:
            return envelope.get("data")

        error_block = envelope.get("error")
        if isinstance(error_block, Mapping):
            raise _classify_failure(
                error_block.get("code"),
                str(error_block.get("message") or ""),
            )
        raise ExportFailed()


def _run_subprocess(command: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed executable, list form, no shell
        list(command),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def _parse_envelope(stdout: str | None, stderr: str | None) -> Mapping[str, Any] | None:
    for stream in (stdout, stderr):
        if not stream:
            continue
        payload = _first_json_object(stream)
        if payload is not None:
            return payload
    return None


def _first_json_object(stream: str) -> Mapping[str, Any] | None:
    text = stream.strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, Mapping):
        return payload

    # Tolerate leading progress or banner lines around the JSON envelope.
    start = text.find("{")
    while start != -1:
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(payload, Mapping):
            return payload
        start = text.find("{", start + 1)
    return None


def _extract_rows(data: Any, key: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, Mapping):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def _classify_failure(code: Any, message: str) -> WeChatCliError:
    """Map CLI error codes and messages onto user-facing errors."""
    normalized = (message or "").lower()
    code_text = code if isinstance(code, str) else ""

    if "weixin.exe" in normalized or "process_not_found" in normalized:
        return WeChatNotRunning()
    if "\u5fae\u4fe1" in (message or "") and (
        "\u672a\u8fd0\u884c" in (message or "")
        or "\u767b\u5f55" in (message or "")
    ):
        return WeChatNotRunning()
    if any(
        token in normalized
        for token in ("hook", "attach_failed", "scan_failed", "\u5bc6\u94a5")
    ):
        return KeyUnavailable()
    if code_text == "CONFIG_MISSING":
        return DatabaseNotFound()
    if code_text == "DB_ERROR":
        return DatabaseNotFound()
    if code_text == "INVALID_ARGUMENT":
        return SessionNotFound()
    if code_text == "NOT_IMPLEMENTED":
        return ExportFailed(
            "\u5f53\u524d\u4ec5\u652f\u6301\u6587\u5b57\u804a\u5929\u8bb0\u5f55\u5bfc\u51fa\u3002"
        )
    return ExportFailed()
