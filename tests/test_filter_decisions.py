"""Tests for Smart Profile filter decision data models."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.filter_decisions import FilterDecision


def test_filter_decision_preserves_all_fields() -> None:
    decision = FilterDecision(
        target="虚构机器人",
        target_type="sender",
        action="ignore",
        confidence=0.97,
        reason="robot_sender_candidate",
        source="auto",
        metadata={"candidate_score": 0.95},
    )

    assert decision.target == "虚构机器人"
    assert decision.target_type == "sender"
    assert decision.action == "ignore"
    assert decision.confidence == 0.97
    assert decision.reason == "robot_sender_candidate"
    assert decision.source == "auto"
    assert decision.metadata == {"candidate_score": 0.95}


def test_filter_decision_can_represent_user_override() -> None:
    decision = FilterDecision(
        target="虚构助手",
        target_type="sender",
        action="keep",
        confidence=1.0,
        reason="user_override",
        source="user",
    )

    assert decision.action == "keep"
    assert decision.source == "user"
    assert decision.metadata == {}


def test_filter_decision_metadata_is_not_shared_between_instances() -> None:
    first = FilterDecision(
        target="虚构模板甲",
        target_type="template",
        action="review",
        confidence=0.75,
        reason="template_candidate",
        source="auto",
    )
    second = FilterDecision(
        target="虚构模板乙",
        target_type="template",
        action="review",
        confidence=0.72,
        reason="template_candidate",
        source="auto",
    )

    first.metadata["matched_message_count"] = 8

    assert first.metadata == {"matched_message_count": 8}
    assert second.metadata == {}
