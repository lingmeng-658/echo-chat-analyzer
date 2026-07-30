"""Tests for statistical robot sender candidate detection."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.detectors.robot_detector import (
    detect_robot_candidates,
)
from qq_chat_analyzer.parser import ParsedMessage


def test_repetitive_sender_becomes_robot_candidate() -> None:
    messages = [
        _message("虚构警卫犬", "签到成功", index)
        for index in range(12)
    ]
    messages.extend(
        _message("虚构普通用户", f"今天讨论话题 {index}", index + 12)
        for index in range(10)
    )

    candidates = detect_robot_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == "虚构警卫犬"
    assert candidate.candidate_type == "robot_sender"
    assert 0.0 <= candidate.score <= 1.0
    assert candidate.score >= 0.7
    assert candidate.reasons == [
        "high_message_ratio",
        "high_repeat_rate",
        "high_template_concentration",
    ]
    assert candidate.metadata == {
        "message_count": 12,
        "message_ratio": 0.5455,
        "unique_message_count": 1,
        "repeat_rate": 0.9167,
        "template_concentration": 1.0,
    }


def test_diverse_sender_is_not_high_confidence_robot_candidate() -> None:
    messages = [
        _message("虚构用户甲", f"不同内容甲 {index} 主题 {index * 7}", index)
        for index in range(12)
    ]
    messages.extend(
        _message(
            "虚构用户乙",
            f"不同内容乙 {index} 讨论 {index * 11}",
            index + 12,
        )
        for index in range(12)
    )

    assert detect_robot_candidates(messages) == []


def test_numbered_fixed_format_contributes_template_signal() -> None:
    messages = [
        _message("虚构任务助手", f"任务 {index} 已完成", index)
        for index in range(8)
    ]
    messages.extend(
        [
            _message("虚构普通用户", "今天去图书馆", 8),
            _message("虚构普通用户", "晚上继续学习", 9),
        ]
    )

    candidates = detect_robot_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == "虚构任务助手"
    assert "high_message_ratio" in candidate.reasons
    assert "high_template_concentration" in candidate.reasons
    assert "high_repeat_rate" not in candidate.reasons
    assert candidate.metadata["template_concentration"] == 1.0
    assert candidate.metadata["repeat_rate"] == 0.0


def test_empty_messages_have_no_candidates() -> None:
    assert detect_robot_candidates([]) == []


def _message(sender: str, text: str, timestamp: int) -> ParsedMessage:
    return ParsedMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )
