"""Group distinctive-word analysis over already-kept, already-tokenized text."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable

from ..models import (
    DistinctiveWord,
    DistinctiveWordAvailability,
    DistinctiveWordReport,
    MemberDistinctiveWords,
)


# First-release product parameters. These are intentionally named and kept
# together so product tuning does not alter the underlying token semantics.
DISTINCTIVE_MIN_WORD_COUNT = 3
DISTINCTIVE_MIN_TOKENIZED_MESSAGES = 30
DISTINCTIVE_MIN_TOKENS = 100
DISTINCTIVE_MIN_CANDIDATE_WORDS = 3
DISTINCTIVE_MIN_ELIGIBLE_MEMBERS = 3
DISTINCTIVE_TOP_WORD_LIMIT = 5
DISTINCTIVE_LOG_ODDS_PRIOR_STRENGTH = 1000.0
DISTINCTIVE_RELATIVE_RATIO_ALPHA = 0.5


class DistinctiveWordAnalyzer:
    """Find words disproportionately associated with eligible group members."""

    def analyze(
        self,
        sender_tokens: Iterable[tuple[str, Iterable[str]]],
        *,
        conversation_type: str,
    ) -> DistinctiveWordReport:
        """Analyze formal pipeline tokens without cleaning or tokenizing again."""
        if conversation_type != "group":
            return DistinctiveWordReport(
                conversation_type=conversation_type,
                availability=DistinctiveWordAvailability.NOT_GROUP,
            )

        speaker_counts: dict[str, Counter[str]] = {}
        tokenized_message_counts: Counter[str] = Counter()
        global_counts: Counter[str] = Counter()

        for speaker_key, tokens in sender_tokens:
            message_tokens = tuple(tokens)
            if not message_tokens:
                continue
            tokenized_message_counts[speaker_key] += 1
            counts = speaker_counts.setdefault(speaker_key, Counter())
            counts.update(message_tokens)
            global_counts.update(message_tokens)

        candidate_counts = {
            speaker_key: sum(
                count >= DISTINCTIVE_MIN_WORD_COUNT
                for count in counts.values()
            )
            for speaker_key, counts in speaker_counts.items()
        }
        eligible_speakers = [
            speaker_key
            for speaker_key, counts in speaker_counts.items()
            if tokenized_message_counts[speaker_key]
            >= DISTINCTIVE_MIN_TOKENIZED_MESSAGES
            and counts.total() >= DISTINCTIVE_MIN_TOKENS
            and candidate_counts[speaker_key]
            >= DISTINCTIVE_MIN_CANDIDATE_WORDS
        ]

        if len(eligible_speakers) < DISTINCTIVE_MIN_ELIGIBLE_MEMBERS:
            return DistinctiveWordReport(
                conversation_type=conversation_type,
                availability=(
                    DistinctiveWordAvailability.INSUFFICIENT_MEMBERS
                ),
                eligible_member_count=len(eligible_speakers),
            )

        all_token_count = global_counts.total()
        members = tuple(
            self._rank_member(
                speaker_key=speaker_key,
                own_counts=speaker_counts[speaker_key],
                tokenized_message_count=tokenized_message_counts[speaker_key],
                candidate_count=candidate_counts[speaker_key],
                global_counts=global_counts,
                all_token_count=all_token_count,
            )
            for speaker_key in eligible_speakers
        )
        return DistinctiveWordReport(
            conversation_type=conversation_type,
            availability=DistinctiveWordAvailability.AVAILABLE,
            eligible_member_count=len(members),
            members=members,
        )

    def _rank_member(
        self,
        *,
        speaker_key: str,
        own_counts: Counter[str],
        tokenized_message_count: int,
        candidate_count: int,
        global_counts: Counter[str],
        all_token_count: int,
    ) -> MemberDistinctiveWords:
        own_total = own_counts.total()
        others_total = all_token_count - own_total
        ranked: list[DistinctiveWord] = []

        for word, count in own_counts.items():
            if count < DISTINCTIVE_MIN_WORD_COUNT:
                continue
            others_count = global_counts[word] - count
            alpha_word = (
                DISTINCTIVE_LOG_ODDS_PRIOR_STRENGTH
                * global_counts[word]
                / all_token_count
            )
            alpha_other = (
                DISTINCTIVE_LOG_ODDS_PRIOR_STRENGTH - alpha_word
            )
            own_odds = (count + alpha_word) / (
                own_total - count + alpha_other
            )
            others_odds = (others_count + alpha_word) / (
                others_total - others_count + alpha_other
            )
            delta = math.log(own_odds) - math.log(others_odds)
            variance = 1.0 / (count + alpha_word) + 1.0 / (
                others_count + alpha_word
            )
            ranking_score = delta / math.sqrt(variance)

            member_rate = count / own_total
            others_rate = others_count / others_total
            smoothed_member_rate = (
                count + DISTINCTIVE_RELATIVE_RATIO_ALPHA
            ) / (own_total + 2 * DISTINCTIVE_RELATIVE_RATIO_ALPHA)
            smoothed_others_rate = (
                others_count + DISTINCTIVE_RELATIVE_RATIO_ALPHA
            ) / (others_total + 2 * DISTINCTIVE_RELATIVE_RATIO_ALPHA)
            ranked.append(
                DistinctiveWord(
                    word=word,
                    count=count,
                    member_rate=member_rate,
                    others_rate=others_rate,
                    relative_ratio=(
                        smoothed_member_rate / smoothed_others_rate
                    ),
                    ranking_score=ranking_score,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item.ranking_score,
                -item.count,
                item.word,
            )
        )
        return MemberDistinctiveWords(
            speaker_key=speaker_key,
            tokenized_message_count=tokenized_message_count,
            token_count=own_total,
            eligible_word_candidate_count=candidate_count,
            words=tuple(ranked[:DISTINCTIVE_TOP_WORD_LIMIT]),
        )
