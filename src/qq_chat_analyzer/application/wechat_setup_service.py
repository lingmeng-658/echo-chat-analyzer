"""Application-layer setup for the WeChat environment.

The connection layer can only report "not configured" until something writes
``wechat.json``. This service is that something: it inspects the stored
configuration, saves a new one on the user's behalf, and refreshes the shared
provider factory so the next read observes the new settings.

Deliberate boundaries:

* No database access and no WeChat parsing happen here. When no key is
  configured, an injected key service may acquire one; otherwise this service
  only reads and writes application configuration.
* No GUI code. A widget calls this through
  :class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade` and never
  writes JSON itself.
* ``check_setup()`` never raises: an unreadable or damaged config becomes a
  status, so a caller can render guidance instead of a traceback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .errors import ApplicationServiceError
from .wechat_data_detector import (
    detect_wechat_data_roots,
    is_valid_wechat_data_root,
)
from .wechat_environment_config import (
    WeChatConfigNotFound,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigLoader,
    WeChatEnvironmentConfigWriter,
    default_wechat_environment_config,
)


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.wechat_setup_service")


MESSAGE_CONFIG_MISSING = (
    "尚未完成微信连接设置。"
)
ACTION_HINT_CONFIG_MISSING = (
    "请先完成微信连接设置，再连接微信。"
)
MESSAGE_CONFIG_READY = (
    "微信连接设置已保存。"
)
ACTION_HINT_CONFIG_READY = (
    "可以返回微信入口开始连接。"
)
MESSAGE_CONFIG_INVALID = (
    "微信连接设置无法使用。"
)
ACTION_HINT_CONFIG_INVALID = (
    "请重新设置微信连接。"
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
            "微信连接设置无效，请重新填写。"
        )

    def __init__(
        self,
        *,
        config_loader: Any = None,
        config_writer: Any = None,
        provider_factory: Any = None,
        connection_service: Any = None,
        key_service: Any = None,
        data_root_detector: Callable[[], Path | None] | None = None,
        data_roots_detector: Callable[[], list[Path]] | None = None,
    ) -> None:
        self._config_loader = config_loader or WeChatEnvironmentConfigLoader()
        self._config_writer = config_writer or WeChatEnvironmentConfigWriter()
        self._provider_factory = provider_factory
        self._connection_service = connection_service
        self._key_service = key_service
        self._data_root_detector = data_root_detector
        self._data_roots_detector = (
            data_roots_detector or detect_wechat_data_roots
        )

    def check_setup(self) -> WeChatSetupStatus:
        """Report whether a usable configuration is stored, never raising."""
        config_path = self._config_path()
        try:
            self._load_config_or_default()
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

    def detect_wechat_data_root(self) -> Path | None:
        """Return a detected local WeChat data directory, or ``None``."""
        if self._data_root_detector is not None:
            try:
                detected = self._data_root_detector()
            except Exception:
                return None
            if detected is None:
                return None
            detected_path = Path(detected)
            if is_valid_wechat_data_root(detected_path):
                return detected_path
            return None
        roots = self.detect_wechat_data_roots()
        if len(roots) == 1:
            return roots[0]
        return None

    def detect_wechat_data_roots(self) -> list[Path]:
        """Return every valid WeChat data directory detected locally.

        The caller decides what to do with several candidates; this service
        never picks one on the user's behalf.
        """
        saved = self._saved_valid_data_root()
        if saved is not None:
            return [saved]

        try:
            detected = self._data_roots_detector()
        except Exception:
            return []
        roots: list[Path] = []
        for value in detected or ():
            if value is None:
                continue
            path = Path(value)
            if is_valid_wechat_data_root(path) and path not in roots:
                roots.append(path)
        if len(roots) == 1 and is_valid_wechat_data_root(roots[0]):
            self._persist_detected_data_root(roots[0])
        return roots

    def save_environment(self, config: WeChatEnvironmentConfig) -> Any:
        """Persist a config, refresh the provider, and re-check connection.

        This only persists configuration. Acquiring the database key needs
        WeChat to be at a login moment, so it belongs to the connect flow via
        :meth:`acquire_db_key`; requiring it here made saving a data root fail
        whenever the user was not logging in. An explicit ``db_key`` on the
        incoming config is still written through untouched.

        The factory is invalidated only after a successful write, so a failed
        save leaves the previously working provider untouched. The return
        value is the refreshed connection status when a connection service is
        available, otherwise ``None``.
        """
        if not isinstance(config, WeChatEnvironmentConfig):
            raise self.InvalidEnvironment()

        config = self._merge_existing_config(config)
        config = self._apply_default_runtime(config)
        self._config_writer.save(config)

        if self._provider_factory is not None:
            self._provider_factory.invalidate()

        if self._connection_service is None:
            return None
        return self._connection_service.check_status()

    def acquire_db_key(
        self,
        progress: Callable[[str], None] | None = None,
    ) -> str | None:
        """Acquire the WeChat database key and persist it, for the connect flow.

        Returns the key, or ``None`` when no key service is configured. A
        failure propagates the key service's own user-safe error so the caller
        can show it verbatim. ``progress`` is forwarded to the key service so
        long waits can surface user-safe status lines.
        """
        if self._key_service is None:
            return None

        _LOGGER.info("[wechat setup] acquire_db_key progress=%s", progress is not None)
        key = self._key_service.acquire(progress=progress)
        if not key or not key.strip():
            return None

        key = key.strip()
        try:
            stored = self._config_loader.load()
        except Exception:
            stored = WeChatEnvironmentConfig()

        config = self._apply_default_runtime(replace(stored, db_key=key))
        self._config_writer.save(config)

        if self._provider_factory is not None:
            self._provider_factory.invalidate()
        return key

    def disconnect(self) -> Any:
        """Release the current WeChat connection key without deleting data.

        The stored data root and runtime paths stay in ``wechat.json``; only
        the database key is cleared, so the next connect flow re-acquires a
        fresh key through the existing path. Provider and process-local key
        state are also dropped.
        """
        _LOGGER.info("[wechat setup] disconnect requested")
        try:
            stored = self._config_loader.load()
        except WeChatConfigNotFound:
            stored = None

        if stored is not None:
            config = self._apply_default_runtime(replace(stored, db_key=None))
            self._config_writer.save(config)
            if self._provider_factory is not None:
                self._provider_factory.invalidate()

        clear = getattr(self._key_service, "clear", None)
        if callable(clear):
            clear()

        if self._connection_service is None:
            return None
        return self._connection_service.check_status()

    # ---------------------------------------------------------------- internals

    def _merge_existing_config(
        self,
        config: WeChatEnvironmentConfig,
    ) -> WeChatEnvironmentConfig:
        """Keep advanced values already stored when the GUI submits only a root."""
        try:
            existing = self._config_loader.load()
        except Exception:
            return config
        return replace(
            config,
            db_key=config.db_key or existing.db_key,
            wcdb_cli_path=config.wcdb_cli_path or existing.wcdb_cli_path,
            wcdb_dll_path=config.wcdb_dll_path or existing.wcdb_dll_path,
        )

    def _saved_valid_data_root(self) -> Path | None:
        try:
            root = self._config_loader.load().data_root
        except Exception:
            return None
        if root is None or not is_valid_wechat_data_root(root):
            return None
        return root

    def _persist_detected_data_root(self, root: Path) -> None:
        try:
            existing = self._config_loader.load()
        except Exception:
            existing = WeChatEnvironmentConfig()
        config = self._apply_default_runtime(
            replace(existing, data_root=root)
        )
        try:
            self._config_writer.save(config)
        except Exception:
            return
        if self._provider_factory is not None:
            self._provider_factory.invalidate()

    @staticmethod
    def _apply_default_runtime(
        config: WeChatEnvironmentConfig,
    ) -> WeChatEnvironmentConfig:
        defaults = default_wechat_environment_config()
        return replace(
            config,
            wcdb_cli_path=(
                config.wcdb_cli_path
                if config.wcdb_cli_path is not None
                and config.wcdb_cli_path.is_file()
                else defaults.wcdb_cli_path
            ),
            wcdb_dll_path=(
                config.wcdb_dll_path
                if config.wcdb_dll_path is not None
                and config.wcdb_dll_path.is_file()
                else defaults.wcdb_dll_path
            ),
        )
    def _ensure_db_key(
        self,
        config: WeChatEnvironmentConfig,
    ) -> WeChatEnvironmentConfig:
        if config.db_key and config.db_key.strip():
            return config
        if self._key_service is None:
            return config
        return replace(config, db_key=self._key_service.acquire())

    def _config_path(self) -> Path | None:
        getter = getattr(self._config_loader, "config_path", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            return None

    def _load_config_or_default(self) -> WeChatEnvironmentConfig:
        loader = getattr(self._config_loader, "load_or_default", None)
        if callable(loader):
            return loader()
        return self._config_loader.load()


__all__ = [
    "WeChatSetupService",
    "WeChatSetupState",
    "WeChatSetupStatus",
]
