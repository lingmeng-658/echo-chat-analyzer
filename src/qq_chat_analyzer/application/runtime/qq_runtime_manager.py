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

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from qq_chat_analyzer.runtime import ChatRuntime, RuntimeInfo

from ..qq_webui_config import disable_qce_auto_open_browser


MESSAGE_UNAVAILABLE = "未检测到 QQ 数据源，暂时无法连接。"
MESSAGE_STOPPED = "QQ 已断开。"
MESSAGE_STARTING = "正在连接 QQ..."
MESSAGE_RUNNING = "QQ 已连接。"
MESSAGE_STOPPING = "正在断开 QQ..."
MESSAGE_ERROR = "操作失败，请稍后重试。"
MESSAGE_NOT_READY = "QQ 正在准备中，请稍候。"

ACTION_HINT_INSTALL = "QQ 数据源暂不可用，请稍后再试。"
ACTION_HINT_RETRY = "请稍后重试。"

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_runtime_manager")


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
        config_preparer: Callable[[], bool] | None = None,
    ) -> None:
        self._runtime = runtime
        self._ready_timeout = ready_timeout
        self._config_preparer = config_preparer or disable_qce_auto_open_browser
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
        """Start the runtime and return immediately.

        Readiness and login authorization are reported by later probes; this
        call never blocks waiting for the external service to come up.
        """
        if not self.is_available():
            return self._status(
                QQRuntimeState.UNAVAILABLE,
                message=MESSAGE_UNAVAILABLE,
                action_hint=ACTION_HINT_INSTALL,
            )

        if not self._config_preparer():
            _LOGGER.warning(
                "[qq runtime] QCE auto-open config could not be prepared"
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
