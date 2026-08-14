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
    EchoConversationSession,
    EchoConversationSessions,
    EchoExpressionHabits,
    EchoLanguageMember,
    EchoLanguageProfile,
    EchoMemberCard,
    EchoReportView,
    EchoSharedWord,
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
        language_profile=EchoLanguageProfile(
            mode="group_distinctive",
            available=True,
            members=(
                EchoLanguageMember(
                    speaker_key="fictional-alice",
                    display_name="虚构 Alice",
                    heading="虚构 Alice",
                    primary_words=("风格词", "回声"),
                    context_words=("讨论", "项目"),
                ),
            ),
        ),
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
        "schema_version": "echo-report.v0.2",
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
            "active_days": 0,
            "average_messages_per_active_day": 0.0,
        },
        "activity": {
            "hourly": [{"label": "09:00-09:59", "value": 3.0}],
            "weekday": [{"label": "周一", "value": 3.0}],
        },
        "conversation_sessions": None,
        "language_profile": {
            "mode": "group_distinctive",
            "available": True,
            "unavailable_reason": "",
            "shared_words": [],
            "side_preference_words": [],
            "members": [
                {
                    "speaker_key": "fictional-alice",
                    "display_name": "虚构 Alice",
                    "heading": "虚构 Alice",
                    "primary_words": ["风格词", "回声"],
                    "context_words": ["讨论", "项目"],
                    "expression_habits": None,
                },
            ],
        },
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
        "active_days": 0,
        "average_messages_per_active_day": 0.0,
    }
    assert payload["activity"] == {"hourly": [], "weekday": []}
    assert payload["language_profile"] is None
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
    assert payload["schema_version"] == "echo-report.v0.2"


def test_language_profile_serializer_hides_log_odds_internal_statistics() -> None:
    payload = echo_report_to_dict(_echo_view())
    language = payload["language_profile"]

    assert language is not None
    serialized = json.dumps(language, ensure_ascii=False)
    for internal_name in (
        "ranking_score",
        "member_rate",
        "others_rate",
        "relative_ratio",
        "eligible_member_count",
    ):
        assert internal_name not in serialized


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
    assert "个人语言画像" in html
    assert 'id="voices-intro"' in html
    assert '"mode":"group_distinctive"' in html


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


def test_private_sessions_serialize_reply_peaks_and_back_and_forth() -> None:
    """Private v1 fields reach the frontend JSON payload without leaking ratios."""
    back_and_forth = EchoConversationSession(
        start_timestamp=10,
        end_timestamp=130,
        duration_seconds=120,
        message_count=11,
        participant_count=2,
        initiator="self",
        initiator_sender_key="fictional-self-id",
        self_message_count=6,
        peer_message_count=5,
    )
    sessions = EchoConversationSessions(
        threshold_seconds=1800,
        session_count=2,
        average_duration_seconds=600.0,
        median_duration_seconds=600.0,
        longest_duration_seconds=1200,
        average_message_count=10.0,
        items=(
            EchoConversationSession(
                start_timestamp=1,
                end_timestamp=2,
                duration_seconds=1,
                message_count=2,
                participant_count=2,
                initiator="self",
                initiator_sender_key="fictional-self-id",
                self_message_count=1,
                peer_message_count=1,
            ),
        ),
        private_self_count=1,
        private_peer_count=1,
        private_unknown_count=0,
        private_self_share=0.5,
        private_peer_share=0.5,
        private_unknown_share=0.0,
        private_self_peak_start_hour=22,
        private_peer_peak_start_hour=9,
        private_reply_median_self_to_peer_seconds=60.0,
        private_reply_median_peer_to_self_seconds=120.0,
        loudest_most_back_and_forth=back_and_forth,
    )
    payload = echo_report_to_dict(
        EchoReportView(
            title="Fictional Private Echo",
            has_data=True,
            conversation_kind="private",
            conversation_sessions=sessions,
        )
    )
    data = payload["conversation_sessions"]

    assert data["private_self_peak_start_hour"] == 22
    assert data["private_peer_peak_start_hour"] == 9
    assert data["private_reply_median_self_to_peer_seconds"] == 60.0
    assert data["private_reply_median_peer_to_self_seconds"] == 120.0
    assert data["items"][0]["self_message_count"] == 1
    assert data["items"][0]["peer_message_count"] == 1
    assert data["loudest_most_back_and_forth"]["self_message_count"] == 6
    assert data["loudest_most_back_and_forth"]["peer_message_count"] == 5
    serialized = json.dumps(data, ensure_ascii=False)
    assert "switch_ratio" not in serialized
    assert "switch_count" not in serialized


def test_private_language_profile_serializes_new_layers_and_overview_density() -> None:
    """Overview density and private language layers reach the frontend JSON."""
    view = EchoReportView(
        title="Fictional Private Echo",
        has_data=True,
        conversation_kind="private",
        active_days=5,
        average_messages_per_active_day=8.8,
        language_profile=EchoLanguageProfile(
            mode="private_common",
            available=True,
            members=(
                EchoLanguageMember(
                    speaker_key="fictional-self-id",
                    display_name="虚构自己",
                    heading="你常说",
                    primary_words=("散步",),
                    expression_habits=EchoExpressionHabits(
                        median_length=5.0,
                        average_length=5.0,
                        max_length=7,
                        run_count=2,
                        average_run_length=2.0,
                        median_run_length=2.0,
                        single_message_run_count=1,
                        multi_message_run_count=1,
                    ),
                ),
            ),
            shared_words=(
                EchoSharedWord(
                    word="回声",
                    self_count=6,
                    peer_count=4,
                    emphasis="shared",
                ),
            ),
            side_preference_words=(
                EchoSharedWord(
                    word="方案",
                    self_count=5,
                    peer_count=1,
                    emphasis="self",
                ),
            ),
        ),
    )

    payload = echo_report_to_dict(view)
    assert payload["overview"]["active_days"] == 5
    assert payload["overview"]["average_messages_per_active_day"] == 8.8

    language = payload["language_profile"]
    assert language["shared_words"] == [
        {"word": "回声", "self_count": 6, "peer_count": 4, "emphasis": "shared"}
    ]
    assert language["side_preference_words"] == [
        {"word": "方案", "self_count": 5, "peer_count": 1, "emphasis": "self"}
    ]
    habits = language["members"][0]["expression_habits"]
    assert habits["median_length"] == 5.0
    assert habits["average_length"] == 5.0
    assert habits["run_count"] == 2
    assert habits["multi_message_run_count"] == 1
