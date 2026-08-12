"""Message composition analysis over normalized chat messages."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import MessageCompositionCategory, MessageCompositionReport
from ...message import ChatMessage


_TEXT_CATEGORY = "文本"
_IMAGE_CATEGORY = "图片"
_VIDEO_CATEGORY = "视频"
_FILE_CATEGORY = "文件"
_OTHER_CATEGORY = "其他"

_SYSTEM_TYPE = "system"

_DISPLAY_CATEGORIES = (
    _TEXT_CATEGORY,
    _IMAGE_CATEGORY,
    _VIDEO_CATEGORY,
    _FILE_CATEGORY,
    _OTHER_CATEGORY,
)

_CATEGORY_BY_TYPE = {
    "text": _TEXT_CATEGORY,
    "reply": _TEXT_CATEGORY,
    "image": _IMAGE_CATEGORY,
    "video": _VIDEO_CATEGORY,
    "file": _FILE_CATEGORY,
}


def _normalized_type(message_type: str) -> str:
    return message_type.strip().lower()


class MessageCompositionAnalyzer:
    """Count messages by display category, ignoring system messages."""

    def analyze(
        self,
        messages: Sequence[ChatMessage],
    ) -> MessageCompositionReport:
        counts = {category: 0 for category in _DISPLAY_CATEGORIES}

        for message in messages:
            if self._is_system_message(message):
                continue
            category = _CATEGORY_BY_TYPE.get(
                _normalized_type(message.message_type),
                _OTHER_CATEGORY,
            )
            counts[category] += 1

        return MessageCompositionReport(
            total_count=sum(counts.values()),
            categories=tuple(
                MessageCompositionCategory(
                    category=category,
                    count=counts[category],
                )
                for category in _DISPLAY_CATEGORIES
            ),
        )

    @staticmethod
    def _is_system_message(message: ChatMessage) -> bool:
        if message.is_system:
            return True
        return _normalized_type(message.message_type) == _SYSTEM_TYPE
