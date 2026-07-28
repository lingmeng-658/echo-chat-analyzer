"""Frequency analysis for already-tokenized chat text."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WordSpeakerSummary:
    """Summary of the sender who used a word most often."""

    word: str
    total_count: int
    top_speaker: str
    top_speaker_count: int
    top_speaker_share_percent: float


def count_word_speakers(
    sender_tokens: Iterable[tuple[str, Iterable[str]]],
) -> dict[str, dict[str, int]]:
    """Count every token occurrence per sender using a sparse mapping."""
    word_sender_counts: dict[str, dict[str, int]] = {}

    for sender, tokens in sender_tokens:
        for token in tokens:
            sender_counts = word_sender_counts.setdefault(token, {})
            sender_counts[sender] = sender_counts.get(sender, 0) + 1

    return word_sender_counts


def top_word_speaker_summary(
    word_sender_counts: Mapping[str, Mapping[str, int]],
    n: int = 25,
) -> list[WordSpeakerSummary]:
    """Return top-word speaker summaries with stable first-use tie ordering."""
    if n <= 0:
        return []

    ranked_words: list[tuple[int, str, Mapping[str, int], int]] = []
    for first_position, (word, sender_counts) in enumerate(
        word_sender_counts.items()
    ):
        total_count = sum(sender_counts.values())
        if not sender_counts or total_count <= 0:
            continue
        ranked_words.append(
            (first_position, word, sender_counts, total_count)
        )

    ranked_words.sort(key=lambda item: (-item[3], item[0]))

    summaries: list[WordSpeakerSummary] = []
    for _, word, sender_counts, total_count in ranked_words[:n]:
        top_speaker, top_speaker_count = max(
            sender_counts.items(),
            key=lambda item: item[1],
        )
        summaries.append(
            WordSpeakerSummary(
                word=word,
                total_count=total_count,
                top_speaker=top_speaker,
                top_speaker_count=top_speaker_count,
                top_speaker_share_percent=round(
                    top_speaker_count / total_count * 100,
                    2,
                ),
            )
        )

    return summaries


def count_words(tokens: list[str]) -> dict[str, int]:
    """Return the occurrence count for each token."""
    return dict(Counter(tokens))


def top_words(tokens: list[str], n: int = 50) -> list[tuple[str, int]]:
    """Return the most frequent tokens with stable tie ordering."""
    if n <= 0:
        return []

    frequencies = count_words(tokens)
    first_positions: dict[str, int] = {}
    for index, token in enumerate(tokens):
        first_positions.setdefault(token, index)

    ranked = sorted(
        frequencies.items(),
        key=lambda item: (-item[1], first_positions[item[0]]),
    )
    return ranked[:n]
