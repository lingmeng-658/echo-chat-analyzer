"""Behavioral tests for token frequency analysis."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import analyzer
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


def test_counts_word_occurrences_for_each_sender() -> None:
    sender_tokens = [
        ("小青", ["数据", "Python"]),
        ("小白", ["数据", "分析"]),
        ("小青", ["数据"]),
    ]

    assert analyzer.count_word_speakers(sender_tokens) == {
        "数据": {"小青": 2, "小白": 1},
        "Python": {"小青": 1},
        "分析": {"小白": 1},
    }


def test_repeated_word_in_one_message_counts_every_occurrence() -> None:
    sender_tokens = [("小青", ["算法", "算法", "算法"])]

    assert analyzer.count_word_speakers(sender_tokens) == {
        "算法": {"小青": 3},
    }


def test_summary_selects_top_twenty_five_words_by_total_count() -> None:
    word_sender_counts = {
        f"词{index:02d}": {"虚构用户": 30 - index}
        for index in range(26)
    }

    summaries = analyzer.top_word_speaker_summary(word_sender_counts)

    assert len(summaries) == 25
    assert [summary.word for summary in summaries] == [
        f"词{index:02d}"
        for index in range(25)
    ]


def test_tied_speakers_choose_the_one_who_used_word_first() -> None:
    sender_tokens = [
        ("先出现者", ["并列词"]),
        ("后出现者", ["并列词", "并列词"]),
        ("先出现者", ["并列词"]),
    ]
    counts = analyzer.count_word_speakers(sender_tokens)

    summaries = analyzer.top_word_speaker_summary(counts)

    assert summaries == [
        analyzer.WordSpeakerSummary(
            word="并列词",
            total_count=4,
            top_speaker="先出现者",
            top_speaker_count=2,
            top_speaker_share_percent=50.0,
        )
    ]


def test_summary_calculates_percentage_to_two_decimal_places() -> None:
    counts = {
        "数据": {
            "小青": 2,
            "小白": 1,
        }
    }

    summaries = analyzer.top_word_speaker_summary(counts)

    assert summaries[0].top_speaker_share_percent == 66.67


def test_single_speaker_has_one_hundred_percent_share() -> None:
    counts = {"Python": {"小青": 3}}

    summaries = analyzer.top_word_speaker_summary(counts)

    assert summaries == [
        analyzer.WordSpeakerSummary(
            word="Python",
            total_count=3,
            top_speaker="小青",
            top_speaker_count=3,
            top_speaker_share_percent=100.0,
        )
    ]


def test_empty_word_speaker_input_returns_empty_results() -> None:
    assert analyzer.count_word_speakers([]) == {}
    assert analyzer.top_word_speaker_summary({}) == []
