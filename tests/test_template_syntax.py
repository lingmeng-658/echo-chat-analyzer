"""Tests for the shared template syntax: literal braces vs generated variables."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.filter_pipeline import _template_matches
from qq_chat_analyzer.template_syntax import (
    escape_literal,
    iter_tokens,
    restore_literal,
    static_text,
    variable_counts,
)


@pytest.mark.parametrize(
    "text",
    [
        "{number}",
        "{variable}",
        "{{",
        "{a,b}",
        "{{{number}",
        "@张三{number}",
        "订单{number}金额",
        "{user}{url}",
        "}{",
        "纯文本",
    ],
)
def test_escape_and_restore_are_reversible(text: str) -> None:
    assert restore_literal(escape_literal(text)) == text


def test_literal_braces_are_not_counted_as_variables() -> None:
    template = escape_literal("订单{number}金额99")

    assert variable_counts(template) == {}
    assert static_text(template) == "订单{number}金额99"


def test_escaped_literal_and_generated_tokens_are_separated() -> None:
    template = "订单{{number}金额{number}"

    assert variable_counts(template) == {"number": 1}
    assert static_text(template) == "订单{number}金额"


def test_tokens_reconstruct_the_decoded_template() -> None:
    template = "订单{{number}金额{number}"

    decoded = "".join(
        value if kind == "literal" else "{" + value + "}"
        for kind, value in iter_tokens(template)
    )

    assert decoded == "订单{number}金额{number}"


@pytest.mark.parametrize(
    ("template", "text", "expected"),
    [
        pytest.param(
            "订单{{number}金额{number}",
            "订单{number}金额99",
            True,
            id="literal_brace_matches_literally",
        ),
        pytest.param(
            "订单{{number}金额{number}",
            "订单7金额99",
            False,
            id="literal_brace_does_not_accept_a_number",
        ),
        pytest.param(
            "编号{{id}的完成{number}",
            "编号{id}的完成99",
            True,
            id="literal_id_matches_literally",
        ),
        pytest.param(
            "编号{{id}的完成{number}",
            "编号123456的完成99",
            False,
            id="literal_id_does_not_accept_an_identifier",
        ),
        pytest.param(
            "编号{id}的完成{number}",
            "编号{id}的完成99",
            False,
            id="generated_id_does_not_accept_literal_text",
        ),
        pytest.param(
            "签到成功，积分+{number}",
            "签到成功，积分+10",
            True,
            id="plain_template_is_unchanged",
        ),
    ],
)
def test_template_pattern_semantics(
    template: str,
    text: str,
    expected: bool,
) -> None:
    assert _template_matches(template, text) is expected
