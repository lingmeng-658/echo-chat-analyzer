"""One-way projection from rich message facts to legacy ChatMessage."""

from __future__ import annotations

from .message import ChatMessage
from .rich_message import RichMessage, TextContent


def project_legacy_message(message: RichMessage) -> ChatMessage:
    """Project the text-bearing subset consumed by existing analysis."""
    text = "".join(
        content.text
        for content in message.contents
        if isinstance(content, TextContent)
    )
    return ChatMessage(
        timestamp=message.timestamp,
        sender=message.sender.display_name,
        message_type=message.message_type,
        text=text,
        platform=message.source,
        source_type=message.source_type,
        message_id=message.message_id,
        sender_id=message.sender.identity_id,
        conversation_id=message.conversation_id,
        is_system=message.is_system,
        sender_remark=message.sender.remark,
        sender_nickname=message.sender.nickname,
        sender_contextual_name=message.sender.contextual_name,
        conversation_type=message.conversation_type,
        is_self=message.is_self,
        recalled=(
            message.recall_state.is_recalled
            if message.recall_state is not None
            else False
        ),
    )


def project_legacy_messages(
    messages: list[RichMessage] | tuple[RichMessage, ...],
) -> list[ChatMessage]:
    """Project a sequence while preserving its order."""
    return [project_legacy_message(message) for message in messages]
