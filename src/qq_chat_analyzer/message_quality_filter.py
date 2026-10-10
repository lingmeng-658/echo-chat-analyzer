"""Local message quality filtering before profile and statistics analysis.

The filter is intentionally deterministic and rule-based:

- messages with 100 or more characters are almost always copied text, bot
  output, or long-running spam in real QQ group samples;
- high-confidence repetition noise from the existing noise detector is reused
  without changing its detection logic.

Filtering only partitions the in-memory message list; the original imported
messages are never mutated or deleted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .candidates import Candidate
from .detectors.noise_detector import detect_noise_candidates
from .message import ChatMessage


LONG_TEXT_THRESHOLD = 100

_INTERNAL_NOISE_TYPES = (
    "noise_single_character_repeat",
    "noise_repeated_fragment",
)
_BURST_NOISE_TYPE = "noise_sender_burst_repeat"


@dataclass(slots=True)
class MessageQualityReason:
    """One traceable reason a message was excluded from analysis."""

    message: ChatMessage
    reason: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class MessageQualityResult:
    """Partitioned messages after deterministic quality filtering."""

    kept_messages: list[ChatMessage]
    filtered_messages: list[ChatMessage]
    reasons: list[MessageQualityReason] = field(default_factory=list)


def apply_message_quality_filter(
    messages: Iterable[ChatMessage],
) -> MessageQualityResult:
    """Partition messages by deterministic quality rules in original order."""
    message_list = list(messages)
    candidates = detect_noise_candidates(message_list)

    internal_noise_by_target: dict[str, Candidate] = {}
    burst_by_index: dict[int, Candidate] = {}
    for candidate in candidates:
        if candidate.candidate_type in _INTERNAL_NOISE_TYPES:
            internal_noise_by_target.setdefault(candidate.target, candidate)
        elif candidate.candidate_type == _BURST_NOISE_TYPE:
            # Indexes refer to this exact input list, including equal messages.
            # Keep the first message of each detected run, not each global key.
            for message_index in candidate.metadata["message_indexes"][1:]:
                burst_by_index[message_index] = candidate

    kept_messages: list[ChatMessage] = []
    filtered_messages: list[ChatMessage] = []
    reasons: list[MessageQualityReason] = []
    for message_index, message in enumerate(message_list):
        text = message.text if isinstance(message.text, str) else ""
        normalized = _normalize_text(text)

        if len(text) >= LONG_TEXT_THRESHOLD:
            filtered_messages.append(message)
            reasons.append(
                MessageQualityReason(
                    message=message,
                    reason="long_text_outlier",
                    metadata={
                        "length": len(text),
                        "threshold": LONG_TEXT_THRESHOLD,
                    },
                )
            )
            continue

        candidate = internal_noise_by_target.get(normalized)
        if candidate is not None:
            filtered_messages.append(message)
            reasons.append(
                MessageQualityReason(
                    message=message,
                    reason=candidate.candidate_type,
                    metadata=candidate.metadata,
                )
            )
            continue

        burst_candidate = burst_by_index.get(message_index)
        if burst_candidate is not None:
            filtered_messages.append(message)
            reasons.append(
                MessageQualityReason(
                    message=message,
                    reason=burst_candidate.candidate_type,
                    metadata=burst_candidate.metadata,
                )
            )
            continue

        kept_messages.append(message)

    return MessageQualityResult(
        kept_messages=kept_messages,
        filtered_messages=filtered_messages,
        reasons=reasons,
    )


def _normalize_text(text: str) -> str:
    """Mirror the noise detector's whitespace normalization exactly."""
    return " ".join(text.split()).strip()
