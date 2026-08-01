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
        "fingerprint": "欢迎 {variable} 加入群聊",
        "occurrence_count": 3,
        "matched_message_count": 3,
        "match_ratio": 0.6,
        "template_examples": welcome_messages,
        "similarity": 1.0,
        "static_character_count": 6,
        "variable_count": 1,
        "variable_counts": {"variable": 1},
        "unique_sender_count": 1,
        "top_sender_ratio": 1.0,
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
    assert candidate.target == "签到成功，积分+{number}"
    assert candidate.candidate_type == "repeated_template"
    assert candidate.reasons == ["high_frequency", "high_similarity"]
    assert candidate.metadata["matched_message_count"] == 3
    assert candidate.metadata["template_examples"] == numbered_messages
    assert candidate.metadata["similarity"] == 1.0
    assert candidate.metadata["fingerprint"] == candidate.target
    assert candidate.metadata["occurrence_count"] == 3
    assert candidate.metadata["variable_counts"] == {"number": 1}


def test_structurally_identical_fortune_messages_share_fingerprint() -> None:
    user_names = [
        "虚构甲",
        "虚构乙",
        "虚构丙",
        "虚构丁",
        "虚构戊",
        "虚构己",
        "虚构庚",
        "虚构辛",
        "虚构壬",
        "虚构癸",
    ]
    messages = [
        _message(
            "虚构运势助手",
            (
                f"@{user_name} 综合指数：{40 + index}.5 "
                f"财运指数：{60 + index}"
            ),
            index,
        )
        for index, user_name in enumerate(user_names)
    ]

    candidates = detect_template_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == (
        "@{user} 综合指数：{number} 财运指数：{number}"
    )
    assert candidate.candidate_type == "repeated_template"
    assert candidate.metadata["fingerprint"] == candidate.target
    assert candidate.metadata["occurrence_count"] == 10
    assert candidate.metadata["variable_count"] == 3
    assert candidate.metadata["variable_counts"] == {
        "user": 1,
        "number": 2,
    }
    assert candidate.metadata["static_character_count"] == 8
    assert candidate.metadata["unique_sender_count"] == 1
    assert candidate.metadata["top_sender_ratio"] == 1.0


def test_welcome_rule_messages_normalize_simple_variable_changes() -> None:
    texts = [
        (
            "欢迎 @虚构新生甲 入群。群规编号 123456，"
            "指南 https://example.test/1001。"
        ),
        (
            "欢迎  @虚构新生乙  入群。群规编号 234567，"
            "指南  https://example.test/1002！"
        ),
        (
            "欢迎\t@虚构新生丙\t入群。群规编号\t345678，"
            "指南\thttps://example.test/1003?"
        ),
        (
            "欢迎\n@虚构新生丁\n入群。群规编号\n456789，"
            "指南\nhttps://example.test/1004"
        ),
    ]
    messages = [
        _message(
            "虚构欢迎助手甲" if index < 3 else "虚构欢迎助手乙",
            text,
            index,
        )
        for index, text in enumerate(texts)
    ]

    candidates = detect_template_candidates(messages)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target == (
        "欢迎 @{user} 入群。群规编号 {id}，指南 {url}"
    )
    assert candidate.candidate_type == "repeated_template"
    assert candidate.metadata["fingerprint"] == candidate.target
    assert candidate.metadata["occurrence_count"] == 4
    assert candidate.metadata["variable_count"] == 3
    assert candidate.metadata["variable_counts"] == {
        "user": 1,
        "id": 1,
        "url": 1,
    }
    assert candidate.metadata["unique_sender_count"] == 2
    assert candidate.metadata["top_sender_ratio"] == 0.75


def test_shared_keywords_with_different_structures_are_not_templates() -> None:
    messages = [
        _message("虚构用户甲", "我觉得新生指南第1段很清楚", 0),
        _message("虚构用户乙", "新生指南第2段我还没看", 1),
        _message("虚构用户丙", "刚看完新生指南3，内容不少", 2),
        _message("虚构用户丁", "有人讨论新生指南第4部分吗", 3),
    ]

    assert detect_template_candidates(messages) == []


def test_variable_tokens_do_not_consume_static_suffixes() -> None:
    messages = [
        _message(
            "虚构助手",
            "提醒 @虚构甲，查看 https://a.test/1，版本甲",
            0,
        ),
        _message(
            "虚构助手",
            "提醒 @虚构乙，查看 https://b.test/2，版本乙",
            1,
        ),
        _message(
            "虚构助手",
            "提醒 @虚构丙，查看 https://c.test/3，版本丙",
            2,
        ),
    ]

    assert detect_template_candidates(messages) == []


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
