"""Behavior tests for source-neutral distinctive-word analysis."""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _analysis():
    return importlib.import_module("qq_chat_analyzer.analysis")


def _eligible_records(
    speaker: str,
    distinctive: str,
    *,
    common_count: int = 90,
    distinctive_count: int = 18,
) -> list[tuple[str, list[str]]]:
    """Build 30 tokenized messages and at least three candidate words."""
    tokens = (
        ["共同词"] * common_count
        + [distinctive] * distinctive_count
        + [f"{distinctive}-二"] * 6
        + [f"{distinctive}-三"] * 3
    )
    records = [(speaker, []) for _ in range(30)]
    for index, token in enumerate(tokens):
        records[index % len(records)][1].append(token)
    return records


def _three_eligible_members():
    return (
        _eligible_records("member-a", "偏好甲")
        + _eligible_records("member-b", "偏好乙")
        + _eligible_records("member-c", "偏好丙")
    )


def _member(report, speaker_key: str):
    return next(
        member
        for member in report.members
        if member.speaker_key == speaker_key
    )


def test_distinctive_words_rank_personal_preference_above_group_common_word() -> None:
    analysis = _analysis()

    report = analysis.DistinctiveWordAnalyzer().analyze(
        _three_eligible_members(),
        conversation_type="group",
    )

    assert report.available is True
    member = _member(report, "member-a")
    words = [item.word for item in member.words]
    assert words[0] == "偏好甲"
    assert words.index("偏好甲") < words.index("共同词")


def test_ranking_score_matches_the_selected_informative_prior_formula() -> None:
    analysis = _analysis()
    report = analysis.DistinctiveWordAnalyzer().analyze(
        _three_eligible_members(),
        conversation_type="group",
    )

    word = next(
        item
        for item in _member(report, "member-a").words
        if item.word == "偏好甲"
    )

    # Fixed oracle for this fictional corpus under the approved all-group
    # frequency prior with total strength 1000.
    assert word.ranking_score == pytest.approx(2.291097728762068)


@pytest.mark.parametrize("rare_count", [1, 2])
def test_word_below_three_member_occurrences_is_not_a_candidate(
    rare_count: int,
) -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    for index in range(rare_count):
        records[index][1].append("稀有噪声")

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert "稀有噪声" not in {
        word.word for word in _member(report, "member-a").words
    }


def test_word_with_exactly_three_member_occurrences_can_enter() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    for index in range(3):
        records[index][1].append("刚好三次")

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert "刚好三次" in {
        word.word for word in _member(report, "member-a").words
    }


def test_member_with_too_few_tokenized_messages_is_ineligible() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    records += [("member-d", ["丁词"] * 5 + [f"丁{i}"] * 5) for i in range(29)]

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert report.available is True
    assert {member.speaker_key for member in report.members} == {
        "member-a",
        "member-b",
        "member-c",
    }


def test_member_with_too_few_tokens_is_ineligible() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    records += [("member-d", [f"丁{i % 3}"]) for i in range(30)]

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert {member.speaker_key for member in report.members} == {
        "member-a",
        "member-b",
        "member-c",
    }


def test_member_with_too_few_candidate_words_is_ineligible() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    tokens = ["丁词一"] * 50 + ["丁词二"] * 50
    records += [("member-d", tokens[index::30]) for index in range(30)]

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert {member.speaker_key for member in report.members} == {
        "member-a",
        "member-b",
        "member-c",
    }


def test_ineligible_member_tokens_remain_in_the_background_corpus() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    records[0][1].extend(["背景词"] * 9)
    ineligible_tokens = ["背景词"] * 20 + ["旁观词"] * 20
    records += [
        ("member-d", ineligible_tokens[index::10])
        for index in range(10)
    ]

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )
    word = next(
        item
        for item in _member(report, "member-a").words
        if item.word == "背景词"
    )
    member_total = _member(report, "member-a").token_count
    all_total = sum(len(tokens) for _, tokens in records)

    assert word.member_rate == pytest.approx(9 / member_total)
    assert word.others_rate == pytest.approx(20 / (all_total - member_total))
    assert math.isfinite(word.relative_ratio)
    assert math.isfinite(word.ranking_score)


def test_fewer_than_three_eligible_members_makes_group_unavailable() -> None:
    analysis = _analysis()
    report = analysis.DistinctiveWordAnalyzer().analyze(
        _eligible_records("member-a", "偏好甲")
        + _eligible_records("member-b", "偏好乙"),
        conversation_type="group",
    )

    assert report.available is False
    assert report.availability is analysis.DistinctiveWordAvailability.INSUFFICIENT_MEMBERS
    assert report.eligible_member_count == 2
    assert report.members == ()


@pytest.mark.parametrize("conversation_type", ["private", "unknown"])
def test_non_group_conversations_do_not_run_distinctive_analysis(
    conversation_type: str,
) -> None:
    analysis = _analysis()
    report = analysis.DistinctiveWordAnalyzer().analyze(
        _three_eligible_members(),
        conversation_type=conversation_type,
    )

    assert report.available is False
    assert report.availability is analysis.DistinctiveWordAvailability.NOT_GROUP
    assert report.eligible_member_count == 0
    assert report.members == ()


def test_repeated_stable_sender_key_aggregates_into_one_member() -> None:
    analysis = _analysis()
    records = _three_eligible_members()
    # The first member arrives in many records under the same source-neutral key.
    assert sum(speaker == "member-a" for speaker, _ in records) == 30

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    member = _member(report, "member-a")
    assert member.tokenized_message_count == 30
    assert len([item for item in report.members if item.speaker_key == "member-a"]) == 1


def test_distinctive_words_are_limited_to_top_five() -> None:
    analysis = _analysis()
    records: list[tuple[str, list[str]]] = []
    for speaker, prefix in (("member-a", "甲"), ("member-b", "乙"), ("member-c", "丙")):
        tokens = ["共同词"] * 80
        for index in range(8):
            tokens.extend([f"{prefix}{index}"] * (12 - index))
        member_records = [(speaker, tokens[index::30]) for index in range(30)]
        records.extend(member_records)

    report = analysis.DistinctiveWordAnalyzer().analyze(
        records,
        conversation_type="group",
    )

    assert all(len(member.words) == 5 for member in report.members)


def test_default_product_parameters_are_named_and_stable() -> None:
    analysis = _analysis()

    assert analysis.DISTINCTIVE_MIN_WORD_COUNT == 3
    assert analysis.DISTINCTIVE_MIN_TOKENIZED_MESSAGES == 30
    assert analysis.DISTINCTIVE_MIN_TOKENS == 100
    assert analysis.DISTINCTIVE_MIN_CANDIDATE_WORDS == 3
    assert analysis.DISTINCTIVE_MIN_ELIGIBLE_MEMBERS == 3
    assert analysis.DISTINCTIVE_TOP_WORD_LIMIT == 5
    assert analysis.DISTINCTIVE_LOG_ODDS_PRIOR_STRENGTH == 1000.0
