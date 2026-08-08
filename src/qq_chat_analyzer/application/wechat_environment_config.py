"""Application-layer WeChat environment configuration.

This module owns the durable configuration that tells the WeChat connection
layer where the local data and native runtime live. It does not read
databases, parse chat messages, or make any runtime decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..resources import user_data_dir


CONFIG_DIRECTORY = "config"
CONFIG_FILENAME = "wechat.json"


class WeChatEnvironmentConfigError(Exception):
    """Base error for reading or validating the WeChat environment config."""

    code = "wechat_environment_config_error"
    public_message = "\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\u65e0\u6cd5\u4f7f\u7528\u3002"

    def __init__(
        self,
        public_message: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class WeChatConfigNotFound(WeChatEnvironmentConfigError):
    """Raised when no configuration file exists yet."""

    code = "wechat_config_not_found"
    public_message = (
        "\u672a\u627e\u5230\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\uff0c"
        "\u8bf7\u5148\u5b8c\u6210\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u3002"
    )


class WeChatConfigCorrupted(WeChatEnvironmentConfigError):
    """Raised when the configuration file cannot be parsed safely."""

    code = "wechat_config_corrupted"
    public_message = (
        "\u5fae\u4fe1\u73af\u5883\u914d\u7f6e\u635f\u574f\uff0c"
        "\u8bf7\u91cd\u65b0\u8bbe\u7f6e\u3002"
    )


@dataclass(frozen=True, slots=True)
class WeChatEnvironmentConfig:
    """Durable WeChat environment settings loaded from disk."""

    data_root: Path | None = None
    db_key: str | None = None
    wcdb_cli_path: Path | None = None
    wcdb_dll_path: Path | None = None


class WeChatEnvironmentConfigLoader:
    """Load a WeChat environment config from user data."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = (
            Path(config_path)
            if config_path is not None
            else user_data_dir() / CONFIG_DIRECTORY / CONFIG_FILENAME
        )

    def config_path(self) -> Path:
        return self._config_path

    def load(self) -> WeChatEnvironmentConfig:
        """Return a config, or raise a user-safe config error."""
        if not self._config_path.exists():
            raise WeChatConfigNotFound()

        try:
            with self._config_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            raise WeChatConfigCorrupted() from None

        if not isinstance(payload, dict):
            raise WeChatConfigCorrupted()

        return WeChatEnvironmentConfig(
            data_root=_path_value(payload.get("data_root")),
            db_key=_string_value(payload.get("db_key")),
            wcdb_cli_path=_path_value(payload.get("wcdb_cli_path")),
            wcdb_dll_path=_path_value(payload.get("wcdb_dll_path")),
        )


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _path_value(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    text = _string_value(value)
    if text is None:
        return None
    return Path(text)


__all__ = [
    "WeChatConfigCorrupted",
    "WeChatConfigNotFound",
    "WeChatEnvironmentConfig",
    "WeChatEnvironmentConfigError",
    "WeChatEnvironmentConfigLoader",
]
