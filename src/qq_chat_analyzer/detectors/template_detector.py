"""Detect frequently repeated message structures as template candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..candidates import Candidate
from ..parser import ParsedMessage


MIN_MATCHED_MESSAGE_COUNT = 3
MIN_STATIC_TEMPLATE_LENGTH = 4
MAX_TEMPLATE_EXAMPLES = 3

_WELCOME_PATTERN = re.compile(r"^欢迎\s+(.+?)\s+加入群聊$")
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_TERMINAL_PUNCTUATION = "。.!！?？"


@dataclass(slots=True)
class _TemplateGroup:
    candidate_type: str
    examples: list[str] = field(default_factory=list)


def detect_template_candidates(
    messages: Iterable[ParsedMessage],
) -> list[Candidate]:
    """Return repeated structure candidates without filtering messages."""
    groups: dict[str, _TemplateGroup] = {}
    total_message_count = 0

    for message in messages:
        text = _normalize_message_text(message.text)
        if not text:
            continue

        total_message_count += 1
        normalized = _normalize_template(text)
        if normalized is None:
            continue

        template, candidate_type = normalized
        if _static_template_length(template) < MIN_STATIC_TEMPLATE_LENGTH:
            continue

        group = groups.setdefault(
            template,
            _TemplateGroup(candidate_type=candidate_type),
        )
        group.examples.append(text)

    if total_message_count == 0:
        return []

    candidates: list[Candidate] = []
    for template, group in groups.items():
        matched_message_count = len(group.examples)
        if matched_message_count < MIN_MATCHED_MESSAGE_COUNT:
            continue

        match_ratio = matched_message_count / total_message_count
        similarity = 1.0
        frequency_strength = min(
            1.0,
            matched_message_count / 5,
        )
        score = round(
            frequency_strength * 0.5 + similarity * 0.5,
            4,
        )

        candidates.append(
            Candidate(
                target=template,
                candidate_type=group.candidate_type,
                score=score,
                reasons=["high_frequency", "high_similarity"],
                metadata={
                    "matched_message_count": matched_message_count,
                    "match_ratio": round(match_ratio, 4),
                    "template_examples": group.examples[
                        :MAX_TEMPLATE_EXAMPLES
                    ],
                    "similarity": similarity,
                },
            )
        )

    return candidates


def _normalize_message_text(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized.rstrip(_TERMINAL_PUNCTUATION).strip()


def _normalize_template(text: str) -> tuple[str, str] | None:
    welcome_match = _WELCOME_PATTERN.fullmatch(text)
    if welcome_match is not None:
        return "欢迎 {variable} 加入群聊", "welcome_template"

    template, replacement_count = _NUMBER_PATTERN.subn(
        "{variable}",
        text,
    )
    if replacement_count == 0:
        return None
    return template, "repeated_template"


def _static_template_length(template: str) -> int:
    static_text = template.replace("{variable}", "")
    return len(re.sub(r"\W+", "", static_text))
