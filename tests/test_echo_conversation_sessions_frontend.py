"""Browser-behavior tests for the Echo conversation sessions chapter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.presentation import (  # noqa: E402
    EchoConversationSession,
    EchoConversationSessions,
    EchoReportView,
    export_echo_report_html,
)


APP_PATH = PROJECT_ROOT / "frontend" / "echo_report" / "app.js"
SESSION_NODE_IDS = (
    "session-toc",
    "conversation-sessions",
    "session-lead",
    "session-median-duration",
    "session-longest-duration",
    "session-average-messages",
    "session-private-initiators",
    "session-self",
    "session-peer",
    "session-group-initiators",
    "session-group-self",
    "session-group-top",
    "session-unknown-note",
    "session-threshold-note",
    "session-beat",
    "session-viewer-identity",
    "session-peak-hour",
    "session-self-peak-hour",
    "session-peer-peak-hour",
    "session-reply",
    "session-reply-self-to-peer",
    "session-reply-peer-to-self",
    "session-movement",
    "session-character",
    "session-highnotes",
    "session-loudest-duration",
    "session-loudest-duration-text",
    "session-loudest-duration-time",
    "session-rest",
)

NODE_RUNNER = r"""
const fs = require("fs");

class FakeNode {
  constructor(id) {
    this.id = id || "";
    this.textContent = "";
    this.hidden = false;
    this.children = [];
    this.className = "";
    this.style = { setProperty: function () {} };
    this.classList = { add: function () {} };
  }
  appendChild(child) { this.children.push(child); return child; }
}

const ids = JSON.parse(process.env.ECHO_NODE_IDS);
const nodes = {};
ids.forEach(function (id) { nodes[id] = new FakeNode(id); });

global.window = { ECHO_DATA: JSON.parse(process.env.ECHO_PAYLOAD) };
global.document = {
  title: "",
  documentElement: new FakeNode("html"),
  getElementById: function (id) { return nodes[id] || null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return new FakeNode(""); }
};

eval(fs.readFileSync(process.env.ECHO_APP_PATH, "utf8"));

const result = {};
ids.forEach(function (id) {
  result[id] = { text: nodes[id].textContent, hidden: nodes[id].hidden };
});
process.stdout.write(JSON.stringify(result));
"""


def _sessions(
    *,
    session_count: int = 8,
    median_duration_seconds: float = 18 * 60,
    longest_duration_seconds: int = 4 * 60 * 60 + 37 * 60,
    average_message_count: float = 12.5,
    private_initiators: dict[str, object] | None = None,
    group_initiators: dict[str, object] | None = None,
    viewer_identity_reliable: bool = False,
    peak_start_hour: int | None = None,
    private_self_peak_start_hour: int | None = None,
    private_peer_peak_start_hour: int | None = None,
    private_reply_median_self_to_peer_seconds: float | None = None,
    private_reply_median_peer_to_self_seconds: float | None = None,
    session_character: str | None = None,
    loudest_longest_duration: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "threshold_seconds": 1800,
        "session_count": session_count,
        "average_duration_seconds": 1200.0,
        "median_duration_seconds": median_duration_seconds,
        "longest_duration_seconds": longest_duration_seconds,
        "average_message_count": average_message_count,
        "private_initiators": private_initiators,
        "group_initiators": group_initiators,
        "viewer_identity_reliable": viewer_identity_reliable,
        "peak_start_hour": peak_start_hour,
        "private_self_peak_start_hour": private_self_peak_start_hour,
        "private_peer_peak_start_hour": private_peer_peak_start_hour,
        "private_reply_median_self_to_peer_seconds": (
            private_reply_median_self_to_peer_seconds
        ),
        "private_reply_median_peer_to_self_seconds": (
            private_reply_median_peer_to_self_seconds
        ),
        "session_character": session_character,
        "loudest_longest_duration": loudest_longest_duration,
        "items": [],
    }


def _render_frontend(
    *,
    kind: str,
    sessions: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    payload = {
        "conversation": {"kind": kind, "name": "", "time_span": ""},
        "overview": {
            "has_data": sessions is not None,
            "total_message_count": 0,
            "participant_count": 0,
            "empty_description": "",
        },
        "activity": {"hourly": [], "weekday": []},
        "members": [],
    }
    if sessions is not None:
        payload["conversation_sessions"] = sessions
    environment = os.environ.copy()
    environment.update(
        {
            "ECHO_APP_PATH": str(APP_PATH),
            "ECHO_NODE_IDS": json.dumps(SESSION_NODE_IDS),
            "ECHO_PAYLOAD": json.dumps(payload),
        }
    )
    completed = subprocess.run(
        ["node", "-e", NODE_RUNNER],
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=environment,
    )
    return json.loads(completed.stdout)


def test_private_sessions_show_rounds_initiators_and_readable_durations() -> None:
    rendered = _render_frontend(
        kind="private",
        sessions=_sessions(
            private_initiators={
                "self_count": 5,
                "peer_count": 3,
                "unknown_count": 0,
                "self_to_peer_ratio": 1.6667,
                "self_share": 0.625,
                "peer_share": 0.375,
                "unknown_share": 0.0,
            }
        ),
    )

    assert rendered["conversation-sessions"]["hidden"] is False
    assert rendered["session-lead"]["text"] == (
        "过去这段时间，你们一共聊起了 8 轮"
    )
    assert rendered["session-beat"]["hidden"] is False
    assert rendered["session-group-top"]["text"] == "你开启 5 轮 · TA 开启 3 轮"
    assert rendered["session-movement"]["hidden"] is False
    assert rendered["session-median-duration"]["text"] == "约 18 分钟"
    assert rendered["session-average-messages"]["text"] == "约 12.5 条"


def test_private_unknown_initiators_do_not_show_made_up_percentages() -> None:
    rendered = _render_frontend(
        kind="private",
        sessions=_sessions(
            session_count=3,
            private_initiators={
                "self_count": 0,
                "peer_count": 0,
                "unknown_count": 3,
                "self_to_peer_ratio": None,
                "self_share": 0.0,
                "peer_share": 0.0,
                "unknown_share": 1.0,
            },
        ),
    )

    assert rendered["session-group-top"]["hidden"] is True
    assert rendered["session-group-top"]["text"] == ""
    assert rendered["session-self-peak-hour"]["hidden"] is True
    assert rendered["session-peer-peak-hour"]["hidden"] is True
    assert rendered["session-unknown-note"]["hidden"] is True


def test_group_sessions_show_self_and_top_initiator_without_raw_key() -> None:
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=12,
            average_message_count=23.0,
            viewer_identity_reliable=True,
            group_initiators={
                "self_count": 3,
                "self_share": 0.25,
                "top_member": {
                    "display_name": "Fictional Alice",
                    "count": 5,
                    "share": 5 / 12,
                    "sender_key": "raw-stable-fictional-id",
                },
            },
        ),
    )

    assert rendered["session-lead"]["text"] == (
        "过去这段时间，群里一共聊起了 12 轮"
    )
    assert rendered["session-viewer-identity"]["hidden"] is False
    assert rendered["session-viewer-identity"]["text"] == "你发起了 3 轮，占 25.0%"
    assert rendered["session-beat"]["hidden"] is False
    assert rendered["session-group-top"]["text"] == (
        "最常发起聊天：Fictional Alice（5 轮，41.7%）"
    )
    assert rendered["session-average-messages"]["text"] == "约 23 条"
    visible_text = " ".join(str(node["text"]) for node in rendered.values())
    assert "raw-stable-fictional-id" not in visible_text


def test_missing_or_empty_sessions_hide_the_chapter_gracefully() -> None:
    missing = _render_frontend(kind="private", sessions=None)
    empty = _render_frontend(
        kind="private",
        sessions=_sessions(session_count=0),
    )

    assert missing["conversation-sessions"]["hidden"] is True
    assert empty["conversation-sessions"]["hidden"] is True
    assert missing["session-toc"]["hidden"] is True
    assert empty["session-toc"]["hidden"] is True


def test_session_duration_formatting_handles_minutes_and_hours() -> None:
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            median_duration_seconds=18 * 60,
            loudest_longest_duration={
                "start_timestamp": 1000,
                "end_timestamp": 10000,
                "duration_seconds": 4 * 60 * 60 + 37 * 60,
                "message_count": 15,
                "participant_count": 3,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
        ),
    )

    assert "18 分钟" in rendered["session-median-duration"]["text"]
    assert rendered["session-loudest-duration"]["hidden"] is False
    assert "4 小时 37 分钟" in rendered["session-loudest-duration-text"]["text"]


def test_session_chapter_explains_the_thirty_minute_boundary() -> None:
    rendered = _render_frontend(kind="group", sessions=_sessions())

    assert rendered["session-threshold-note"]["text"] == (
        "超过 30 分钟未继续交流，会视作下一轮聊天。"
    )


def test_session_chapter_never_displays_stable_ids_or_technical_ratio() -> None:
    sessions = _sessions(
        private_initiators={
            "self_count": 1,
            "peer_count": 1,
            "unknown_count": 0,
            "self_to_peer_ratio": 999.123,
            "self_share": 0.5,
            "peer_share": 0.5,
            "unknown_share": 0.0,
        }
    )
    sessions["items"] = [
        {
            "start_timestamp": 1,
            "end_timestamp": 2,
            "duration_seconds": 1,
            "message_count": 2,
            "initiator": "self",
            "initiator_sender_key": "raw-stable-fictional-id",
        }
    ]

    rendered = _render_frontend(kind="private", sessions=sessions)
    visible_text = " ".join(str(node["text"]) for node in rendered.values())

    assert "raw-stable-fictional-id" not in visible_text
    assert "999.123" not in visible_text
    assert "self-to-peer" not in visible_text.lower()


def test_self_contained_echo_html_includes_the_session_chapter(
    tmp_path: Path,
) -> None:
    view = EchoReportView(
        title="Fictional Echo",
        has_data=True,
        conversation_kind="group",
        conversation_sessions=EchoConversationSessions(
            threshold_seconds=1800,
            session_count=1,
            average_duration_seconds=60.0,
            median_duration_seconds=60.0,
            longest_duration_seconds=60,
            average_message_count=2.0,
            items=(
                EchoConversationSession(
                    start_timestamp=1,
                    end_timestamp=61,
                    duration_seconds=60,
                    message_count=2,
                    initiator="raw-stable-fictional-id",
                    initiator_sender_key="raw-stable-fictional-id",
                ),
            ),
        ),
    )

    output = export_echo_report_html(view, tmp_path / "echo-report.html")
    html = output.read_text(encoding="utf-8")

    assert 'id="conversation-sessions"' in html
    assert 'id="session-median-duration"' in html
    assert 'id="session-beat"' in html
    assert "会视作下一轮聊天" in html
