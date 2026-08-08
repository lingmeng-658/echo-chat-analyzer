"""Behavior tests for the WeChat environment config loader.

All tests use temporary config files. No real WeChat data, key, or runtime
path is touched.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application.wechat_environment_config import (  # noqa: E402
    WeChatConfigCorrupted,
    WeChatConfigNotFound,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigLoader,
)


def _loader(tmp_path: Path, payload: object) -> WeChatEnvironmentConfigLoader:
    config_path = tmp_path / "wechat.json"
    if isinstance(payload, str):
        config_path.write_text(payload, encoding="utf-8")
    else:
        config_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    return WeChatEnvironmentConfigLoader(config_path)


def test_loader_reads_a_complete_config(tmp_path: Path) -> None:
    loader = _loader(
        tmp_path,
        {
            "data_root": "D:\\WeChatData\\xwechat_files",
            "db_key": "a" * 64,
            "wcdb_cli_path": "C:\\tools\\wcdb_cli.exe",
            "wcdb_dll_path": "C:\\tools\\WCDB.dll",
        },
    )

    config = loader.load()

    assert config.data_root == Path("D:\\WeChatData\\xwechat_files")
    assert config.db_key == "a" * 64
    assert config.wcdb_cli_path == Path("C:\\tools\\wcdb_cli.exe")
    assert config.wcdb_dll_path == Path("C:\\tools\\WCDB.dll")
    assert dataclasses.is_dataclass(config)


def test_loader_treats_missing_config_as_a_user_safe_error(
    tmp_path: Path,
) -> None:
    loader = WeChatEnvironmentConfigLoader(tmp_path / "absent.json")

    with pytest.raises(WeChatConfigNotFound) as excinfo:
        loader.load()

    assert excinfo.value.code == "wechat_config_not_found"
    assert excinfo.value.public_message != ""


def test_loader_treats_corrupted_config_as_a_user_safe_error(
    tmp_path: Path,
) -> None:
    loader = _loader(tmp_path, "{not-json")

    with pytest.raises(WeChatConfigCorrupted) as excinfo:
        loader.load()

    assert excinfo.value.code == "wechat_config_corrupted"
    assert excinfo.value.public_message != ""
    assert "not-json" not in str(excinfo.value)


def test_loader_treats_non_object_json_as_corrupted(tmp_path: Path) -> None:
    loader = _loader(tmp_path, ["not", "a", "config"])

    with pytest.raises(WeChatConfigCorrupted):
        loader.load()


def test_loader_tolerates_missing_fields(tmp_path: Path) -> None:
    loader = _loader(tmp_path, {})

    config = loader.load()

    assert config == WeChatEnvironmentConfig()
    assert config.data_root is None
    assert config.db_key is None
    assert config.wcdb_cli_path is None
    assert config.wcdb_dll_path is None


def test_loader_parses_path_fields_and_ignores_empty_values(
    tmp_path: Path,
) -> None:
    loader = _loader(
        tmp_path,
        {
            "data_root": "C:\\WeChat",
            "db_key": "",
            "wcdb_cli_path": 123,
            "wcdb_dll_path": "   ",
        },
    )

    config = loader.load()

    assert config.data_root == Path("C:\\WeChat")
    assert config.db_key is None
    assert config.wcdb_cli_path is None
    assert config.wcdb_dll_path is None


def test_environment_config_is_frozen() -> None:
    config = WeChatEnvironmentConfig(data_root=Path("C:\\WeChat"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.data_root = Path("D:\\Other")
