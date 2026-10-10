"""Build the selected QQ provider from one environment configuration.

The QQ connection status, session listing, export flow, and setup service all
share this factory so they observe the same provider instance and the same
configuration source.
"""

from __future__ import annotations

from typing import Any, Callable
import threading

from ..errors import ApplicationServiceError
from .qq_environment_config import (
    QQEnvironmentConfig,
    QQEnvironmentConfigError,
    QQEnvironmentConfigLoader,
)
from .qq_runtime_session import default_qq_runtime_session


class QQProviderUnavailable(ApplicationServiceError):
    """Raised when a NapCat provider cannot be built from the current config."""

    code = "qq_provider_unavailable"
    public_message = "无法连接 QQ 数据源，请稍后重试。"


class QQReconnectRequired(ApplicationServiceError):
    code = "qq_reconnect_required"
    public_message = "QQ 运行环境已变化，请点击「重新连接」后继续。"


def default_provider_builder(config: QQEnvironmentConfig, *, credential: object | None = None) -> Any:
    """Construct the Desktop Echo NapCat provider bound to the launch credential."""
    from ...providers.napcat_qq_provider import NapCatQQProvider
    return NapCatQQProvider(config.napcat_bridge_url, credential=credential)


class QQProviderFactory:
    """Create and cache one QQ provider built from stored configuration.

    A verified provider belongs to one connection. A stale binding is retained
    until an explicit reconnect; ordinary config invalidation cannot replace it.
    """

    def __init__(
        self,
        *,
        config_loader: QQEnvironmentConfigLoader | None = None,
        provider_builder: Callable[..., Any] | None = None,
        bridge_credential: object | None = None,
    ) -> None:
        self._config_loader = config_loader or QQEnvironmentConfigLoader()
        self._provider_builder = provider_builder or default_provider_builder
        self._bridge_credential = bridge_credential or default_qq_runtime_session()
        self._provider: Any | None = None
        # Keep the connection owner even when its ordinary config cache expires.
        # Retain it before verification too: an outstanding status probe may
        # establish the first binding after invalidate() returns.
        self._connection_provider: Any | None = None
        self._reconnect_required = False
        self._lock = threading.RLock()

    @property
    def reconnect_required(self) -> bool:
        with self._lock:
            return self._reconnect_required or getattr(self._connection_provider, "requires_reconnect", False) is True

    def require_reconnect(self, provider: Any = None) -> None:
        with self._lock:
            if provider is None or provider is self._connection_provider:
                self._reconnect_required = True

    def reconnect(self) -> None:
        """Only an explicit user connection action may discard a stale binding."""
        with self._lock:
            self._provider = None
            self._connection_provider = None
            self._reconnect_required = False

    def create(self) -> Any:
        """Return the shared provider, building it on first use."""
        with self._lock:
            if self.reconnect_required:
                self.require_reconnect()
                raise QQReconnectRequired()
            if self._provider is None:
                if self._connection_provider is None:
                    self._connection_provider = self._build()
                self._provider = self._connection_provider
            return self._provider

    def invalidate(self) -> None:
        """Expire the cache, never the connection's generation constraint.

        Configuration changes take effect at the next explicit reconnect.
        """
        with self._lock:
            if self.reconnect_required:
                self.require_reconnect()
                return
            self._provider = None

    @property
    def config_loader(self) -> QQEnvironmentConfigLoader:
        return self._config_loader

    # ---------------------------------------------------------------- internals

    def _build(self) -> Any:
        config = self._config_loader.load_or_default()
        try:
            return self._provider_builder(config, credential=self._bridge_credential)
        except QQEnvironmentConfigError:
            raise
        except Exception:
            raise QQProviderUnavailable() from None


__all__ = [
    "QQProviderFactory",
    "QQProviderUnavailable",
    "default_provider_builder",
]
