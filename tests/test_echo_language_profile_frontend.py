"""Browser contract tests for Echo's language-profile chapter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "frontend" / "echo_report" / "app.js"

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

function allText(node) {
  return [node.textContent].concat(node.children.map(allText)).join(" ").trim();
}

const nodes = {
  "voices-intro": new FakeNode("voices-intro"),
  "member-list": new FakeNode("member-list")
};
global.window = { ECHO_DATA: JSON.parse(process.env.ECHO_PAYLOAD) };
global.document = {
  title: "",
  documentElement: new FakeNode("html"),
  getElementById: function (id) { return nodes[id] || null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return new FakeNode(""); }
};

eval(fs.readFileSync(process.env.ECHO_APP_PATH, "utf8"));
process.stdout.write(JSON.stringify({
  intro: allText(nodes["voices-intro"]),
  body: allText(nodes["member-list"]),
  childCount: nodes["member-list"].children.length
}));
"""


def _render(language_profile: dict[str, object]) -> dict[str, object]:
    payload = {
        "conversation": {"kind": "unknown", "name": "", "time_span": ""},
        "overview": {
            "has_data": True,
            "total_message_count": 1,
            "participant_count": 2,
            "empty_description": "",
        },
        "activity": {"hourly": [], "weekday": []},
        "conversation_sessions": None,
        "language_profile": language_profile,
        "members": [],
    }
    environment = os.environ.copy()
    environment.update(
        {
            "ECHO_APP_PATH": str(APP_PATH),
            "ECHO_PAYLOAD": json.dumps(payload, ensure_ascii=False),
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


def test_group_frontend_renders_precomputed_distinctive_words_as_primary() -> None:
    rendered = _render(
        {
            "mode": "group_distinctive",
            "available": True,
            "unavailable_reason": "",
            "members": [
                {
                    "speaker_key": "private-stable-key",
                    "display_name": "虚构成员甲",
                    "heading": "虚构成员甲",
                    "primary_words": ["风格词", "回声", "夜航"],
                    "context_words": ["项目", "讨论"],
                }
            ],
        }
    )

    assert "在这段聊天里，这些词更像 TA" in rendered["intro"]
    assert "虚构成员甲" in rendered["body"]
    assert "风格词" in rendered["body"]
    assert "常聊：项目 · 讨论" in rendered["body"]
    assert "private-stable-key" not in rendered["body"]


def test_private_frontend_renders_two_prepared_voice_headings() -> None:
    rendered = _render(
        {
            "mode": "private_common",
            "available": True,
            "unavailable_reason": "",
            "members": [
                {
                    "speaker_key": "a",
                    "display_name": "虚构甲",
                    "heading": "你常说",
                    "primary_words": ["散步", "晚安"],
                    "context_words": [],
                },
                {
                    "speaker_key": "b",
                    "display_name": "虚构乙",
                    "heading": "TA 常说",
                    "primary_words": ["到家", "明天"],
                    "context_words": [],
                },
            ],
        }
    )

    assert "两种声音" in rendered["intro"]
    assert "你常说" in rendered["body"]
    assert "TA 常说" in rendered["body"]
    assert "散步" in rendered["body"]
    assert "到家" in rendered["body"]
    assert "消息数量" not in rendered["body"]


def test_frontend_renders_presentation_unavailable_reason_without_recalculation() -> None:
    rendered = _render(
        {
            "mode": "group_distinctive",
            "available": False,
            "unavailable_reason": "样本不足，暂时无法比较成员特色词。",
            "members": [],
        }
    )

    assert rendered["body"] == "样本不足，暂时无法比较成员特色词。"


def test_frontend_contains_no_log_odds_eligibility_or_identity_implementation() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "ranking_score",
        "relative_ratio",
        "eligible_member",
        "tokenized_messages",
        "Math.log",
        "is_viewer",
    ):
        assert forbidden not in source
