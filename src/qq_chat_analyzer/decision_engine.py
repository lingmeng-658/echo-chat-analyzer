"""Convert Smart Profile candidates into filtering decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .candidates import Candidate
from .filter_decisions import FilterDecision


_ACTION_PRIORITY = {
    "keep": 0,
    "review": 1,
    "ignore": 2,
}


def create_filter_decisions(
    candidates: Iterable[Candidate],
) -> list[FilterDecision]:
    """Create decisions from candidates without executing any filtering."""
    decisions: list[FilterDecision] = []
    decision_indexes: dict[tuple[str, str], int] = {}

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
        elif candidate.candidate_type == "automation_source":
            target_type = "sender"
            source_kind = candidate.metadata.get("source_kind")
            if source_kind == "interactive_bot":
                if _has_strong_interactive_bot_evidence(candidate):
                    action = "ignore"
                    reason = "high_confidence_interactive_bot"
                else:
                    action = "review"
                    reason = "possible_interactive_bot"
            else:
                action = "review"
                reason = "unsupported_automation_source_kind"
        else:
            target_type = "unknown"
            action = "review"
            reason = "unsupported_candidate_type"

        decision = FilterDecision(
            target=candidate.target,
            target_type=target_type,
            action=action,
            confidence=candidate.score,
            reason=reason,
            source="auto",
        )
        key = (decision.target_type, decision.target)
        existing_index = decision_indexes.get(key)
        if existing_index is None:
            decision_indexes[key] = len(decisions)
            decisions.append(decision)
        elif _decision_priority(decision) > _decision_priority(
            decisions[existing_index]
        ):
            decisions[existing_index] = decision

    return decisions


def _has_strong_interactive_bot_evidence(
    candidate: Candidate,
) -> bool:
    metrics = candidate.metadata.get("metrics")
    if not isinstance(metrics, Mapping):
        return False

    mention_count = metrics.get("mention_count")
    response_rate = metrics.get("response_rate")

    return (
        type(mention_count) is int
        and mention_count >= 30
        and type(response_rate) is float
        and response_rate >= 0.8
    )


def _decision_priority(decision: FilterDecision) -> tuple[int, float]:
    return (
        _ACTION_PRIORITY.get(decision.action, -1),
        decision.confidence,
    )
