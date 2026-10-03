"""Build the selected QQ provider from one environment configuration.

The QQ connection status, session listing, export flow, and setup service all
share this factory so they observe the same provider instance and the same
configuration source.
"""

from __future__ import annotations

from typing import Any, Callable

from ..errors import ApplicationServiceError
from .qq_environment_config import (
    QQEnvironmentConfig,
    QQEnvironmentConfigError,
    QQEnvironmentConfigLoader,
)


class QQProviderUnavailable(ApplicationServiceError):
    """Raised when a NapCat provider cannot be built from the current config."""

    code = "qq_provider_unavailable"
    public_message = "无法连接 QQ 数据源，请稍后重试。"


def default_provider_builder(config: QQEnvironmentConfig) -> Any:
    """Construct the Desktop Echo NapCat provider."""
    from ...providers.napcat_qq_provider import NapCatQQProvider
    return NapCatQQProvider(config.napcat_bridge_url)


class QQProviderFactory:
    """Create and cache one QQ provider built from stored configuration."""

    def __init__(
        self,
        *,
        config_loader: QQEnvironmentConfigLoader | None = None,
        provider_builder: Callable[[QQEnvironmentConfig], Any] | None = None,
    ) -> None:
        self._config_loader = config_loader or QQEnvironmentConfigLoader()
        self._provider_builder = provider_builder or default_provider_builder
        self._provider: Any | None = None

    def create(self) -> Any:
        """Return the shared provider, building it on first use."""
        if self._provider is None:
            self._provider = self._build()
        return self._provider

    def invalidate(self) -> None:
        """Drop the cached provider so the next call reloads the config."""
        self._provider = None

    @property
    def config_loader(self) -> QQEnvironmentConfigLoader:
        return self._config_loader

    # ---------------------------------------------------------------- internals

    def _build(self) -> Any:
        config = self._config_loader.load_or_default()
        try:
            return self._provider_builder(config)
        except QQEnvironmentConfigError:
            raise
        except Exception:
            raise QQProviderUnavailable() from None


__all__ = [
    "QQProviderFactory",
    "QQProviderUnavailable",
    "default_provider_builder",
]
