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
from .qq_environment_config import (
    QQConfigCorrupted,
    QQConfigNotFound,
    QQEnvironmentConfigError,
)


MESSAGE_AVAILABLE = "QQ 数据源已连接。"
MESSAGE_NOT_RUNNING = "QQ 服务未运行，QQ 数据源当前不可用。"
MESSAGE_TOKEN_MISSING = "QQ 需要先登录并授权才能读取聊天记录。"
MESSAGE_UNKNOWN_ERROR = "无法确认 QQ 数据源状态，请稍后重试。"
MESSAGE_CONFIG_MISSING = "QQ 数据源尚未连接。"
MESSAGE_CONFIG_INVALID = "QQ 数据源暂不可用，请稍后重试。"

ACTION_HINT_AVAILABLE = "可以开始选择 QQ 账号分析聊天记录。"
ACTION_HINT_START_QCE = "请打开并登录 QQ 后重试。"
ACTION_HINT_AUTHORIZE = "请在 QQ 中完成登录授权后重试。"
ACTION_HINT_RETRY = "请稍后重试，或确认 QQ 已完成登录授权。"
ACTION_HINT_CONFIG_MISSING = "请点击「连接QQ」自动完成连接。"
ACTION_HINT_CONFIG_INVALID = "请稍后重试。"


@dataclass(frozen=True, slots=True)
class QQConnectionStatus:
    """User-facing snapshot of the QQ connection state.

    ``available`` is the only flag a caller should gate on; it means the QQ
    account data is usable right now. ``qce_running`` says the QCE service is
    up, and ``authenticated`` only records QCE's own API token, never the QQ
    login itself. ``message`` and ``action_hint`` tell the user what is wrong
    and what to do next.
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

    def list_groups(self, limit: int = 1) -> Any:  # pragma: no cover - contract only
        """Return QQ groups, raising until the QQ account data is usable."""
        ...


class QQConnectionService:
    """Turn provider health and token state into a stable user status."""

    def __init__(
        self,
        provider: QQConnectionProvider | None = None,
        *,
        provider_factory: Any = None,
    ) -> None:
        if provider is None and provider_factory is None:
            raise TypeError(
                "QQConnectionService needs a provider or provider_factory"
            )
        self._injected_provider = provider
        self._provider_factory = provider_factory

    def provider(self) -> QQConnectionProvider:
        """Return the provider used for probes.

        When a shared provider factory is injected, the instance comes from
        that factory, so connection checks and session reads use the same
        configuration and provider.
        """
        if self._provider_factory is not None:
            return self._provider_factory.create()
        return self._injected_provider

    @property
    def _provider(self) -> QQConnectionProvider:
        return self.provider()

    def check_status(self) -> QQConnectionStatus:
        """Ask the provider once and translate the answer for a caller.

        Provider probing is deliberately not copied here: ``health_check`` and
        ``resolve_token`` are the provider's own behaviours, and this service
        only composes them into user-visible state.
        """
        try:
            provider = self.provider()
        except QQConfigNotFound:
            return self._config_missing_status()
        except (QQConfigCorrupted, QQEnvironmentConfigError):
            return self._config_invalid_status()
        except Exception:
            return self._unknown_status()

        try:
            health = provider.health_check()
            running = bool(getattr(health, "available", False))
            version = getattr(health, "version", None) or None
        except Exception:
            return self._unknown_status()

        if not running:
            return QQConnectionStatus(
                available=False,
                qce_running=False,
                authenticated=False,
                version=None,
                message=MESSAGE_NOT_RUNNING,
                action_hint=ACTION_HINT_START_QCE,
            )

        api_authenticated = self._resolve_api_authenticated()
        if not self._resolve_qq_data_available():
            return QQConnectionStatus(
                available=False,
                qce_running=True,
                authenticated=api_authenticated,
                version=version,
                message=MESSAGE_TOKEN_MISSING,
                action_hint=ACTION_HINT_AUTHORIZE,
            )
        return QQConnectionStatus(
            available=True,
            qce_running=True,
            authenticated=api_authenticated,
            version=version,
            message=MESSAGE_AVAILABLE,
            action_hint=ACTION_HINT_AVAILABLE,
        )

    # ---------------------------------------------------------------- internals

    def _resolve_api_authenticated(self) -> bool:
        """Return whether QCE's own API authentication token is present."""
        try:
            token = self._provider.resolve_token()
        except TokenUnavailable:
            return False
        except Exception:
            return False
        return bool(token)

    def _resolve_qq_data_available(self) -> bool:
        """Return whether the QQ account data is actually reachable.

        The security token only proves QCE API authentication. QCE serves
        QQ-scoped data only after the QQ account has logged in, so a small
        group probe is the real data availability check.
        """
        try:
            self._provider.list_groups(limit=1)
        except Exception:
            return False
        return True

    def _unknown_status(self) -> QQConnectionStatus:
        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message=MESSAGE_UNKNOWN_ERROR,
            action_hint=ACTION_HINT_RETRY,
        )

    def _config_missing_status(self) -> QQConnectionStatus:
        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message=MESSAGE_CONFIG_MISSING,
            action_hint=ACTION_HINT_CONFIG_MISSING,
        )

    def _config_invalid_status(self) -> QQConnectionStatus:
        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message=MESSAGE_CONFIG_INVALID,
            action_hint=ACTION_HINT_CONFIG_INVALID,
        )
