"""Source-neutral P0 semantic model for chat messages."""

from __future__ import annotations

from dataclasses import dataclass


EXPRESSION_KIND_UNICODE = "unicode"
EXPRESSION_KIND_PLATFORM_FACE = "platform_face"
EXPRESSION_KIND_STICKER = "sticker"


@dataclass(frozen=True, slots=True)
class SenderIdentity:
    """Stable source identity plus its human-readable name."""

    identity_id: str | None
    display_name: str
    remark: str | None = None
    nickname: str | None = None
    contextual_name: str | None = None


@dataclass(frozen=True, slots=True)
class TextContent:
    """Text authored in the current message."""

    text: str


@dataclass(frozen=True, slots=True)
class ExpressionContent:
    """One source-neutral expression occurrence in a message."""

    expression_kind: str
    expression_key: str
    display_text: str | None = None
    source: str | None = None
    position: int | None = None
    text_before: str | None = None
    text_after: str | None = None


@dataclass(frozen=True, slots=True)
class ReplyRelation:
    """Relation from the current message to the replied-to message."""

    target_message_id: str


@dataclass(frozen=True, slots=True)
class MentionRelation:
    """Relation from the current message to a mentioned identity."""

    target_identity_id: str
    display_text: str | None = None


@dataclass(frozen=True, slots=True)
class RecallState:
    """Known recall state of a message; absence means the source did not say."""

    is_recalled: bool


@dataclass(frozen=True, slots=True)
class RecallEvent:
    """Known facts about an event that recalled a target message."""

    target_message_id: str
    actor_identity_id: str | None = None
    timestamp: int | float | str | None = None


RichContent = TextContent | ExpressionContent
MessageRelation = ReplyRelation | MentionRelation


@dataclass(frozen=True, slots=True)
class RichMessage:
    """P0 source-neutral message fact used before legacy projection."""

    message_id: str | None
    source: str
    conversation_id: str | None
    sender: SenderIdentity
    timestamp: int | float | str
    message_type: str
    contents: tuple[RichContent, ...]
    source_type: str | int | None = None
    relations: tuple[MessageRelation, ...] = ()
    recall_state: RecallState | None = None
    recall_event: RecallEvent | None = None
    is_system: bool = False
    conversation_type: str = "unknown"
    is_self: bool | None = None
