"""Integration contract for Conversation Sessions in Analysis/Echo DTOs."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.analysis.conversation_sessions import (  # noqa: E402
    analyze_conversation_sessions,
)
from qq_chat_analyzer.analysis.models import AnalysisReports  # noqa: E402
from qq_chat_analyzer.message import ChatMessage  # noqa: E402
from qq_chat_analyzer.presentation import (  # noqa: E402
    build_echo_report_view,
    echo_report_to_dict,
)


def _message(timestamp: int, *, is_self: bool) -> ChatMessage:
    return ChatMessage(
        timestamp=timestamp,
        sender="Fictional Sender",
        sender_id="fictional-sender-id",
        message_type="text",
        text="fictional text",
        platform="fictional",
        conversation_id="fictional-conversation",
        conversation_type="private",
        is_self=is_self,
    )


def test_analysis_reports_exposes_conversation_session_report() -> None:
    session_report = analyze_conversation_sessions(
        (_message(1_704_067_200, is_self=True),)
    )

    reports = AnalysisReports(conversation_sessions=session_report)

    assert reports.conversation_sessions is session_report


def test_echo_payload_minimally_exposes_session_summary_and_items() -> None:
    session_report = analyze_conversation_sessions(
        (
            _message(1_704_067_200, is_self=True),
            _message(1_704_069_061, is_self=False),
        )
    )
    view = build_echo_report_view(
        AnalysisReports(conversation_sessions=session_report),
        conversation_kind="private",
    )

    payload = echo_report_to_dict(view)

    sessions = payload["conversation_sessions"]
    assert sessions["threshold_seconds"] == 1800
    assert sessions["session_count"] == 2
    assert sessions["average_duration_seconds"] == 0.0
    assert sessions["median_duration_seconds"] == 0.0
    assert sessions["longest_duration_seconds"] == 0
    assert sessions["average_message_count"] == 1.0
    assert sessions["private_initiators"] == {
        "self_count": 1,
        "peer_count": 1,
        "unknown_count": 0,
        "self_to_peer_ratio": 1.0,
        "self_share": 0.5,
        "peer_share": 0.5,
        "unknown_share": 0.0,
    }
    assert [item["initiator"] for item in sessions["items"]] == [
        "self",
        "peer",
    ]


def test_echo_payload_uses_null_when_session_report_is_unavailable() -> None:
    payload = echo_report_to_dict(build_echo_report_view(AnalysisReports()))

    assert payload["conversation_sessions"] is None
