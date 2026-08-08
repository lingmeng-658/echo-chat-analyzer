"""Presentation layer turning analysis reports into display-ready models."""

from __future__ import annotations

from .builders import DashboardBuilder, build_dashboard_view
from .formatters import (
    format_active_period,
    format_average,
    format_count,
    format_duration,
    format_hour,
    format_length_bucket,
    format_percent,
    format_weekday,
)
from .models import (
    ChartData,
    ChartKind,
    ChartPoint,
    ChartSeries,
    ConversationCard,
    DashboardView,
    MetricCard,
    UserCard,
)


__all__ = [
    "ChartData",
    "ChartKind",
    "ChartPoint",
    "ChartSeries",
    "ConversationCard",
    "DashboardBuilder",
    "DashboardView",
    "MetricCard",
    "UserCard",
    "build_dashboard_view",
    "format_active_period",
    "format_average",
    "format_count",
    "format_duration",
    "format_hour",
    "format_length_bucket",
    "format_percent",
    "format_weekday",
]