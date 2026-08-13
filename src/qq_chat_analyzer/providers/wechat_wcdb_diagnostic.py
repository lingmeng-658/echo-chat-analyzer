"""Echo-side launcher for the standalone WCDB diagnostic runner.

Temporary diagnostic capability. When ``ECHO_WCDB_DIAGNOSTIC=1`` and the
WeChat connection flow knows both the DbKey and the real ``session.db`` path,
Echo starts ``scripts/run_wechat_wcdb_diagnostic.ps1`` as a detached child
process. The runner reuses the bundled ``wcdb_cli.exe`` and writes a redacted
report to ``%LOCALAPPDATA%\\LocalChatAnalyzer\\logs\\wcdb-diagnostic.txt``.

Privacy rules:
- The DbKey is only passed through the child environment variable
  ``ECHO_WX_DB_KEY``; it is never placed on the command line and never logged.
- Failures are swallowed: the diagnostic must never disturb the WeChat
  connection flow or its return values.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from ..resources import bundled_runtime_dir, user_data_dir

DIAGNOSTIC_ENV_VARIABLE = "ECHO_WCDB_DIAGNOSTIC"
KEY_ENVIRONMENT_VARIABLE = "ECHO_WX_DB_KEY"
_RUNNER_RELATIVE_PATH = Path("scripts") / "run_wechat_wcdb_diagnostic.ps1"
_REPORT_RELATIVE_PATH = Path("logs") / "wcdb-diagnostic.txt"
_RUNNER_TIMEOUT_SECONDS = 900

_LOGGER = logging.getLogger("qq_chat_analyzer.providers.wechat_wcdb_diagnostic")


def runner_script_path(echo_dir: Path | None = None) -> Path:
    """Return the diagnostic runner script under the Echo root directory."""
    root = echo_dir if echo_dir is not None else bundled_runtime_dir().parent
    return root / _RUNNER_RELATIVE_PATH


def diagnostic_report_path() -> Path:
    """Return the user-facing diagnostic report location."""
    return user_data_dir() / _REPORT_RELATIVE_PATH


def _default_spawner(command: list[str], environment: dict[str, str]) -> None:
    """Launch PowerShell detached with no console window; never wait."""

    def _run() -> None:
        process_options: dict[str, object] = {}
        if os.name == "nt":
            process_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.run(  # noqa: S603 - fixed executable list, no shell
                list(command),
                env=environment,
                shell=False,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_RUNNER_TIMEOUT_SECONDS,
                **process_options,
            )
        except Exception:
            _LOGGER.debug("wcdb diagnostic runner failed", exc_info=True)

    threading.Thread(target=_run, daemon=True, name="wcdb-diagnostic").start()


def maybe_launch_wcdb_diagnostic(
    session_db: Path,
    db_key: str,
    *,
    echo_dir: Path | None = None,
    runner: Callable[[list[str], dict[str, str]], None] | None = None,
) -> bool:
    """Launch the diagnostic runner when ``ECHO_WCDB_DIAGNOSTIC=1``.

    Returns True when a runner subprocess was started, False when the gate is
    off, the script is missing, or the launch failed. Never raises and never
    logs the DbKey.
    """
    if os.environ.get(DIAGNOSTIC_ENV_VARIABLE) != "1":
        return False

    script = runner_script_path(echo_dir)
    if not script.is_file():
        _LOGGER.debug("wcdb diagnostic runner script missing: %s", script)
        return False

    environment = dict(os.environ)
    environment[KEY_ENVIRONMENT_VARIABLE] = db_key
    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-SessionDb",
        str(session_db),
        "-EchoDir",
        str(echo_dir if echo_dir is not None else bundled_runtime_dir().parent),
        "-ReportPath",
        str(diagnostic_report_path()),
    ]

    launch = runner if runner is not None else _default_spawner
    try:
        launch(command, environment)
    except Exception:
        _LOGGER.debug("wcdb diagnostic runner launch failed", exc_info=True)
        return False
    _LOGGER.debug(
        "wcdb diagnostic runner launched session_db=%s",
        session_db,
    )
    return True