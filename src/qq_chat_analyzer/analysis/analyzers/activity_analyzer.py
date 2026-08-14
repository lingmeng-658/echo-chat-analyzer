"""Temporal activity analysis over normalized chat messages."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import ActivityReport, HourlyActivity, WeekdayActivity
from ..peaks import (
    DAYS_PER_WEEK,
    HOURS_PER_DAY,
    WEEKDAY_KEYS,
    busiest_index,
)
from ..timestamps import to_chat_datetime
from ...message import ChatMessage


class ActivityAnalyzer:
    """Report how messages are distributed across hours and weekdays."""

    def analyze(self, messages: Sequence[ChatMessage]) -> ActivityReport:
        """Return the temporal distribution for the given messages."""
        hourly_counts = [0] * HOURS_PER_DAY
        weekday_counts = [0] * DAYS_PER_WEEK
        dated_message_count = 0

        for message in messages:
            moment = to_chat_datetime(message.timestamp)
            if moment is None:
                continue
            dated_message_count += 1
            hourly_counts[moment.hour] += 1
            weekday_counts[moment.weekday()] += 1

        peak_hour = busiest_index(hourly_counts)
        peak_weekday_index = busiest_index(weekday_counts)

        return ActivityReport(
            total_message_count=len(messages),
            dated_message_count=dated_message_count,
            hourly_counts=tuple(
                HourlyActivity(hour=hour, count=count)
                for hour, count in enumerate(hourly_counts)
            ),
            weekday_counts=tuple(
                WeekdayActivity(weekday=weekday, count=count)
                for weekday, count in enumerate(weekday_counts)
            ),
            busiest_hour=peak_hour,
            busiest_weekday=peak_weekday_index,
            hour_distribution={
                hour: count for hour, count in enumerate(hourly_counts)
            },
            weekday_distribution={
                WEEKDAY_KEYS[weekday]: count
                for weekday, count in enumerate(weekday_counts)
            },
            peak_hour=peak_hour,
            peak_weekday=(
                None
                if peak_weekday_index is None
                else WEEKDAY_KEYS[peak_weekday_index]
            ),
        )
