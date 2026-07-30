"""Tests for repeated message template candidate detection."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.detectors.template_detector import (
    detect_template_candidates,
)
from qq_chat_analyzer.parser import ParsedMessage


def test_welcome_messages_form_welcome_template_candidate() -> None:
    welcome_messages = [
        "欢迎 虚构张三 加入群聊",
        "欢迎 虚构李四 加入群聊",
        "欢迎 虚构王五 加入群聊",
    ]
    messages = [
        _message("虚构欢迎助手", text, index)
        for index, text in enumerate(welcome_messages)
    ]
    messages.extend(
        [
            _message("虚构用户", "大家晚上好", 3),
            _message("虚构用户", "今天讨论什么", 4),
        ]
    )

    candidates = detect_template_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == "欢迎 {variable} 加入群聊"
    assert candidate.candidate_type == "welcome_template"
    assert 0.0 <= candidate.score <= 1.0
    assert candidate.reasons == ["high_frequency", "high_similarity"]
    assert candidate.metadata == {
        "matched_message_count": 3,
        "match_ratio": 0.6,
        "template_examples": welcome_messages,
        "similarity": 1.0,
    }


def test_number_changes_form_repeated_template_candidate() -> None:
    numbered_messages = [
        "签到成功，积分+10",
        "签到成功，积分+20",
        "签到成功，积分+30",
    ]
    messages = [
        _message("虚构签到助手", text, index)
        for index, text in enumerate(numbered_messages)
    ]

    candidates = detect_template_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == "签到成功，积分+{variable}"
    assert candidate.candidate_type == "repeated_template"
    assert candidate.reasons == ["high_frequency", "high_similarity"]
    assert candidate.metadata["matched_message_count"] == 3
    assert candidate.metadata["template_examples"] == numbered_messages
    assert candidate.metadata["similarity"] == 1.0


def test_diverse_ordinary_chat_has_no_template_candidates() -> None:
    messages = [
        _message("虚构用户甲", "今天吃什么？", 0),
        _message("虚构用户乙", "晚上打游戏吗？", 1),
        _message("虚构用户丙", "明天去图书馆", 2),
        _message("虚构用户丁", "作业写完了吗？", 3),
    ]

    assert detect_template_candidates(messages) == []


def test_empty_messages_have_no_template_candidates() -> None:
    assert detect_template_candidates([]) == []


def _message(sender: str, text: str, timestamp: int) -> ParsedMessage:
    return ParsedMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )
