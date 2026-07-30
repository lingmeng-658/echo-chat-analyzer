"""Tests for Smart Profile candidate data models."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.candidates import Candidate


def test_candidate_preserves_all_discovery_fields() -> None:
    candidate = Candidate(
        target="虚构警卫犬",
        candidate_type="robot_sender",
        score=0.95,
        reasons=["high_message_ratio", "high_repeat_rate"],
        metadata={"message_count": 120, "source": "synthetic_fixture"},
    )

    assert candidate.target == "虚构警卫犬"
    assert candidate.candidate_type == "robot_sender"
    assert candidate.score == 0.95
    assert candidate.reasons == [
        "high_message_ratio",
        "high_repeat_rate",
    ]
    assert candidate.metadata == {
        "message_count": 120,
        "source": "synthetic_fixture",
    }


def test_candidate_defaults_do_not_share_mutable_state() -> None:
    sender_candidate = Candidate(
        target="虚构助手",
        candidate_type="robot_sender",
        score=0.8,
    )
    template_candidate = Candidate(
        target=r"欢迎.*加入虚构群聊",
        candidate_type="welcome_template",
        score=0.9,
    )

    sender_candidate.reasons.append("high_repeat_rate")
    sender_candidate.metadata["message_count"] = 50

    assert template_candidate.reasons == []
    assert template_candidate.metadata == {}
