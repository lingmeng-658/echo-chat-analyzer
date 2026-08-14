"""Behavior tests for the Echo expression asset resolver."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.presentation.expression_assets import (  # noqa: E402
    expression_asset_data_uri,
    resolve_wechat_asset_data_uri,
    resolve_wechat_asset_key,
    wechat_asset_index,
)


def test_known_wechat_emoji_resolves_to_asset() -> None:
    for name in ("捂脸", "旺柴", "裂开"):
        assert resolve_wechat_asset_key(name) == f"wechat:{name}"
        uri = resolve_wechat_asset_data_uri(name)
        assert uri is not None
        assert uri.startswith("data:image/png;base64,")
        assert expression_asset_data_uri(f"wechat:{name}") == uri


def test_unknown_key_returns_fallback_none() -> None:
    assert resolve_wechat_asset_key("not-a-real-emoji") is None
    assert resolve_wechat_asset_data_uri("not-a-real-emoji") is None
    assert expression_asset_data_uri("wechat:not-a-real-emoji") is None
    assert expression_asset_data_uri("qq:not-supported") is None


def test_asset_index_matches_vendored_dictionary_count() -> None:
    assert len(wechat_asset_index()) == 109
