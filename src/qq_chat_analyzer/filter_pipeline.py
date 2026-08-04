"""Execute filtering decisions against parsed messages."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .filter_decisions import FilterDecision
from .message import ChatMessage


_TEMPLATE_PLACEHOLDER_PATTERN = re.compile(
    r"\{(?P<kind>variable|number|id|user|url)\}"
)
_TEMPLATE_PLACEHOLDER_REGEXES = {
    "variable": r".+?",
    "number": r"(?:\d+\.\d+|\d{1,5})",
    "id": r"\d{6,}",
    "user": r"[^\s，,。.!！?？、:：;；）)\]】}]+",
    "url": r"(?i:https?)://[^\s，,。！!？、；;）)\]】}]+",
}
_TERMINAL_PUNCTUATION = "。.!！?？"


@dataclass(slots=True)
class FilteringResult:
    """Traceable result of applying filtering decisions."""

    kept_messages: list[ChatMessage]
    filtered_messages: list[ChatMessage]
    applied_decisions: list[FilterDecision]


class FilterPipeline:
    """Apply explicit decisions without creating new decisions."""

    def apply_filter_decisions(
        self,
        messages: Iterable[ChatMessage],
        decisions: Iterable[FilterDecision],
    ) -> FilteringResult:
        """Partition messages while preserving their original order."""
        decision_list = list(decisions)
        applied_flags = [False] * len(decision_list)
        kept_messages: list[ChatMessage] = []
        filtered_messages: list[ChatMessage] = []

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
    message: ChatMessage,
) -> bool:
    if decision.target_type == "sender":
        return message.sender == decision.target
    if decision.target_type == "template":
        return _template_matches(decision.target, message.text)
    return False


def _template_matches(template: str, text: str) -> bool:
    normalized_template = _normalize_template_text(template)
    normalized_text = _normalize_template_text(text)
    pattern = _template_pattern(normalized_template)
    return re.fullmatch(pattern, normalized_text) is not None


def _template_pattern(template: str) -> str:
    parts: list[str] = []
    position = 0

    for match in _TEMPLATE_PLACEHOLDER_PATTERN.finditer(template):
        parts.append(re.escape(template[position : match.start()]))
        parts.append(
            _TEMPLATE_PLACEHOLDER_REGEXES[match.group("kind")]
        )
        position = match.end()

    parts.append(re.escape(template[position:]))
    return "".join(parts)


def _normalize_template_text(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized.rstrip(_TERMINAL_PUNCTUATION).strip()
