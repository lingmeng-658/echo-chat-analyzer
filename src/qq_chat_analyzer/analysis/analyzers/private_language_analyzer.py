"""Private shared-word analysis over already-tokenized sender tokens."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from ..models import PrivateLanguageReport, PrivateSharedWord


class PrivateLanguageAnalyzer:
    """Find words both private sides use, with normalized per-side rates.

    This analyzer never re-tokenizes and never calls the group
    DistinctiveWordAnalyzer. Rates are word_count / speaker_total_tokens and
    the v1 common strength is min(rate_a, rate_b).
    """

    def analyze(
        self,
        sender_tokens: Iterable[tuple[str, Iterable[str]]],
        *,
        conversation_type: str,
    ) -> PrivateLanguageReport:
        if conversation_type != "private":
            return PrivateLanguageReport()

        speaker_counts: dict[str, Counter[str]] = {}
        speaker_totals: dict[str, int] = {}
        for speaker_key, tokens in sender_tokens:
            message_tokens = tuple(tokens)
            if not message_tokens:
                continue
            counts = speaker_counts.setdefault(speaker_key, Counter())
            counts.update(message_tokens)
            speaker_totals[speaker_key] = (
                speaker_totals.get(speaker_key, 0) + len(message_tokens)
            )

        ordered = sorted(
            speaker_totals,
            key=lambda key: (-speaker_totals[key], key),
        )
        if len(ordered) < 2:
            return PrivateLanguageReport()
        speaker_a, speaker_b = ordered[0], ordered[1]
        total_a = speaker_totals[speaker_a]
        total_b = speaker_totals[speaker_b]
        if total_a <= 0 or total_b <= 0:
            return PrivateLanguageReport()

        counts_a = speaker_counts[speaker_a]
        counts_b = speaker_counts[speaker_b]
        shared: list[PrivateSharedWord] = []
        for word, count_a in counts_a.items():
            count_b = counts_b.get(word, 0)
            if count_b <= 0:
                continue
            rate_a = count_a / total_a
            rate_b = count_b / total_b
            preferred_speaker_key = (
                speaker_a
                if rate_a > rate_b
                else speaker_b
                if rate_b > rate_a
                else None
            )
            shared.append(
                PrivateSharedWord(
                    word=word,
                    speaker_a=speaker_a,
                    speaker_b=speaker_b,
                    count_a=count_a,
                    count_b=count_b,
                    total_tokens_a=total_a,
                    total_tokens_b=total_b,
                    rate_a=rate_a,
                    rate_b=rate_b,
                    common_strength=min(rate_a, rate_b),
                    preferred_speaker_key=preferred_speaker_key,
                    occurrence_support=min(count_a, count_b),
                )
            )

        shared.sort(key=lambda item: (-item.common_strength, item.word))
        return PrivateLanguageReport(shared_words=tuple(shared))
