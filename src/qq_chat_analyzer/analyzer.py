"""Frequency analysis for already-tokenized chat text."""

from __future__ import annotations

from collections import Counter


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
