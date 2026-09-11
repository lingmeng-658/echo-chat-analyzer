"""Echo share-card presentation: builder, HTML template, and PNG rendering."""

from __future__ import annotations

from .builder import (
    SHARE_SUBTITLE,
    SHARE_TITLE,
    ShareCardData,
    ShareExpressionCombo,
    ShareExpressions,
    ShareLanguage,
    ShareRhythm,
    ShareSessions,
    build_share_card_data,
)
from .renderer import (
    SHARE_IMAGE_HEIGHT,
    SHARE_IMAGE_WIDTH,
    ShareImageRenderError,
    find_chromium,
    render_share_html_to_png,
)
from .template import build_share_card_html


__all__ = [
    "SHARE_IMAGE_HEIGHT",
    "SHARE_IMAGE_WIDTH",
    "SHARE_SUBTITLE",
    "SHARE_TITLE",
    "ShareCardData",
    "ShareExpressionCombo",
    "ShareExpressions",
    "ShareImageRenderError",
    "ShareLanguage",
    "ShareRhythm",
    "ShareSessions",
    "build_share_card_data",
    "build_share_card_html",
    "find_chromium",
    "render_share_html_to_png",
]
