"""Message length analysis over normalized chat messages."""

from __future__ import annotations

from collections.abc import Sequence

from ..identity import stable_sender_key
from ..models import LengthBucket, MessageLengthReport, SpeakerLength
from ...cleaner import clean_text
from ...message import ChatMessage


_BUCKET_BOUNDS: tuple[tuple[int, int | None], ...] = (
    (0, 10),
    (10, 30),
    (30, 60),
    (60, 120),
    (120, None),
)


class MessageLengthAnalyzer:
    """Report global and per-speaker message length statistics."""

    def analyze(self, messages: Sequence[ChatMessage]) -> MessageLengthReport:
        """Return length statistics for every message carrying text."""
        lengths: list[int] = []
        speaker_lengths: dict[str, list[int]] = {}
        speaker_names: dict[str, str] = {}

        for message in messages:
            length = len(clean_text(message.text))
            if length == 0:
                continue
            lengths.append(length)
            speaker_key = stable_sender_key(message)
            speaker_names.setdefault(speaker_key, message.sender)
            speaker_lengths.setdefault(speaker_key, []).append(length)

        return MessageLengthReport(
            message_count=len(lengths),
            average_length=_average(lengths),
            max_length=max(lengths, default=0),
            buckets=_build_buckets(lengths),
            speaker_lengths=tuple(
                SpeakerLength(
                    speaker=speaker_names[speaker],
                    message_count=len(speaker_values),
                    average_length=_average(speaker_values),
                    max_length=max(speaker_values),
                )
                for speaker, speaker_values in speaker_lengths.items()
            ),
        )


def _average(lengths: Sequence[int]) -> float:
    if not lengths:
        return 0.0
    return round(sum(lengths) / len(lengths), 2)


def _build_buckets(lengths: Sequence[int]) -> tuple[LengthBucket, ...]:
    counts = [0] * len(_BUCKET_BOUNDS)

    for length in lengths:
        for index, (lower_bound, upper_bound) in enumerate(_BUCKET_BOUNDS):
            if length >= lower_bound and (
                upper_bound is None or length < upper_bound
            ):
                counts[index] += 1
                break

    return tuple(
        LengthBucket(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            count=counts[index],
        )
        for index, (lower_bound, upper_bound) in enumerate(_BUCKET_BOUNDS)
    )
