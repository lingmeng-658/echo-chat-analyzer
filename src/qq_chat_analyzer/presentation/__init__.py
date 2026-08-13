"""Presentation layer turning analysis reports into display-ready models."""

from __future__ import annotations

from .builders import (
    DashboardBuilder,
    EchoReportBuilder,
    build_dashboard_view,
    build_echo_report_view,
)
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
from .echo_serializer import (
    ECHO_REPORT_SCHEMA_VERSION,
    echo_report_to_dict,
    export_echo_report_html,
    export_echo_report_json,
)
from .models import (
    ChartData,
    ChartKind,
    ChartPoint,
    ChartSeries,
    ConversationCard,
    DashboardView,
    EchoMemberCard,
    EchoReportView,
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
    "EchoMemberCard",
    "EchoReportBuilder",
    "EchoReportView",
    "ECHO_REPORT_SCHEMA_VERSION",
    "MetricCard",
    "UserCard",
    "build_dashboard_view",
    "build_echo_report_view",
    "echo_report_to_dict",
    "export_echo_report_html",
    "export_echo_report_json",
    "format_active_period",
    "format_average",
    "format_count",
    "format_duration",
    "format_hour",
    "format_length_bucket",
    "format_percent",
    "format_weekday",
]
