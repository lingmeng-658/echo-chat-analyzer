"""Behavior tests for the P0 Rich Semantic Model and legacy projection."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.legacy_projection import project_legacy_message
from qq_chat_analyzer.rich_message import (
    EXPRESSION_KIND_PLATFORM_FACE,
    EXPRESSION_KIND_STICKER,
    EXPRESSION_KIND_UNICODE,
    ExpressionContent,
    MentionRelation,
    RecallEvent,
    RecallState,
    ReplyRelation,
    RichMessage,
    SenderIdentity,
    TextContent,
)


def test_expression_content_defaults_keep_existing_construction_compatible() -> None:
    expression = ExpressionContent(
        expression_kind=EXPRESSION_KIND_STICKER,
        expression_key="fictional-sticker",
    )

    assert expression.source is None
    assert expression.position is None
    assert expression.text_before is None
    assert expression.text_after is None
    assert EXPRESSION_KIND_UNICODE == "unicode"
    assert EXPRESSION_KIND_PLATFORM_FACE == "platform_face"
    assert EXPRESSION_KIND_STICKER == "sticker"


def _text_message(
    *,
    relations: tuple[ReplyRelation | MentionRelation, ...] = (),
) -> RichMessage:
    return RichMessage(
        message_id="fictional-message-1",
        source="qq",
        source_type="qq-db-json",
        conversation_id="fictional-group-1",
        sender=SenderIdentity(
            identity_id="fictional-user-1",
            display_name="Fictional Alice",
        ),
        timestamp=1750000000000,
        message_type="text",
        contents=(TextContent(text="Hello from Rich Model"),),
        relations=relations,
    )


def test_legacy_projection_preserves_sender_text_and_timestamp() -> None:
    rich_message = _text_message(
        relations=(ReplyRelation(target_message_id="fictional-message-0"),)
    )

    legacy = project_legacy_message(rich_message)

    assert legacy.sender == "Fictional Alice"
    assert legacy.text == "Hello from Rich Model"
    assert legacy.timestamp == 1750000000000
    assert legacy.message_id == "fictional-message-1"
    assert legacy.sender_id == "fictional-user-1"
    assert legacy.conversation_id == "fictional-group-1"
