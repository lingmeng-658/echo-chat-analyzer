"""Browser-behavior tests for the Echo expression culture chapter."""

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
  constructor(id, tag) {
    this.id = id || "";
    this.tagName = (tag || "").toUpperCase();
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

const ids = JSON.parse(process.env.ECHO_NODE_IDS);
const nodes = {};
ids.forEach(function (id) { nodes[id] = new FakeNode(id); });

global.window = {
  ECHO_DATA: JSON.parse(process.env.ECHO_PAYLOAD),
  ECHO_ASSETS: JSON.parse(process.env.ECHO_ASSETS || "{}")
};
global.document = {
  title: "",
  documentElement: new FakeNode("html"),
  getElementById: function (id) { return nodes[id] || null; },
  querySelectorAll: function () { return []; },
  createElement: function (tag) { return new FakeNode("", tag); }
};

eval(fs.readFileSync(process.env.ECHO_APP_PATH, "utf8"));

const result = {};
function toNode(node) {
  return {
    tag: node.tagName,
    src: node.src,
    text: node.textContent,
    children: (node.children || []).map(toNode)
  };
}
ids.forEach(function (id) {
  result[id] = {
    text: allText(nodes[id]),
    hidden: nodes[id].hidden,
    childCount: nodes[id].children.length,
    children: nodes[id].children.map(toNode)
  };
});
process.stdout.write(JSON.stringify(result));
"""


def _render(
    expression_culture: dict[str, object] | None,
    *,
    assets: dict[str, str] | None = None,
    language_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = {
        "conversation": {"kind": "group", "name": "虚构讨论组", "time_span": ""},
        "overview": {
            "has_data": True,
            "total_message_count": 3,
            "participant_count": 2,
            "empty_description": "",
        },
        "activity": {"hourly": [], "weekday": []},
        "conversation_sessions": None,
        "language_profile": language_profile,
        "expression_culture": expression_culture,
        "members": [],
    }
    environment = os.environ.copy()
    environment.update(
        {
            "ECHO_APP_PATH": str(APP_PATH),
            "ECHO_NODE_IDS": json.dumps(
                [
                    "expression",
                    "expression-toc",
                    "expression-intro",
                    "expression-message-count",
                    "expression-only-count",
                    "expression-unique-count",
                    "expression-top-list",
                    "expression-combos",
                    "expression-combo-list",
                    "expression-members",
                    "member-list",
                ]
            ),
            "ECHO_PAYLOAD": json.dumps(payload, ensure_ascii=False),
            "ECHO_ASSETS": json.dumps(assets or {}, ensure_ascii=True),
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


def test_expression_chapter_renders_precomputed_culture() -> None:
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 9,
            "expression_only_message_count": 2,
            "expression_only_rate": 0.22,
            "unique_expression_count": 4,
            "top_expressions": [
                {"display_text": "😀", "count": 5, "kind": "unicode"},
                {
                    "display_text": "[QQ表情 66]",
                    "count": 2,
                    "kind": "platform_face",
                    "with_text_message_count": 2,
                    "text_only_message_count": 0,
                },
            ],
            "members": [
                {
                    "speaker_key": "fictional-stable-key",
                    "display_name": "虚构 Alice",
                    "expression_occurrence_count": 5,
                    "expression_message_count": 4,
                    "expression_share_percent": 55.6,
                    "expression_only_message_count": 1,
                    "top_expressions": [
                        {
                            "display_text": "😀",
                            "count": 4,
                            "kind": "unicode",
                            "with_text_message_count": 4,
                            "text_only_message_count": 0,
                        }
                    ],
                }
            ],
        }
    )

    assert rendered["expression"]["hidden"] is False
    assert rendered["expression-toc"]["hidden"] is False
    assert "共同语言" in rendered["expression-intro"]["text"]
    assert "9 条" in rendered["expression-message-count"]["text"]
    assert "2 条" in rendered["expression-only-count"]["text"]
    assert "2 种" in rendered["expression-unique-count"]["text"]
    assert "😀" in rendered["expression-top-list"]["text"]
    assert "5 次" in rendered["expression-top-list"]["text"]
    assert "贴图" not in rendered["expression-top-list"]["text"]
    assert "带文字" not in rendered["expression-top-list"]["text"]
    assert "纯表情" not in rendered["expression-top-list"]["text"]
    assert "平台表情" not in rendered["expression-top-list"]["text"]
    assert "Unicode" not in rendered["expression-top-list"]["text"]
    assert "虚构 Alice" in rendered["expression-members"]["text"]
    assert "占全部表达" not in rendered["expression-members"]["text"]
    assert "带表达消息" not in rendered["expression-members"]["text"]
    assert "fictional-stable-key" not in rendered["expression-members"]["text"]


def test_expression_chapter_hides_when_unavailable() -> None:
    rendered = _render(None)

    assert rendered["expression"]["hidden"] is True
    assert rendered["expression-toc"]["hidden"] is True
    assert rendered["expression-intro"]["text"] == ""


def test_expression_visual_asset_renders_image() -> None:
    asset_uri = "data:image/png;base64,AAAA"
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 226,
            "expression_only_message_count": 226,
            "expression_only_rate": 1.0,
            "unique_expression_count": 99,
            "top_expressions": [
                {
                    "display_text": "捂脸",
                    "count": 226,
                    "kind": "platform_face",
                    "with_text_message_count": 0,
                    "text_only_message_count": 226,
                    "asset_key": "wechat:捂脸",
                }
            ],
            "members": [],
        },
        assets={"wechat:捂脸": asset_uri},
    )

    children = rendered["expression-top-list"]["children"]
    assert any(child["tag"] == "IMG" for child in children[0]["children"])
    assert any(
        child["src"] == asset_uri
        for child in children[0]["children"]
    )
    assert "226 次" in rendered["expression-top-list"]["text"]
    assert "捂脸" not in rendered["expression-top-list"]["text"]
    assert "[捂脸]" not in rendered["expression-top-list"]["text"]
    assert "平台表情" not in rendered["expression-top-list"]["text"]
    assert "带文字" not in rendered["expression-top-list"]["text"]
    assert "纯表情" not in rendered["expression-top-list"]["text"]
    assert all(
        child["tag"] != "SPAN" or child["text"] != "捂脸"
        for child in children[0]["children"]
    )
    assert rendered["expression-unique-count"]["text"] == "1 种"


def test_expression_without_asset_renders_fallback_text() -> None:
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 1,
            "expression_only_message_count": 1,
            "expression_only_rate": 1.0,
            "unique_expression_count": 1,
            "top_expressions": [
                {
                    "display_text": "未知表达",
                    "count": 1,
                    "kind": "platform_face",
                    "with_text_message_count": 0,
                    "text_only_message_count": 1,
                }
            ],
            "members": [],
        }
    )

    assert "未知表达" in rendered["expression-top-list"]["text"]
    assert all(
        child["tag"] != "IMG"
        and all(grand["tag"] != "IMG" for grand in child["children"])
        for child in rendered["expression-top-list"]["children"]
    )


def test_expression_top_copy_uses_echo_language() -> None:
    html = (PROJECT_ROOT / "frontend" / "echo_report" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "带表达的消息" in html
    assert "只用表达回应" in html
    assert "常用表达" in html
    assert "这段交流最常用的表达" in html
    assert "常一起出现的表达" in html


def test_expression_combination_renders_asset_images() -> None:
    asset_uri = "data:image/png;base64,AAAA"
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 2,
            "expression_only_message_count": 2,
            "expression_only_rate": 1.0,
            "unique_expression_count": 2,
            "top_expressions": [],
            "top_combinations": [
                {
                    "asset_keys": ["wechat:捂脸", "wechat:旺柴"],
                    "count": 3,
                    "common_members": [
                        {
                            "display_name": "虚构离黎",
                            "count": 2,
                            "share_percent": 66.7,
                        }
                    ],
                }
            ],
            "members": [],
        },
        assets={
            "wechat:捂脸": asset_uri,
            "wechat:旺柴": asset_uri,
        },
    )

    assert rendered["expression-combos"]["hidden"] is False
    assert rendered["expression-combo-list"]["childCount"] == 1
    def find_imgs(nodes):
        images = []
        for node in nodes:
            if node["tag"] == "IMG":
                images.append(node)
            images.extend(find_imgs(node.get("children", [])))
        return images

    images = find_imgs(rendered["expression-combo-list"]["children"])
    assert len(images) == 2
    assert "3 次" in rendered["expression-combo-list"]["text"]
    assert "常用者" in rendered["expression-combo-list"]["text"]
    assert "虚构离黎" in rendered["expression-combo-list"]["text"]


def test_expression_combination_fallback_without_assets() -> None:
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 1,
            "expression_only_message_count": 1,
            "expression_only_rate": 1.0,
            "unique_expression_count": 2,
            "top_expressions": [],
            "top_combinations": [
                {
                    "asset_keys": [None, None],
                    "count": 2,
                    "common_members": [],
                }
            ],
            "members": [],
        }
    )

    assert rendered["expression-combos"]["hidden"] is True
    assert rendered["expression-combo-list"]["childCount"] == 0
    assert "两个表达组合" not in rendered["expression-combo-list"]["text"]
    assert "2 次" not in rendered["expression-combo-list"]["text"]


def test_expression_nearby_words_uses_space_separator() -> None:
    rendered = _render(
        {
            "available": True,
            "expression_message_count": 1,
            "expression_only_message_count": 0,
            "expression_only_rate": 0.0,
            "unique_expression_count": 1,
            "top_expressions": [
                {
                    "display_text": "😀",
                    "count": 2,
                    "kind": "unicode",
                    "with_text_message_count": 2,
                    "text_only_message_count": 0,
                    "nearby_words": ["离谱", "不会吧", "又来了"],
                }
            ],
            "members": [],
        }
    )

    text = rendered["expression-top-list"]["text"]
    assert "常和这些词一起：离谱 不会吧 又来了" in text
    assert "·" not in text


def test_expression_member_area_uses_fixed_scroll_container() -> None:
    css = (PROJECT_ROOT / "frontend" / "echo_report" / "style.css").read_text(
        encoding="utf-8"
    )
    assert ".expression-members" in css
    assert "height: 460px" in css
    assert "overflow-y: hidden" in css
    assert ".expression-members:hover" in css
    assert "overflow-y: auto" in css


def test_voice_expression_token_renders_image() -> None:
    asset_uri = "data:image/png;base64,AAAA"
    rendered = _render(
        None,
        assets={"wechat:捂脸": asset_uri},
        language_profile={
            "mode": "private_common",
            "available": True,
            "members": [
                {
                    "speaker_key": "fictional-self",
                    "display_name": "你",
                    "heading": "你常说",
                    "primary_words": [{"asset_key": "wechat:捂脸"}],
                    "context_words": [],
                    "expression_habits": None,
                }
            ],
            "shared_words": [],
            "side_preference_words": [],
        },
    )

    def find_imgs(nodes):
        images = []
        for node in nodes:
            if node["tag"] == "IMG":
                images.append(node)
            images.extend(find_imgs(node.get("children", [])))
        return images

    assert find_imgs(rendered["member-list"]["children"])
    assert "捂脸" not in rendered["member-list"]["text"]


def test_expression_frontend_contains_no_internal_statistics() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    for forbidden in ("expression_key", "face_type", "packId", "stickerId"):
        assert forbidden not in source

    html = (PROJECT_ROOT / "frontend" / "echo_report" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="expression"' in html
    assert "表达文化" in html
