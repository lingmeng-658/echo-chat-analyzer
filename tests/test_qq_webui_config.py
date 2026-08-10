"""Tests for QCE WebUI auto-open config control.

Only temp files are used; the real QCE user config under the home directory
is never touched.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_webui_config"
    )


def test_default_config_path_points_to_qce_user_config() -> None:
    module = _module()

    path = module.qce_user_config_path()

    assert path.name == module.QCE_USER_CONFIG_FILENAME
    assert path.parent.name == module.QCE_CONFIG_DIR_NAME


def test_disable_creates_config_when_missing(tmp_path: Path) -> None:
    module = _module()
    config_path = tmp_path / "user-config.json"

    result = module.disable_qce_auto_open_browser(config_path)

    assert result is True
    payload = _read_json(config_path)
    assert payload["autoOpenBrowser"] is False


def test_disable_preserves_existing_config_keys(tmp_path: Path) -> None:
    module = _module()
    config_path = tmp_path / "user-config.json"
    config_path.write_text(
        '{"customOutputDir": "C:/exports", "autoOpenBrowser": true}',
        encoding="utf-8",
    )

    result = module.disable_qce_auto_open_browser(config_path)

    assert result is True
    payload = _read_json(config_path)
    assert payload["autoOpenBrowser"] is False
    assert payload["customOutputDir"] == "C:/exports"


def test_disable_repairs_corrupt_config(tmp_path: Path) -> None:
    module = _module()
    config_path = tmp_path / "user-config.json"
    config_path.write_text("not json", encoding="utf-8")

    result = module.disable_qce_auto_open_browser(config_path)

    assert result is True
    payload = _read_json(config_path)
    assert payload == {"autoOpenBrowser": False}


def test_disable_returns_false_when_write_impossible(tmp_path: Path) -> None:
    module = _module()
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    config_path = blocked / "user-config.json"

    result = module.disable_qce_auto_open_browser(config_path)

    assert result is False


def _read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
