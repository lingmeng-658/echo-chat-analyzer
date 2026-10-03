"""Track the QQ processes LCA itself launched.

The bundled QQ runtime is a process tree: Echo starts the NapCat boot launcher, and the launcher starts the injected QQ client.
Only those PIDs belong to LCA; a QQ client the user opened on their own must
never be touched. This registry records exactly the PIDs LCA created so the
application can stop them on exit without scanning or killing unrelated QQ
processes.

Every step logs a privacy-safe summary: the owned PIDs, the taskkill command,
its return code, and a truncated output digest.  Echo's real shutdown left an
owned launcher tree running, and without that record nothing could say whether
the registry was empty or the kill simply failed.
"""

from __future__ import annotations

import locale
import logging
import os
import signal
import subprocess
from typing import Any, Callable


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_process_registry")

#: taskkill output is diagnostic only, so it is collapsed to one line and
#: truncated before it reaches the log.
_MAX_OUTPUT_SUMMARY = 200


class QQProcessRegistry:
    """Record launched PIDs and terminate only them, best-effort."""

    def __init__(
        self,
        terminator: Callable[[int], Any] | None = None,
    ) -> None:
        self._terminator = terminator or _terminate_process_tree
        self._pids: set[int] = set()

    def record(self, pid: int | None) -> None:
        """Remember one PID LCA launched. Invalid values are ignored."""
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return
        self._pids.add(pid)
        _LOGGER.info(
            "QQ owned process recorded pid=%s owned=%s",
            pid,
            len(self._pids),
        )

    def discard(self, pid: int | None) -> None:
        """Forget one PID, e.g. after it was stopped normally."""
        if isinstance(pid, bool) or not isinstance(pid, int):
            return
        self._pids.discard(pid)

    def recorded(self) -> tuple[int, ...]:
        """Return the currently recorded PIDs."""
        return tuple(sorted(self._pids))

    def terminate_all(self) -> int:
        """Terminate every recorded process tree and clear the registry.

        Never raises: a missing process, a permission failure, or a slow
        kill cannot block application shutdown.  A terminator that reports
        ``False``, raises, or times out is counted as failed, so the log can
        tell "no owned PID" apart from "the kill did not work".

        A PID whose termination failed stays recorded.  Ownership has to
        outlive a failed kill: forgetting it would leave the process running
        with nobody accountable for it, and the application-exit hook would
        have nothing left to terminate.
        """
        pids = tuple(sorted(self._pids))
        self._pids.clear()
        _LOGGER.info("QQ runtime termination requested pids=%s", pids)
        failed = 0
        survived: list[int] = []
        for pid in pids:
            _LOGGER.info("QQ runtime terminating pid=%s", pid)
            try:
                result = self._terminator(pid)
            except Exception as error:
                failed += 1
                survived.append(pid)
                _LOGGER.warning(
                    "QQ runtime termination failed pid=%s error=%s",
                    pid,
                    type(error).__name__,
                )
                continue
            if result is False:
                failed += 1
                survived.append(pid)
                _LOGGER.warning("QQ runtime termination failed pid=%s", pid)
        if survived:
            self._pids.update(survived)
        _LOGGER.info(
            "QQ runtime termination finished pids=%s terminated=%s failed=%s "
            "still_owned=%s",
            len(pids),
            len(pids) - failed,
            failed,
            tuple(sorted(self._pids)),
        )
        return len(pids)

    def clear(self) -> None:
        """Forget every recorded PID without terminating anything."""
        self._pids.clear()


def _output_summary(value: Any) -> str:
    """Collapse and truncate captured taskkill output for the log."""
    if isinstance(value, bytes):
        text = value.decode(locale.getpreferredencoding(False), errors="replace")
    else:
        text = value if isinstance(value, str) else ""
    collapsed = " ".join(text.split())
    if len(collapsed) > _MAX_OUTPUT_SUMMARY:
        return collapsed[:_MAX_OUTPUT_SUMMARY] + "..."
    return collapsed


def _terminate_process_tree(pid: int) -> bool:
    """Stop one recorded process and its children, reporting the outcome."""
    command = ["taskkill", "/PID", str(pid), "/T", "/F"]
    if os.name == "nt":
        try:
            completed = subprocess.run(  # noqa: S603 - fixed args, specific PID only
                command,
                capture_output=True,
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            _LOGGER.warning(
                "taskkill did not finish pid=%s command=%s timeout=%s",
                pid,
                command,
                5,
            )
            return False
        except OSError as error:
            _LOGGER.warning(
                "taskkill could not start pid=%s command=%s error=%s",
                pid,
                command,
                type(error).__name__,
            )
            return False
        returncode = getattr(completed, "returncode", None)
        _LOGGER.info(
            "taskkill result pid=%s command=%s returncode=%s stdout=%s stderr=%s",
            pid,
            command,
            returncode,
            _output_summary(getattr(completed, "stdout", "")),
            _output_summary(getattr(completed, "stderr", "")),
        )
        return returncode == 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _LOGGER.info("taskkill skipped pid=%s reason=process_lookup_error", pid)
        return True
    except OSError as error:
        _LOGGER.warning(
            "taskkill failed pid=%s error=%s",
            pid,
            type(error).__name__,
        )
        return False
    return True


_DEFAULT_REGISTRY = QQProcessRegistry()


def default_qq_process_registry() -> QQProcessRegistry:
    """Return the shared registry used by the desktop application."""
    return _DEFAULT_REGISTRY


__all__ = [
    "QQProcessRegistry",
    "default_qq_process_registry",
]
