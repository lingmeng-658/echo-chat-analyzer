"""Browser contract tests for Echo's language-profile chapter."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


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
  "member-list": new FakeNode("member-list"),
  "private-shared-words": new FakeNode("private-shared-words"),
  "private-side-words": new FakeNode("private-side-words"),
  "private-shared-words-list": new FakeNode("private-shared-words-list"),
  "private-side-words-list": new FakeNode("private-side-words-list")
};
global.window = {
  ECHO_DATA: JSON.parse(process.env.ECHO_PAYLOAD),
  ECHO_ASSETS: {}
};
global.document = {
  title: "",
  documentElement: new FakeNode("html"),
  getElementById: function (id) { return nodes[id] || null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return new FakeNode(""); },
  createTextNode: function (text) {
    var node = new FakeNode("");
    node.textContent = String(text);
    return node;
  }
};

eval(fs.readFileSync(process.env.ECHO_APP_PATH, "utf8"));
process.stdout.write(JSON.stringify({
  intro: allText(nodes["voices-intro"]),
  body: allText(nodes["member-list"]),
  bodyClass: nodes["member-list"].className,
  childCount: nodes["member-list"].children.length,
  sharedHidden: nodes["private-shared-words"].hidden,
  shared: allText(nodes["private-shared-words"]) + " " + allText(nodes["private-shared-words-list"]),
  sideHidden: nodes["private-side-words"].hidden,
  side: allText(nodes["private-side-words"]) + " " + allText(nodes["private-side-words-list"])
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
    assert "常聊：" in rendered["body"]
    assert "项目" in rendered["body"]
    assert "讨论" in rendered["body"]
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


def test_private_frontend_renders_shared_words_and_side_preference() -> None:
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
                    "primary_words": ["散步"],
                    "context_words": [],
                    "expression_habits": {
                        "median_length": 5.0,
                        "average_length": 5.0,
                        "max_length": 7,
                        "run_count": 2,
                        "average_run_length": 2.0,
                        "median_run_length": 2.0,
                        "single_message_run_count": 1,
                        "multi_message_run_count": 1,
                    },
                },
                {
                    "speaker_key": "b",
                    "display_name": "虚构乙",
                    "heading": "TA 常说",
                    "primary_words": ["到家"],
                    "context_words": [],
                    "expression_habits": {
                        "median_length": 3.0,
                        "average_length": 3.0,
                        "max_length": 5,
                        "run_count": 1,
                        "average_run_length": 3.0,
                        "median_run_length": 3.0,
                        "single_message_run_count": 0,
                        "multi_message_run_count": 1,
                    },
                },
            ],
            "shared_words": [
                {"word": "回声", "self_count": 6, "peer_count": 4, "emphasis": "shared"}
            ],
            "side_preference_words": [
                {"word": "方案", "self_count": 5, "peer_count": 1, "emphasis": "self"}
            ],
        }
    )

    assert rendered["sharedHidden"] is False
    assert "回声" in rendered["shared"]
    assert rendered["sideHidden"] is False
    assert "方案" in rendered["side"]
    assert "你更常说" in rendered["side"]
    assert "中位 5 字" in rendered["body"]
    assert "连发 2 条" in rendered["body"]
    assert "common_strength" not in rendered["shared"]
    assert "rate_a" not in rendered["shared"]

    html_source = (PROJECT_ROOT / "frontend" / "echo_report" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "同频" in html_source
    assert "谁更常这样说" in html_source


def test_frontend_contains_no_log_odds_eligibility_or_identity_implementation() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "ranking_score",
        "relative_ratio",
        "eligible_member",
        "tokenized_messages",
        "Math.log",
        "is_viewer",
        "common_strength",
        "preferred_speaker_key",
        "rate_a",
        "rate_b",
    ):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# Group length control: many members scroll inside the chapter
# ---------------------------------------------------------------------------


STYLE_PATH = PROJECT_ROOT / "frontend" / "echo_report" / "style.css"


def _read_css_sources() -> tuple[str, str]:
    """Both copies of the report stylesheet must stay in sync."""
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from qq_chat_analyzer.presentation.echo_report_template import ECHO_REPORT_CSS

    return ECHO_REPORT_CSS, STYLE_PATH.read_text(encoding="utf-8")


def test_group_member_list_scrolls_within_a_bounded_section() -> None:
    """A big group must not stretch the chapter: the portraits scroll inside."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert ".member-list.mode-group {" in css
        assert "max-height: min(560px, 72vh);" in css
        assert "overflow-y: auto;" in css
        assert "overscroll-behavior: contain;" in css
        # On paper every portrait unfolds instead of scrolling.
        assert ".member-list.mode-group { max-height: none; overflow: visible; }" in css


def test_private_member_list_keeps_its_original_layout() -> None:
    """Private chats are untouched: no cap, no scroll, same two-column grid."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert ".member-list { border-top: 1px solid var(--ink); }" in css
        assert (
            ".member-list.mode-private { display: grid; "
            "grid-template-columns: 1fr 1fr; }" in css
        )
        for line in css.splitlines():
            if ".mode-private" in line:
                assert "overflow" not in line, line
                assert "max-height" not in line, line


def test_group_portraits_use_two_compact_desktop_columns() -> None:
    """A wide screen shows six voices: two columns inside the bounded scroll box."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert (
            ".member-list.mode-group {\n"
            "  display: grid;\n"
            "  grid-template-columns: repeat(2, minmax(0, 1fr));\n"
        ) in css
        # The chapter keeps its bounded height, and paper still unfolds it.
        assert "max-height: min(560px, 72vh);" in css
        assert ".member-list.mode-group { max-height: none; overflow: visible; }" in css
        # Narrow screens fall back to one portrait per row.
        assert ".member-list.mode-group { display: block; }" in css


def test_group_portrait_words_share_one_compact_line() -> None:
    """Five words stay on a single line instead of wrapping into large type."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert (
            ".member-list.mode-group .voice-words "
            "{ gap: 6px 7px; margin: 11px 0 0; }" in css
        )
        assert (
            ".member-list.mode-group .voice-words li "
            "{ font: 400 20px/1.3 var(--serif); letter-spacing: 0; }" in css
        )
        assert (
            ".member-list.mode-group .voice-words li::after "
            "{ margin-left: 7px; font-size: .5em; }" in css
        )
        # The oversized clamp stays only in the shared base rule.
        assert (
            ".voice-words li { position: relative; min-width: 0; max-width: 100%; "
            "overflow-wrap: anywhere; color: var(--ink); "
            "font: 400 clamp(25px, 4vw, 39px)/1.25 var(--serif); "
            "letter-spacing: -.02em; }" in css
        )


def test_group_portrait_cards_stay_compact() -> None:
    """One card must be short enough for three rows to fit on a laptop screen."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert ".member-list.mode-group .voice-entry { padding: 20px 0 18px; }" in css
        assert (
            ".member-list.mode-group .voice-entry h3 "
            "{ font: 500 18px/1.35 var(--sans); }" in css
        )
        assert (
            ".member-list.mode-group .voice-descriptor "
            "{ margin: 6px 0 0; font-size: 12.5px; line-height: 1.6; }" in css
        )
        assert (
            ".member-list.mode-group .voice-context "
            "{ margin: 9px 0 0; font: 12px/1.7 var(--serif); }" in css
        )


def test_long_names_and_words_cannot_overflow_their_column() -> None:
    """A narrow column must absorb long nicknames and long words."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert ".voice-entry { position: relative; min-width: 0;" in css
        assert ".voice-entry header { display: flex; flex-wrap: wrap;" in css
        assert (
            ".voice-entry h3 { min-width: 0; margin: 0; overflow-wrap: anywhere;" in css
        )
        assert ".voice-words { display: flex; flex-wrap: wrap; min-width: 0;" in css
        assert ".voice-words li { position: relative; min-width: 0; max-width: 100%;" in css
        assert "  max-width: 100%;\n  overflow-wrap: anywhere;" in css
        assert (
            ".voice-context { margin: 30px 0 0 40px; color: var(--faint); "
            "font: 13px/1.8 var(--serif); overflow-wrap: anywhere; }" in css
        )


def test_private_portraits_keep_their_own_larger_words() -> None:
    """The compaction is scoped to group mode; private chats keep their scale."""
    template_css, file_css = _read_css_sources()

    for css in (template_css, file_css):
        assert ".mode-private .voice-words li { margin: 0; font-size: 30px; }" in css
        assert ".mode-private .voice-entry { min-height: 340px;" in css
        assert ".mode-private .voice-words li::after { content: \"\"; }" in css


def test_group_member_list_renders_every_member_without_slicing() -> None:
    """Length control is CSS only: the DOM keeps all members and portraits."""
    members = [
        {
            "speaker_key": f"fictional-key-{index}",
            "display_name": f"虚构成员{index:02d}",
            "heading": f"虚构成员{index:02d}",
            "primary_words": ["风格词", "回声"],
            "context_words": ["项目"],
        }
        for index in range(60)
    ]

    rendered = _render(
        {
            "mode": "group_distinctive",
            "available": True,
            "unavailable_reason": "",
            "members": members,
        }
    )

    assert rendered["childCount"] == 60
    assert rendered["bodyClass"] == "member-list mode-group"
    assert "虚构成员00" in rendered["body"]
    assert "虚构成员59" in rendered["body"]
    assert "fictional-key-59" not in rendered["body"]


def test_private_member_list_still_renders_the_two_prepared_voices() -> None:
    """The private branch keeps its own class and both prepared portraits."""
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
                    "primary_words": ["散步"],
                    "context_words": [],
                },
                {
                    "speaker_key": "b",
                    "display_name": "虚构乙",
                    "heading": "TA 常说",
                    "primary_words": ["到家"],
                    "context_words": [],
                },
            ],
        }
    )

    assert rendered["bodyClass"] == "member-list mode-private"
    assert rendered["childCount"] == 2


# ---------------------------------------------------------------------------
# Real layout regression: a desktop screen must show six compact voices
# ---------------------------------------------------------------------------


LAYOUT_PROBE = r"""
<script>
(function () {
  var voices = document.getElementById('voices');
  if (voices) {
    var top = voices.getBoundingClientRect().top + window.scrollY;
    document.body.style.position = 'relative';
    document.body.style.top = (-top) + 'px';
  }
  function nodes(selector, root) {
    return Array.prototype.slice.call(
      (root || document).querySelectorAll(selector)
    );
  }
  var list = document.getElementById('member-list');
  var cards = nodes('.voice-entry');
  var viewportHeight = window.innerHeight;
  var fullyVisible = 0;
  var wrappedWordCards = 0;
  var overflowingCards = 0;
  var cardHeights = [];
  cards.forEach(function (card) {
    var cardRect = card.getBoundingClientRect();
    if (cardRect.top >= -1 && cardRect.bottom <= viewportHeight + 1) {
      fullyVisible += 1;
    }
    cardHeights.push(Math.round(cardRect.height));
    var rows = {};
    nodes('.voice-words > li', card).forEach(function (item) {
      rows[Math.round(item.getBoundingClientRect().top)] = true;
    });
    if (Object.keys(rows).length > 1) {
      wrappedWordCards += 1;
    }
    var overflowed = nodes('*', card).some(function (node) {
      if (node.classList.contains('voice-expression')) {
        return false;
      }
      var nodeRect = node.getBoundingClientRect();
      return (
        nodeRect.right > cardRect.right + 1 ||
        nodeRect.left < cardRect.left - 1
      );
    });
    if (overflowed) {
      overflowingCards += 1;
    }
  });
  var wordItems = nodes('.voice-words > li');
  var metrics = {
    columns: cards.length > 1 &&
      cards[0].getBoundingClientRect().top ===
        cards[1].getBoundingClientRect().top
      ? 2
      : 1,
    cardCount: cards.length,
    cardHeightMax: cardHeights.length ? Math.max.apply(null, cardHeights) : 0,
    fullyVisibleCards: fullyVisible,
    wrappedWordCards: wrappedWordCards,
    overflowingCards: overflowingCards,
    wordFontSize: wordItems.length
      ? getComputedStyle(wordItems[0]).fontSize
      : null,
    listOverflowY: list ? getComputedStyle(list).overflowY : null,
    listDisplay: list ? getComputedStyle(list).display : null
  };
  var tag = document.createElement('div');
  tag.id = 'echo-layout-metrics';
  tag.setAttribute('data-json', JSON.stringify(metrics));
  document.documentElement.appendChild(tag);
})();
</script>
"""


def _group_layout_members() -> list[dict[str, object]]:
    """Nine prepared group voices, including a long nickname (all fictional)."""
    prepared = (
        ("虚构甲", ("晚安", "收到", "好的", "明天", "加油"), ("项目", "会议室")),
        ("虚构乙", ("好家伙", "真行", "哈哈哈", "绝了", "离谱"), ("比赛", "复盘")),
        (
            "爱在深夜整理歌单的虚构成员丙",
            ("歌单", "循环", "深夜", "耳机", "安静"),
            ("音乐", "通勤"),
        ),
        ("虚构丁", ("总结", "结论", "先这样", "再确认", "复盘"), ("流程",)),
        ("虚构戊", ("早上好", "吃了吗", "下班", "路上", "小心"), ("通勤", "天气")),
        ("虚构己", ("图片", "链接", "稍后", "看了", "有趣"), ("收藏", "分享")),
        ("虚构庚", ("那就这样", "没问题", "辛苦", "谢谢", "收到"), ("安排", "时间")),
        ("虚构辛", ("来了", "出发", "到了", "等一下", "马上"), ("路线", "门票")),
        ("虚构壬", ("哈哈哈", "好家伙", "不会吧", "真的吗", "笑死我"), ("群里", "转发")),
    )
    return [
        {
            "speaker_key": f"fictional-key-{index:02d}",
            "display_name": name,
            "heading": name,
            "primary_words": list(words),
            "context_words": list(context),
        }
        for index, (name, words, context) in enumerate(prepared, start=1)
    ]


def _layout_metrics(html_path: Path, width: int, height: int) -> dict[str, object]:
    """Measure the rendered chapter in a real, throwaway Chromium window."""
    from qq_chat_analyzer.presentation.share.renderer import find_chromium

    chromium = find_chromium()
    if not chromium:
        pytest.skip("No local Chromium is available for the layout regression.")
    completed = subprocess.run(
        [
            chromium,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--no-first-run",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            "--virtual-time-budget=5000",
            "--dump-dom",
            html_path.as_uri(),
        ],
        check=True,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
    )
    marker = 'id="echo-layout-metrics" data-json="'
    index = completed.stdout.find(marker)
    assert index >= 0, "The language-profile chapter did not render in Chromium."
    start = index + len(marker)
    end = completed.stdout.find('"', start)
    return json.loads(completed.stdout[start:end].replace("&quot;", '"'))


@pytest.mark.slow_integration
def test_group_chapter_shows_six_compact_voices_on_a_desktop_screen(
    tmp_path: Path,
) -> None:
    """Two columns, six readable voices, five words per line, nothing clipped."""
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from qq_chat_analyzer.presentation import (
        EchoLanguageMember,
        EchoLanguageProfile,
        EchoReportView,
        export_echo_report_html,
    )

    members = tuple(
        EchoLanguageMember(
            speaker_key=entry["speaker_key"],
            display_name=entry["display_name"],
            heading=entry["heading"],
            primary_words=tuple(entry["primary_words"]),
            context_words=tuple(entry["context_words"]),
        )
        for entry in _group_layout_members()
    )
    view = EchoReportView(
        title="Fictional Group",
        has_data=True,
        conversation_kind="group",
        conversation_name="虚构群聊",
        total_message_count=4321,
        participant_count=len(members),
        language_profile=EchoLanguageProfile(
            mode="group_distinctive",
            available=True,
            members=members,
        ),
    )
    report_path = tmp_path / "echo-report.html"
    export_echo_report_html(view, report_path)
    probe_path = tmp_path / "echo-report-probe.html"
    probe_path.write_text(
        report_path.read_text(encoding="utf-8").replace(
            "</body>", LAYOUT_PROBE + "</body>"
        ),
        encoding="utf-8",
    )

    desktop = _layout_metrics(probe_path, 1440, 1051)  # ~1422 x 899 CSS px

    assert desktop["cardCount"] == len(members)
    assert desktop["columns"] == 2
    assert desktop["listDisplay"] == "grid"
    assert desktop["listOverflowY"] == "auto"
    assert desktop["fullyVisibleCards"] >= 6
    assert desktop["wrappedWordCards"] == 0
    assert desktop["overflowingCards"] == 0
    assert desktop["cardHeightMax"] <= 200
    assert desktop["wordFontSize"] == "20px"

    narrow = _layout_metrics(probe_path, 500, 1047)  # ~500 x 895 CSS px

    assert narrow["columns"] == 1
    assert narrow["wrappedWordCards"] == 0
    assert narrow["overflowingCards"] == 0
