"""Tests for behavior-based interactive bot candidate detection."""

from __future__ import annotations

import importlib.util

from qq_chat_analyzer.detectors.interactive_bot_detector import (
    detect_interactive_bot_candidates,
)
from qq_chat_analyzer.parser import ParsedMessage


BOT = "虚构交互助手"


def test_interactive_bot_detector_module_exists() -> None:
    spec = importlib.util.find_spec(
        "qq_chat_analyzer.detectors.interactive_bot_detector"
    )

    assert spec is not None


def test_frequent_mention_triggered_responses_create_high_confidence_candidate(
) -> None:
    messages: list[ParsedMessage] = []
    start_timestamp = 1_700_000_000_000
    for index in range(20):
        timestamp = start_timestamp + index * 10_000
        messages.extend(
            [
                _message(
                    f"虚构用户{index}",
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(
                    BOT,
                    f"虚构动态回复{index}",
                    timestamp + 1_000,
                ),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == BOT
    assert candidate.candidate_type == "automation_source"
    assert candidate.score >= 0.9
    assert candidate.reasons == [
        "high_mention_count",
        "high_response_rate",
    ]
    assert candidate.metadata == {
        "source_kind": "interactive_bot",
        "metrics": {
            "mention_count": 20,
            "response_count": 20,
            "response_rate": 1.0,
            "unique_trigger_source_count": 20,
            "response_template_score": 1.0,
        },
    }


def test_intervening_senders_do_not_prevent_response_detection() -> None:
    messages: list[ParsedMessage] = []
    for index in range(5):
        timestamp = index * 10
        messages.extend(
            [
                _message(
                    f"虚构提问者{index}",
                    f"@{BOT} 虚构命令",
                    timestamp,
                ),
                _message("虚构路人甲", "虚构普通聊天甲", timestamp + 1),
                _message("虚构路人乙", "虚构普通聊天乙", timestamp + 2),
                _message(BOT, f"虚构响应{index}", timestamp + 3),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert 0.6 <= candidate.score < 0.9
    assert candidate.score != candidate.metadata["metrics"]["response_rate"]
    assert candidate.metadata["metrics"] == {
        "mention_count": 5,
        "response_count": 5,
        "response_rate": 1.0,
        "unique_trigger_source_count": 5,
        "response_template_score": 1.0,
    }


def test_unique_trigger_source_count_counts_distinct_mention_senders(
) -> None:
    trigger_senders = [
        "虚构用户甲",
        "虚构用户乙",
        "虚构用户丙",
        "虚构用户甲",
        "虚构用户乙",
    ]
    messages: list[ParsedMessage] = []
    for index, trigger_sender in enumerate(trigger_senders):
        timestamp = index * 10
        messages.extend(
            [
                _message(
                    trigger_sender,
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(BOT, f"虚构响应{index}", timestamp + 1),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    assert (
        candidates[0]
        .metadata["metrics"]["unique_trigger_source_count"]
        == 3
    )


def test_unique_trigger_source_count_ignores_blank_senders() -> None:
    messages: list[ParsedMessage] = []
    for index in range(5):
        timestamp = index * 10
        messages.extend(
            [
                _message("", f"@{BOT} 虚构查询", timestamp),
                _message(BOT, f"虚构响应{index}", timestamp + 1),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    assert (
        candidates[0]
        .metadata["metrics"]["unique_trigger_source_count"]
        == 0
    )


def test_number_normalized_responses_have_high_template_score() -> None:
    messages: list[ParsedMessage] = []
    for index in range(5):
        timestamp = index * 10
        messages.extend(
            [
                _message(
                    f"虚构用户{index}",
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(
                    BOT,
                    f"虚构结果 {100 + index}",
                    timestamp + 1,
                ),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    assert (
        candidates[0]
        .metadata["metrics"]["response_template_score"]
        == 1.0
    )


def test_varied_responses_have_low_template_score() -> None:
    response_texts = [
        "虚构回答甲",
        "虚构建议乙",
        "虚构说明丙",
        "虚构分析丁",
        "虚构结论戊",
    ]
    messages: list[ParsedMessage] = []
    for index, response_text in enumerate(response_texts):
        timestamp = index * 10
        messages.extend(
            [
                _message(
                    f"虚构用户{index}",
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(BOT, response_text, timestamp + 1),
            ]
        )

    candidates = detect_interactive_bot_candidates(messages)

    assert len(candidates) == 1
    assert (
        candidates[0]
        .metadata["metrics"]["response_template_score"]
        == 0.2
    )


def test_low_response_rate_sender_is_not_a_candidate() -> None:
    messages: list[ParsedMessage] = []
    for index in range(10):
        timestamp = index * 10
        messages.append(
            _message(
                f"虚构用户{index}",
                f"@{BOT} 虚构讨论",
                timestamp,
            )
        )
        if index < 2:
            messages.append(
                _message(BOT, f"虚构人工回复{index}", timestamp + 1)
            )

    assert detect_interactive_bot_candidates(messages) == []


def test_fewer_than_five_mentions_is_not_a_candidate() -> None:
    messages: list[ParsedMessage] = []
    for index in range(4):
        timestamp = index * 10
        messages.extend(
            [
                _message(
                    f"虚构用户{index}",
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(BOT, f"虚构回复{index}", timestamp + 1),
            ]
        )

    assert detect_interactive_bot_candidates(messages) == []


def test_response_after_twenty_messages_is_outside_window() -> None:
    messages: list[ParsedMessage] = []
    for mention_index in range(5):
        timestamp = mention_index * 100
        messages.append(
            _message(
                f"虚构提问者{mention_index}",
                f"@{BOT} 虚构查询",
                timestamp,
            )
        )
        messages.extend(
            _message(
                f"虚构路人{filler_index}",
                f"虚构普通消息{filler_index}",
                timestamp + filler_index + 1,
            )
            for filler_index in range(20)
        )
        messages.append(
            _message(BOT, "虚构延迟响应", timestamp + 21)
        )

    assert detect_interactive_bot_candidates(messages) == []


def test_response_after_three_hundred_seconds_is_outside_window() -> None:
    messages: list[ParsedMessage] = []
    for index in range(5):
        timestamp = index * 1_000
        messages.extend(
            [
                _message(
                    f"虚构用户{index}",
                    f"@{BOT} 虚构查询",
                    timestamp,
                ),
                _message(BOT, "虚构超时响应", timestamp + 301),
            ]
        )

    assert detect_interactive_bot_candidates(messages) == []


def _message(
    sender: str,
    text: str,
    timestamp: int,
) -> ParsedMessage:
    return ParsedMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )
