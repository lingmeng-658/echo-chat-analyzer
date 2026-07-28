"""Behavioral tests for token frequency analysis."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.analyzer import count_words, top_words


def test_counts_each_distinct_token() -> None:
    assert count_words(["Python", "数据", "2026"]) == {
        "Python": 1,
        "数据": 1,
        "2026": 1,
    }


def test_counts_repeated_tokens() -> None:
    assert count_words(["数据", "分析", "数据", "数据"]) == {
        "数据": 3,
        "分析": 1,
    }


def test_top_words_limits_the_number_of_results() -> None:
    tokens = ["甲", "乙", "甲", "丙", "甲", "乙", "丁"]

    assert top_words(tokens, n=2) == [("甲", 3), ("乙", 2)]


def test_top_words_orders_results_by_descending_frequency() -> None:
    tokens = ["低频", "高频", "高频", "中频", "中频", "高频"]

    assert top_words(tokens) == [
        ("高频", 3),
        ("中频", 2),
        ("低频", 1),
    ]


def test_empty_tokens_return_empty_results() -> None:
    assert count_words([]) == {}
    assert top_words([]) == []


def test_equal_frequencies_preserve_first_appearance_order() -> None:
    tokens = ["第三", "第一", "第二", "第一", "第二", "第三"]

    assert top_words(tokens) == [
        ("第三", 2),
        ("第一", 2),
        ("第二", 2),
    ]
