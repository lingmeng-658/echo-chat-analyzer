"""Convert Smart Profile candidates into filtering decisions."""

from __future__ import annotations

from collections.abc import Iterable

from .candidates import Candidate
from .filter_decisions import FilterDecision


def create_filter_decisions(
    candidates: Iterable[Candidate],
) -> list[FilterDecision]:
    """Create decisions from candidates without executing any filtering."""
    decisions: list[FilterDecision] = []

    for candidate in candidates:
        if candidate.candidate_type == "robot_sender":
            if candidate.score < 0.6:
                continue
            target_type = "sender"
            if candidate.score >= 0.9:
                action = "ignore"
                reason = "high_confidence_robot_sender"
            else:
                action = "review"
                reason = "possible_robot_sender"
        elif candidate.candidate_type == "welcome_template":
            target_type = "template"
            if candidate.score >= 0.9:
                action = "ignore"
                reason = "high_confidence_welcome_template"
            else:
                action = "review"
                reason = "possible_welcome_template"
        else:
            target_type = "unknown"
            action = "review"
            reason = "unsupported_candidate_type"

        decisions.append(
            FilterDecision(
                target=candidate.target,
                target_type=target_type,
                action=action,
                confidence=candidate.score,
                reason=reason,
                source="auto",
            )
        )

    return decisions
