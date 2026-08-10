"""Own the QQ connection lifecycle behind one application-layer entry point.

Before this manager existed, the desktop page asked three separate questions
(setup state, runtime state, connection state) and stitched the answers into
something a user could read. That made the GUI the de facto owner of the
connection policy. This class takes that job back.

Responsibilities:

* sequence the lifecycle: stored setup -> runtime start -> service health and
  authorization;
* translate every outcome into one :class:`ConnectionSnapshot`;
* never raise. A failed probe becomes an ``ERROR`` snapshot with safe wording.

Non-responsibilities: no HTTP, no process control, no config file access. The
setup service still owns runtime lifecycle and config persistence, and the
connection service still owns provider probing. This manager only decides
which of them to ask, in what order, and what the answer means to a user.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ConnectionSnapshot, ConnectionState


SOURCE_QQ = "qq"

MESSAGE_DISCONNECTED = "QQ \u5c1a\u672a\u8fde\u63a5\u3002"
MESSAGE_CONNECTED = "QQ \u5df2\u8fde\u63a5\u3002"
MESSAGE_STARTING = "\u6b63\u5728\u542f\u52a8 QQ \u8fd0\u884c\u73af\u5883..."
MESSAGE_WAITING_AUTH = (
    "QQ \u9700\u8981\u5148\u5b8c\u6210\u767b\u5f55\u6388\u6743\u3002"
)
MESSAGE_ERROR = (
    "\u65e0\u6cd5\u8fde\u63a5 QQ\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)
MESSAGE_UNAVAILABLE = "QQ \u6570\u636e\u6e90\u6682\u4e0d\u53ef\u7528\u3002"

HINT_CONNECT = "\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002"
HINT_CONNECTED = (
    "\u53ef\u4ee5\u5f00\u59cb\u9009\u62e9 QQ \u8d26\u53f7\u5206\u6790\u804a\u5929\u8bb0\u5f55\u3002"
)
HINT_WAITING_AUTH = (
    "\u8bf7\u5728 QQ \u4e2d\u5b8c\u6210\u767b\u5f55\u6388\u6743\u540e\u91cd\u8bd5\u3002"
)
HINT_RETRY = "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_connection_manager")


class QQConnectionManager:
    """Drive and report the QQ connection lifecycle."""

    def __init__(
        self,
        *,
        setup_service: Any = None,
        connection_service: Any = None,
    ) -> None:
        self._setup_service = setup_service
        self._connection_service = connection_service

    # ------------------------------------------------------------ inspection

    def get_snapshot(self) -> ConnectionSnapshot:
        """Report the current lifecycle state without starting anything.

        This is the passive question the GUI asks when a user selects QQ. It
        never launches a runtime, so selecting the source stays cheap.
        """
        if self._setup_service is None and self._connection_service is None:
            return self._unavailable()

        status = self._safe_connection_status()
        if status is None:
            return self._snapshot(
                ConnectionState.DISCONNECTED,
                MESSAGE_DISCONNECTED,
                HINT_CONNECT,
            )
        return self._from_connection_status(status)

    # --------------------------------------------------------------- actions

    def connect(self) -> ConnectionSnapshot:
        """Run the one-click connect flow and report the result.

        The heavy lifting stays in the setup service, which already knows how
        to reuse a running service, persist bundled defaults, and start the
        runtime. This method turns its answer into lifecycle vocabulary.
        """
        if self._setup_service is None:
            return self._unavailable()

        try:
            status = self._setup_service.connect()
        except Exception as error:
            _LOGGER.info(
                "[qq connection] connect failed error=%s",
                type(error).__name__,
            )
            return self._snapshot(
                ConnectionState.ERROR,
                _public_message(error, MESSAGE_ERROR),
                HINT_RETRY,
            )

        if status is None:
            return self._snapshot(
                ConnectionState.ERROR,
                MESSAGE_ERROR,
                HINT_RETRY,
            )

        snapshot = self._from_connection_status(status)
        _LOGGER.info("[qq connection] connect state=%s", snapshot.state.value)
        return snapshot

    # ------------------------------------------------------------- internals

    def _safe_connection_status(self) -> Any:
        """Ask the connection service once, swallowing every failure."""
        service = self._connection_service
        if service is None:
            return None
        try:
            return service.check_status()
        except Exception as error:
            _LOGGER.info(
                "[qq connection] status probe failed error=%s",
                type(error).__name__,
            )
            return None

    def _from_connection_status(self, status: Any) -> ConnectionSnapshot:
        """Map one QQConnectionStatus onto the lifecycle vocabulary.

        The three flags the connection service exposes map cleanly:
        available means connected, a running service without authorization
        means the user still has to log in, and anything else is a plain
        disconnected state the user can act on.
        """
        available = bool(getattr(status, "available", False))
        running = bool(getattr(status, "qce_running", False))
        authenticated = bool(getattr(status, "authenticated", False))
        version = getattr(status, "version", None) or None
        message = _clean(getattr(status, "message", ""))
        action_hint = _clean(getattr(status, "action_hint", ""))

        if available:
            return self._snapshot(
                ConnectionState.CONNECTED,
                message or MESSAGE_CONNECTED,
                action_hint or HINT_CONNECTED,
                version=version,
            )
        if running and not authenticated:
            return self._snapshot(
                ConnectionState.WAITING_AUTH,
                message or MESSAGE_WAITING_AUTH,
                action_hint or HINT_WAITING_AUTH,
                version=version,
            )
        return self._snapshot(
            ConnectionState.DISCONNECTED,
            message or MESSAGE_DISCONNECTED,
            action_hint or HINT_CONNECT,
            version=version,
        )

    def _unavailable(self) -> ConnectionSnapshot:
        return self._snapshot(
            ConnectionState.ERROR,
            MESSAGE_UNAVAILABLE,
            HINT_RETRY,
        )

    @staticmethod
    def _snapshot(
        state: ConnectionState,
        message: str,
        action_hint: str = "",
        *,
        version: str | None = None,
    ) -> ConnectionSnapshot:
        return ConnectionSnapshot(
            state=state,
            source=SOURCE_QQ,
            message=message,
            action_hint=action_hint,
            version=version,
        )


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _public_message(error: Exception, fallback: str) -> str:
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


__all__ = ["QQConnectionManager", "SOURCE_QQ"]
