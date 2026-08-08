"""User profile analysis combining volume, length, and activity."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from ..models import ProfileWord, UserProfile, UserProfileReport
from ..peaks import DAYS_PER_WEEK, HOURS_PER_DAY, busiest_index
from ..timestamps import to_utc_datetime
from ...analyzer import top_words
from ...cleaner import clean_text
from ...message import ChatMessage


class UserProfileAnalyzer:
    """Combine existing signals into one profile per speaker."""

    def analyze(
        self,
        messages: Sequence[ChatMessage],
        sender_tokens: Iterable[tuple[str, Iterable[str]]] | None = None,
        top_words_per_user: int = 10,
        speaker_names: Mapping[str, str] | None = None,
    ) -> UserProfileReport:
        """Return per-speaker profiles ordered by message volume.

        Tokens are never recomputed here; callers pass already-tokenized
        ``sender_tokens`` so tokenization stays owned by the tokenizer.

        ``speaker_names`` optionally maps a raw sender key to a friendly
        name. Names come from the caller so this analyzer stays independent
        of any chat source.
        """
        stats: dict[str, _SpeakerStats] = {}

        for message in messages:
            speaker_stats = stats.setdefault(message.sender, _SpeakerStats())
            speaker_stats.add(message)

        total_message_count = len(messages)
        speaker_words = _speaker_top_words(sender_tokens, top_words_per_user)
        profiles = [
            UserProfile(
                speaker=speaker,
                message_count=speaker_stats.message_count,
                message_share_percent=_share_percent(
                    speaker_stats.message_count,
                    total_message_count,
                ),
                average_length=speaker_stats.average_length(),
                max_length=speaker_stats.max_length,
                busiest_hour=busiest_index(speaker_stats.hourly_counts),
                busiest_weekday=busiest_index(speaker_stats.weekday_counts),
                top_words=speaker_words.get(speaker, ()),
                display_name=_speaker_display_name(speaker, speaker_names),
            )
            for speaker, speaker_stats in stats.items()
        ]
        profiles.sort(key=lambda profile: -profile.message_count)

        return UserProfileReport(
            total_message_count=total_message_count,
            speaker_count=len(profiles),
            profiles=tuple(profiles),
        )


class _SpeakerStats:
    """Mutable accumulator for one speaker."""

    __slots__ = (
        "message_count",
        "hourly_counts",
        "weekday_counts",
        "text_lengths",
        "max_length",
    )

    def __init__(self) -> None:
        self.message_count = 0
        self.hourly_counts = [0] * HOURS_PER_DAY
        self.weekday_counts = [0] * DAYS_PER_WEEK
        self.text_lengths: list[int] = []
        self.max_length = 0

    def add(self, message: ChatMessage) -> None:
        self.message_count += 1

        length = len(clean_text(message.text))
        if length > 0:
            self.text_lengths.append(length)
            self.max_length = max(self.max_length, length)

        moment = to_utc_datetime(message.timestamp)
        if moment is not None:
            self.hourly_counts[moment.hour] += 1
            self.weekday_counts[moment.weekday()] += 1

    def average_length(self) -> float:
        if not self.text_lengths:
            return 0.0
        return round(sum(self.text_lengths) / len(self.text_lengths), 2)


def _share_percent(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total * 100, 2)


def _speaker_top_words(
    sender_tokens: Iterable[tuple[str, Iterable[str]]] | None,
    top_words_per_user: int,
) -> dict[str, tuple[ProfileWord, ...]]:
    if sender_tokens is None or top_words_per_user <= 0:
        return {}

    token_lists: dict[str, list[str]] = {}
    for sender, tokens in sender_tokens:
        token_lists.setdefault(sender, []).extend(tokens)

    return {
        sender: tuple(
            ProfileWord(word=word, count=count)
            for word, count in top_words(tokens, top_words_per_user)
        )
        for sender, tokens in token_lists.items()
    }


def _speaker_display_name(
    speaker: str,
    speaker_names: Mapping[str, str] | None,
) -> str | None:
    """Look up a friendly name for one speaker key."""
    if not speaker_names:
        return None
    name = speaker_names.get(speaker)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None
