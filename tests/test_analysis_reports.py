"""Behavior tests for the Analysis Core v2 report analyzers."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _models():
    return importlib.import_module("qq_chat_analyzer.analysis.models")


def _analyzers():
    return importlib.import_module("qq_chat_analyzer.analysis.analyzers")


def _chat_message():
    return importlib.import_module("qq_chat_analyzer.message").ChatMessage


def _epoch(
    year: int = 2024,
    month: int = 1,
    day: int = 1,
    hour: int = 0,
    minute: int = 0,
) -> int:
    return int(
        datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=timezone.utc,
        ).timestamp()
    )


def _message(
    *,
    timestamp: int | float | str = 0,
    sender: str = "Fictional-Alice",
    text: str = "fictional text",
    conversation_id: str | None = "fictional-room-1",
):
    return _chat_message()(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
        platform="fictional",
        conversation_id=conversation_id,
    )


def test_report_models_are_immutable_dataclasses_without_instance_dicts() -> None:
    models = _models()

    for model_type in (
        models.ActivityReport,
        models.MessageLengthReport,
        models.UserProfileReport,
        models.ConversationReport,
        models.AnalysisReports,
    ):
        assert dataclasses.is_dataclass(model_type)

    report = models.ActivityReport(
        total_message_count=0,
        dated_message_count=0,
    )
    assert not hasattr(report, "__dict__")


def test_activity_analyzer_handles_empty_input_with_full_distribution() -> None:
    report = _analyzers().ActivityAnalyzer().analyze(())

    assert report.total_message_count == 0
    assert report.dated_message_count == 0
    assert len(report.hourly_counts) == 24
    assert len(report.weekday_counts) == 7
    assert all(entry.count == 0 for entry in report.hourly_counts)
    assert report.busiest_hour is None
    assert report.busiest_weekday is None


def test_activity_analyzer_counts_single_message_hour_and_weekday() -> None:
    message = _message(timestamp=_epoch(hour=9))

    report = _analyzers().ActivityAnalyzer().analyze((message,))

    hourly = {entry.hour: entry.count for entry in report.hourly_counts}
    weekday = {
        entry.weekday: entry.count for entry in report.weekday_counts
    }
    assert report.total_message_count == 1
    assert report.dated_message_count == 1
    assert hourly[9] == 1
    assert sum(hourly.values()) == 1
    assert weekday[0] == 1
    assert report.busiest_hour == 9
    assert report.busiest_weekday == 0


def test_activity_analyzer_picks_the_busiest_hour_across_messages() -> None:
    messages = (
        _message(timestamp=_epoch(hour=9)),
        _message(timestamp=_epoch(hour=21)),
        _message(timestamp=_epoch(hour=21)),
    )

    report = _analyzers().ActivityAnalyzer().analyze(messages)

    assert report.busiest_hour == 21
    assert report.dated_message_count == 3


def test_activity_analyzer_accepts_iso_strings_and_skips_unparsable() -> None:
    messages = (
        _message(timestamp="2024-01-01T09:30:00+00:00"),
        _message(timestamp="not-a-timestamp"),
    )

    report = _analyzers().ActivityAnalyzer().analyze(messages)

    hourly = {entry.hour: entry.count for entry in report.hourly_counts}
    assert report.total_message_count == 2
    assert report.dated_message_count == 1
    assert hourly[9] == 1


def test_message_length_analyzer_handles_empty_input() -> None:
    report = _analyzers().MessageLengthAnalyzer().analyze(())

    assert report.message_count == 0
    assert report.average_length == 0.0
    assert report.max_length == 0
    assert report.speaker_lengths == ()


def test_message_length_analyzer_reports_global_and_speaker_stats() -> None:
    messages = (
        _message(sender="Fictional-Alice", text="12345"),
        _message(sender="Fictional-Alice", text="123"),
        _message(sender="Fictional-Bob", text="1234567890"),
    )

    report = _analyzers().MessageLengthAnalyzer().analyze(messages)

    assert report.message_count == 3
    assert report.average_length == 6.0
    assert report.max_length == 10
    by_speaker = {
        entry.speaker: entry for entry in report.speaker_lengths
    }
    assert by_speaker["Fictional-Alice"].average_length == 4.0
    assert by_speaker["Fictional-Alice"].max_length == 5
    assert by_speaker["Fictional-Bob"].average_length == 10.0
    assert sum(bucket.count for bucket in report.buckets) == 3


def test_message_length_analyzer_ignores_messages_without_text() -> None:
    messages = (
        _message(text="1234"),
        _message(text="   "),
        _message(text=""),
    )

    report = _analyzers().MessageLengthAnalyzer().analyze(messages)

    assert report.message_count == 1
    assert report.average_length == 4.0


def test_user_profile_analyzer_handles_empty_input() -> None:
    report = _analyzers().UserProfileAnalyzer().analyze(())

    assert report.total_message_count == 0
    assert report.profiles == ()


def test_user_profile_analyzer_reports_shares_for_multiple_users() -> None:
    messages = (
        _message(sender="Fictional-Alice", text="1234", timestamp=_epoch(hour=8)),
        _message(sender="Fictional-Alice", text="12", timestamp=_epoch(hour=8)),
        _message(sender="Fictional-Alice", text="12", timestamp=_epoch(hour=9)),
        _message(sender="Fictional-Bob", text="123456", timestamp=_epoch(hour=22)),
    )

    report = _analyzers().UserProfileAnalyzer().analyze(messages)

    assert report.total_message_count == 4
    profiles = {profile.speaker: profile for profile in report.profiles}
    assert report.profiles[0].speaker == "Fictional-Alice"
    assert profiles["Fictional-Alice"].message_count == 3
    assert profiles["Fictional-Alice"].message_share_percent == 75.0
    assert profiles["Fictional-Alice"].busiest_hour == 8
    assert profiles["Fictional-Bob"].message_share_percent == 25.0
    assert profiles["Fictional-Bob"].average_length == 6.0


def test_user_profile_analyzer_reuses_supplied_tokens_for_top_words() -> None:
    messages = (
        _message(sender="Fictional-Alice", text="fictional deck talk"),
        _message(sender="Fictional-Bob", text="fictional trade talk"),
    )
    sender_tokens = (
        ("Fictional-Alice", ["deck", "deck", "talk"]),
        ("Fictional-Bob", ["trade"]),
    )

    report = _analyzers().UserProfileAnalyzer().analyze(
        messages,
        sender_tokens=sender_tokens,
        top_words_per_user=2,
    )

    profiles = {profile.speaker: profile for profile in report.profiles}
    alice_words = profiles["Fictional-Alice"].top_words
    assert alice_words[0].word == "deck"
    assert alice_words[0].count == 2
    assert len(alice_words) == 2
    assert profiles["Fictional-Bob"].top_words[0].word == "trade"


def test_conversation_analyzer_handles_empty_input() -> None:
    report = _analyzers().ConversationAnalyzer().analyze(())

    assert report.conversation_count == 0
    assert report.conversations == ()


def test_conversation_analyzer_reports_span_and_speakers_per_conversation() -> None:
    start = _epoch(hour=8)
    end = _epoch(hour=10)
    messages = (
        _message(
            conversation_id="fictional-room-1",
            sender="Fictional-Alice",
            timestamp=start,
        ),
        _message(
            conversation_id="fictional-room-1",
            sender="Fictional-Bob",
            timestamp=end,
        ),
        _message(
            conversation_id="fictional-room-2",
            sender="Fictional-Alice",
            timestamp=start,
        ),
    )

    report = _analyzers().ConversationAnalyzer().analyze(messages)

    assert report.conversation_count == 2
    conversations = {
        entry.conversation_id: entry for entry in report.conversations
    }
    room_one = conversations["fictional-room-1"]
    assert room_one.message_count == 2
    assert room_one.speaker_count == 2
    assert room_one.start_timestamp == start
    assert room_one.end_timestamp == end
    assert room_one.duration_seconds == 7200
    assert conversations["fictional-room-2"].duration_seconds == 0


def test_conversation_analyzer_groups_messages_without_conversation_id() -> None:
    messages = (
        _message(conversation_id=None, timestamp=_epoch(hour=1)),
        _message(conversation_id=None, timestamp=_epoch(hour=2)),
    )

    report = _analyzers().ConversationAnalyzer().analyze(messages)

    assert report.conversation_count == 1
    assert report.conversations[0].conversation_id is None
    assert report.conversations[0].message_count == 2


def test_conversation_analyzer_reports_no_span_without_valid_timestamps() -> None:
    messages = (_message(timestamp="not-a-timestamp"),)

    report = _analyzers().ConversationAnalyzer().analyze(messages)

    conversation = report.conversations[0]
    assert conversation.message_count == 1
    assert conversation.start_timestamp is None
    assert conversation.end_timestamp is None
    assert conversation.duration_seconds is None