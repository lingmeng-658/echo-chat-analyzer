"""Stable JSON and self-contained HTML serialization for Echo Report views."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from ..resources import resource_path
from .echo_report_template import (
    ECHO_REPORT_APP_JS,
    ECHO_REPORT_CSS,
    ECHO_REPORT_HTML_SKELETON,
)
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
    destination.parent.mkdir(parents=True, exist_ok=True)
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
        "primary_name": member.primary_name,
        "secondary_name": member.secondary_name,
        "remark": member.remark,
        "contextual_name": member.contextual_name,
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


_ECHO_WORDMARK_RELATIVE_PATH = "assets/branding/echo/echo_wordmark_with_slogan.png"
_ECHO_FAVICON_RELATIVE_PATH = "assets/branding/echo/echo_icon_32.png"


def export_echo_report_html(
    view: EchoReportView,
    output_path: str | Path,
) -> Path:
    """Write a self-contained Echo Report HTML file and return its path."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    html = _build_echo_report_html(view)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)
    return destination


def _build_echo_report_html(view: EchoReportView) -> str:
    favicon_data_uri = _png_data_uri(_ECHO_FAVICON_RELATIVE_PATH)
    wordmark_data_uri = _png_data_uri(_ECHO_WORDMARK_RELATIVE_PATH)
    favicon_tag = (
        f'<link rel="icon" type="image/png" href="{favicon_data_uri}">'
        if favicon_data_uri
        else ""
    )
    logo_tag = (
        f'<img class="brand-logo" src="{wordmark_data_uri}" alt="余音 Echo">'
        if wordmark_data_uri
        else '<span class="brand-name">余音 Echo</span>'
    )
    return (
        ECHO_REPORT_HTML_SKELETON.replace("__ECHO_FAVICON_TAG__", favicon_tag)
        .replace("__ECHO_LOGO_TAG__", logo_tag)
        .replace("__ECHO_CSS__", ECHO_REPORT_CSS)
        .replace("__ECHO_DATA__", _encode_echo_data(view))
        .replace("__ECHO_APP_JS__", ECHO_REPORT_APP_JS)
    )


def _encode_echo_data(view: EchoReportView) -> str:
    """Serialize the view as a JS-safe JSON object literal."""
    payload = json.dumps(
        echo_report_to_dict(view),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        payload.replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _png_data_uri(relative_path: str) -> str:
    """Return a base64 PNG data URI for a bundled brand asset, or empty text."""
    source = resource_path(relative_path)
    if not source.is_file():
        return ""
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
