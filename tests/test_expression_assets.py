"""Behavior tests for the Echo expression asset resolver."""

from __future__ import annotations

import base64
import inspect
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.presentation import expression_assets  # noqa: E402
from qq_chat_analyzer.presentation.expression_assets import (  # noqa: E402
    expression_asset_data_uri,
    resolve_wechat_asset_data_uri,
    resolve_wechat_asset_key,
    wechat_asset_index,
)


#: A throwaway payload; tests only assert it round-trips through base64.
_FAKE_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfake-minimal-png"


def _source_aware_resolver():
    resolver = getattr(expression_assets, "resolve_expression_asset_key", None)
    assert callable(resolver), "unified expression asset resolver is missing"
    if "source" not in inspect.signature(resolver).parameters:
        pytest.fail(
            "resolver is not source-aware; it still guesses QQ before WeChat"
        )
    return resolver


def _qq_data_uri_resolver():
    resolver = getattr(expression_assets, "resolve_qq_asset_data_uri", None)
    assert callable(resolver), "QQ expression data URI resolver is missing"
    return resolver


@pytest.fixture
def qq_asset_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Point the QQ resolver at a throwaway directory of fake PNGs."""
    root = tmp_path / "qq-emojis"
    root.mkdir()
    monkeypatch.setattr(
        expression_assets, "QQ_ASSET_ROOT", str(root), raising=False
    )
    monkeypatch.setattr(
        expression_assets, "_qq_asset_index", None, raising=False
    )
    return root


def _write_qq_png(root: Path, face_id: str) -> None:
    (root / f"{face_id}.png").write_bytes(_FAKE_PNG_BYTES)


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


def test_source_explicit_resolver_disambiguates_666(qq_asset_root: Path) -> None:
    # A bundled QQ 666.png must never hijack the WeChat emoji named "666".
    _write_qq_png(qq_asset_root, "666")
    resolve = _source_aware_resolver()
    assert resolve("666", "wechat") == "wechat:666"
    assert resolve("666", "qq") == "qq:666"


def test_source_explicit_resolver_never_guesses_without_source(
    qq_asset_root: Path,
) -> None:
    _write_qq_png(qq_asset_root, "666")
    resolve = _source_aware_resolver()
    assert resolve("666", None) is None
    assert resolve("666", "unknown") is None


def test_qq_face_id_resolves_with_qq_source(qq_asset_root: Path) -> None:
    _write_qq_png(qq_asset_root, "265")
    assert _source_aware_resolver()("265", "qq") == "qq:265"


def test_qq_asset_key_resolves_to_data_uri(qq_asset_root: Path) -> None:
    _write_qq_png(qq_asset_root, "265")
    expected = "data:image/png;base64," + base64.b64encode(
        _FAKE_PNG_BYTES
    ).decode("ascii")
    assert _qq_data_uri_resolver()("265") == expected
    assert expression_asset_data_uri("qq:265") == expected


def test_qq_face_id_without_asset_falls_back_to_none(
    qq_asset_root: Path,
) -> None:
    assert _source_aware_resolver()("999", "qq") is None
    assert expression_asset_data_uri("qq:999") is None


def test_source_scopes_assets_to_their_own_index(qq_asset_root: Path) -> None:
    _write_qq_png(qq_asset_root, "265")
    resolve = _source_aware_resolver()
    # A QQ-only id must not leak into the WeChat source.
    assert resolve("265", "wechat") is None
    # WeChat names keep resolving, and never leak into the QQ source.
    assert resolve("捂脸", "wechat") == "wechat:捂脸"
    assert resolve("捂脸", "qq") is None
    assert expression_asset_data_uri("wechat:捂脸") is not None
