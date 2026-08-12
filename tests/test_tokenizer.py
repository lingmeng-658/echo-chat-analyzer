"""Behavioral tests for jieba tokenization and stopword filtering."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.tokenizer import tokenize


def test_tokenizes_chinese_text_with_jieba() -> None:
    assert tokenize("我喜欢数据分析") == ["喜欢", "数据分析"]


def test_filters_trimmed_stopwords_and_ignores_blank_lines(
    tmp_path: Path,
) -> None:
    stopwords_path = tmp_path / "stopwords.txt"
    stopwords_path.write_text("  我  \n\n喜欢\n", encoding="utf-8")

    assert tokenize("我喜欢数据分析", str(stopwords_path)) == ["数据分析"]


def test_missing_stopwords_file_is_treated_as_empty(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-stopwords.txt"

    assert tokenize("我喜欢数据分析", str(missing_path)) == [
        "喜欢",
        "数据分析",
    ]


def test_filters_single_chinese_characters() -> None:
    text = "不 吗 想 过 还 吧 没 啊 给 天津 中科大"

    assert tokenize(text) == ["天津", "中科大"]


def test_preserves_english_words_numbers_and_multi_character_chinese() -> None:
    text = "Python CS61B 2026 天津 中科大"

    assert tokenize(text) == ["Python", "CS61B", "2026", "天津", "中科大"]


def test_preserves_hyphenated_ascii_nickname_as_one_token() -> None:
    tokens = tokenize("欢迎 fall-anchor 加入群聊")

    assert "fall-anchor" in tokens
    assert "fall" not in tokens
    assert "anchor" not in tokens


def test_preserves_existing_ascii_tokens_and_hyphenated_word() -> None:
    tokens = tokenize("Python CS61B hello-world")

    assert tokens == ["Python", "CS61B", "hello-world"]


def test_user_dictionary_keeps_custom_phrase_as_one_token(
    tmp_path: Path,
) -> None:
    user_dict_path = tmp_path / "user-dict.txt"
    user_dict_path.write_text("量子猫猫协议 100000 n\n", encoding="utf-8")

    assert tokenize(
        "量子猫猫协议",
        user_dict_path=str(user_dict_path),
    ) == ["量子猫猫协议"]


def test_missing_user_dictionary_is_safely_ignored(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-user-dict.txt"

    assert tokenize(
        "天津 Python 2026",
        user_dict_path=str(missing_path),
    ) == ["天津", "Python", "2026"]


def test_empty_text_returns_empty_list() -> None:
    assert tokenize("") == []
    assert tokenize(" \t\n ") == []


def test_filters_single_ascii_letters_case_insensitively() -> None:
    assert tokenize("b x Y") == []


def test_filters_one_and_two_digit_integers() -> None:
    assert tokenize("0 7 12 23 40 00") == []


def test_preserves_integers_with_three_or_more_digits() -> None:
    assert tokenize("666 2026") == ["666", "2026"]


def test_filters_deck_quantity_markers_case_insensitively() -> None:
    assert tokenize("1x 2x 10x 3X") == []


def test_preserves_informative_ascii_and_hyphenated_tokens() -> None:
    text = "AI DK JJC CS61B 666 2026 fall-anchor"

    assert tokenize(text) == [
        "AI",
        "DK",
        "JJC",
        "CS61B",
        "666",
        "2026",
        "fall-anchor",
    ]


def test_preserves_multi_character_chinese_after_low_information_filtering() -> None:
    assert tokenize("\u5929\u6d25 \u4e2d\u79d1\u5927") == [
        "\u5929\u6d25",
        "\u4e2d\u79d1\u5927",
    ]

def test_filters_english_function_words_case_insensitively(
    tmp_path: Path,
) -> None:
    stopwords_path = tmp_path / "stopwords.txt"
    stopwords_path.write_text(
        "the\nto\nmy\nin\nis\non\nand\nof\nfor\nare\nwas\n",
        encoding="utf-8",
    )

    assert tokenize(
        "Hello to my friends in China",
        str(stopwords_path),
    ) == ["Hello", "friends", "China"]
    assert tokenize(
        "The book is on the table",
        str(stopwords_path),
    ) == ["book", "table"]


def test_preserves_english_topic_words(tmp_path: Path) -> None:
    stopwords_path = tmp_path / "stopwords.txt"
    stopwords_path.write_text("the\nto\nmy\nin\nis\n", encoding="utf-8")

    assert tokenize(
        "China friends Trump Crazy Thursday",
        str(stopwords_path),
    ) == ["China", "friends", "Trump", "Crazy", "Thursday"]


def test_url_tokens_are_ignored() -> None:
    assert tokenize("看看 https://b23.tv/abc 怎么样") == [
        "看看",
        "怎么样",
    ]
    assert tokenize("www.example.com") == []
    assert tokenize("明天一起 https://a.com 吃饭") == [
        "明天",
        "一起",
        "吃饭",
    ]


def test_url_mask_does_not_leak_placeholder() -> None:
    tokens = tokenize("https://example.com/a?b=1")

    assert tokens == []
    assert not any("QQCHATURLPLACEHOLDER" in token for token in tokens)


def test_normal_text_not_harmed() -> None:
    assert tokenize("今天天气不错 Python 2026 天津") == [
        "今天天气",
        "不错",
        "Python",
        "2026",
        "天津",
    ]
