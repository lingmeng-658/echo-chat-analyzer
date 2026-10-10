"""Convert Smart Profile candidates into filtering decisions."""

from __future__ import annotations

from collections.abc import Iterable

from .candidates import Candidate
from .filter_decisions import FilterDecision


_ACTION_PRIORITY = {
    "keep": 0,
    "review": 1,
    "ignore": 2,
}

MIN_IGNORE_STATIC_TEMPLATE_LENGTH = 5


def create_filter_decisions(
    candidates: Iterable[Candidate],
) -> list[FilterDecision]:
    """Create decisions from candidates without executing any filtering.

    Decisions are deduplicated per ``(target_type, target, sender identity)``
    and the strongest action wins, then the higher confidence. Interactive
    automation evidence is capped at ``review``: it is kept for human review but
    never deletes messages on its own, because a nickname cannot isolate a
    member and the responder credited for a mention may be a member who simply
    answers quickly. An identity-scoped ``ignore`` therefore only comes from the
    statistical sender detectors, or from a name that no resolved identity uses.
    """
    decisions: list[FilterDecision] = []
    decision_indexes: dict[tuple[str, str, str | None], int] = {}

    for candidate in candidates:
        identity_metadata: dict[str, object] = {}
        if candidate.candidate_type == "robot_sender":
            if candidate.score < 0.6:
                continue
            target_type = "sender"
            identity_metadata = _identity_metadata(candidate)
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
        elif candidate.candidate_type == "repeated_template":
            target_type = "template"
            if (
                candidate.score >= 0.9
                and _static_template_length(candidate)
                >= MIN_IGNORE_STATIC_TEMPLATE_LENGTH
            ):
                action = "ignore"
                reason = "high_confidence_repeated_template"
            else:
                action = "review"
                reason = "possible_repeated_template"
        elif candidate.candidate_type == "automation_source":
            target_type = "sender"
            identity_metadata = _identity_metadata(candidate)
            source_kind = candidate.metadata.get("source_kind")
            if source_kind == "interactive_bot":
                # Interactive evidence never deletes on its own, even at the
                # calibrated 30-mention / 80%-response strength: the candidate,
                # its metrics and its confidence are preserved for review only.
                action = "review"
                if identity_metadata.get("sender_identity_ambiguous") is True:
                    # A nickname shared by several identities cannot be
                    # isolated, so an automatic deletion is not safe either.
                    reason = "ambiguous_sender_identity"
                else:
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
            metadata=identity_metadata,
        )
        # Sender decisions are deduplicated per stable identity: two identities
        # may legitimately share one display name.
        sender_key = decision.metadata.get("sender_key")
        key = (
            decision.target_type,
            decision.target,
            sender_key if isinstance(sender_key, str) else None,
        )
        existing_index = decision_indexes.get(key)
        if existing_index is None:
            decision_indexes[key] = len(decisions)
            decisions.append(decision)
        elif _decision_priority(decision) > _decision_priority(
            decisions[existing_index]
        ):
            decisions[existing_index] = decision

    return decisions


def _identity_metadata(candidate: Candidate) -> dict[str, object]:
    """Copy the sender identity evidence a filter decision needs to match."""
    metadata: dict[str, object] = {}
    sender_key = candidate.metadata.get("sender_key")
    if isinstance(sender_key, str) and sender_key.strip():
        metadata["sender_key"] = sender_key
    if candidate.metadata.get("sender_identity_ambiguous") is True:
        metadata["sender_identity_ambiguous"] = True
    return metadata


def _static_template_length(candidate: Candidate) -> int:
    """Return the candidate's static template length when it is an integer."""
    static_length = candidate.metadata.get("static_character_count")
    if type(static_length) is not int:
        return 0
    return static_length


def _decision_priority(decision: FilterDecision) -> tuple[int, float]:
    return (
        _ACTION_PRIORITY.get(decision.action, -1),
        decision.confidence,
    )
