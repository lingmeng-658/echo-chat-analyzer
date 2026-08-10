"""Application-layer QQ environment configuration.

This module owns the durable settings that tell the QQ connection layer where
the local QQ client, NapCat-QCE runtime, and QCE service live. It does not
start processes, read chat data, or make runtime decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..resources import (
    default_qq_qce_path,
    default_qq_runtime_directory,
    default_qq_static_directory,
    user_data_dir,
)


CONFIG_DIRECTORY = "config"
CONFIG_FILENAME = "qq.json"
DEFAULT_QCE_BASE_URL = "http://127.0.0.1:40653"
DEFAULT_NAPCAT_BRIDGE_URL = "http://127.0.0.1:40654"


class QQEnvironmentConfigError(Exception):
    """Base error for reading or writing the QQ environment config."""

    code = "qq_environment_config_error"
    public_message = "QQ 数据源暂不可用。"

    def __init__(
        self,
        public_message: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class QQConfigNotFound(QQEnvironmentConfigError):
    """Raised when no QQ environment config file exists yet."""

    code = "qq_config_not_found"
    public_message = "QQ 数据源尚未连接。"


class QQConfigCorrupted(QQEnvironmentConfigError):
    """Raised when the QQ environment config cannot be parsed safely."""

    code = "qq_config_corrupted"
    public_message = "QQ 数据源暂不可用，请重新连接。"


class QQConfigWriteFailed(QQEnvironmentConfigError):
    """Raised when the QQ environment config cannot be written safely."""

    code = "qq_config_write_failed"
    public_message = "QQ 数据源配置保存失败，请稍后重试。"


@dataclass(frozen=True, slots=True)
class QQEnvironmentConfig:
    """Durable QQ environment settings loaded from disk."""

    qq_install_path: Path | None = None
    runtime_directory: Path | None = None
    qce_path: Path | None = None
    qce_config_directory: Path | None = None
    base_url: str = DEFAULT_QCE_BASE_URL
    security_path: Path | None = None
    napcat_bridge_url: str = DEFAULT_NAPCAT_BRIDGE_URL
    version: str | None = None


class QQEnvironmentConfigWriter:
    """Persist a QQ environment config as stable JSON."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        writer: Callable[[Path, str], None] | None = None,
    ) -> None:
        self._config_path = (
            Path(config_path)
            if config_path is not None
            else user_data_dir() / CONFIG_DIRECTORY / CONFIG_FILENAME
        )
        self._writer = writer or self._write_file

    def config_path(self) -> Path:
        return self._config_path

    def save(self, config: QQEnvironmentConfig) -> None:
        """Persist one config, raising a user-safe error on failure."""
        payload = {
            "qq_install_path": _stringify(config.qq_install_path),
            "runtime_directory": _stringify(config.runtime_directory),
            "qce_path": _stringify(config.qce_path),
            "qce_config_directory": _stringify(config.qce_config_directory),
            "base_url": config.base_url or DEFAULT_QCE_BASE_URL,
            "security_path": _stringify(config.security_path),
            "napcat_bridge_url": (
                config.napcat_bridge_url or DEFAULT_NAPCAT_BRIDGE_URL
            ),
            "version": config.version or None,
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer(self._config_path, body)
        except Exception:
            raise QQConfigWriteFailed() from None

    @staticmethod
    def _write_file(path: Path, body: str) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(body)


class QQEnvironmentConfigLoader:
    """Load a QQ environment config from user data."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = (
            Path(config_path)
            if config_path is not None
            else user_data_dir() / CONFIG_DIRECTORY / CONFIG_FILENAME
        )

    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> QQEnvironmentConfig:
        """Return a config, or raise a user-safe config error."""
        if not self._config_path.exists():
            raise QQConfigNotFound()

        try:
            with self._config_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise QQConfigCorrupted() from None

        if not isinstance(payload, dict):
            raise QQConfigCorrupted()

        return QQEnvironmentConfig(
            qq_install_path=_path_value(payload.get("qq_install_path")),
            runtime_directory=_path_value(payload.get("runtime_directory")),
            qce_path=_path_value(payload.get("qce_path")),
            qce_config_directory=_path_value(
                payload.get("qce_config_directory")
            ),
            base_url=(
                _string_value(payload.get("base_url"))
                or DEFAULT_QCE_BASE_URL
            ),
            security_path=_path_value(payload.get("security_path")),
            napcat_bridge_url=(
                _string_value(payload.get("napcat_bridge_url"))
                or DEFAULT_NAPCAT_BRIDGE_URL
            ),
            version=_string_value(payload.get("version")),
        )

    def load_or_default(self) -> QQEnvironmentConfig:
        """Load user config, falling back to bundled runtime defaults."""
        try:
            return self.load()
        except QQConfigNotFound:
            if bundled_qq_runtime_available():
                return default_qq_environment_config()
            raise


def bundled_qq_runtime_available() -> bool:
    """Return whether bundled QQ runtime components are present."""
    return (
        default_qq_qce_path().is_file()
        and default_qq_static_directory().is_dir()
        and (default_qq_runtime_directory() / "napcat.mjs").is_file()
    )


def default_qq_environment_config() -> QQEnvironmentConfig:
    """Return a config pointing at bundled QQ runtime components."""
    qce_config_directory = (
        user_data_dir() / "runtime" / "qq" / ".qce-config"
    )
    runtime_directory = (
        default_qq_runtime_directory()
        if default_qq_runtime_directory().is_dir()
        else None
    )
    return QQEnvironmentConfig(
        qq_install_path=None,
        runtime_directory=runtime_directory,
        qce_path=(
            default_qq_qce_path()
            if default_qq_qce_path().is_file()
            else None
        ),
        qce_config_directory=qce_config_directory,
        base_url=DEFAULT_QCE_BASE_URL,
        security_path=qce_config_directory / "security.json",
        napcat_bridge_url=DEFAULT_NAPCAT_BRIDGE_URL,
        version=None,
    )


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _path_value(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    text = _string_value(value)
    if text is None:
        return None
    return Path(text)


__all__ = [
    "DEFAULT_NAPCAT_BRIDGE_URL",
    "DEFAULT_QCE_BASE_URL",
    "QQConfigCorrupted",
    "QQConfigNotFound",
    "QQConfigWriteFailed",
    "QQEnvironmentConfig",
    "QQEnvironmentConfigError",
    "QQEnvironmentConfigLoader",
    "QQEnvironmentConfigWriter",
    "bundled_qq_runtime_available",
    "default_qq_environment_config",
]
