"""Behavioral tests for CSV and word-cloud exporters."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.exporters import (
    export_word_frequency_csv,
    generate_wordcloud,
)


WORDS = [("数据", 3), ("Python", 2), ("分析", 1)]


def test_csv_creates_parent_directory_and_utf8_bom(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "word-frequency.csv"

    export_word_frequency_csv(WORDS, str(output_path))

    assert output_path.is_file()
    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_contains_word_and_count_columns(tmp_path: Path) -> None:
    output_path = tmp_path / "word-frequency.csv"

    export_word_frequency_csv(WORDS, str(output_path))

    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows == [
        {"word": "数据", "count": "3"},
        {"word": "Python", "count": "2"},
        {"word": "分析", "count": "1"},
    ]


def test_wordcloud_creates_png_with_explicit_font(tmp_path: Path) -> None:
    font_path = _available_chinese_font()
    output_path = tmp_path / "explicit-font" / "wordcloud.png"

    generate_wordcloud(WORDS, str(output_path), str(font_path))

    assert output_path.is_file()
    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(output_path) as image:
        assert image.size == (1600, 900)
        assert image.convert("RGB").getpixel((0, 0)) == (234, 246, 255)


def test_wordcloud_auto_discovers_available_font(tmp_path: Path) -> None:
    _available_chinese_font()
    output_path = tmp_path / "auto-font" / "wordcloud.png"

    generate_wordcloud(WORDS, str(output_path))

    assert output_path.is_file()
    assert output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def _available_chinese_font() -> Path:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = [
        windows_fonts / "msyh.ttc",
        windows_fonts / "msyhbd.ttc",
        windows_fonts / "simhei.ttf",
        windows_fonts / "simsun.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    pytest.skip("No Chinese font is available for the word-cloud test.")
