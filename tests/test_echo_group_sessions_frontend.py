"""Frontend tests for the Echo group conversation sessions 5-section narrative."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.presentation import (
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

    "session-group-top",
    "session-unknown-note",
    "session-threshold-note",
    "session-viewer-identity",
    "session-peak-hour",
    "session-character",
    "session-loudest-messages",
    "session-loudest-duration",
    "session-loudest-participants",
    "session-loudest-densest",
    "session-loudest-messages-text",
    "session-loudest-duration-text",
    "session-loudest-participants-text",
    "session-loudest-densest-text",
    "session-loudest-messages-time",
    "session-loudest-duration-time",
    "session-loudest-participants-time",
    "session-loudest-densest-time",
    "session-fields-old",
    "session-median-duration-old",
    "session-average-messages-old",
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
  setAttribute() {}
  querySelector() { return null; }
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
    longest_duration_seconds: int = 277,
    average_message_count: float = 12.5,
    private_initiators: dict | None = None,
    group_initiators: dict | None = None,
    session_character: str | None = None,
    peak_start_hour: int | None = None,
    viewer_identity_reliable: bool = False,
    loudest_most_messages: dict | None = None,
    loudest_longest_duration: dict | None = None,
    loudest_most_participants: dict | None = None,
    loudest_densest: dict | None = None,
) -> dict:
    return {
        "threshold_seconds": 1800,
        "session_count": session_count,
        "average_duration_seconds": 1200.0,
        "median_duration_seconds": median_duration_seconds,
        "longest_duration_seconds": longest_duration_seconds,
        "average_message_count": average_message_count,
        "private_initiators": private_initiators,
        "group_initiators": group_initiators,
        "session_character": session_character,
        "peak_start_hour": peak_start_hour,
        "viewer_identity_reliable": viewer_identity_reliable,
        "loudest_most_messages": loudest_most_messages,
        "loudest_longest_duration": loudest_longest_duration,
        "loudest_most_participants": loudest_most_participants,
        "loudest_densest": loudest_densest,
        "items": [],
    }

def _render_frontend(
    *,
    kind: str,
    sessions: dict | None,
) -> dict[str, dict]:
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

def test_private_regression_no_change() -> None:
    """Private sessions keep existing layout unchanged."""
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
    assert rendered["session-lead"]["text"] == "过去这段时间，你们一共聊起了 8 轮"
    assert rendered["session-self"]["text"] == "你先开口 62.5%（5 次）"
    assert rendered["session-peer"]["text"] == "对方先开口 37.5%（3 次）"
    assert rendered["session-private-initiators"]["hidden"] is False
    assert rendered["session-fields-old"]["hidden"] is False, "private: old KPI must be visible"

def test_group_session_shows_total_rounds() -> None:
    """Group sessions show total rounds in session-lead."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(session_count=12),
    )
    assert rendered["session-lead"]["text"] == "过去这段时间，群里一共聊起了 12 轮"
    assert rendered["session-fields-old"]["hidden"] is True, "group: old KPI must be hidden"

def test_group_viewer_identity_secondary_text() -> None:
    """Viewer identity appears as secondary text when reliable."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=10,
            group_initiators={
                "self_count": 3,
                "self_share": 0.3,
                "top_member": {
                    "display_name": "Alice",
                    "count": 5,
                    "share": 0.5,
                    "sender_key": "alice-id",
                },
            },
            viewer_identity_reliable=True,
        ),
    )
    assert rendered["session-viewer-identity"]["hidden"] is False
    assert "3" in rendered["session-viewer-identity"]["text"]
    assert "30.0" in rendered["session-viewer-identity"]["text"]
    visible = " ".join(str(v["text"]) for v in rendered.values())
    assert "alice-id" not in visible

def test_group_viewer_identity_hidden_when_unreliable() -> None:
    """Viewer identity is hidden when viewer_identity_reliable is False."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            viewer_identity_reliable=False,
            group_initiators={
                "self_count": 3,
                "self_share": 0.3,
                "top_member": {
                    "display_name": "Alice",
                    "count": 5,
                    "share": 0.5,
                    "sender_key": "alice-id",
                },
            },
        ),
    )
    assert rendered["session-viewer-identity"]["hidden"] is True

def test_group_peak_start_hour() -> None:
    """Group sessions show peak_start_hour."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(peak_start_hour=20, session_count=8),
    )
    assert rendered["session-peak-hour"]["hidden"] is False

def test_group_peak_start_hour_none() -> None:
    """When peak_start_hour is None, the peak hour section is hidden."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(peak_start_hour=None, session_count=5),
    )
    assert rendered["session-peak-hour"]["hidden"] is True

def test_group_session_character_editorial() -> None:
    """Session character is rendered as editorial text."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(session_character="一旦聊开，就会聊很久", session_count=8),
    )
    assert rendered["session-character"]["hidden"] is False
    assert "一旦聊开" in rendered["session-character"]["text"]

def test_group_session_character_none() -> None:
    """When session_character is None, character section hides."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(session_character=None, session_count=2),
    )
    assert rendered["session-character"]["hidden"] is True

def test_group_loudest_most_messages() -> None:
    """Loudest most_messages shows message count and duration."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=8,
            loudest_most_messages={
                "start_timestamp": 1000,
                "end_timestamp": 2000,
                "duration_seconds": 1000,
                "message_count": 42,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
        ),
    )
    assert rendered["session-loudest-messages"]["hidden"] is False
    assert "42" in rendered["session-loudest-messages-text"]["text"]

def test_group_loudest_longest_duration() -> None:
    """Loudest longest_duration shows duration and message count."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=8,
            loudest_longest_duration={
                "start_timestamp": 1000,
                "end_timestamp": 10000,
                "duration_seconds": 9000,
                "message_count": 15,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
        ),
    )
    assert rendered["session-loudest-duration"]["hidden"] is False
    assert "15" in rendered["session-loudest-duration-text"]["text"]

def test_group_loudest_most_participants() -> None:
    """Loudest most_participants shows participant count and message count."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=8,
            loudest_most_participants={
                "start_timestamp": 1000,
                "end_timestamp": 5000,
                "duration_seconds": 4000,
                "message_count": 20,
                "participant_count": 5,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
        ),
    )
    assert rendered["session-loudest-participants"]["hidden"] is False
    assert "5" in rendered["session-loudest-participants-text"]["text"]

def test_group_loudest_densest_null_graceful_degradation() -> None:
    """When densest is null, the densest card is hidden, not empty."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=8,
            loudest_most_messages={
                "start_timestamp": 1000,
                "end_timestamp": 2000,
                "duration_seconds": 1000,
                "message_count": 42,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_longest_duration={
                "start_timestamp": 1000,
                "end_timestamp": 10000,
                "duration_seconds": 9000,
                "message_count": 15,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_most_participants={
                "start_timestamp": 1000,
                "end_timestamp": 5000,
                "duration_seconds": 4000,
                "message_count": 20,
                "participant_count": 5,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_densest=None,
        ),
    )
    assert rendered["session-loudest-densest"]["hidden"] is True
    assert rendered["session-loudest-messages"]["hidden"] is False

def test_group_loudest_densest_shows_when_present() -> None:
    """When densest is present, the densest card is shown."""
    rendered = _render_frontend(
        kind="group",
        sessions=_sessions(
            session_count=8,
            loudest_most_messages={
                "start_timestamp": 1000,
                "end_timestamp": 2000,
                "duration_seconds": 1000,
                "message_count": 42,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_longest_duration={
                "start_timestamp": 1000,
                "end_timestamp": 10000,
                "duration_seconds": 9000,
                "message_count": 15,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_most_participants={
                "start_timestamp": 1000,
                "end_timestamp": 5000,
                "duration_seconds": 4000,
                "message_count": 20,
                "participant_count": 5,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
            loudest_densest={
                "start_timestamp": 1000,
                "end_timestamp": 1100,
                "duration_seconds": 100,
                "message_count": 50,
                "participant_count": 1,
                "initiator": "a",
                "initiator_sender_key": "a",
            },
        ),
    )
    assert rendered["session-loudest-densest"]["hidden"] is False
    assert "50" in rendered["session-loudest-densest-text"]["text"]

def test_group_session_threshold_note() -> None:
    """Group sessions still show the threshold note."""
    rendered = _render_frontend(kind="group", sessions=_sessions())
    assert rendered["session-threshold-note"]["text"] == "超过 30 分钟未继续交流，会视作下一轮聊天。"


def _read_css_sources():
    import sys

    sys.path.insert(0, "src")
    from qq_chat_analyzer.presentation.echo_report_template import ECHO_REPORT_CSS

    css_file = __file__.rsplit("tests", 1)[0] + "frontend/echo_report/style.css"
    css_content = open(css_file, "r", encoding="utf-8").read()
    return ECHO_REPORT_CSS, css_content


def _assert_valid_css_shell(css: str) -> None:
    """Stray `*/` outside comments and unbalanced braces make the CSS shell invalid."""
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    assert "*/" not in stripped, "CSS has stray */ outside comment blocks"
    assert stripped.count("{") == stripped.count("}"), "CSS braces are unbalanced"


def test_group_old_private_grid_hidden_override_in_both_css() -> None:
    """The old private grid must not keep rendering in Group mode via display overrides."""
    template_css, file_css = _read_css_sources()
    for css in (template_css, file_css):
        _assert_valid_css_shell(css)
        assert ".session-initiators[hidden] { display: none; }" in css, (
            "CSS must hide the old private initiator grid when hidden"
        )
        assert ".session-fields[hidden] { display: none; }" in css, (
            "CSS must hide the old private KPI fields when hidden"
        )


def test_group_highnote_final_labels_fixed_in_both_html() -> None:
    """The four highnote labels and music accents are fixed in the shared HTML sources."""
    import sys

    sys.path.insert(0, "src")
    from qq_chat_analyzer.presentation.echo_report_template import ECHO_REPORT_HTML_SKELETON

    html_file = __file__.rsplit("tests", 1)[0] + "frontend/echo_report/index.html"
    html_content = open(html_file, "r", encoding="utf-8").read()
    expected = (
        '<span class="highnote-note" aria-hidden="true">♪</span>话最多',
        '<span class="highnote-note" aria-hidden="true">𝅝</span>聊最久',
        '<span class="highnote-note" aria-hidden="true">♫</span>最热闹',
        '<span class="highnote-note" aria-hidden="true">♬</span>接得最紧',
    )
    for html in (ECHO_REPORT_HTML_SKELETON, html_content):
        for label in expected:
            assert label in html
        for retired_label in ("最能聊", "最慢长", "最密集"):
            assert f'class="highnote-badge">{retired_label}' not in html


def test_group_rest_downgraded_to_right_footnote() -> None:
    """休止 is a small right-aligned footnote above the folio, not a full movement."""
    import sys

    sys.path.insert(0, "src")
    from qq_chat_analyzer.presentation.echo_report_template import (
        ECHO_REPORT_CSS,
        ECHO_REPORT_HTML_SKELETON,
    )

    html_file = __file__.rsplit("tests", 1)[0] + "frontend/echo_report/index.html"
    html_content = open(html_file, "r", encoding="utf-8").read()
    for html in (ECHO_REPORT_HTML_SKELETON, html_content):
        assert '<p class="session-rest-note" id="session-rest" hidden>' in html
        assert (
            '<span class="session-rest-symbol" aria-hidden="true">𝄽</span> 休止 · '
            '<span id="session-threshold-note"></span>'
        ) in html
        assert 'class="session-movement" id="session-rest"' not in html

    template_css, file_css = _read_css_sources()
    for css in (ECHO_REPORT_CSS, file_css):
        assert ".session-rest-note" in css
        assert "text-align: right;" in css


def test_group_session_vertical_rhythm_is_tightened_in_flow() -> None:
    """Session chapter spacing is tightened with normal flow, not negative margins."""
    template_css, file_css = _read_css_sources()
    for css in (template_css, file_css):
        assert ".session-chapter .chapter-intro" in css
        assert "margin: 0 0 40px;" in css
        assert "margin-top: 36px;" in css
        identity = css[css.index(".session-viewer-identity"):]
        identity = identity[:identity.index("}")]
        assert "margin-top: -" not in identity


def test_template_js_syntax() -> None:
    """ECHO_REPORT_APP_JS (the template-embedded JS) must be syntactically valid.
    This catches raw-string pitfalls that introduce literal backslash+newline
    pairs which break JavaScript parsing, even when app.js is correct."""
    import subprocess
    import tempfile
    from pathlib import Path
    from qq_chat_analyzer.presentation.echo_report_template import ECHO_REPORT_APP_JS

    # 1. No literal backslash+newline pairs outside string literals
    bs_nl = 0
    for i in range(len(ECHO_REPORT_APP_JS) - 1):
        if ECHO_REPORT_APP_JS[i] == "\\" and ECHO_REPORT_APP_JS[i + 1] == "\n":
            bs_nl += 1
    assert bs_nl == 0, (
        f"ECHO_REPORT_APP_JS has {bs_nl} literal backslash+newline pairs; "
        f"these are invalid JavaScript outside string literals"
    )

    # 2. Node.js syntax check
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(ECHO_REPORT_APP_JS)
        tmp_path = tmp.name
    try:
        completed = subprocess.run(
            ["node", "--check", tmp_path],
            capture_output=True,
            encoding="utf-8",
        )
        assert completed.returncode == 0, (
            f"Template JS syntax check failed:\n{completed.stderr}"
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_old_kpi_hidden_effective_in_group_mode() -> None:
    """Group mode: the old KPI section (session-fields-old) must be hidden
    both semantically (hidden=true) and visually (CSS rule ensures display:none).
    Private mode: the old KPI section must remain visible (hidden=false)."""
    import sys
    sys.path.insert(0, "src")
    from qq_chat_analyzer.presentation.echo_report_template import ECHO_REPORT_CSS
    from qq_chat_analyzer.presentation import (
        EchoConversationSession,
        EchoConversationSessions,
        EchoReportView,
    )

    # 1. CSS contains the [hidden] override for .session-fields
    assert ".session-fields[hidden]" in ECHO_REPORT_CSS, (
        "CSS must have .session-fields[hidden] rule to override "
        "display:grid on hidden elements"
    )

    # 2. File-based CSS also has the rule
    css_file = __file__.rsplit("tests", 1)[0] + "frontend/echo_report/style.css"
    css_content = open(css_file, "r", encoding="utf-8").read()
    assert ".session-fields[hidden]" in css_content, (
        "CSS file must have .session-fields[hidden] rule"
    )
