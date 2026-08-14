"""Behavior tests for source-neutral expression frequency analysis."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.analysis.analyzers.expression_analyzer import (
    EXPRESSION_KIND_PLATFORM_FACE,
    EXPRESSION_KIND_UNICODE,
    ExpressionAnalyzer,
)
from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.rich_message import (
    ExpressionContent,
    RichMessage,
    SenderIdentity,
    TextContent,
)


def _chat(
    text: str,
    *,
    sender_id: str = "fictional-user-1",
    message_id: str = "fictional-message-1",
) -> ChatMessage:
    return ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text=text,
        platform="qq",
        sender_id=sender_id,
        message_id=message_id,
        conversation_type="group",
    )


def _rich(
    message_id: str,
    *,
    text: str = "",
    faces: tuple[ExpressionContent, ...] = (),
) -> RichMessage:
    contents: list[object] = []
    if text:
        contents.append(TextContent(text=text))
    contents.extend(faces)
    return RichMessage(
        message_id=message_id,
        source="qq",
        conversation_id="fictional-group",
        sender=SenderIdentity(
            identity_id="fictional-user-1",
            display_name="Fictional Alice",
        ),
        timestamp=1,
        message_type="text",
        contents=tuple(contents),
        conversation_type="group",
    )


def test_unicode_emoji_clusters_are_counted_and_attributed() -> None:
    messages = [
        _chat("今天 😀 😀 加油", sender_id="fictional-a", message_id="m1"),
        _chat(
            "👍🏽 和 👨‍👩‍👧 和 🇨🇳",
            sender_id="fictional-b",
            message_id="m2",
        ),
    ]

    report = ExpressionAnalyzer().analyze(messages)

    assert report.expression_message_count == 2
    assert report.expression_occurrence_count == 5
    assert report.unique_expression_count == 4
    assert {item.expression_key for item in report.top_expressions} == {
        "😀",
        "👍🏽",
        "👨‍👩‍👧",
        "🇨🇳",
    }
    assert all(item.kind == EXPRESSION_KIND_UNICODE for item in report.top_expressions)
    assert report.members[0].speaker_key == "fictional-b"
    assert report.members[0].expression_occurrence_count == 3


def test_platform_face_from_rich_message_counts_as_expression_only() -> None:
    message = _chat("", sender_id="fictional-a", message_id="m1")
    rich = _rich(
        "m1",
        faces=(
            ExpressionContent(
                expression_kind=EXPRESSION_KIND_PLATFORM_FACE,
                expression_key="358",
                display_text="/骰子",
            ),
        ),
    )

    report = ExpressionAnalyzer().analyze([message], rich_messages=[rich])

    assert report.expression_message_count == 1
    assert report.expression_only_message_count == 1
    assert report.expression_only_rate == 1.0
    assert report.top_expressions[0].kind == EXPRESSION_KIND_PLATFORM_FACE
    assert report.top_expressions[0].expression_key == "358"
    assert report.members[0].expression_only_message_count == 1


def test_mixed_text_and_face_message_is_not_expression_only() -> None:
    message = _chat("哈哈 😂 来了", sender_id="fictional-a", message_id="m1")
    rich = _rich(
        "m1",
        text="哈哈 😂 来了",
        faces=(
            ExpressionContent(
                expression_kind=EXPRESSION_KIND_PLATFORM_FACE,
                expression_key="66",
                display_text="[QQ表情 66]",
            ),
        ),
    )

    report = ExpressionAnalyzer().analyze([message], rich_messages=[rich])

    assert report.expression_message_count == 1
    assert report.expression_only_message_count == 0
    assert report.unique_expression_count == 2
    assert {item.expression_key for item in report.top_expressions} == {
        "😂",
        "66",
    }


def test_unicode_fallback_uses_chat_message_text_without_rich() -> None:
    messages = [_chat("收到 😀", sender_id="fictional-a", message_id="m1")]

    report = ExpressionAnalyzer().analyze(messages)

    assert report.expression_message_count == 1
    assert report.expression_only_message_count == 0
    assert report.top_expressions[0].expression_key == "😀"


def test_rich_message_matching_falls_back_per_message_id() -> None:
    messages = [
        _chat("", sender_id="fictional-a", message_id="with-face"),
        _chat("晚安 😴", sender_id="fictional-b", message_id="text-only"),
    ]
    rich = _rich(
        "with-face",
        faces=(
            ExpressionContent(
                expression_kind=EXPRESSION_KIND_PLATFORM_FACE,
                expression_key="7",
                display_text="[QQ表情 7]",
            ),
        ),
    )

    report = ExpressionAnalyzer().analyze(messages, rich_messages=[rich])

    assert report.expression_message_count == 2
    assert {item.expression_key for item in report.top_expressions} == {
        "7",
        "😴",
    }
    assert report.members[0].expression_occurrence_count == 1
    assert report.members[1].expression_occurrence_count == 1


def test_report_is_empty_without_expressions() -> None:
    report = ExpressionAnalyzer().analyze(
        [_chat("普通文本", message_id="plain")]
    )

    assert report.expression_message_count == 0
    assert report.expression_only_message_count == 0
    assert report.unique_expression_count == 0
    assert report.top_expressions == ()
    assert report.members == ()


def test_expression_analyzer_has_no_platform_branches() -> None:
    source = (
        SRC_ROOT / "qq_chat_analyzer" / "analysis" / "analyzers" / "expression_analyzer.py"
    ).read_text(encoding="utf-8")

    for marker in ("wechat", "wxid", "chatroom", '"qq"', "'qq'"):
        assert marker not in source
