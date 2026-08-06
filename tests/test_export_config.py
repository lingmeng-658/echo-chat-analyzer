"""Contract tests for the ExportConfig domain model."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import ExportConfig


def test_export_config_defaults_to_text_only() -> None:
    config = ExportConfig()

    assert config.include_text is True
    assert config.include_avatar is False
    assert config.include_image is False
    assert config.include_file is False
    assert config.include_media is False


def test_export_config_preserves_explicit_choices() -> None:
    config = ExportConfig(
        include_text=True,
        include_avatar=True,
        include_image=True,
        include_file=True,
        include_media=True,
    )

    assert config.include_text is True
    assert config.include_avatar is True
    assert config.include_image is True
    assert config.include_file is True
    assert config.include_media is True
