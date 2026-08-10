"""Behavioral tests for the future chat-text cleaner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.cleaner import clean_text


def test_removes_image_placeholder() -> None:
    assert clean_text("开始[图片]继续") == "开始继续"


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("[回复消息] 收到", "收到"),
        ("[回复消息：这是一段虚构引用] 我同意", "我同意"),
    ],
)
def test_removes_reply_structure_text(raw_text: str, expected: str) -> None:
    assert clean_text(raw_text) == expected


def test_removes_nickname_mention() -> None:
    assert clean_text("@虚构用户乙 请查看资料") == "请查看资料"


def test_removes_mention_all() -> None:
    assert clean_text("@全体成员 明天下午开会") == "明天下午开会"


def test_removes_zero_width_characters() -> None:
    assert clean_text("学\u200b习\u200cPython\ufeff") == "学习Python"


def test_removes_control_characters_and_normalizes_whitespace_controls() -> None:
    assert clean_text("甲\x00乙\x07丙\n丁\t戊") == "甲乙丙 丁 戊"


def test_collapses_repeated_whitespace() -> None:
    assert clean_text("今天   学习\n\t Python") == "今天 学习 Python"


def test_preserves_normal_chinese_english_and_numbers() -> None:
    assert clean_text("中文 Python3 CS61B 2026") == "中文 Python3 CS61B 2026"


def test_preserves_common_group_chat_expressions() -> None:
    assert clean_text("哈哈 笑死 太强了") == "哈哈 笑死 太强了"


def test_wechat_clean_removes_internal_ids() -> None:
    assert clean_text("今天开会 wxid_test", platform="wechat") == "今天开会"
    assert clean_text(
        "内部 xa66c49rvh7212 hvly3bywwfbz22 记录",
        platform="wechat",
    ) == "内部 记录"


def test_wechat_clean_preserves_emojis_and_normal_text() -> None:
    assert clean_text(
        "[旺柴] 😂 [捂脸] 明天见",
        platform="wechat",
    ) == "[旺柴] 😂 [捂脸] 明天见"


def test_wechat_clean_does_not_affect_other_platforms() -> None:
    assert clean_text("内部 wxid_test xa66c49rvh7212") == (
        "内部 wxid_test xa66c49rvh7212"
    )
    assert clean_text(
        "内部 wxid_test xa66c49rvh7212",
        platform="qq",
    ) == "内部 wxid_test xa66c49rvh7212"


def test_structural_only_text_cleans_to_empty_string() -> None:
    raw_text = "@全体成员 [图片] [回复消息]\u200b \x00"

    assert clean_text(raw_text) == ""
