"""Contract tests for the Echo Report JSON output layer."""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.presentation import (  # noqa: E402
    ChartPoint,
    EchoMemberCard,
    EchoReportView,
    echo_report_to_dict,
    export_echo_report_html,
    export_echo_report_json,
)

from qq_chat_analyzer.resources import resource_path


def _echo_view() -> EchoReportView:
    return EchoReportView(
        title="余音 Echo",
        has_data=True,
        conversation_kind="group",
        conversation_name="虚构讨论组",
        time_span="2 小时 0 分钟",
        total_message_count=3,
        participant_count=2,
        hourly_activity=(ChartPoint(label="09:00-09:59", value=3.0),),
        weekday_activity=(ChartPoint(label="周一", value=3.0),),
        members=(
            EchoMemberCard(
                speaker_key="fictional-alice",
                display_name="虚构 Alice",
                is_viewer=True,
                message_count=2,
                message_share_percent=66.67,
                average_length=4.5,
                max_length=6,
                active_period="周一 09:00-09:59",
                hourly_activity=(
                    ChartPoint(label="09:00-09:59", value=2.0),
                ),
                weekday_activity=(ChartPoint(label="周一", value=2.0),),
                top_words=("讨论", "项目"),
            ),
        ),
    )


def test_echo_report_converts_to_stable_frontend_json_object() -> None:
    payload = echo_report_to_dict(_echo_view())

    assert payload == {
        "schema_version": "echo-report.v0.1",
        "title": "余音 Echo",
        "conversation": {
            "kind": "group",
            "name": "虚构讨论组",
            "time_span": "2 小时 0 分钟",
        },
        "overview": {
            "has_data": True,
            "total_message_count": 3,
            "participant_count": 2,
            "empty_description": "",
        },
        "activity": {
            "hourly": [{"label": "09:00-09:59", "value": 3.0}],
            "weekday": [{"label": "周一", "value": 3.0}],
        },
        "conversation_sessions": None,
        "members": [
            {
                "speaker_key": "fictional-alice",
                "display_name": "虚构 Alice",
                "primary_name": None,
                "secondary_name": None,
                "remark": None,
                "contextual_name": None,
                "is_viewer": True,
                "message_count": 2,
                "message_share_percent": 66.67,
                "average_length": 4.5,
                "max_length": 6,
                "active_period": "周一 09:00-09:59",
                "activity": {
                    "hourly": [
                        {"label": "09:00-09:59", "value": 2.0},
                    ],
                    "weekday": [{"label": "周一", "value": 2.0}],
                },
                "top_words": ["讨论", "项目"],
            },
        ],
    }


def test_echo_member_serializes_identity_skeleton() -> None:
    member = EchoMemberCard(
        speaker_key="10001",
        display_name="Alice",
        primary_name="Alice",
        is_viewer=False,
        message_count=1,
        message_share_percent=100.0,
        average_length=3.0,
        max_length=3,
        active_period="",
    )

    payload = echo_report_to_dict(
        EchoReportView(
            title="Echo Report",
            has_data=True,
            members=(member,),
        )
    )
    serialized = payload["members"][0]

    assert serialized["speaker_key"] == "10001"
    assert serialized["primary_name"] == "Alice"
    assert serialized["display_name"] == "Alice"
    assert serialized["secondary_name"] is None
    assert serialized["remark"] is None
    assert serialized["contextual_name"] is None
    assert serialized["is_viewer"] is False


def test_echo_report_json_file_preserves_viewer_highlight(tmp_path: Path) -> None:
    output_path = tmp_path / "echo-report.json"

    result_path = export_echo_report_json(_echo_view(), output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert result_path == output_path
    assert payload["members"][0]["is_viewer"] is True
    assert "余音 Echo" in output_path.read_text(encoding="utf-8")


def test_empty_echo_report_serializes_with_stable_empty_collections() -> None:
    payload = echo_report_to_dict(EchoReportView(title="Echo Report"))

    assert payload["conversation"] == {
        "kind": "unknown",
        "name": "",
        "time_span": "",
    }
    assert payload["overview"] == {
        "has_data": False,
        "total_message_count": 0,
        "participant_count": 0,
        "empty_description": "",
    }
    assert payload["activity"] == {"hourly": [], "weekday": []}
    assert payload["members"] == []


def test_export_echo_report_json_creates_parent_directories(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "private" / "nested"
    result_path = export_echo_report_json(
        _echo_view(),
        nested / "echo-report.json",
    )

    assert result_path.is_file()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "echo-report.v0.1"


def test_echo_report_html_is_self_contained_with_real_data(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "echo-report.html"

    result_path = export_echo_report_html(_echo_view(), output_path)

    assert result_path == output_path
    html = output_path.read_text(encoding="utf-8")
    assert "window.ECHO_DATA" in html
    assert "虚构讨论组" in html
    assert "虚构 Alice" in html
    assert "data:image/png;base64," in html
    assert "fetch(" not in html
    assert "1,284" not in html
    assert "林间回声" not in html
    assert "2024.01.01" not in html
    assert "12 人" not in html
    assert "frontend/echo_report" not in html
    assert "assets/branding" not in html
    assert 'href="style.css"' not in html
    assert 'src="app.js"' not in html


def test_echo_report_html_escapes_injected_user_text(tmp_path: Path) -> None:
    view = EchoReportView(
        title="余音 Echo",
        has_data=True,
        conversation_kind="group",
        conversation_name='<script>alert("x")</script>&"\'余音',
        time_span="1 天",
        total_message_count=1,
        participant_count=1,
        hourly_activity=(ChartPoint(label="09:00-09:59", value=1.0),),
        weekday_activity=(ChartPoint(label="周一", value=1.0),),
        members=(
            EchoMemberCard(
                speaker_key="fictional-alice",
                display_name="</script><b>x</b>",
                is_viewer=False,
                message_count=1,
                message_share_percent=100.0,
                average_length=1.0,
                max_length=1,
                active_period="09:00-09:59",
            ),
        ),
    )

    output_path = tmp_path / "echo-report.html"
    export_echo_report_html(view, output_path)
    html = output_path.read_text(encoding="utf-8")

    match = re.search(
        r"window\.ECHO_DATA = (\{.*?\});",
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["conversation"]["name"] == (
        '<script>alert("x")</script>&"\'余音'
    )
    assert payload["members"][0]["display_name"] == "</script><b>x</b>"
    assert html.count("</script>") == 2
    assert "<\\/script>" in html


def test_empty_echo_report_html_still_generates_self_contained_file(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "echo-report.html"

    export_echo_report_html(EchoReportView(title="Echo Report"), output_path)

    html = output_path.read_text(encoding="utf-8")
    assert "window.ECHO_DATA" in html
    assert "data:image/png;base64," in html
    assert "fetch(" not in html



def test_echo_report_html_inlines_current_brand_assets(tmp_path: Path) -> None:
    """Generated HTML must inline the current bundled brand assets."""
    output_path = tmp_path / "echo-report.html"
    export_echo_report_html(_echo_view(), output_path)
    html = output_path.read_text(encoding="utf-8")

    favicon = resource_path("assets/branding/echo/echo_icon_32.png")
    logo = resource_path("assets/branding/echo/echo_wordmark_with_slogan.png")
    assert favicon.is_file()
    assert logo.is_file()

    uris = re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
    assert len(uris) == 2
    embedded = {base64.b64decode(uri) for uri in uris}
    assert favicon.read_bytes() in embedded
    assert logo.read_bytes() in embedded
