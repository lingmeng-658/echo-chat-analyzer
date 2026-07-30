"""Execute filtering decisions against parsed messages."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .filter_decisions import FilterDecision
from .parser import ParsedMessage


_TEMPLATE_VARIABLE = "{variable}"
_TERMINAL_PUNCTUATION = "。.!！?？"


@dataclass(slots=True)
class FilteringResult:
    """Traceable result of applying filtering decisions."""

    kept_messages: list[ParsedMessage]
    filtered_messages: list[ParsedMessage]
    applied_decisions: list[FilterDecision]


class FilterPipeline:
    """Apply explicit decisions without creating new decisions."""

    def apply_filter_decisions(
        self,
        messages: Iterable[ParsedMessage],
        decisions: Iterable[FilterDecision],
    ) -> FilteringResult:
        """Partition messages while preserving their original order."""
        decision_list = list(decisions)
        applied_flags = [False] * len(decision_list)
        kept_messages: list[ParsedMessage] = []
        filtered_messages: list[ParsedMessage] = []

        for message in messages:
            should_filter = False

            for index, decision in enumerate(decision_list):
                if decision.action != "ignore":
                    continue
                if _decision_matches_message(decision, message):
                    should_filter = True
                    applied_flags[index] = True

            if should_filter:
                filtered_messages.append(message)
            else:
                kept_messages.append(message)

        applied_decisions = [
            decision
            for decision, was_applied in zip(
                decision_list,
                applied_flags,
                strict=True,
            )
            if was_applied
        ]

        return FilteringResult(
            kept_messages=kept_messages,
            filtered_messages=filtered_messages,
            applied_decisions=applied_decisions,
        )


def _decision_matches_message(
    decision: FilterDecision,
    message: ParsedMessage,
) -> bool:
    if decision.target_type == "sender":
        return message.sender == decision.target
    if decision.target_type == "template":
        return _template_matches(decision.target, message.text)
    return False


def _template_matches(template: str, text: str) -> bool:
    normalized_template = _normalize_template_text(template)
    normalized_text = _normalize_template_text(text)
    parts = normalized_template.split(_TEMPLATE_VARIABLE)
    pattern = ".+?".join(re.escape(part) for part in parts)
    return re.fullmatch(pattern, normalized_text) is not None


def _normalize_template_text(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized.rstrip(_TERMINAL_PUNCTUATION).strip()
