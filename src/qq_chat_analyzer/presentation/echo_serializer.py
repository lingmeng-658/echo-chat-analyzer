"""Stable JSON serialization for the Echo Report presentation model."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ChartPoint, EchoMemberCard, EchoReportView


ECHO_REPORT_SCHEMA_VERSION = "echo-report.v0.1"


def echo_report_to_dict(view: EchoReportView) -> dict[str, object]:
    """Convert an Echo view to frontend-ready JSON-compatible primitives."""
    return {
        "schema_version": ECHO_REPORT_SCHEMA_VERSION,
        "title": view.title,
        "conversation": {
            "kind": view.conversation_kind,
            "name": view.conversation_name,
            "time_span": view.time_span,
        },
        "overview": {
            "has_data": view.has_data,
            "total_message_count": view.total_message_count,
            "participant_count": view.participant_count,
            "empty_description": view.empty_description,
        },
        "activity": {
            "hourly": _points_to_list(view.hourly_activity),
            "weekday": _points_to_list(view.weekday_activity),
        },
        "members": [_member_to_dict(member) for member in view.members],
    }


def export_echo_report_json(
    view: EchoReportView,
    output_path: str | Path,
) -> Path:
    """Write an Echo view as UTF-8 JSON and return the destination path."""
    destination = Path(output_path)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            echo_report_to_dict(view),
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")
    return destination


def _member_to_dict(member: EchoMemberCard) -> dict[str, object]:
    return {
        "speaker_key": member.speaker_key,
        "display_name": member.display_name,
        "is_viewer": member.is_viewer,
        "message_count": member.message_count,
        "message_share_percent": member.message_share_percent,
        "average_length": member.average_length,
        "max_length": member.max_length,
        "active_period": member.active_period,
        "activity": {
            "hourly": _points_to_list(member.hourly_activity),
            "weekday": _points_to_list(member.weekday_activity),
        },
        "top_words": list(member.top_words),
    }


def _points_to_list(points: tuple[ChartPoint, ...]) -> list[dict[str, object]]:
    return [
        {"label": point.label, "value": point.value}
        for point in points
    ]
