"""Contract tests for the vendored official WeChat emoji dictionary."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.wechat_official_emojis import (  # noqa: E402
    OFFICIAL_WECHAT_EMOJI_NAMES,
)


def test_dictionary_contains_target_official_emoji_names() -> None:
    assert {"捂脸", "旺柴", "裂开"} <= OFFICIAL_WECHAT_EMOJI_NAMES


def test_dictionary_matches_vendored_wechat_emoji_asset_count() -> None:
    assert len(OFFICIAL_WECHAT_EMOJI_NAMES) == 109


def test_dictionary_names_are_non_empty_without_brackets() -> None:
    assert all(name and "[" not in name and "]" not in name for name in OFFICIAL_WECHAT_EMOJI_NAMES)
