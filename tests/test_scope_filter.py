"""Behavior tests for the application-layer analysis scope filter."""

from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _scope_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.scope_filter"
    )


def _message(timestamp):
    message_module = importlib.import_module("qq_chat_analyzer.message")
    return message_module.ChatMessage(
        timestamp=timestamp,
        sender="Fictional Alice",
        message_type="text",
        text="Fictional message",
    )


def test_all_scope_keeps_every_message_and_its_order() -> None:
    scope = _scope_module()
    messages = [
        _message(None),
        _message("not-a-timestamp"),
        _message("2026-08-11 12:00:00"),
    ]

    filtered = scope.filter_messages(messages, scope.AnalysisScope.all())

    assert filtered == messages


def test_last_year_uses_inclusive_calendar_date_boundaries() -> None:
    scope = _scope_module()
    messages = [
        _message("2025-08-10 23:59:59"),
        _message("2025-08-11 00:00:00"),
        _message("2026-08-11 23:59:59"),
        _message("2026-08-12 00:00:00"),
    ]

    filtered = scope.filter_messages(
        messages,
        scope.AnalysisScope.last_year(date(2026, 8, 11)),
    )

    assert [message.timestamp for message in filtered] == [
        "2025-08-11 00:00:00",
        "2026-08-11 23:59:59",
    ]


def test_last_six_months_uses_inclusive_calendar_date_boundaries() -> None:
    scope = _scope_module()
    messages = [
        _message("2026-02-10 23:59:59"),
        _message("2026-02-11 00:00:00"),
        _message("2026-08-11 23:59:59"),
        _message("2026-08-12 00:00:00"),
    ]

    filtered = scope.filter_messages(
        messages,
        scope.AnalysisScope.last_six_months(date(2026, 8, 11)),
    )

    assert [message.timestamp for message in filtered] == [
        "2026-02-11 00:00:00",
        "2026-08-11 23:59:59",
    ]


def test_custom_scope_includes_both_whole_boundary_dates() -> None:
    scope = _scope_module()
    messages = [
        _message("2026-03-31 23:59:59"),
        _message("2026-04-01 00:00:00"),
        _message("2026-04-30 23:59:59.999999"),
        _message("2026-05-01 00:00:00"),
    ]

    filtered = scope.filter_messages(
        messages,
        scope.AnalysisScope.custom(date(2026, 4, 1), date(2026, 4, 30)),
    )

    assert [message.timestamp for message in filtered] == [
        "2026-04-01 00:00:00",
        "2026-04-30 23:59:59.999999",
    ]


@pytest.mark.parametrize(
    ("reference_date", "expected_start"),
    [
        (date(2026, 8, 31), date(2026, 2, 28)),
        (date(2025, 5, 31), date(2024, 11, 30)),
        (date(2024, 8, 31), date(2024, 2, 29)),
    ],
)
def test_six_month_rollback_clamps_to_the_target_month_end(
    reference_date: date,
    expected_start: date,
) -> None:
    scope = _scope_module()

    resolved = scope.AnalysisScope.last_six_months(reference_date)

    assert resolved.start_date == expected_start
    assert resolved.end_date == reference_date


def test_year_rollback_clamps_leap_day_to_february_28() -> None:
    scope = _scope_module()

    resolved = scope.AnalysisScope.last_year(date(2024, 2, 29))

    assert resolved.start_date == date(2023, 2, 28)
    assert resolved.end_date == date(2024, 2, 29)


@pytest.mark.parametrize("timestamp", [None, "", "not-a-timestamp"])
def test_scoped_filter_excludes_unusable_timestamps(timestamp) -> None:
    scope = _scope_module()

    filtered = scope.filter_messages(
        [_message(timestamp)],
        scope.AnalysisScope.custom(date(2026, 1, 1), date(2026, 12, 31)),
    )

    assert filtered == []


def test_custom_scope_rejects_start_after_end() -> None:
    scope = _scope_module()

    with pytest.raises(scope.InvalidAnalysisScope) as captured:
        scope.AnalysisScope.custom(date(2026, 8, 12), date(2026, 8, 11))

    assert captured.value.public_message == "开始日期不能晚于结束日期，请重新选择。"


def test_custom_scope_rejects_a_missing_date() -> None:
    scope = _scope_module()

    with pytest.raises(scope.InvalidAnalysisScope) as captured:
        scope.AnalysisScope.custom(None, date(2026, 8, 11))

    assert captured.value.public_message == "请选择开始日期和结束日期。"


def test_resolve_scope_converts_custom_iso_dates() -> None:
    scope = _scope_module()

    resolved = scope.resolve_scope(
        scope.AnalysisScopeMode.CUSTOM,
        start_time="2026-02-11",
        end_time="2026-08-11",
    )

    assert resolved == scope.AnalysisScope.custom(
        date(2026, 2, 11),
        date(2026, 8, 11),
    )


def test_resolve_scope_preserves_legacy_explicit_bounds() -> None:
    scope = _scope_module()

    resolved = scope.resolve_scope(
        scope.AnalysisScopeMode.ALL,
        start_time="2026-02-11",
        end_time="2026-08-11",
    )

    assert resolved.mode is scope.AnalysisScopeMode.CUSTOM


def test_resolve_scope_calculates_relative_mode_from_reference_date() -> None:
    scope = _scope_module()

    resolved = scope.resolve_scope(
        scope.AnalysisScopeMode.LAST_SIX_MONTHS,
        reference_date=date(2026, 8, 31),
    )

    assert resolved.start_date == date(2026, 2, 28)
    assert resolved.end_date == date(2026, 8, 31)
