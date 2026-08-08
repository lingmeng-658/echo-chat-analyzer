"""Application-layer setup for the WeChat environment.

The connection layer can only report "not configured" until something writes
``wechat.json``. This service is that something: it inspects the stored
configuration, saves a new one on the user's behalf, and refreshes the shared
provider factory so the next read observes the new settings.

Deliberate boundaries:

* No database access, no key discovery, and no WeChat parsing happen here.
  The service only reads and writes application configuration.
* No GUI code. A widget calls this through
  :class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade` and never
  writes JSON itself.
* ``check_setup()`` never raises: an unreadable or damaged config becomes a
  status, so a caller can render guidance instead of a traceback.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import ApplicationServiceError
from .wechat_environment_config import (
    WeChatConfigNotFound,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigLoader,
    WeChatEnvironmentConfigWriter,
)


MESSAGE_CONFIG_MISSING = (
    "\u5c1a\u672a\u914d\u7f6e\u5fae\u4fe1\u8fd0\u884c\u73af\u5883\u3002"
)
ACTION_HINT_CONFIG_MISSING = (
    "\u8bf7\u5148\u8bbe\u7f6e\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3001"
    "\u6570\u636e\u5e93\u5bc6\u94a5\u548c\u8bfb\u53d6\u7ec4\u4ef6\u3002"
)
MESSAGE_CONFIG_READY = (
    "\u5fae\u4fe1\u8fd0\u884c\u73af\u5883\u914d\u7f6e\u5df2\u4fdd\u5b58\u3002"
)
ACTION_HINT_CONFIG_READY = (
    "\u53ef\u4ee5\u8fd4\u56de\u5fae\u4fe1\u5165\u53e3\u68c0\u6d4b\u8fde\u63a5\u72b6\u6001\u3002"
)
MESSAGE_CONFIG_INVALID = (
    "\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\u65e0\u6cd5\u8bfb\u53d6\u3002"
)
ACTION_HINT_CONFIG_INVALID = (
    "\u8bf7\u91cd\u65b0\u8bbe\u7f6e\u5fae\u4fe1\u8fd0\u884c\u73af\u5883\u3002"
)


class WeChatSetupState(Enum):
    """Coarse state of the stored WeChat environment configuration."""

    CONFIG_MISSING = "config_missing"
    CONFIG_READY = "config_ready"
    CONFIG_INVALID = "config_invalid"


@dataclass(frozen=True, slots=True)
class WeChatSetupStatus:
    """User-facing snapshot of the stored WeChat configuration."""

    state: WeChatSetupState
    configured: bool
    message: str
    action_hint: str
    config_path: Path | None = None


class WeChatSetupService:
    """Inspect and persist the WeChat environment configuration."""

    class InvalidEnvironment(ApplicationServiceError):
        """Raised when the caller supplies something that is not a config."""

        code = "wechat_invalid_environment"
        public_message = (
            "\u5fae\u4fe1\u73af\u5883\u53c2\u6570\u65e0\u6548\uff0c"
            "\u8bf7\u91cd\u65b0\u586b\u5199\u3002"
        )

    def __init__(
        self,
        *,
        config_loader: Any = None,
        config_writer: Any = None,
        provider_factory: Any = None,
        connection_service: Any = None,
    ) -> None:
        self._config_loader = config_loader or WeChatEnvironmentConfigLoader()
        self._config_writer = config_writer or WeChatEnvironmentConfigWriter()
        self._provider_factory = provider_factory
        self._connection_service = connection_service

    def check_setup(self) -> WeChatSetupStatus:
        """Report whether a usable configuration is stored, never raising."""
        config_path = self._config_path()
        try:
            self._config_loader.load()
        except WeChatConfigNotFound:
            return WeChatSetupStatus(
                state=WeChatSetupState.CONFIG_MISSING,
                configured=False,
                message=MESSAGE_CONFIG_MISSING,
                action_hint=ACTION_HINT_CONFIG_MISSING,
                config_path=config_path,
            )
        except Exception:
            return WeChatSetupStatus(
                state=WeChatSetupState.CONFIG_INVALID,
                configured=False,
                message=MESSAGE_CONFIG_INVALID,
                action_hint=ACTION_HINT_CONFIG_INVALID,
                config_path=config_path,
            )

        return WeChatSetupStatus(
            state=WeChatSetupState.CONFIG_READY,
            configured=True,
            message=MESSAGE_CONFIG_READY,
            action_hint=ACTION_HINT_CONFIG_READY,
            config_path=config_path,
        )

    def save_environment(self, config: WeChatEnvironmentConfig) -> Any:
        """Persist a config, refresh the provider, and re-check connection.

        The factory is invalidated only after a successful write, so a failed
        save leaves the previously working provider untouched. The return
        value is the refreshed connection status when a connection service is
        available, otherwise ``None``.
        """
        if not isinstance(config, WeChatEnvironmentConfig):
            raise self.InvalidEnvironment()

        self._config_writer.save(config)

        if self._provider_factory is not None:
            self._provider_factory.invalidate()

        if self._connection_service is None:
            return None
        return self._connection_service.check_status()

    # ---------------------------------------------------------------- internals

    def _config_path(self) -> Path | None:
        getter = getattr(self._config_loader, "config_path", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None


__all__ = [
    "WeChatSetupService",
    "WeChatSetupState",
    "WeChatSetupStatus",
]