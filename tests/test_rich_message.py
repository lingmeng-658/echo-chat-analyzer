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
    MentionRelation,
    RecallEvent,
    RecallState,
    ReplyRelation,
    RichMessage,
    SenderIdentity,
    TextContent,
)


def _text_message(
    *,
    relations: tuple[ReplyRelation | MentionRelation, ...] = (),
) -> RichMessage:
    return RichMessage(
        message_id="fictional-message-1",
        source="qq",
        source_type="qce-json",
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


def test_rich_model_creates_a_text_message() -> None:
    message = _text_message()

    assert message.message_id == "fictional-message-1"
    assert message.source == "qq"
    assert message.conversation_id == "fictional-group-1"
    assert message.sender.identity_id == "fictional-user-1"
    assert message.sender.display_name == "Fictional Alice"
    assert message.contents == (TextContent(text="Hello from Rich Model"),)


def test_rich_model_keeps_a_reply_relation() -> None:
    relation = ReplyRelation(target_message_id="fictional-message-0")

    message = _text_message(relations=(relation,))

    assert message.relations == (relation,)


def test_rich_model_keeps_a_mention_relation() -> None:
    relation = MentionRelation(
        target_identity_id="fictional-user-2",
        display_text="@Fictional Bob",
    )

    message = _text_message(relations=(relation,))

    assert message.relations == (relation,)


def test_rich_model_distinguishes_recall_state_from_recall_event() -> None:
    event = RecallEvent(
        target_message_id="fictional-message-1",
        actor_identity_id="fictional-user-1",
        timestamp=1750000001000,
    )
    message = replace(
        _text_message(),
        recall_state=RecallState(is_recalled=True),
        recall_event=event,
    )

    assert message.recall_state == RecallState(is_recalled=True)
    assert message.recall_event == event


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
