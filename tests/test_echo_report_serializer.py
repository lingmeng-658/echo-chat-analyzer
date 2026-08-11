"""Contract tests for the Echo Report JSON output layer."""

from __future__ import annotations

import json
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
    export_echo_report_json,
)


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
        "members": [
            {
                "speaker_key": "fictional-alice",
                "display_name": "虚构 Alice",
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
