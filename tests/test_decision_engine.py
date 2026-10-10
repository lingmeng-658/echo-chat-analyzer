"""Tests for converting candidates into filtering decisions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.candidates import Candidate
from qq_chat_analyzer.decision_engine import create_filter_decisions
from qq_chat_analyzer.filter_decisions import FilterDecision


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        pytest.param(
            Candidate(target="虚构签到助手", candidate_type="robot_sender", score=0.95),
            FilterDecision(
                target="虚构签到助手", target_type="sender", action="ignore",
                confidence=0.95, reason="high_confidence_robot_sender", source="auto",
            ),
            id="high_confidence_robot_sender_is_ignored",
        ),
        pytest.param(
            Candidate(target="虚构提醒助手", candidate_type="robot_sender", score=0.7),
            FilterDecision(
                target="虚构提醒助手", target_type="sender", action="review",
                confidence=0.7, reason="possible_robot_sender", source="auto",
            ),
            id="medium_confidence_robot_sender_is_reviewed",
        ),
        pytest.param(
            Candidate(
                target="欢迎 {variable} 加入虚构群聊",
                candidate_type="welcome_template", score=0.94,
            ),
            FilterDecision(
                target="欢迎 {variable} 加入虚构群聊", target_type="template", action="ignore",
                confidence=0.94, reason="high_confidence_welcome_template", source="auto",
            ),
            id="high_confidence_welcome_template_is_ignored",
        ),
        pytest.param(
            Candidate(
                target="欢迎 {variable} 加入虚构讨论组",
                candidate_type="welcome_template", score=0.58,
            ),
            FilterDecision(
                target="欢迎 {variable} 加入虚构讨论组", target_type="template", action="review",
                confidence=0.58, reason="possible_welcome_template", source="auto",
            ),
            id="lower_confidence_welcome_template_is_reviewed",
        ),
        pytest.param(
            Candidate(
                target="@{user} 虚构查询", candidate_type="repeated_template",
                score=1.0, metadata={"static_character_count": 4},
            ),
            FilterDecision(
                target="@{user} 虚构查询", target_type="template", action="review",
                confidence=1.0, reason="possible_repeated_template", source="auto",
            ),
            id="high_score_repeated_template_with_short_static_text_is_reviewed",
        ),
        pytest.param(
            Candidate(
                target="签到成功，积分+{number}", candidate_type="repeated_template",
                score=1.0, metadata={"static_character_count": 8},
            ),
            FilterDecision(
                target="签到成功，积分+{number}", target_type="template", action="ignore",
                confidence=1.0, reason="high_confidence_repeated_template", source="auto",
            ),
            id="high_confidence_repeated_template_is_ignored",
        ),
        pytest.param(
            Candidate(
                target="查询结果：{variable}", candidate_type="repeated_template", score=0.8,
            ),
            FilterDecision(
                target="查询结果：{variable}", target_type="template", action="review",
                confidence=0.8, reason="possible_repeated_template", source="auto",
            ),
            id="medium_confidence_repeated_template_is_reviewed",
        ),
    ],
)
def test_candidate_creates_expected_decision(
    candidate: Candidate,
    expected: FilterDecision,
) -> None:
    assert create_filter_decisions([candidate]) == [expected]


def test_low_confidence_robot_sender_has_no_decision() -> None:
    candidate = Candidate(
        target="虚构普通用户",
        candidate_type="robot_sender",
        score=0.59,
    )

    assert create_filter_decisions([candidate]) == []


def test_interactive_bot_strong_evidence_is_reviewed_only() -> None:
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
            action="review",
            confidence=0.95,
            reason="possible_interactive_bot",
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


def test_interactive_bot_concentration_does_not_create_ignore() -> None:
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
            action="review",
            confidence=0.96,
            reason="possible_interactive_bot",
            source="auto",
        )
    ]


def test_interactive_bot_high_volume_evidence_is_reviewed_only() -> None:
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
            action="review",
            confidence=0.97,
            reason="possible_interactive_bot",
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


def test_interactive_bot_score_never_produces_ignore() -> None:
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
            action="review",
            confidence=0.59,
            reason="possible_interactive_bot",
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


def test_robot_evidence_keeps_the_identity_scoped_ignore() -> None:
    """Action priority outranks confidence for one identity's candidates."""
    robot_candidate = Candidate(
        target="虚构复合助手",
        candidate_type="robot_sender",
        score=0.92,
        metadata={"sender_key": "u-composite"},
    )
    interactive_candidate = Candidate(
        target="虚构复合助手",
        candidate_type="automation_source",
        score=0.97,
        metadata={
            "source_kind": "interactive_bot",
            "sender_key": "u-composite",
            "metrics": {
                "mention_count": 100,
                "response_rate": 0.95,
                "unique_trigger_source_count": 20,
                "concentrated_in_short_window": False,
            },
        },
    )

    assert create_filter_decisions([interactive_candidate]) == [
        FilterDecision(
            target="虚构复合助手",
            target_type="sender",
            action="review",
            confidence=0.97,
            reason="possible_interactive_bot",
            source="auto",
            metadata={"sender_key": "u-composite"},
        )
    ]

    assert create_filter_decisions(
        [interactive_candidate, robot_candidate]
    ) == [
        FilterDecision(
            target="虚构复合助手",
            target_type="sender",
            action="ignore",
            confidence=0.92,
            reason="high_confidence_robot_sender",
            source="auto",
            metadata={"sender_key": "u-composite"},
        )
    ]


def test_same_identity_interactive_candidates_keep_one_review() -> None:
    """Repeated interactive evidence stays a single, non-deleting review."""
    candidates = [
        Candidate(
            target="虚构重复助手",
            candidate_type="automation_source",
            score=0.71,
            metadata={"source_kind": "interactive_bot", "sender_key": "u-review"},
        ),
        Candidate(
            target="虚构重复助手",
            candidate_type="automation_source",
            score=0.95,
            metadata={"source_kind": "interactive_bot", "sender_key": "u-review"},
        ),
    ]

    decisions = create_filter_decisions(candidates)

    assert decisions == [
        FilterDecision(
            target="虚构重复助手",
            target_type="sender",
            action="review",
            confidence=0.95,
            reason="possible_interactive_bot",
            source="auto",
            metadata={"sender_key": "u-review"},
        )
    ]


def test_ambiguous_interactive_identity_keeps_its_own_review_reason() -> None:
    candidate = Candidate(
        target="虚构同名助手",
        candidate_type="automation_source",
        score=0.98,
        metadata={
            "source_kind": "interactive_bot",
            "sender_identity_ambiguous": True,
            "metrics": {"mention_count": 100, "response_rate": 0.95},
        },
    )

    assert create_filter_decisions([candidate]) == [
        FilterDecision(
            target="虚构同名助手",
            target_type="sender",
            action="review",
            confidence=0.98,
            reason="ambiguous_sender_identity",
            source="auto",
            metadata={"sender_identity_ambiguous": True},
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
