"""Translate WeChat database readiness into a user-facing connection status.

This module is the WeChat counterpart of
:mod:`~qq_chat_analyzer.application.qq_connection_service`. It probes the
provider's existing resolver surface and returns a stable status instead of
leaking provider exceptions to a caller such as the GUI.

Deliberate boundaries:

* The service reads :class:`WeChatEnvironmentConfig` from the application
  config loader and builds the provider through an injectable factory. GUI
  and Facade callers never pass data roots, keys, or runtime paths directly.
* It calls the same resolver probes used by
  :class:`~qq_chat_analyzer.providers.wechat_database_provider
  .WeChatDatabaseProvider` and never calls ``list_sessions`` or
  ``read_session_rows``, so a status check does not read chat content.
* ``check_status()`` never raises. Every failure collapses into a status with
  a safe message and an actionable hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..providers.wechat_database_provider import (
    DatabaseNotFound,
    KeyUnavailable,
    WcdbHelperNotFound,
    WcdbLibraryNotFound,
)
from .wechat_environment_config import (
    WeChatConfigCorrupted,
    WeChatConfigNotFound,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigError,
    WeChatEnvironmentConfigLoader,
)


MESSAGE_AVAILABLE = (
    "\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528\uff0c"
    "\u53ef\u4ee5\u5f00\u59cb\u5206\u6790\u3002"
)
ACTION_HINT_AVAILABLE = (
    "\u53ef\u4ee5\u5f00\u59cb\u9009\u62e9\u4f1a\u8bdd\u5e76\u5206\u6790\u3002"
)
MESSAGE_DATA_MISSING = (
    "\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3002"
    "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u5728\u672c\u673a\u767b\u5f55\u8fc7\uff0c"
    "\u6216\u624b\u52a8\u6307\u5b9a\u6570\u636e\u76ee\u5f55\u3002"
)
ACTION_HINT_DATA_MISSING = (
    "\u8bf7\u786e\u8ba4\u5fae\u4fe1\u5df2\u767b\u5f55\u5e76"
    "\u751f\u6210\u6570\u636e\u76ee\u5f55\uff0c\u6216\u624b\u52a8"
    "\u6307\u5b9a\u6570\u636e\u76ee\u5f55\u3002"
)
MESSAGE_KEY_MISSING = (
    "\u7f3a\u5c11\u5fae\u4fe1\u6570\u636e\u5e93\u5bc6\u94a5\uff0c"
    "\u6682\u65f6\u65e0\u6cd5\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u3002"
)
ACTION_HINT_KEY_MISSING = (
    "\u8bf7\u4fdd\u6301\u5fae\u4fe1\u767b\u5f55\u72b6\u6001\u5e76"
    "\u83b7\u53d6\u6570\u636e\u5e93\u5bc6\u94a5\u540e\u91cd\u8bd5\u3002"
)
MESSAGE_RUNTIME_MISSING = (
    "\u5fae\u4fe1\u6570\u636e\u5e93\u8bfb\u53d6\u7ec4\u4ef6\u4e0d\u5b8c\u6574\uff0c"
    "\u6682\u65f6\u65e0\u6cd5\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u3002"
)
ACTION_HINT_RUNTIME_MISSING = (
    "\u8bf7\u786e\u8ba4 wcdb_cli \u4e0e WCDB.dll \u53ef\u7528\uff0c"
    "\u6216\u7b49\u5f85\u5b89\u88c5\u5305\u8865\u9f50\u3002"
)
MESSAGE_UNKNOWN = (
    "\u65e0\u6cd5\u786e\u8ba4\u5fae\u4fe1\u6570\u636e\u6e90\u72b6\u6001\uff0c"
    "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)
ACTION_HINT_UNKNOWN = (
    "\u8bf7\u7a0d\u540e\u91cd\u8bd5\uff0c\u6216\u67e5\u770b\u5e94\u7528\u65e5\u5fd7\u3002"
)
MESSAGE_CONFIG_MISSING = (
    "\u672a\u627e\u5230\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\uff0c"
    "\u8bf7\u5148\u5b8c\u6210\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u3002"
)
ACTION_HINT_CONFIG_MISSING = (
    "\u8bf7\u5148\u914d\u7f6e\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3001"
    "\u6570\u636e\u5e93\u5bc6\u94a5\u548c\u8bfb\u53d6\u7ec4\u4ef6\u3002"
)
MESSAGE_CONFIG_CORRUPTED = (
    "\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\u65e0\u6cd5\u4f7f\u7528\uff0c"
    "\u8bf7\u91cd\u65b0\u8bbe\u7f6e\u3002"
)
ACTION_HINT_CONFIG_CORRUPTED = (
    "\u8bf7\u91cd\u65b0\u8bbe\u7f6e\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\u3002"
)


def _is_shared_factory(candidate: Any) -> bool:
    """Tell a shared provider factory from a plain config->provider callable.

    Both forms are accepted for backwards compatibility: existing callers and
    tests pass a callable taking a config, while the composition root passes a
    :class:`~qq_chat_analyzer.application.wechat_provider_factory
    .WeChatProviderFactory` that owns config loading itself.
    """
    return candidate is not None and hasattr(candidate, "create")


@dataclass(frozen=True, slots=True)
class WeChatConnectionStatus:
    """User-facing snapshot of the WeChat database connection state.

    ``available`` is the only flag a caller should gate on. The other flags
    explain why it is false, while ``message`` and ``action_hint`` tell the
    user what to do next.
    """

    available: bool
    data_found: bool
    db_key_available: bool
    runtime_available: bool
    message: str
    action_hint: str


def default_provider_factory(config: WeChatEnvironmentConfig) -> Any:
    """Build the real provider from one environment config."""
    from ..providers.wechat_database_provider import WeChatDatabaseProvider

    return WeChatDatabaseProvider(
        data_root=config.data_root,
        db_key=config.db_key,
        wcdb_cli_path=config.wcdb_cli_path,
        wcdb_dll_path=config.wcdb_dll_path,
    )


class WeChatConnectionService:
    """Turn WeChat provider readiness into a stable user status."""

    def __init__(
        self,
        provider: Any | None = None,
        *,
        config_loader: WeChatEnvironmentConfigLoader | None = None,
        provider_factory: Callable[[WeChatEnvironmentConfig], Any] | None = None,
    ) -> None:
        self._provider = provider
        self._shared_factory = (
            provider_factory
            if _is_shared_factory(provider_factory)
            else None
        )
        self._config_loader = (
            config_loader or WeChatEnvironmentConfigLoader()
        )
        self._provider_factory = (
            provider_factory
            if provider_factory is not None and self._shared_factory is None
            else default_provider_factory
        )

    def provider(self) -> Any:
        """Return the provider this service probes.

        When a shared :class:`~qq_chat_analyzer.application
        .wechat_provider_factory.WeChatProviderFactory` is injected, the
        instance comes from that factory, so the status check and the session
        read path observe exactly the same provider and configuration.
        """
        if self._shared_factory is not None:
            return self._shared_factory.create()
        if self._provider is None:
            config = self._config_loader.load()
            self._provider = self._provider_factory(config)
        return self._provider

    def check_status(self) -> WeChatConnectionStatus:
        """Load config, build a provider, and translate the result."""
        if self._shared_factory is not None or self._provider is None:
            config_status = self._load_config_status()
            if config_status is not None:
                return config_status

        data_found = self._probe_data()
        key_available = self._probe_key()
        runtime_available = self._probe_runtime()

        if (
            data_found is None
            or key_available is None
            or runtime_available is None
        ):
            return self._unknown_status(
                data_found,
                key_available,
                runtime_available,
            )

        if not data_found:
            return WeChatConnectionStatus(
                available=False,
                data_found=False,
                db_key_available=key_available,
                runtime_available=runtime_available,
                message=MESSAGE_DATA_MISSING,
                action_hint=ACTION_HINT_DATA_MISSING,
            )
        if not key_available:
            return WeChatConnectionStatus(
                available=False,
                data_found=True,
                db_key_available=False,
                runtime_available=runtime_available,
                message=MESSAGE_KEY_MISSING,
                action_hint=ACTION_HINT_KEY_MISSING,
            )
        if not runtime_available:
            return WeChatConnectionStatus(
                available=False,
                data_found=True,
                db_key_available=True,
                runtime_available=False,
                message=MESSAGE_RUNTIME_MISSING,
                action_hint=ACTION_HINT_RUNTIME_MISSING,
            )

        return WeChatConnectionStatus(
            available=True,
            data_found=True,
            db_key_available=True,
            runtime_available=True,
            message=MESSAGE_AVAILABLE,
            action_hint=ACTION_HINT_AVAILABLE,
        )

    # ---------------------------------------------------------------- internals

    def _load_config_status(self) -> WeChatConnectionStatus | None:
        try:
            config = (
                None
                if self._shared_factory is not None
                else self._config_loader.load()
            )
        except WeChatConfigNotFound:
            return self._config_missing_status()
        except (WeChatConfigCorrupted, WeChatEnvironmentConfigError):
            return self._config_corrupted_status()
        except Exception:
            return self._unknown_status(None, None, None)

        try:
            self._provider = (
                self._shared_factory.create()
                if self._shared_factory is not None
                else self._provider_factory(config)
            )
        except WeChatConfigNotFound:
            return self._config_missing_status()
        except (WeChatConfigCorrupted, WeChatEnvironmentConfigError):
            return self._config_corrupted_status()
        except Exception:
            return self._unknown_status(None, None, None)
        return None

    def _probe_data(self) -> bool | None:
        try:
            self._provider._session_db_path()
        except DatabaseNotFound:
            return False
        except Exception:
            return None
        return True

    def _probe_key(self) -> bool | None:
        try:
            key = self._provider._resolve_key()
        except KeyUnavailable:
            return False
        except Exception:
            return None
        return bool(key and key.strip())

    def _probe_runtime(self) -> bool | None:
        try:
            self._provider._resolve_helper()
            self._provider._resolve_library()
        except (WcdbHelperNotFound, WcdbLibraryNotFound):
            return False
        except Exception:
            return None
        return True

    def _config_missing_status(self) -> WeChatConnectionStatus:
        return WeChatConnectionStatus(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message=MESSAGE_CONFIG_MISSING,
            action_hint=ACTION_HINT_CONFIG_MISSING,
        )

    def _config_corrupted_status(self) -> WeChatConnectionStatus:
        return WeChatConnectionStatus(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message=MESSAGE_CONFIG_CORRUPTED,
            action_hint=ACTION_HINT_CONFIG_CORRUPTED,
        )

    def _unknown_status(
        self,
        data_found: bool | None,
        key_available: bool | None,
        runtime_available: bool | None,
    ) -> WeChatConnectionStatus:
        return WeChatConnectionStatus(
            available=False,
            data_found=bool(data_found),
            db_key_available=bool(key_available),
            runtime_available=bool(runtime_available),
            message=MESSAGE_UNKNOWN,
            action_hint=ACTION_HINT_UNKNOWN,
        )


__all__ = [
    "WeChatConnectionService",
    "WeChatConnectionStatus",
]
