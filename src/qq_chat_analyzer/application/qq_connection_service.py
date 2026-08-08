"""Translate QCE provider state into a user-facing QQ connection status.

This module is the application-layer seam for connection awareness. It owns
the wording a caller sees ("service is not running", "please authorize"),
while the provider keeps owning the actual probing and token resolution.

Deliberate boundaries:

* No HTTP, no security.json reading, and no provider internals live here. The
  provider is injected and only has to satisfy :class:`QQConnectionProvider`.
* ``check_status()`` never raises. Every provider failure collapses into a
  status with a safe message, so a GUI never has to know the underlying error.
* The model is user-facing: it exposes booleans, an optional version, and two
  human-readable strings, never an exception or an HTTP detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..providers.qq_chat_exporter_provider import TokenUnavailable


MESSAGE_AVAILABLE = (
    "QQ \u6570\u636E\u6E90\u53EF\u7528\uFF0CQQChatExporter \u670D\u52A1\u5DF2\u8FDE\u63A5\u3002"
)
MESSAGE_NOT_RUNNING = (
    "QQChatExporter \u670D\u52A1\u672A\u8FD0\u884C\uFF0CQQ \u6570\u636E\u6E90\u5F53\u524D\u4E0D\u53EF\u7528\u3002"
)
MESSAGE_TOKEN_MISSING = (
    "QQChatExporter \u8BBF\u95EE\u51ED\u636E\u4E0D\u5B58\u5728\uFF0C\u9700\u8981\u5148\u5B8C\u6210\u521D\u59CB\u5316\u6216\u6388\u6743\u3002"
)
MESSAGE_UNKNOWN_ERROR = (
    "\u65E0\u6CD5\u786E\u8BA4 QQ \u6570\u636E\u6E90\u72B6\u6001\uFF0C\u8BF7\u7A0D\u540E\u91CD\u8BD5\u3002"
)

ACTION_HINT_AVAILABLE = "\u53EF\u4EE5\u5F00\u59CB\u5BFC\u51FA\u7FA4\u804A\u8BB0\u5F55\u3002"
ACTION_HINT_START_QCE = "\u8BF7\u5148\u542F\u52A8\u5E76\u767B\u5F55 QQChatExporter\uFF0C\u7136\u540E\u91CD\u8BD5\u3002"
ACTION_HINT_AUTHORIZE = "\u8BF7\u786E\u8BA4 QQChatExporter \u5DF2\u6B63\u5E38\u542F\u52A8\u8FC7\u4E00\u6B21\uFF0C\u518D\u91CD\u65B0\u6388\u6743\u3002"
ACTION_HINT_RETRY = "\u8BF7\u7A0D\u540E\u91CD\u8BD5\uFF0C\u6216\u786E\u8BA4 QQChatExporter \u5DF2\u542F\u52A8\u5E76\u6388\u6743\u3002"


@dataclass(frozen=True, slots=True)
class QQConnectionStatus:
    """User-facing snapshot of the QQ connection state.

    ``available`` is the only flag a caller should gate on. ``qce_running``
    and ``authenticated`` explain *why*, while ``message`` and ``action_hint``
    tell the user what is wrong and what to do next.
    """

    available: bool
    qce_running: bool
    authenticated: bool
    version: str | None
    message: str
    action_hint: str


@runtime_checkable
class QQConnectionProvider(Protocol):
    """Minimal surface the connection service needs from a QCE provider."""

    def health_check(self) -> Any:  # pragma: no cover - contract only
        """Probe the service and return a ServiceHealth snapshot."""
        ...

    def resolve_token(self) -> str:  # pragma: no cover - contract only
        """Return the access token, raising TokenUnavailable when absent."""
        ...


class QQConnectionService:
    """Turn provider health and token state into a stable user status."""

    def __init__(self, provider: QQConnectionProvider) -> None:
        self._provider = provider

    def check_status(self) -> QQConnectionStatus:
        """Ask the provider once and translate the answer for a caller.

        Provider probing is deliberately not copied here: ``health_check`` and
        ``resolve_token`` are the provider's own behaviours, and this service
        only composes them into user-visible state.
        """
        try:
            health = self._provider.health_check()
            running = bool(getattr(health, "available", False))
            version = getattr(health, "version", None) or None
        except Exception:
            return self._unknown_status()

        authenticated = self._resolve_authenticated()
        if not running:
            return QQConnectionStatus(
                available=False,
                qce_running=False,
                authenticated=authenticated,
                version=None,
                message=MESSAGE_NOT_RUNNING,
                action_hint=ACTION_HINT_START_QCE,
            )
        if not authenticated:
            return QQConnectionStatus(
                available=False,
                qce_running=True,
                authenticated=False,
                version=version,
                message=MESSAGE_TOKEN_MISSING,
                action_hint=ACTION_HINT_AUTHORIZE,
            )
        return QQConnectionStatus(
            available=True,
            qce_running=True,
            authenticated=True,
            version=version,
            message=MESSAGE_AVAILABLE,
            action_hint=ACTION_HINT_AVAILABLE,
        )

    # ---------------------------------------------------------------- internals

    def _resolve_authenticated(self) -> bool:
        try:
            token = self._provider.resolve_token()
        except TokenUnavailable:
            return False
        except Exception:
            return False
        return bool(token)

    def _unknown_status(self) -> QQConnectionStatus:
        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message=MESSAGE_UNKNOWN_ERROR,
            action_hint=ACTION_HINT_RETRY,
        )
