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
