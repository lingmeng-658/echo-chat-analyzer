"""Resolve display-safe expression assets for the Echo report."""

from __future__ import annotations

import base64
from pathlib import Path

from ..resources import resource_path


WECHAT_ASSET_ROOT = "frontend/echo_report/wechat-emojis"
WECHAT_ASSET_PREFIX = "wechat:"
QQ_ASSET_ROOT = "frontend/echo_report/qq-emojis"
QQ_ASSET_PREFIX = "qq:"

WECHAT_SOURCE = "wechat"
QQ_SOURCE = "qq"

_asset_index: dict[str, Path] | None = None
_qq_asset_index: dict[str, Path] | None = None


def wechat_asset_index() -> dict[str, Path]:
    """Return expression name -> bundled PNG path for official WeChat emojis."""
    global _asset_index
    if _asset_index is not None:
        return _asset_index
    root = resource_path(WECHAT_ASSET_ROOT)
    index: dict[str, Path] = {}
    if root.is_dir():
        for category_dir in root.iterdir():
            if not category_dir.is_dir():
                continue
            for asset in category_dir.glob("*.png"):
                index[asset.stem] = asset
    _asset_index = index
    return index


def qq_asset_index() -> dict[str, Path]:
    """Return QQ face id -> bundled PNG path for built-in QQ faces.

    Files are flat and named ``<face_id>.png`` so the mapping stays keyed on
    the numeric face id reported by the source, never on a translated name.
    """
    global _qq_asset_index
    if _qq_asset_index is not None:
        return _qq_asset_index
    root = resource_path(QQ_ASSET_ROOT)
    index: dict[str, Path] = {}
    if root.is_dir():
        for asset in root.glob("*.png"):
            index[asset.stem] = asset
    _qq_asset_index = index
    return index


def resolve_wechat_asset_key(expression_key: str) -> str | None:
    """Return a display-safe asset key, or None when no visual exists."""
    if expression_key in wechat_asset_index():
        return f"{WECHAT_ASSET_PREFIX}{expression_key}"
    return None


def resolve_qq_asset_key(expression_key: str) -> str | None:
    """Return a QQ face asset key, or None when the face id is unbundled."""
    if expression_key in qq_asset_index():
        return f"{QQ_ASSET_PREFIX}{expression_key}"
    return None


def resolve_expression_asset_key(
    expression_key: str,
    source: str | None,
) -> str | None:
    """Resolve an expression key strictly by its explicit platform source.

    Both platforms own numeric keys (WeChat ships a ``666`` emoji while QQ
    faces are numeric ids), so the caller's source context decides which
    bundle is consulted. An unknown or missing source resolves nothing
    instead of guessing through lookup order.
    """
    if not expression_key:
        return None
    if source == QQ_SOURCE:
        return resolve_qq_asset_key(expression_key)
    if source == WECHAT_SOURCE:
        return resolve_wechat_asset_key(expression_key)
    return None


def resolve_wechat_asset_data_uri(expression_key: str) -> str | None:
    """Return an inline data URI for a known official WeChat emoji."""
    path = wechat_asset_index().get(expression_key)
    if path is None or not path.is_file():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def resolve_qq_asset_data_uri(expression_key: str) -> str | None:
    """Return an inline data URI for a known built-in QQ face."""
    path = qq_asset_index().get(expression_key)
    if path is None or not path.is_file():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def expression_asset_data_uri(asset_key: str) -> str | None:
    """Resolve an asset_key produced by the presentation layer."""
    if asset_key.startswith(QQ_ASSET_PREFIX):
        return resolve_qq_asset_data_uri(asset_key[len(QQ_ASSET_PREFIX) :])
    if asset_key.startswith(WECHAT_ASSET_PREFIX):
        return resolve_wechat_asset_data_uri(
            asset_key[len(WECHAT_ASSET_PREFIX) :]
        )
    return None
