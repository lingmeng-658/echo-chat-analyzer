"""Application-layer setup and one-click connection for the QQ source.

The QQ connection layer depends on a bundled runtime and a stored environment
configuration. This service auto-detects that runtime, checks readiness,
persists detected settings on the user's behalf, and refreshes the shared
provider factory so the next connection probe uses the saved environment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .errors import ApplicationServiceError
from .qq_environment_config import (
    QQConfigNotFound,
    QQEnvironmentConfig,
    QQEnvironmentConfigLoader,
    QQEnvironmentConfigWriter,
)
from .runtime import QQRuntimeManager, QQRuntimeState, QQRuntimeStatus


MESSAGE_CONFIG_MISSING = "QQ 尚未连接。"
ACTION_HINT_CONFIG_MISSING = "请点击「连接QQ」自动完成连接。"
MESSAGE_CONFIG_READY = "QQ 已就绪。"
ACTION_HINT_CONFIG_READY = "可以开始选择 QQ 账号分析聊天记录。"
MESSAGE_CONFIG_INVALID = "QQ 数据源暂不可用。"
ACTION_HINT_CONFIG_INVALID = "请稍后重试。"
MESSAGE_RUNTIME_MISSING = "QQ 数据源暂不可用。"
ACTION_HINT_RUNTIME_MISSING = "请稍后重试。"
MESSAGE_RUNTIME_MANAGER_MISSING = "QQ 数据源暂不可用，请稍后重试。"
ACTION_HINT_RUNTIME_MANAGER_MISSING = "请稍后重试。"


class QQSetupState(str, Enum):
    """Coarse state of the stored QQ environment configuration."""

    CONFIG_MISSING = "config_missing"
    CONFIG_READY = "config_ready"
    CONFIG_INVALID = "config_invalid"
    RUNTIME_MISSING = "runtime_missing"


@dataclass(frozen=True, slots=True)
class QQSetupStatus:
    """User-facing snapshot of the stored QQ environment."""

    state: QQSetupState
    configured: bool
    runtime_available: bool
    message: str
    action_hint: str
    config_path: Path | None = None


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_setup_service")


class QQSetupService:
    """Inspect and persist the QQ environment configuration."""

    class InvalidEnvironment(ApplicationServiceError):
        """Raised when the caller supplies something that is not a config."""

        code = "qq_invalid_environment"
        public_message = (
            "QQ 连接参数无效，请重新填写。"
        )

    def __init__(
        self,
        *,
        config_loader: Any = None,
        config_writer: Any = None,
        provider_factory: Any = None,
        connection_service: Any = None,
        runtime_manager: Any = None,
        runtime_factory: Callable[[QQEnvironmentConfig], Any] | None = None,
    ) -> None:
        self._config_loader = config_loader or QQEnvironmentConfigLoader()
        self._config_writer = config_writer or QQEnvironmentConfigWriter()
        self._provider_factory = provider_factory
        self._connection_service = connection_service
        self._runtime_manager = runtime_manager
        self._runtime_factory = runtime_factory or default_runtime_factory
        self._built_runtime_manager: Any = None

    def check_setup(self) -> QQSetupStatus:
        """Report whether a usable environment is stored, never raising."""
        config_path = self._config_path()
        try:
            config = self._load_config_or_default()
        except QQConfigNotFound:
            return QQSetupStatus(
                state=QQSetupState.CONFIG_MISSING,
                configured=False,
                runtime_available=False,
                message=MESSAGE_CONFIG_MISSING,
                action_hint=ACTION_HINT_CONFIG_MISSING,
                config_path=config_path,
            )
        except Exception:
            return QQSetupStatus(
                state=QQSetupState.CONFIG_INVALID,
                configured=False,
                runtime_available=False,
                message=MESSAGE_CONFIG_INVALID,
                action_hint=ACTION_HINT_CONFIG_INVALID,
                config_path=config_path,
            )

        if not self._runtime_complete(config):
            return QQSetupStatus(
                state=QQSetupState.RUNTIME_MISSING,
                configured=True,
                runtime_available=False,
                message=MESSAGE_RUNTIME_MISSING,
                action_hint=ACTION_HINT_RUNTIME_MISSING,
                config_path=config_path,
            )

        return QQSetupStatus(
            state=QQSetupState.CONFIG_READY,
            configured=True,
            runtime_available=True,
            message=MESSAGE_CONFIG_READY,
            action_hint=ACTION_HINT_CONFIG_READY,
            config_path=config_path,
        )

    def get_environment_config(self) -> QQEnvironmentConfig:
        """Return the effective QQ environment config (saved or default)."""
        return self._load_config_or_default()

    def save_environment(self, config: QQEnvironmentConfig) -> Any:
        """Persist a config, refresh the provider, and re-check connection.

        The provider factory is invalidated only after a successful write. The
        return value is the refreshed QQ connection status when a connection
        service is available, otherwise ``None``.
        """
        if not isinstance(config, QQEnvironmentConfig):
            raise self.InvalidEnvironment()

        self._config_writer.save(config)

        if self._provider_factory is not None:
            self._provider_factory.invalidate()
        self._built_runtime_manager = None

        if self._connection_service is None:
            return None
        return self._connection_service.check_status()

    def connect(self) -> Any:
        """Auto-detect the bundled runtime, start it, and check the connection.

        This is the one-click user path. The effective config already falls
        back to bundled defaults, so connecting only persists that default
        when no user config exists, starts the runtime when needed, and
        reports the resulting connection state. Nothing about QCE, runtime
        directories, or config files is exposed to the caller. A connect
        attempt never silently returns the idle "not connected" prompt: when
        no runtime can be started and the service is still unavailable, the
        caller gets an explicit failure status instead.
        """
        config = self._load_runtime_config()
        _LOGGER.info(
            "[qq setup] connect config_available=%s",
            config is not None,
        )
        runtime_status = None
        if config is not None and self._runtime_complete(config):
            self._persist_bundled_config_if_missing(config)
            if self._connection_service is not None:
                status = self._connection_service.check_status()
                if status.available:
                    _LOGGER.info("[qq setup] connect reused running QCE service")
                    return status
            runtime_status = self._runtime_manager_for(config).get_status()
            if runtime_status.state is not QQRuntimeState.RUNNING:
                _LOGGER.info(
                    "[qq setup] connect starting runtime state=%s",
                    runtime_status.state.value,
                )
                runtime_status = self._runtime_manager_for(config).start()
            if runtime_status.state is not QQRuntimeState.RUNNING:
                _LOGGER.info(
                    "[qq setup] connect runtime not ready state=%s",
                    runtime_status.state.value,
                )
                return self._connection_status_from_runtime(runtime_status)

        if self._connection_service is None:
            if runtime_status is not None:
                return self._connection_status_from_runtime(runtime_status)
            return self._connection_unavailable_status(self.check_setup())

        status = self._connection_service.check_status()
        if status.available or runtime_status is not None:
            return status

        from .qq_connection_service import QQConnectionStatus

        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=getattr(status, "version", None),
            message="\u65e0\u6cd5\u8fde\u63a5 QQ\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002",
            action_hint=(
                "QQ \u6570\u636e\u6e90\u6682\u4e0d\u53ef\u7528\uff0c"
                "\u8bf7\u786e\u8ba4\u5e94\u7528\u5b89\u88c5\u5b8c\u6574\u540e\u91cd\u8bd5\u3002"
            ),
        )

    def get_runtime_status(self) -> QQRuntimeStatus:
        """Return the current QQ runtime lifecycle status."""
        config = self._load_runtime_config()
        if config is None or not self._runtime_complete(config):
            return self._runtime_unavailable_status(self.check_setup())
        return self._runtime_manager_for(config).get_status()

    def start_runtime(self) -> QQRuntimeStatus:
        """Start the configured runtime and wait until it is ready."""
        config = self._load_runtime_config()
        if config is None or not self._runtime_complete(config):
            return self._runtime_unavailable_status(self.check_setup())
        return self._runtime_manager_for(config).start()

    def stop_runtime(self) -> QQRuntimeStatus:
        """Stop the configured runtime and clean up its process tree."""
        config = self._load_runtime_config()
        if config is None or not self._runtime_complete(config):
            return self._runtime_unavailable_status(self.check_setup())
        return self._runtime_manager_for(config).stop()

    def wait_runtime_ready(self, timeout: float = 30.0) -> QQRuntimeStatus:
        """Wait for a started runtime to become healthy."""
        config = self._load_runtime_config()
        if config is None or not self._runtime_complete(config):
            return self._runtime_unavailable_status(self.check_setup())
        return self._runtime_manager_for(config).wait_ready(timeout=timeout)

    # ---------------------------------------------------------------- internals

    @staticmethod
    def _runtime_complete(config: QQEnvironmentConfig) -> bool:
        required = (
            config.runtime_directory,
            config.qce_path,
        )
        return all(
            path is not None and path.exists() for path in required
        )

    def _config_path(self) -> Path | None:
        getter = getattr(self._config_loader, "config_path", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _load_runtime_config(self) -> QQEnvironmentConfig | None:
        try:
            return self._load_config_or_default()
        except Exception:
            return None

    def _load_config_or_default(self) -> QQEnvironmentConfig:
        loader = getattr(self._config_loader, "load_or_default", None)
        if callable(loader):
            return loader()
        return self._config_loader.load()

    def _runtime_manager_for(self, config: QQEnvironmentConfig) -> Any:
        if self._runtime_manager is not None:
            return self._runtime_manager
        if self._built_runtime_manager is None:
            self._built_runtime_manager = self._runtime_factory(config)
        return self._built_runtime_manager

    def _runtime_unavailable_status(
        self,
        config_status: QQSetupStatus,
    ) -> QQRuntimeStatus:
        return QQRuntimeStatus(
            state=QQRuntimeState.UNAVAILABLE,
            available=False,
            message=config_status.message or MESSAGE_RUNTIME_MANAGER_MISSING,
            action_hint=(
                config_status.action_hint
                or ACTION_HINT_RUNTIME_MANAGER_MISSING
            ),
        )

    def _persist_bundled_config_if_missing(
        self,
        config: QQEnvironmentConfig,
    ) -> None:
        """Write the detected config only when no user config exists yet."""
        try:
            self._config_loader.load()
        except QQConfigNotFound:
            pass
        except Exception:
            return
        else:
            return

        try:
            self._config_writer.save(config)
        except Exception:
            return
        if self._provider_factory is not None:
            self._provider_factory.invalidate()

    def _connection_unavailable_status(
        self,
        setup_status: QQSetupStatus,
    ) -> Any:
        from .qq_connection_service import QQConnectionStatus

        return QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message=setup_status.message or MESSAGE_RUNTIME_MANAGER_MISSING,
            action_hint=(
                setup_status.action_hint
                or ACTION_HINT_RUNTIME_MANAGER_MISSING
            ),
        )

    def _connection_status_from_runtime(
        self,
        runtime_status: QQRuntimeStatus,
    ) -> Any:
        from .qq_connection_service import QQConnectionStatus

        running = runtime_status.state is QQRuntimeState.RUNNING
        return QQConnectionStatus(
            available=running,
            qce_running=running,
            authenticated=False,
            version=runtime_status.version,
            message=runtime_status.message,
            action_hint=runtime_status.action_hint,
        )


def default_runtime_factory(config: QQEnvironmentConfig) -> Any:
    """Build a QQRuntimeManager from one QQ environment config."""
    from ..runtime import BundledQQRuntime, QQRuntimeConfig

    static_directory = None
    if config.runtime_directory is not None:
        static_directory = config.runtime_directory / "static" / "qce"

    runtime = BundledQQRuntime(
        QQRuntimeConfig(
            executable_path=config.qce_path,
            working_directory=config.runtime_directory or Path("."),
            base_url=config.base_url,
            config_directory=config.qce_config_directory,
            security_path=config.security_path,
            static_directory=static_directory,
            bridge_url=config.napcat_bridge_url,
            version=config.version,
        )
    )
    return QQRuntimeManager(runtime)


__all__ = [
    "QQSetupService",
    "QQSetupState",
    "QQSetupStatus",
    "default_runtime_factory",
]
