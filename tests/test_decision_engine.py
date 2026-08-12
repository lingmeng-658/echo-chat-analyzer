"""Tests for converting candidates into filtering decisions."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.candidates import Candidate
from qq_chat_analyzer.decision_engine import create_filter_decisions
from qq_chat_analyzer.filter_decisions import FilterDecision


def test_high_confidence_robot_sender_is_ignored() -> None:
    candidate = Candidate(
        target="虚构签到助手",
        candidate_type="robot_sender",
        score=0.95,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构签到助手",
            target_type="sender",
            action="ignore",
            confidence=0.95,
            reason="high_confidence_robot_sender",
            source="auto",
        )
    ]


def test_medium_confidence_robot_sender_is_reviewed() -> None:
    candidate = Candidate(
        target="虚构提醒助手",
        candidate_type="robot_sender",
        score=0.7,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构提醒助手",
            target_type="sender",
            action="review",
            confidence=0.7,
            reason="possible_robot_sender",
            source="auto",
        )
    ]


def test_high_confidence_welcome_template_is_ignored() -> None:
    candidate = Candidate(
        target="欢迎 {variable} 加入虚构群聊",
        candidate_type="welcome_template",
        score=0.94,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="欢迎 {variable} 加入虚构群聊",
            target_type="template",
            action="ignore",
            confidence=0.94,
            reason="high_confidence_welcome_template",
            source="auto",
        )
    ]


def test_lower_confidence_welcome_template_is_reviewed() -> None:
    candidate = Candidate(
        target="欢迎 {variable} 加入虚构讨论组",
        candidate_type="welcome_template",
        score=0.58,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="欢迎 {variable} 加入虚构讨论组",
            target_type="template",
            action="review",
            confidence=0.58,
            reason="possible_welcome_template",
            source="auto",
        )
    ]


def test_low_confidence_robot_sender_has_no_decision() -> None:
    candidate = Candidate(
        target="虚构普通用户",
        candidate_type="robot_sender",
        score=0.59,
    )

    assert create_filter_decisions([candidate]) == []


def test_interactive_bot_uses_only_mentions_and_response_rate() -> None:
    candidate = Candidate(
        target="虚构交互助手",
        candidate_type="automation_source",
        score=0.95,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 100,
                "response_rate": 0.95,
                "unique_trigger_source_count": 1,
                "response_template_score": 0.0,
                "concentrated_in_short_window": True,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构交互助手",
            target_type="sender",
            action="ignore",
            confidence=0.95,
            reason="high_confidence_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_with_small_sample_is_reviewed() -> None:
    candidate = Candidate(
        target="虚构小样本助手",
        candidate_type="automation_source",
        score=0.95,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 10,
                "response_rate": 1.0,
                "unique_trigger_source_count": 2,
                "concentrated_in_short_window": True,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构小样本助手",
            target_type="sender",
            action="review",
            confidence=0.95,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_below_ten_mentions_is_reviewed() -> None:
    candidate = Candidate(
        target="fictional_low_volume_source",
        candidate_type="automation_source",
        score=0.99,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 9,
                "response_rate": 1.0,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="fictional_low_volume_source",
            target_type="sender",
            action="review",
            confidence=0.99,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_below_response_rate_threshold_is_reviewed() -> None:
    candidate = Candidate(
        target="fictional_low_response_source",
        candidate_type="automation_source",
        score=0.99,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 100,
                "response_rate": 0.79,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="fictional_low_response_source",
            target_type="sender",
            action="review",
            confidence=0.99,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_concentration_does_not_prevent_ignore() -> None:
    candidate = Candidate(
        target="虚构集中触发助手",
        candidate_type="automation_source",
        score=0.96,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 100,
                "response_rate": 0.95,
                "unique_trigger_source_count": 20,
                "concentrated_in_short_window": True,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构集中触发助手",
            target_type="sender",
            action="ignore",
            confidence=0.96,
            reason="high_confidence_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_without_old_evidence_fields_is_ignored() -> None:
    candidate = Candidate(
        target="虚构单来源互动助手",
        candidate_type="automation_source",
        score=0.97,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 143,
                "response_rate": 0.86,
                "unique_trigger_source_count": 5,
                "top_trigger_frequency_ratio": 0.965,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构单来源互动助手",
            target_type="sender",
            action="ignore",
            confidence=0.97,
            reason="high_confidence_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_with_invalid_metrics_is_reviewed() -> None:
    candidate = Candidate(
        target="虚构指标异常助手",
        candidate_type="automation_source",
        score=0.98,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": "100",
                "response_rate": 0.95,
                "unique_trigger_source_count": 20,
                "concentrated_in_short_window": False,
            },
        },
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构指标异常助手",
            target_type="sender",
            action="review",
            confidence=0.98,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_with_invalid_response_rate_type_is_reviewed() -> None:
    for response_rate in ("0.95", None):
        candidate = Candidate(
            target="虚构响应率异常助手",
            candidate_type="automation_source",
            score=0.98,
            metadata={
                "source_kind": "interactive_bot",
                "metrics": {
                    "mention_count": 100,
                    "response_rate": response_rate,
                    "unique_trigger_source_count": 20,
                    "concentrated_in_short_window": False,
                },
            },
        )

        decisions = create_filter_decisions([candidate])

        assert decisions == [
            FilterDecision(
                target="虚构响应率异常助手",
                target_type="sender",
                action="review",
                confidence=0.98,
                reason="possible_interactive_bot",
                source="auto",
            )
        ]


def test_medium_confidence_interactive_bot_is_reviewed() -> None:
    candidate = Candidate(
        target="虚构查询助手",
        candidate_type="automation_source",
        score=0.7,
        metadata={"source_kind": "interactive_bot"},
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构查询助手",
            target_type="sender",
            action="review",
            confidence=0.7,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_score_does_not_participate_in_decision() -> None:
    candidate = Candidate(
        target="虚构低置信助手",
        candidate_type="automation_source",
        score=0.59,
        metadata={
            "source_kind": "interactive_bot",
            "metrics": {
                "mention_count": 30,
                "response_rate": 0.8,
            },
        },
    )

    assert create_filter_decisions([candidate]) == [
        FilterDecision(
            target="虚构低置信助手",
            target_type="sender",
            action="ignore",
            confidence=0.59,
            reason="high_confidence_interactive_bot",
            source="auto",
        )
    ]


def test_unknown_automation_source_kind_is_reviewed() -> None:
    candidate = Candidate(
        target="虚构未知自动化来源",
        candidate_type="automation_source",
        score=0.98,
        metadata={"source_kind": "future_source_kind"},
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构未知自动化来源",
            target_type="sender",
            action="review",
            confidence=0.98,
            reason="unsupported_automation_source_kind",
            source="auto",
        )
    ]


def test_same_sender_automation_candidates_create_one_decision() -> None:
    candidates = [
        Candidate(
            target="虚构复合助手",
            candidate_type="robot_sender",
            score=0.92,
        ),
        Candidate(
            target="虚构复合助手",
            candidate_type="automation_source",
            score=0.97,
            metadata={
                "source_kind": "interactive_bot",
                "metrics": {
                    "mention_count": 100,
                    "response_rate": 0.95,
                    "unique_trigger_source_count": 20,
                    "concentrated_in_short_window": False,
                },
            },
        ),
    ]

    decisions = create_filter_decisions(candidates)

    assert decisions == [
        FilterDecision(
            target="虚构复合助手",
            target_type="sender",
            action="ignore",
            confidence=0.97,
            reason="high_confidence_interactive_bot",
            source="auto",
        )
    ]


def test_high_score_repeated_template_with_short_static_text_is_reviewed() -> None:
    candidate = Candidate(
        target="@{user} 虚构查询",
        candidate_type="repeated_template",
        score=1.0,
        metadata={"static_character_count": 4},
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="@{user} 虚构查询",
            target_type="template",
            action="review",
            confidence=1.0,
            reason="possible_repeated_template",
            source="auto",
        )
    ]


def test_high_confidence_repeated_template_is_ignored() -> None:
    candidate = Candidate(
        target="签到成功，积分+{number}",
        candidate_type="repeated_template",
        score=1.0,
        metadata={"static_character_count": 8},
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="签到成功，积分+{number}",
            target_type="template",
            action="ignore",
            confidence=1.0,
            reason="high_confidence_repeated_template",
            source="auto",
        )
    ]


def test_medium_confidence_repeated_template_is_reviewed() -> None:
    candidate = Candidate(
        target="查询结果：{variable}",
        candidate_type="repeated_template",
        score=0.8,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="查询结果：{variable}",
            target_type="template",
            action="review",
            confidence=0.8,
            reason="possible_repeated_template",
            source="auto",
        )
    ]


def test_unknown_candidate_type_is_reviewed_safely() -> None:
    candidate = Candidate(
        target="虚构未知对象",
        candidate_type="future_candidate_type",
        score=0.42,
    )

    decisions = create_filter_decisions([candidate])

    assert decisions == [
        FilterDecision(
            target="虚构未知对象",
            target_type="unknown",
            action="review",
            confidence=0.42,
            reason="unsupported_candidate_type",
            source="auto",
        )
    ]
