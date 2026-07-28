"""Text cleaning helpers for normalized QQ chat messages."""

from __future__ import annotations

import re
import unicodedata


_IMAGE_PLACEHOLDER_RE = re.compile(
    r"\[(?:图片|图像|动画表情|CQ:image)(?:[：:,，][^\]]*)?\]",
    flags=re.IGNORECASE,
)
_REPLY_MARKER_RE = re.compile(
    r"\[(?:回复消息|回复)(?:[：:][^\]]*)?\]",
)
_MENTION_ALL_RE = re.compile(r"(?<!\w)@全体成员")
_MENTION_RE = re.compile(r"(?<!\w)@[^\s@，。！？、,:;；]+")
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
_WHITESPACE_CONTROL_RE = re.compile(r"[\t\n\r\f\v]+")
_REPEATED_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Remove chat structure while preserving the user's actual wording."""
    if not isinstance(text, str):
        return ""

    cleaned = _IMAGE_PLACEHOLDER_RE.sub("", text)
    cleaned = _REPLY_MARKER_RE.sub("", cleaned)
    cleaned = _MENTION_ALL_RE.sub("", cleaned)
    cleaned = _MENTION_RE.sub("", cleaned)
    cleaned = _ZERO_WIDTH_RE.sub("", cleaned)

    # Newlines and tabs separate words, so normalize them before removing
    # other control and formatting characters.
    cleaned = _WHITESPACE_CONTROL_RE.sub(" ", cleaned)
    cleaned = "".join(
        character
        for character in cleaned
        if unicodedata.category(character) not in {"Cc", "Cf"}
    )

    return _REPEATED_WHITESPACE_RE.sub(" ", cleaned).strip()
