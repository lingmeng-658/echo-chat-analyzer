"""Detect senders whose behavior resembles mention-triggered automation."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ..candidates import Candidate
from ..parser import ParsedMessage
from .template_detector import _NUMBER_PATTERN, _normalize_message_text


MAX_RESPONSE_MESSAGES = 20
MAX_RESPONSE_SECONDS = 300

MIN_MENTION_COUNT = 5
MIN_RESPONSE_RATE = 0.6
HIGH_MENTION_COUNT = 20
HIGH_RESPONSE_RATE = 0.8

_MILLISECOND_TIMESTAMP_THRESHOLD = 100_000_000_000
_MENTION_BOUNDARY = r"(?=$|[\s。，！？，、,:;；])"


def detect_interactive_bot_candidates(
    messages: Iterable[ParsedMessage],
) -> list[Candidate]:
    """Return interactive automation candidates without changing messages."""
    message_list = list(messages)
    senders = {
        message.sender.strip()
        for message in message_list
        if message.sender.strip()
    }
    mention_pattern = _compile_mention_pattern(senders)
    if mention_pattern is None:
        return []

    mention_counts: Counter[str] = Counter()
    response_counts: Counter[str] = Counter()
    trigger_sources: dict[str, set[str]] = {}
    response_templates: dict[str, Counter[str]] = {}

    for index, message in enumerate(message_list):
        source_sender = message.sender.strip()
        mentioned_senders = {
            match.group("sender")
            for match in mention_pattern.finditer(message.text)
            if match.group("sender") != source_sender
        }

        for target_sender in mentioned_senders:
            mention_counts[target_sender] += 1
            if source_sender:
                trigger_sources.setdefault(target_sender, set()).add(
                    source_sender
                )
            response_message = _find_response_in_window(
                message_list,
                mention_index=index,
                target_sender=target_sender,
            )
            if response_message is not None:
                response_counts[target_sender] += 1
                normalized_response = _normalize_response_template(
                    response_message.text
                )
                response_templates.setdefault(
                    target_sender,
                    Counter(),
                )[normalized_response] += 1

    candidates: list[Candidate] = []
    for sender in senders:
        mention_count = mention_counts[sender]
        if mention_count < MIN_MENTION_COUNT:
            continue

        response_count = response_counts[sender]
        response_rate = response_count / mention_count
        if response_rate < MIN_RESPONSE_RATE:
            continue

        score = _interactive_bot_score(
            mention_count=mention_count,
            response_rate=response_rate,
        )
        reasons = [
            (
                "high_mention_count"
                if mention_count >= HIGH_MENTION_COUNT
                else "sufficient_mention_count"
            ),
            (
                "high_response_rate"
                if response_rate >= HIGH_RESPONSE_RATE
                else "elevated_response_rate"
            ),
        ]
        candidates.append(
            Candidate(
                target=sender,
                candidate_type="automation_source",
                score=score,
                reasons=reasons,
                metadata={
                    "source_kind": "interactive_bot",
                    "metrics": {
                        "mention_count": mention_count,
                        "response_count": response_count,
                        "response_rate": round(response_rate, 4),
                        "unique_trigger_source_count": len(
                            trigger_sources.get(sender, set())
                        ),
                        "response_template_score": (
                            _response_template_score(
                                response_templates.get(
                                    sender,
                                    Counter(),
                                ),
                                response_count=response_count,
                            )
                        ),
                    },
                },
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            candidate.target,
        ),
    )


def _compile_mention_pattern(
    senders: set[str],
) -> re.Pattern[str] | None:
    if not senders:
        return None

    alternatives = "|".join(
        re.escape(sender)
        for sender in sorted(senders, key=len, reverse=True)
    )
    return re.compile(
        rf"@(?P<sender>{alternatives}){_MENTION_BOUNDARY}"
    )


def _find_response_in_window(
    messages: list[ParsedMessage],
    *,
    mention_index: int,
    target_sender: str,
) -> ParsedMessage | None:
    mention_timestamp = _timestamp_seconds(
        messages[mention_index].timestamp
    )
    stop_index = min(
        len(messages),
        mention_index + MAX_RESPONSE_MESSAGES + 1,
    )

    for response_index in range(mention_index + 1, stop_index):
        response_message = messages[response_index]
        response_timestamp = _timestamp_seconds(
            response_message.timestamp
        )
        if (
            mention_timestamp is not None
            and response_timestamp is not None
            and response_timestamp - mention_timestamp
            > MAX_RESPONSE_SECONDS
        ):
            break
        if response_message.sender.strip() == target_sender:
            return response_message

    return None


def _normalize_response_template(text: str) -> str:
    normalized_text = _normalize_message_text(text)
    return _NUMBER_PATTERN.sub("{variable}", normalized_text)


def _response_template_score(
    template_counts: Counter[str],
    *,
    response_count: int,
) -> float:
    if response_count == 0:
        return 0.0

    highest_template_count = max(
        template_counts.values(),
        default=0,
    )
    return round(highest_template_count / response_count, 4)


def _timestamp_seconds(value: int | float | str) -> float | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None

    if abs(timestamp) >= _MILLISECOND_TIMESTAMP_THRESHOLD:
        timestamp /= 1_000
    return timestamp


def _interactive_bot_score(
    *,
    mention_count: int,
    response_rate: float,
) -> float:
    if (
        mention_count >= HIGH_MENTION_COUNT
        and response_rate >= HIGH_RESPONSE_RATE
    ):
        mention_bonus = min(0.05, (mention_count - 20) * 0.0025)
        response_bonus = min(
            0.05,
            (response_rate - HIGH_RESPONSE_RATE) * 0.25,
        )
        return round(0.9 + mention_bonus + response_bonus, 4)

    sample_strength = min(
        1.0,
        (mention_count - MIN_MENTION_COUNT)
        / (HIGH_MENTION_COUNT - MIN_MENTION_COUNT),
    )
    response_strength = (
        (response_rate - MIN_RESPONSE_RATE)
        / (1.0 - MIN_RESPONSE_RATE)
    )
    score = (
        0.6
        + sample_strength * 0.15
        + response_strength * 0.14
    )
    return round(min(0.89, score), 4)
