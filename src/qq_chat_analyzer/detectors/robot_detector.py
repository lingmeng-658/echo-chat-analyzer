"""Detect senders whose message patterns resemble automated behavior."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ..candidates import Candidate
from ..parser import ParsedMessage


MIN_MESSAGE_COUNT = 5
HIGH_MESSAGE_RATIO = 0.5
HIGH_REPEAT_RATE = 0.6
HIGH_TEMPLATE_CONCENTRATION = 0.8
MIN_CANDIDATE_SCORE = 0.55

MESSAGE_RATIO_WEIGHT = 0.4
REPEAT_RATE_WEIGHT = 0.35
TEMPLATE_CONCENTRATION_WEIGHT = 0.25

_NUMBER_PATTERN = re.compile(r"\d+")


def detect_robot_candidates(
    messages: Iterable[ParsedMessage],
) -> list[Candidate]:
    """Return suspected robot senders without changing or filtering messages."""
    sender_texts: dict[str, list[str]] = {}
    total_message_count = 0

    for message in messages:
        sender = message.sender.strip()
        text = _normalize_text(message.text)
        if not sender or not text:
            continue

        sender_texts.setdefault(sender, []).append(text)
        total_message_count += 1

    if total_message_count == 0:
        return []

    candidates: list[Candidate] = []
    for sender, texts in sender_texts.items():
        message_count = len(texts)
        if message_count < MIN_MESSAGE_COUNT:
            continue

        message_ratio = message_count / total_message_count
        unique_message_count = len(set(texts))
        repeat_rate = (message_count - unique_message_count) / message_count
        template_concentration = _template_concentration(texts)

        reasons = _candidate_reasons(
            message_ratio=message_ratio,
            repeat_rate=repeat_rate,
            template_concentration=template_concentration,
        )
        score = _candidate_score(
            message_ratio=message_ratio,
            repeat_rate=repeat_rate,
            template_concentration=template_concentration,
        )

        if len(reasons) < 2 or score < MIN_CANDIDATE_SCORE:
            continue

        candidates.append(
            Candidate(
                target=sender,
                candidate_type="robot_sender",
                score=score,
                reasons=reasons,
                metadata={
                    "message_count": message_count,
                    "message_ratio": round(message_ratio, 4),
                    "unique_message_count": unique_message_count,
                    "repeat_rate": round(repeat_rate, 4),
                    "template_concentration": round(
                        template_concentration,
                        4,
                    ),
                },
            )
        )

    return candidates


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def _template_concentration(texts: list[str]) -> float:
    templates = [_NUMBER_PATTERN.sub("<number>", text) for text in texts]
    most_common_count = Counter(templates).most_common(1)[0][1]
    return most_common_count / len(templates)


def _candidate_reasons(
    *,
    message_ratio: float,
    repeat_rate: float,
    template_concentration: float,
) -> list[str]:
    reasons: list[str] = []
    if message_ratio >= HIGH_MESSAGE_RATIO:
        reasons.append("high_message_ratio")
    if repeat_rate >= HIGH_REPEAT_RATE:
        reasons.append("high_repeat_rate")
    if template_concentration >= HIGH_TEMPLATE_CONCENTRATION:
        reasons.append("high_template_concentration")
    return reasons


def _candidate_score(
    *,
    message_ratio: float,
    repeat_rate: float,
    template_concentration: float,
) -> float:
    score = (
        message_ratio * MESSAGE_RATIO_WEIGHT
        + repeat_rate * REPEAT_RATE_WEIGHT
        + template_concentration * TEMPLATE_CONCENTRATION_WEIGHT
    )
    return min(1.0, round(score, 4))
