"""Application-layer time scoping for source-neutral chat messages."""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from ..analysis.timestamps import to_epoch_seconds
from ..message import ChatMessage
from .errors import (
    InvalidAnalysisScope,
    InvalidAnalysisScopeRange,
    MissingAnalysisScopeDate,
)


class AnalysisScopeMode(str, Enum):
    """User-selectable time windows for one analysis run."""

    ALL = "all"
    LAST_YEAR = "last_year"
    LAST_SIX_MONTHS = "last_six_months"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    """One resolved, inclusive calendar-date range."""

    mode: AnalysisScopeMode = AnalysisScopeMode.ALL
    start_date: date | None = None
    end_date: date | None = None

    @classmethod
    def all(cls) -> "AnalysisScope":
        return cls()

    @classmethod
    def last_year(cls, reference_date: date | None = None) -> "AnalysisScope":
        end_date = reference_date or date.today()
        return cls(
            mode=AnalysisScopeMode.LAST_YEAR,
            start_date=_shift_year(end_date, -1),
            end_date=end_date,
        )

    @classmethod
    def last_six_months(
        cls,
        reference_date: date | None = None,
    ) -> "AnalysisScope":
        end_date = reference_date or date.today()
        return cls(
            mode=AnalysisScopeMode.LAST_SIX_MONTHS,
            start_date=_shift_months(end_date, -6),
            end_date=end_date,
        )

    @classmethod
    def custom(
        cls,
        start_date: date | None,
        end_date: date | None,
    ) -> "AnalysisScope":
        if start_date is None or end_date is None:
            raise MissingAnalysisScopeDate()
        if start_date > end_date:
            raise InvalidAnalysisScopeRange()
        return cls(
            mode=AnalysisScopeMode.CUSTOM,
            start_date=start_date,
            end_date=end_date,
        )


def filter_messages(
    messages: Iterable[ChatMessage],
    scope: AnalysisScope,
) -> list[ChatMessage]:
    """Return messages whose own timestamps fall inside ``scope``."""
    source_messages = list(messages)
    if scope.mode is AnalysisScopeMode.ALL:
        return source_messages

    if scope.start_date is None or scope.end_date is None:
        raise InvalidAnalysisScope()

    return [
        message
        for message in source_messages
        if (
            (message_date := _message_date(message.timestamp)) is not None
            and scope.start_date <= message_date <= scope.end_date
        )
    ]


def resolve_scope(
    mode: AnalysisScopeMode | str,
    *,
    start_time: Any = None,
    end_time: Any = None,
    reference_date: date | None = None,
) -> AnalysisScope:
    """Resolve one GUI/facade selection into inclusive calendar dates."""
    try:
        resolved_mode = AnalysisScopeMode(mode)
    except ValueError:
        raise InvalidAnalysisScope() from None

    if resolved_mode is AnalysisScopeMode.ALL and (
        start_time is not None or end_time is not None
    ):
        resolved_mode = AnalysisScopeMode.CUSTOM

    if resolved_mode is AnalysisScopeMode.ALL:
        return AnalysisScope.all()
    if resolved_mode is AnalysisScopeMode.LAST_YEAR:
        return AnalysisScope.last_year(reference_date)
    if resolved_mode is AnalysisScopeMode.LAST_SIX_MONTHS:
        return AnalysisScope.last_six_months(reference_date)
    return AnalysisScope.custom(
        _coerce_date(start_time),
        _coerce_date(end_time),
    )


def _shift_year(value: date, years: int) -> date:
    target_year = value.year + years
    target_day = min(value.day, calendar.monthrange(target_year, value.month)[1])
    return date(target_year, value.month, target_day)


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    target_year, zero_based_month = divmod(month_index, 12)
    target_month = zero_based_month + 1
    target_day = min(value.day, calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def _message_date(timestamp: object) -> date | None:
    if isinstance(timestamp, bool) or timestamp is None:
        return None
    if isinstance(timestamp, datetime):
        return (
            timestamp.astimezone().date()
            if timestamp.tzinfo is not None
            else timestamp.date()
        )
    if isinstance(timestamp, date):
        return timestamp
    if isinstance(timestamp, (int, float)):
        return _epoch_date(timestamp)
    if not isinstance(timestamp, str):
        return None

    text = timestamp.strip()
    if not text:
        return None
    try:
        return _epoch_date(float(text))
    except ValueError:
        pass

    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
    except ValueError:
        epoch_seconds = to_epoch_seconds(text)
        return _epoch_date(epoch_seconds) if epoch_seconds is not None else None
    return parsed.astimezone().date() if parsed.tzinfo is not None else parsed.date()


def _coerce_date(value: Any) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return _epoch_date(value)
    if not isinstance(value, str):
        raise InvalidAnalysisScope()
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise InvalidAnalysisScope() from None


def _epoch_date(timestamp: int | float) -> date | None:
    epoch_seconds = to_epoch_seconds(timestamp)
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(epoch_seconds).date()
    except (OSError, OverflowError, ValueError):
        return None


__all__ = [
    "AnalysisScope",
    "AnalysisScopeMode",
    "InvalidAnalysisScope",
    "filter_messages",
    "resolve_scope",
]
