"""Tests for deterministic local message quality filtering."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.message_quality_filter import (
    LONG_TEXT_THRESHOLD,
    apply_message_quality_filter,
)


def test_messages_at_least_100_characters_are_filtered() -> None:
    long_text = _long_text(LONG_TEXT_THRESHOLD)
    message = _message("虚构用户", long_text, 1_700_000_000)

    result = apply_message_quality_filter([message])

    assert len(long_text) == LONG_TEXT_THRESHOLD
    assert result.kept_messages == []
    assert result.filtered_messages == [message]
    assert len(result.reasons) == 1
    reason = result.reasons[0]
    assert reason.message is message
    assert reason.reason == "long_text_outlier"
    assert reason.metadata == {
        "length": LONG_TEXT_THRESHOLD,
        "threshold": LONG_TEXT_THRESHOLD,
    }


def test_99_character_normal_message_is_kept() -> None:
    normal_long_text = _long_text(LONG_TEXT_THRESHOLD - 1)
    message = _message("虚构用户", normal_long_text, 1_700_000_000)

    result = apply_message_quality_filter([message])

    assert len(normal_long_text) == LONG_TEXT_THRESHOLD - 1
    assert result.kept_messages == [message]
    assert result.filtered_messages == []
    assert result.reasons == []


def test_single_character_repeat_spam_is_filtered() -> None:
    message = _message("虚构用户", "哈哈哈哈哈哈哈哈", 1_700_000_000)

    result = apply_message_quality_filter([message])

    assert result.kept_messages == []
    assert result.filtered_messages == [message]
    assert result.reasons[0].reason == "noise_single_character_repeat"


def test_repeated_fragment_meme_is_filtered() -> None:
    message = _message("虚构用户", "芜湖起飞" * 3, 1_700_000_000)

    result = apply_message_quality_filter([message])

    assert result.kept_messages == []
    assert result.filtered_messages == [message]
    assert result.reasons[0].reason == "noise_repeated_fragment"


def test_same_text_burst_within_60_seconds_keeps_only_first() -> None:
    first = _message("虚构用户甲", "这句话被连续复制", 1_700_000_000)
    second = _message("虚构用户甲", "这句话被连续复制", 1_700_000_015)
    third = _message("虚构用户甲", "这句话被连续复制", 1_700_000_030)

    result = apply_message_quality_filter([first, second, third])

    assert result.kept_messages == [first]
    assert result.filtered_messages == [second, third]
    assert [reason.reason for reason in result.reasons] == [
        "noise_sender_burst_repeat",
        "noise_sender_burst_repeat",
    ]
    assert all(
        reason.metadata["repeat_count"] == 3 for reason in result.reasons
    )


def test_normal_chat_is_not_mis_filtered() -> None:
    messages = [
        _message("虚构用户甲", "今天天气不错，我们晚上一起吃饭吧", 1_700_000_000),
        _message("虚构用户甲", "哈哈哈", 1_700_000_010),
        _message("虚构用户乙", "😂😂", 1_700_000_020),
        _message("虚构用户乙", "好的，七点见", 1_700_000_030),
        _message("虚构用户甲", "明天见", 1_700_000_040),
    ]

    result = apply_message_quality_filter(messages)

    assert result.kept_messages == messages
    assert result.filtered_messages == []
    assert result.reasons == []


def test_two_identical_messages_are_not_a_burst() -> None:
    first = _message("虚构用户", "复制内容", 1_700_000_000)
    second = _message("虚构用户", "复制内容", 1_700_000_010)

    result = apply_message_quality_filter([first, second])

    assert result.kept_messages == [first, second]
    assert result.filtered_messages == []


def test_original_messages_are_never_removed_from_input() -> None:
    messages = [
        _message("虚构用户", "哈哈哈哈哈哈哈哈", 1_700_000_000),
        _message("虚构用户", "正常消息", 1_700_000_010),
    ]
    snapshot = list(messages)

    result = apply_message_quality_filter(messages)

    assert messages == snapshot
    assert len(messages) == 2
    assert set(result.kept_messages) | set(result.filtered_messages) == set(messages)


def test_empty_input_returns_empty_partition() -> None:
    result = apply_message_quality_filter([])

    assert result.kept_messages == []
    assert result.filtered_messages == []
    assert result.reasons == []


def _long_text(length: int) -> str:
    base = (
        "本地聊天分析工具只在本机处理数据，不依赖任何网络服务，"
        "所有隐私信息都不会离开这台电脑，这是设计上最重要的原则。"
    )
    return (base * 3)[:length]


def _message(sender: str, text: str, timestamp: int) -> ChatMessage:
    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )