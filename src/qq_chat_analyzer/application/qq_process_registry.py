"""Track the QQ processes LCA itself launched.

The bundled QQ runtime is a process tree: LCA starts the QCE API server and
the NapCat boot launcher, and the launcher starts the injected QQ client.
Only those PIDs belong to LCA; a QQ client the user opened on their own must
never be touched. This registry records exactly the PIDs LCA created so the
application can stop them on exit without scanning or killing unrelated QQ
processes.
"""

from __future__ import annotations

import os
import signal
import subprocess
from typing import Callable


class QQProcessRegistry:
    """Record launched PIDs and terminate only them, best-effort."""

    def __init__(
        self,
        terminator: Callable[[int], None] | None = None,
    ) -> None:
        self._terminator = terminator or _terminate_process_tree
        self._pids: set[int] = set()

    def record(self, pid: int | None) -> None:
        """Remember one PID LCA launched. Invalid values are ignored."""
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return
        self._pids.add(pid)

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
        kill cannot block application shutdown.
        """
        pids = tuple(sorted(self._pids))
        self._pids.clear()
        for pid in pids:
            try:
                self._terminator(pid)
            except Exception:
                continue
        return len(pids)

    def clear(self) -> None:
        """Forget every recorded PID without terminating anything."""
        self._pids.clear()


def _terminate_process_tree(pid: int) -> None:
    """Stop one recorded process and its children."""
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - fixed args, specific PID only
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


_DEFAULT_REGISTRY = QQProcessRegistry()


def default_qq_process_registry() -> QQProcessRegistry:
    """Return the shared registry used by the desktop application."""
    return _DEFAULT_REGISTRY


__all__ = [
    "QQProcessRegistry",
    "default_qq_process_registry",
]
