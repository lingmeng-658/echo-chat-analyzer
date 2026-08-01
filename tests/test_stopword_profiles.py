"""Behavioral contracts for the bundled stopword profiles."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.tokenizer import tokenize


@pytest.mark.parametrize(
    "profile_filename",
    [
        "stopwords.txt",
        "stopwords_topic.txt",
        "stopwords_culture.txt",
    ],
)
def test_profiles_preserve_new_student_topic_while_filtering_template_terms(
    profile_filename: str,
) -> None:
    tokens = tokenize(
        "新生 欢迎 群规 25 2026",
        str(PROJECT_ROOT / profile_filename),
    )

    assert tokens == ["新生", "2026"]
