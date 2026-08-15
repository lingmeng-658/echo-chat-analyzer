"""Tests for high-confidence repetitive message noise detection."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.detectors.noise_detector import detect_noise_candidates
from qq_chat_analyzer.message import ChatMessage


def test_detects_single_character_spam() -> None:
    candidates = detect_noise_candidates(
        [_message("虚构用户", "哈哈哈哈哈哈哈哈", 1_700_000_000)]
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.candidate_type == "noise_single_character_repeat"
    assert candidate.target == "哈哈哈哈哈哈哈哈"
    assert candidate.score == 1.0
    assert candidate.metadata["repeat_count"] == 8


def test_detects_repeated_fragment_meme() -> None:
    candidates = detect_noise_candidates(
        [_message("虚构用户", "芜湖起飞芜湖起飞芜湖起飞", 1_700_000_000)]
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.candidate_type == "noise_repeated_fragment"
    assert candidate.metadata["fragment"] == "芜湖起飞"
    assert candidate.metadata["repeat_count"] == 3


def test_detects_same_sender_short_interval_copy_paste() -> None:
    messages = [
        _message("虚构用户甲", "这句话被连续复制", 1_700_000_000),
        _message("虚构用户甲", "这句话被连续复制", 1_700_000_015),
        _message("虚构用户甲", "这句话被连续复制", 1_700_000_030),
    ]

    candidates = detect_noise_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.candidate_type == "noise_sender_burst_repeat"
    assert candidate.target == "这句话被连续复制"
    assert candidate.metadata["sender"] == "虚构用户甲"
    assert candidate.metadata["repeat_count"] == 3
    assert candidate.metadata["window_seconds"] == 30


def test_normal_long_messages_are_not_noise() -> None:
    messages = [
        _message(
            "虚构用户",
            "今天把本地分析流程重新整理了一遍，明天继续验证报告。",
            1_700_000_000,
        )
    ]

    assert detect_noise_candidates(messages) == []


def test_ordinary_frequent_words_are_not_noise() -> None:
    messages = [
        _message("虚构用户甲", "晚安", 1_700_000_000),
        _message("虚构用户乙", "晚安", 1_700_000_010),
        _message("虚构用户甲", "明天见", 1_700_000_020),
        _message("虚构用户甲", "晚安", 1_700_000_030),
    ]

    assert detect_noise_candidates(messages) == []


def test_small_emoji_expression_is_not_noise() -> None:
    messages = [
        _message("虚构用户", "😂😂", 1_700_000_000),
        _message("虚构用户", "👌", 1_700_000_010),
    ]

    assert detect_noise_candidates(messages) == []


def test_two_copies_or_copies_outside_window_are_not_noise() -> None:
    messages = [
        _message("虚构用户", "复制内容", 1_700_000_000),
        _message("虚构用户", "复制内容", 1_700_000_010),
        _message("虚构用户", "复制内容", 1_700_000_120),
    ]

    assert detect_noise_candidates(messages) == []


def test_interleaved_message_breaks_consecutive_copy_run() -> None:
    messages = [
        _message("虚构用户", "复制内容", 1_700_000_000),
        _message("虚构用户", "正常回复", 1_700_000_010),
        _message("虚构用户", "复制内容", 1_700_000_020),
        _message("虚构用户", "复制内容", 1_700_000_030),
    ]

    assert detect_noise_candidates(messages) == []


def _message(sender: str, text: str, timestamp: int) -> ChatMessage:
    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )
