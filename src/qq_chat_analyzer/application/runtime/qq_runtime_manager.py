"""Manage an externally installed QQ runtime without touching its internals.

The manager is deliberately thin. It tracks lifecycle state, delegates
process control to a :class:`~qq_chat_analyzer.runtime.ChatRuntime`
implementation, and turns
every runtime failure into a user-facing :class:`QQRuntimeStatus`. It never
parses the external tool's output, never writes to its install directory, and
never communicates with its HTTP API; those remain Provider and runtime
responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from qq_chat_analyzer.runtime import ChatRuntime, RuntimeInfo


MESSAGE_UNAVAILABLE = (
    "\u672a\u627e\u5230 QQ \u8fd0\u884c\u73af\u5883\uff0c\u65e0\u6cd5\u542f\u52a8\u3002"
)
MESSAGE_STOPPED = "QQ \u8fd0\u884c\u73af\u5883\u5df2\u505c\u6b62\u3002"
MESSAGE_STARTING = "\u6b63\u5728\u542f\u52a8 QQ \u8fd0\u884c\u73af\u5883..."
MESSAGE_RUNNING = "QQ \u8fd0\u884c\u73af\u5883\u5df2\u542f\u52a8\u3002"
MESSAGE_STOPPING = "\u6b63\u5728\u505c\u6b62 QQ \u8fd0\u884c\u73af\u5883..."
MESSAGE_ERROR = "\u64cd\u4f5c\u5931\u8d25\uff0c\u65e0\u6cd5\u5b8c\u6210\u6240\u9700\u52a8\u4f5c\u3002"
MESSAGE_NOT_READY = (
    "\u8fd0\u884c\u73af\u5883\u5df2\u542f\u52a8\uff0c"
    "\u4f46\u670d\u52a1\u5c1a\u672a\u5c31\u7eea\u3002"
)

ACTION_HINT_INSTALL = "\u8bf7\u5148\u5b89\u88c5\u5305\u542b QQ \u8fd0\u884c\u73af\u5883\u7684\u7248\u672c\u3002"
ACTION_HINT_RETRY = "\u8bf7\u786e\u8ba4\u8fd0\u884c\u73af\u5883\u540e\u91cd\u8bd5\u3002"


class QQRuntimeState(str, Enum):
    """User-facing lifecycle state of the QQ runtime."""

    UNAVAILABLE = "unavailable"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class QQRuntimeStatus:
    """User-facing snapshot of the QQ runtime lifecycle."""

    state: QQRuntimeState
    available: bool
    pid: int | None = None
    version: str | None = None
    message: str = ""
    action_hint: str = ""


class QQRuntimeManager:
    """Detect, start, stop and report an externally managed QQ runtime."""

    def __init__(
        self,
        runtime: ChatRuntime,
        ready_timeout: float = 30.0,
    ) -> None:
        self._runtime = runtime
        self._ready_timeout = ready_timeout
        self._state = (
            QQRuntimeState.STOPPED
            if runtime.is_installed()
            else QQRuntimeState.UNAVAILABLE
        )
        self._pid: int | None = None
        self._version: str | None = None

    def is_available(self) -> bool:
        """Return whether a usable runtime is present on this machine."""
        return self._runtime.is_installed()

    def start(self) -> QQRuntimeStatus:
        """Start the runtime and return the resulting status."""
        if not self.is_available():
            return self._status(
                QQRuntimeState.UNAVAILABLE,
                message=MESSAGE_UNAVAILABLE,
                action_hint=ACTION_HINT_INSTALL,
            )

        self._state = QQRuntimeState.STARTING
        try:
            info = self._runtime.start()
        except Exception as error:
            self._state = QQRuntimeState.ERROR
            return self._status(
                QQRuntimeState.ERROR,
                message=_runtime_error_message(error, MESSAGE_ERROR),
                action_hint=ACTION_HINT_RETRY,
            )

        try:
            self._runtime.wait_ready(timeout=self._ready_timeout)
        except Exception as error:
            self._stop_after_failed_start()
            self._state = QQRuntimeState.ERROR
            return self._status(
                QQRuntimeState.ERROR,
                message=_runtime_error_message(error, MESSAGE_NOT_READY),
                action_hint=ACTION_HINT_RETRY,
            )

        self._state = QQRuntimeState.RUNNING
        self._pid = _optional_int(getattr(info, "pid", None))
        self._version = _optional_str(getattr(info, "version", None))
        return self._status(
            QQRuntimeState.RUNNING,
            message=MESSAGE_RUNNING,
        )

    def stop(self) -> QQRuntimeStatus:
        """Stop the runtime and return the resulting status."""
        if not self.is_available():
            return self._status(
                QQRuntimeState.UNAVAILABLE,
                message=MESSAGE_UNAVAILABLE,
                action_hint=ACTION_HINT_INSTALL,
            )
        if not self._runtime.running():
            return self._status(
                QQRuntimeState.ERROR,
                message=MESSAGE_ERROR,
                action_hint=ACTION_HINT_RETRY,
            )

        self._state = QQRuntimeState.STOPPING
        try:
            self._runtime.stop()
        except Exception as error:
            self._state = QQRuntimeState.ERROR
            return self._status(
                QQRuntimeState.ERROR,
                message=_runtime_error_message(error, MESSAGE_ERROR),
                action_hint=ACTION_HINT_RETRY,
            )

        self._state = QQRuntimeState.STOPPED
        self._pid = None
        return self._status(
            QQRuntimeState.STOPPED,
            message=MESSAGE_STOPPED,
        )

    def get_status(self) -> QQRuntimeStatus:
        """Return the current lifecycle snapshot without probing the runtime."""
        message = {
            QQRuntimeState.UNAVAILABLE: MESSAGE_UNAVAILABLE,
            QQRuntimeState.STOPPED: MESSAGE_STOPPED,
            QQRuntimeState.STARTING: MESSAGE_STARTING,
            QQRuntimeState.RUNNING: MESSAGE_RUNNING,
            QQRuntimeState.STOPPING: MESSAGE_STOPPING,
            QQRuntimeState.ERROR: MESSAGE_ERROR,
        }.get(self._state, MESSAGE_ERROR)
        action_hint = (
            ACTION_HINT_INSTALL
            if self._state is QQRuntimeState.UNAVAILABLE
            else (
                ACTION_HINT_RETRY
                if self._state is QQRuntimeState.ERROR
                else ""
            )
        )
        return QQRuntimeStatus(
            state=self._state,
            available=self.is_available(),
            pid=self._pid,
            version=self._version,
            message=message,
            action_hint=action_hint,
        )

    def _status(
        self,
        state: QQRuntimeState,
        *,
        message: str,
        action_hint: str = "",
    ) -> QQRuntimeStatus:
        return QQRuntimeStatus(
            state=state,
            available=self.is_available(),
            pid=self._pid,
            version=self._version,
            message=message,
            action_hint=action_hint,
        )

    def _stop_after_failed_start(self) -> None:
        try:
            self._runtime.stop()
        except Exception:
            pass


def _runtime_error_message(error: Exception, fallback: str) -> str:
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
