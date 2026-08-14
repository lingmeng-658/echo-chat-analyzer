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
