"""Behavior tests for source-neutral conversation session analysis."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.analysis.conversation_sessions import (  # noqa: E402
    DEFAULT_SESSION_THRESHOLD_SECONDS,
    analyze_conversation_sessions,
)
from qq_chat_analyzer.message import ChatMessage  # noqa: E402


BASE_TIMESTAMP = 1_704_067_200


def _message(
    offset_seconds: int | None,
    *,
    sender: str = "Fictional Alice",
    sender_id: str | None = "fictional-alice-id",
    conversation_type: str = "private",
    is_self: bool | None = True,
) -> ChatMessage:
    timestamp: int | str = (
        BASE_TIMESTAMP + offset_seconds
        if offset_seconds is not None
        else "invalid-time"
    )
    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        sender_id=sender_id,
        message_type="text",
        text="fictional message",
        platform="fictional",
        conversation_id="fictional-conversation",
        conversation_type=conversation_type,
        is_self=is_self,
    )


def test_empty_messages_produce_empty_session_report() -> None:
    report = analyze_conversation_sessions(())

    assert report.threshold_seconds == DEFAULT_SESSION_THRESHOLD_SECONDS
    assert report.session_count == 0
    assert report.sessions == ()
    assert report.average_duration_seconds == 0.0
    assert report.median_duration_seconds == 0.0
    assert report.longest_duration_seconds == 0
    assert report.average_message_count == 0.0
    assert report.private_stats is None


def test_messages_within_thirty_minutes_stay_in_one_session() -> None:
    report = analyze_conversation_sessions(
        (_message(0), _message(29 * 60 + 59))
    )

    assert report.session_count == 1
    assert report.sessions[0].message_count == 2
    assert report.sessions[0].duration_seconds == 29 * 60 + 59


def test_gap_over_thirty_minutes_starts_new_session() -> None:
    report = analyze_conversation_sessions(
        (_message(0), _message(30 * 60 + 1))
    )

    assert report.session_count == 2
    assert tuple(item.message_count for item in report.sessions) == (1, 1)


def test_gap_exactly_thirty_minutes_stays_in_same_session() -> None:
    report = analyze_conversation_sessions((_message(0), _message(30 * 60)))

    assert report.session_count == 1
    assert report.sessions[0].duration_seconds == 30 * 60


def test_custom_threshold_controls_session_boundary() -> None:
    report = analyze_conversation_sessions(
        (_message(0), _message(60 * 60)),
        threshold_seconds=60 * 60,
    )

    assert report.threshold_seconds == 60 * 60
    assert report.session_count == 1


def test_single_message_session_has_zero_duration() -> None:
    report = analyze_conversation_sessions((_message(0),))

    session = report.sessions[0]
    assert session.start_timestamp == BASE_TIMESTAMP
    assert session.end_timestamp == BASE_TIMESTAMP
    assert session.duration_seconds == 0
    assert session.message_count == 1


def test_invalid_and_zero_timestamps_do_not_split_or_distort_session() -> None:
    zero_timestamp = _message(0)
    zero_timestamp = ChatMessage(
        timestamp=0,
        sender=zero_timestamp.sender,
        sender_id=zero_timestamp.sender_id,
        message_type=zero_timestamp.message_type,
        text=zero_timestamp.text,
        platform=zero_timestamp.platform,
        conversation_id=zero_timestamp.conversation_id,
        conversation_type=zero_timestamp.conversation_type,
        is_self=zero_timestamp.is_self,
    )
    report = analyze_conversation_sessions(
        (
            _message(0),
            _message(None),
            zero_timestamp,
            _message(20 * 60),
        )
    )

    assert report.session_count == 1
    session = report.sessions[0]
    assert session.message_count == 4
    assert session.start_timestamp == BASE_TIMESTAMP
    assert session.end_timestamp == BASE_TIMESTAMP + 20 * 60
    assert session.duration_seconds == 20 * 60


def test_private_sessions_report_self_peer_and_unknown_initiators() -> None:
    report = analyze_conversation_sessions(
        (
            _message(0, is_self=True),
            _message(31 * 60, is_self=False),
            _message(62 * 60, is_self=None),
        )
    )

    assert tuple(item.initiator for item in report.sessions) == (
        "self",
        "peer",
        "unknown",
    )
    stats = report.private_stats
    assert stats is not None
    assert stats.self_initiated_count == 1
    assert stats.peer_initiated_count == 1
    assert stats.unknown_initiated_count == 1
    assert stats.self_to_peer_ratio == 1.0
    assert stats.self_initiated_share == 1 / 3
    assert stats.peer_initiated_share == 1 / 3
    assert stats.unknown_initiated_share == 1 / 3


def test_private_report_calculates_duration_and_message_aggregates() -> None:
    report = analyze_conversation_sessions(
        (
            _message(0),
            _message(10 * 60),
            _message(60 * 60, is_self=False),
            _message(80 * 60, is_self=True),
            _message(90 * 60, is_self=False),
        )
    )

    assert report.session_count == 2
    assert report.average_duration_seconds == 20 * 60
    assert report.median_duration_seconds == 20 * 60
    assert report.longest_duration_seconds == 30 * 60
    assert report.average_message_count == 2.5
    assert report.private_stats is not None
    assert report.private_stats.self_initiated_count == 1
    assert report.private_stats.peer_initiated_count == 1


def test_private_self_to_peer_ratio_is_none_without_peer_sessions() -> None:
    report = analyze_conversation_sessions((_message(0, is_self=True),))

    assert report.private_stats is not None
    assert report.private_stats.self_to_peer_ratio is None


def test_group_session_uses_stable_sender_identity_as_initiator() -> None:
    report = analyze_conversation_sessions(
        (
            _message(
                0,
                sender="Old Fictional Name",
                sender_id="stable-fictional-id",
                conversation_type="group",
                is_self=None,
            ),
            _message(
                10,
                sender="New Fictional Name",
                sender_id="stable-fictional-id",
                conversation_type="group",
                is_self=None,
            ),
        )
    )

    assert report.conversation_type == "group"
    assert report.sessions[0].initiator == "stable-fictional-id"
    assert report.sessions[0].initiator_sender_key == "stable-fictional-id"
    assert report.private_stats is None


def test_group_report_aggregates_self_and_top_initiator() -> None:
    report = analyze_conversation_sessions(
        (
            _message(
                0,
                sender="Fictional Alice",
                sender_id="fictional-alice-id",
                conversation_type="group",
                is_self=True,
            ),
            _message(
                31 * 60,
                sender="Fictional Alice Renamed",
                sender_id="fictional-alice-id",
                conversation_type="group",
                is_self=True,
            ),
            _message(
                62 * 60,
                sender="Fictional Bob",
                sender_id="fictional-bob-id",
                conversation_type="group",
                is_self=False,
            ),
        )
    )

    stats = report.group_stats
    assert stats is not None
    assert stats.self_initiated_count == 2
    assert stats.self_initiated_share == 2 / 3
    assert stats.top_initiator_sender_key == "fictional-alice-id"
    assert stats.top_initiated_count == 2
    assert stats.top_initiated_share == 2 / 3


def test_group_self_initiator_stats_require_reliable_identity() -> None:
    report = analyze_conversation_sessions(
        (
            _message(0, conversation_type="group", is_self=None),
            _message(31 * 60, conversation_type="group", is_self=None),
        )
    )

    stats = report.group_stats
    assert stats is not None
    assert stats.self_initiated_count is None
    assert stats.self_initiated_share is None
# === Group conversation session records ===


def _group_message(
    offset_seconds: int | None,
    *,
    sender: str = "Fictional Alice",
    sender_id: str | None = "fictional-alice-id",
    is_self: bool | None = None,
) -> ChatMessage:
    """Helper for group-chat test messages."""
    timestamp: int | str = (
        BASE_TIMESTAMP + offset_seconds
        if offset_seconds is not None
        else "invalid-time"
    )
    return ChatMessage(
        timestamp=timestamp,
        sender=sender,
        sender_id=sender_id,
        message_type="text",
        text="fictional message",
        platform="fictional",
        conversation_id="fictional-conversation",
        conversation_type="group",
        is_self=is_self,
    )


def test_group_session_participant_count_tracks_unique_senders() -> None:
    """participant_count must reflect unique stable sender identities."""
    report = analyze_conversation_sessions((
        _group_message(0, sender="Alice", sender_id="alice-id"),
        _group_message(10, sender="Alice Renamed", sender_id="alice-id"),
        _group_message(20, sender="Bob", sender_id="bob-id"),
    ))
    assert report.session_count == 1
    assert report.sessions[0].participant_count == 2


def test_participant_count_single_sender_is_one() -> None:
    """A session with one sender has participant_count = 1."""
    report = analyze_conversation_sessions((
        _group_message(0, sender="Alice", sender_id="alice-id"),
        _group_message(10, sender="Alice", sender_id="alice-id"),
    ))
    assert report.sessions[0].participant_count == 1


def test_participant_count_fallback_to_sender_when_no_sender_id() -> None:
    """When sender_id is None, fall back to sender field for counting."""
    report = analyze_conversation_sessions((
        _group_message(0, sender="Alice", sender_id=None),
        _group_message(10, sender="Bob", sender_id=None),
    ))
    assert report.sessions[0].participant_count == 2

def test_start_hour_peak_reflects_most_common_session_start() -> None:
    """peak_start_hour identifies the hour with the most session starts.

    BASE_TIMESTAMP = 1704067200 = 2024-01-01 00:00:00 UTC = 08:00 CST.
    CST 10:00 = offset 7200, CST 14:00 = offset 21600.
    """
    report = analyze_conversation_sessions((
        _group_message(7200, sender_id="a"),
        _group_message(9001, sender_id="b"),
        _group_message(21600, sender_id="c"),
    ), threshold_seconds=1800)
    assert report.session_count == 3
    assert report.peak_start_hour == 10


def test_start_hour_peak_tie_break_uses_lower_hour() -> None:
    """When two hours tie, the smaller hour wins.

    BASE = 2024-01-01 08:00 CST.
    CST 08:00 = offset 0, CST 20:00 = offset 43200.
    """
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1801, sender_id="b"),
        _group_message(43200, sender_id="c"),
        _group_message(45001, sender_id="d"),
    ), threshold_seconds=1800)
    assert report.session_count == 4
    assert report.peak_start_hour == 8


def test_start_hour_ignores_sessions_without_valid_timestamp() -> None:
    """Sessions with None start_timestamp do not contribute to start-hour."""
    report = analyze_conversation_sessions((
        _group_message(None, sender_id="a"),
        _group_message(None, sender_id="b"),
    ))
    assert report.session_count == 1
    assert report.start_hour_counts == ()
    assert report.peak_start_hour is None


def test_start_hour_counts_has_24_entries() -> None:
    """start_hour_counts returns a 24-element tuple of HourlyActivity."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1801, sender_id="b"),
    ), threshold_seconds=1800)
    assert len(report.start_hour_counts) == 24
    total = sum(entry.count for entry in report.start_hour_counts)
    assert total == report.session_count


def test_session_character_quick_and_brief() -> None:
    """Short median duration and >60% sessions with <=5 messages -> quick_and_brief."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(61, sender_id="b"),
        _group_message(1862, sender_id="c"),
        _group_message(1922, sender_id="a"),
        _group_message(3723, sender_id="b"),
        _group_message(3783, sender_id="c"),
        _group_message(5584, sender_id="a"),
        _group_message(5585, sender_id="a"),
        _group_message(5586, sender_id="a"),
        _group_message(5587, sender_id="a"),
        _group_message(5588, sender_id="a"),
        _group_message(5589, sender_id="a"),
        _group_message(5590, sender_id="a"),
        _group_message(5591, sender_id="a"),
        _group_message(5592, sender_id="a"),
        _group_message(5593, sender_id="a"),
    ), threshold_seconds=1800)
    assert report.session_character == "quick_and_brief"


def test_session_character_long_running() -> None:
    """Median duration > 1800s -> long_running."""
    # 3 sessions, each lasting > 1800s
    # Session 1: offsets 0, 1800, 2000, 2200 -> 4msgs, 2200s
    # Session 2: offsets 4001, 5800, 6000, 6200 -> 4msgs, 2199s
    # Session 3: offsets 8001, 9800, 10000, 10200 -> 4msgs, 2199s
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1800, sender_id="b"),
        _group_message(2000, sender_id="c"),
        _group_message(2200, sender_id="a"),
        _group_message(4001, sender_id="b"),
        _group_message(5800, sender_id="c"),
        _group_message(6000, sender_id="a"),
        _group_message(6200, sender_id="b"),
        _group_message(8001, sender_id="c"),
        _group_message(9800, sender_id="a"),
        _group_message(10000, sender_id="b"),
        _group_message(10200, sender_id="c"),
    ), threshold_seconds=1800)
    assert report.session_character == "long_running"


def test_session_character_mixed() -> None:
    """Neither quick nor long -> mixed."""
    # 3 sessions, median between 300 and 1800, not >60% short
    # Session 1: offsets 0..604 -> 6msgs, 604s
    # Session 2: offsets 2405..3004 -> 6msgs, 599s
    # Session 3: offsets 4805..5404 -> 6msgs, 599s
    # Median = 599s, 0/3=0% <=5msgs -> not quick_and_brief
    # 599s < 1800s -> not long_running -> mixed
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(600, sender_id="b"),
        _group_message(601, sender_id="c"),
        _group_message(602, sender_id="a"),
        _group_message(603, sender_id="b"),
        _group_message(604, sender_id="c"),
        _group_message(2405, sender_id="a"),
        _group_message(3000, sender_id="b"),
        _group_message(3001, sender_id="c"),
        _group_message(3002, sender_id="a"),
        _group_message(3003, sender_id="b"),
        _group_message(3004, sender_id="c"),
        _group_message(4805, sender_id="a"),
        _group_message(5400, sender_id="b"),
        _group_message(5401, sender_id="c"),
        _group_message(5402, sender_id="a"),
        _group_message(5403, sender_id="b"),
        _group_message(5404, sender_id="c"),
    ), threshold_seconds=1800)
    assert report.session_character == "mixed"


def test_session_character_none_when_few_sessions() -> None:
    """Fewer than 3 sessions -> character is None."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1801, sender_id="b"),
    ), threshold_seconds=1800)
    assert report.session_character is None
def test_loudest_most_messages_picks_session_with_highest_message_count() -> None:
    """loudest_most_messages picks the session with the highest message_count."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(10, sender_id="b"),
        _group_message(20, sender_id="c"),
        _group_message(1821, sender_id="a"),
        _group_message(3622, sender_id="b"),
        _group_message(3631, sender_id="c"),
    ), threshold_seconds=1800)
    assert report.loudest_most_messages is not None
    loudest = report.sessions[report.loudest_most_messages]
    assert loudest.message_count == 3


def test_loudest_longest_duration_picks_session_with_longest_duration() -> None:
    """loudest_longest_duration picks the session with the greatest duration_seconds."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1800, sender_id="b"),
        _group_message(3601, sender_id="a"),
        _group_message(5401, sender_id="b"),
    ), threshold_seconds=1800)
    assert report.loudest_longest_duration is not None
    loudest = report.sessions[report.loudest_longest_duration]
    assert loudest.duration_seconds == 1800


def test_loudest_most_participants_picks_session_with_most_unique_senders() -> None:
    """loudest_most_participants picks the session with the highest participant_count."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(10, sender_id="b"),
        _group_message(20, sender_id="c"),
        _group_message(1821, sender_id="a"),
        _group_message(3622, sender_id="b"),
        _group_message(3631, sender_id="c"),
        _group_message(3640, sender_id="a"),
    ), threshold_seconds=1800)
    assert report.loudest_most_participants is not None
    loudest = report.sessions[report.loudest_most_participants]
    assert loudest.participant_count == 3


def test_loudest_densest_picks_session_with_highest_density() -> None:
    """loudest_densest picks the candidate with highest messages-per-second ratio."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(60, sender_id="b"),
        _group_message(120, sender_id="c"),
        _group_message(1921, sender_id="a"),
        _group_message(1930, sender_id="b"),
        _group_message(1940, sender_id="c"),
        _group_message(1950, sender_id="a"),
        _group_message(1960, sender_id="b"),
        _group_message(1970, sender_id="c"),
        _group_message(1980, sender_id="a"),
        _group_message(1990, sender_id="b"),
        _group_message(2000, sender_id="c"),
        _group_message(2120, sender_id="a"),
    ), threshold_seconds=1800)
    loudest_idx = report.loudest_densest
    assert loudest_idx is not None
    assert loudest_idx == 1


def test_loudest_densest_no_eligible_candidate() -> None:
    """When no session meets minimum duration and message_count, densest is None."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(1801, sender_id="b"),
        _group_message(3601, sender_id="c"),
    ), threshold_seconds=1800)
    assert report.loudest_densest is None


def test_loudest_tie_break_uses_earlier_start_timestamp() -> None:
    """When two sessions tie on the primary metric, earlier start_timestamp wins."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(60, sender_id="b"),
        _group_message(1861, sender_id="c"),
        _group_message(1921, sender_id="a"),
    ), threshold_seconds=1800)
    assert report.loudest_most_messages is not None
    loudest = report.sessions[report.loudest_most_messages]
    assert loudest == report.sessions[0]


def test_loudest_densest_tie_break_uses_message_count() -> None:
    """When two sessions tie on density, higher message_count then earlier start wins."""
    report = analyze_conversation_sessions((
        _group_message(0, sender_id="a"),
        _group_message(10, sender_id="b"),
        _group_message(20, sender_id="c"),
        _group_message(30, sender_id="a"),
        _group_message(40, sender_id="b"),
        _group_message(50, sender_id="c"),
        _group_message(60, sender_id="a"),
        _group_message(70, sender_id="b"),
        _group_message(80, sender_id="c"),
        _group_message(200, sender_id="a"),
        _group_message(2001, sender_id="b"),
        _group_message(2010, sender_id="c"),
        _group_message(2020, sender_id="a"),
        _group_message(2030, sender_id="b"),
        _group_message(2040, sender_id="c"),
        _group_message(2050, sender_id="a"),
        _group_message(2060, sender_id="b"),
        _group_message(2070, sender_id="c"),
        _group_message(2080, sender_id="a"),
        _group_message(2201, sender_id="b"),
    ), threshold_seconds=1800)
    assert report.loudest_densest is not None
    # Same density, same message_count, session 1 starts earlier -> index 0
    assert report.loudest_densest == 0


# === Private conversation session v1 ===


def _private_pair(offset_seconds, *, self_message: bool) -> ChatMessage:
    """One private message from the self/peer side with a distinct sender key."""
    if self_message:
        return _message(
            offset_seconds,
            is_self=True,
            sender="Fictional Self",
            sender_id="fictional-self-id",
        )
    return _message(
        offset_seconds,
        is_self=False,
        sender="Fictional Peer",
        sender_id="fictional-peer-id",
    )


def test_private_reply_timing_medians_for_both_directions() -> None:
    """Reply latency is the initiator's first valid message to the other side."""
    report = analyze_conversation_sessions(
        (
            _private_pair(0, self_message=True),
            _private_pair(60, self_message=False),
            _private_pair(120, self_message=True),
            _private_pair(2000, self_message=False),
            _private_pair(2045, self_message=True),
            _private_pair(2090, self_message=False),
        )
    )

    assert report.conversation_type == "private"
    assert report.private_reply_timing is not None
    assert report.private_reply_timing.self_to_peer_median_seconds == 60.0
    assert report.private_reply_timing.peer_to_self_median_seconds == 45.0


def test_private_reply_timing_excludes_one_sided_sessions() -> None:
    """Sessions where only one side appears never contribute reply latency."""
    report = analyze_conversation_sessions(
        (
            _private_pair(0, self_message=True),
            _private_pair(60, self_message=True),
            _private_pair(2000, self_message=False),
            _private_pair(2090, self_message=True),
        )
    )

    assert report.private_reply_timing is not None
    assert report.private_reply_timing.self_to_peer_median_seconds is None
    assert report.private_reply_timing.peer_to_self_median_seconds == 90.0


def test_private_reply_timing_uses_initiators_first_valid_message() -> None:
    """An invalid initiator timestamp is skipped, not treated as time zero."""
    report = analyze_conversation_sessions(
        (
            _message(None, is_self=True, sender_id="fictional-self-id"),
            _private_pair(100, self_message=True),
            _private_pair(250, self_message=False),
        )
    )

    assert report.private_reply_timing is not None
    assert report.private_reply_timing.self_to_peer_median_seconds == 150.0


def test_private_reply_timing_ignores_negative_reply_windows() -> None:
    """If the other side appears before the initiator's first valid message, skip."""
    report = analyze_conversation_sessions(
        (
            _message(None, is_self=True, sender_id="fictional-self-id"),
            _private_pair(100, self_message=False),
            _private_pair(200, self_message=True),
        )
    )

    assert report.private_reply_timing is not None
    assert report.private_reply_timing.self_to_peer_median_seconds is None


def test_private_start_hour_peak_is_per_initiator() -> None:
    """Self and peer each get their own most common active-start hour."""
    report = analyze_conversation_sessions(
        (
            _private_pair(7200, self_message=True),
            _private_pair(9001, self_message=True),
            _private_pair(21601, self_message=False),
            _private_pair(25201, self_message=False),
        ),
        threshold_seconds=1800,
    )

    assert report.private_self_peak_start_hour == 10
    assert report.private_peer_peak_start_hour == 14


def test_private_start_hour_peak_is_none_when_side_missing() -> None:
    """A side with no reliably initiated sessions has no peak hour."""
    report = analyze_conversation_sessions(
        (
            _private_pair(7200, self_message=True),
            _private_pair(9001, self_message=True),
        ),
        threshold_seconds=1800,
    )

    assert report.private_self_peak_start_hour == 10
    assert report.private_peer_peak_start_hour is None


def _alternating_session(
    start_offset: int,
    *,
    message_count: int,
    gap_seconds: int = 10,
    first_self: bool = True,
) -> tuple[ChatMessage, ...]:
    messages = []
    for index in range(message_count):
        offset = start_offset + index * gap_seconds
        self_message = (index % 2 == 0) if first_self else (index % 2 == 1)
        messages.append(_private_pair(offset, self_message=self_message))
    return tuple(messages)


def test_private_back_and_forth_prefers_higher_switch_ratio() -> None:
    """Higher sender-switch ratio wins among eligible sessions."""
    alternating = _alternating_session(0, message_count=10, gap_seconds=20)
    clustered = (
        _private_pair(2000, self_message=True),
        _private_pair(2015, self_message=True),
        _private_pair(2030, self_message=True),
        _private_pair(2045, self_message=True),
        _private_pair(2060, self_message=True),
        _private_pair(2075, self_message=True),
        _private_pair(2090, self_message=False),
        _private_pair(2105, self_message=False),
        _private_pair(2120, self_message=False),
        _private_pair(2135, self_message=False),
        _private_pair(2150, self_message=False),
        _private_pair(2165, self_message=False),
    )
    report = analyze_conversation_sessions(alternating + clustered)

    assert report.loudest_most_back_and_forth == 0


def test_private_back_and_forth_eligibility_thresholds() -> None:
    """Candidates need duration >= 120s and message_count >= 10."""
    too_short = _alternating_session(0, message_count=10, gap_seconds=10)
    report = analyze_conversation_sessions(too_short)
    assert report.sessions[0].duration_seconds == 90
    assert report.loudest_most_back_and_forth is None

    too_few = _alternating_session(0, message_count=9, gap_seconds=20)
    report = analyze_conversation_sessions(too_few)
    assert report.sessions[0].message_count == 9
    assert report.loudest_most_back_and_forth is None


def test_private_back_and_forth_tie_breaks() -> None:
    """Ties resolve by messages, duration, earlier start, then original order."""
    report = analyze_conversation_sessions(
        _alternating_session(0, message_count=12, gap_seconds=20)
        + _alternating_session(2200, message_count=10, gap_seconds=20)
    )
    assert report.loudest_most_back_and_forth == 0

    report = analyze_conversation_sessions(
        _alternating_session(0, message_count=10, gap_seconds=10)
        + _alternating_session(2000, message_count=10, gap_seconds=20)
    )
    assert report.loudest_most_back_and_forth == 1

    report = analyze_conversation_sessions(
        _alternating_session(0, message_count=10, gap_seconds=20)
        + _alternating_session(2000, message_count=10, gap_seconds=20)
    )
    assert report.loudest_most_back_and_forth == 0


def test_private_back_and_forth_uses_valid_messages_only() -> None:
    """Invalid timestamps are excluded from the switch-ratio denominator."""
    messages = list(_alternating_session(0, message_count=12, gap_seconds=20))
    messages[3] = _message(None, is_self=True, sender_id="fictional-self-id")
    messages[8] = _message(None, is_self=False, sender_id="fictional-peer-id")
    report = analyze_conversation_sessions(tuple(messages))

    assert report.loudest_most_back_and_forth == 0


def test_private_session_self_peer_message_counts() -> None:
    """Private sessions carry per-side counts, or None when identity is unreliable."""
    report = analyze_conversation_sessions(
        (
            _private_pair(0, self_message=True),
            _private_pair(10, self_message=True),
            _private_pair(20, self_message=False),
            _private_pair(30, self_message=False),
            _private_pair(40, self_message=True),
        )
    )
    session = report.sessions[0]
    assert session.self_message_count == 3
    assert session.peer_message_count == 2

    unreliable = analyze_conversation_sessions(
        (
            _private_pair(0, self_message=True),
            _message(10, is_self=None, sender_id="fictional-unknown-id"),
            _private_pair(20, self_message=False),
        )
    )
    assert unreliable.sessions[0].self_message_count is None
    assert unreliable.sessions[0].peer_message_count is None


def test_private_reuses_character_and_loudest_rules() -> None:
    """Private sessions reuse group character/loudest rules without participant metric."""
    report = analyze_conversation_sessions(
        (
            _private_pair(0, self_message=True),
            _private_pair(1800, self_message=False),
            _private_pair(2000, self_message=True),
            _private_pair(2200, self_message=False),
            _private_pair(4001, self_message=True),
            _private_pair(5800, self_message=False),
            _private_pair(6000, self_message=True),
            _private_pair(6200, self_message=False),
            _private_pair(8001, self_message=True),
            _private_pair(9800, self_message=False),
            _private_pair(10000, self_message=True),
            _private_pair(10200, self_message=False),
        ),
        threshold_seconds=1800,
    )

    assert report.session_character == "long_running"
    assert report.loudest_most_messages is not None
    assert report.loudest_longest_duration is not None
    assert report.loudest_most_participants is None


def test_private_loudest_densest_uses_group_rules() -> None:
    """Private densest reuses the group eligibility and tie rules."""
    report = analyze_conversation_sessions(
        _alternating_session(0, message_count=12, gap_seconds=20)
    )
    assert report.sessions[0].duration_seconds == 220
    assert report.sessions[0].message_count == 12
    assert report.loudest_densest == 0
