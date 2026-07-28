"""Behavioral tests for CSV and word-cloud exporters."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest
from matplotlib.font_manager import FontProperties
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import exporters
from qq_chat_analyzer.analyzer import WordSpeakerSummary
from qq_chat_analyzer.exporters import (
    export_word_frequency_csv,
    generate_wordcloud,
)


WORDS = [("数据", 3), ("Python", 2), ("分析", 1)]
SPEAKER_SUMMARIES = [
    WordSpeakerSummary(
        word="数据",
        total_count=3,
        top_speaker="小青",
        top_speaker_count=2,
        top_speaker_share_percent=66.67,
    ),
    WordSpeakerSummary(
        word="Python",
        total_count=1,
        top_speaker="小白",
        top_speaker_count=1,
        top_speaker_share_percent=100.0,
    ),
]


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


def test_word_speaker_summary_csv_has_bom_header_and_formatted_data(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "word_speaker_summary.csv"

    exporters.export_word_speaker_summary_csv(
        SPEAKER_SUMMARIES,
        str(output_path),
    )

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows == [
        {
            "word": "数据",
            "total_count": "3",
            "top_speaker": "小青",
            "top_speaker_count": "2",
            "top_speaker_share_percent": "66.67",
        },
        {
            "word": "Python",
            "total_count": "1",
            "top_speaker": "小白",
            "top_speaker_count": "1",
            "top_speaker_share_percent": "100.00",
        },
    ]


def test_word_speaker_frequency_csv_preserves_input_order(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "word_speaker_frequency.csv"
    rows = [
        ("Python", "先出现者", 2),
        ("Python", "后出现者", 2),
        ("数据", "第三位", 1),
    ]

    exporters.export_word_speaker_frequency_csv(rows, str(output_path))

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        exported_rows = list(csv.DictReader(file))
    assert exported_rows == [
        {"word": "Python", "speaker": "先出现者", "count": "2"},
        {"word": "Python", "speaker": "后出现者", "count": "2"},
        {"word": "数据", "speaker": "第三位", "count": "1"},
    ]


def test_word_top_speakers_chart_draws_fewer_than_twenty_five_rows(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "word_top_speakers.png"

    exporters.generate_word_top_speakers_chart(
        SPEAKER_SUMMARIES,
        str(output_path),
        str(_available_chinese_font()),
    )

    assert output_path.is_file()
    with Image.open(output_path) as image:
        assert image.width > 0
        assert image.height > 0


def test_word_top_speakers_chart_draws_twenty_five_rows(
    tmp_path: Path,
) -> None:
    summaries = [
        WordSpeakerSummary(
            word=f"词语{index:02d}",
            total_count=30 - index,
            top_speaker=f"用户{index:02d}",
            top_speaker_count=25 - index,
            top_speaker_share_percent=round(
                (25 - index) / (30 - index) * 100,
                2,
            ),
        )
        for index in range(25)
    ]
    output_path = tmp_path / "word_top_speakers.png"

    exporters.generate_word_top_speakers_chart(
        summaries,
        str(output_path),
        str(_available_chinese_font()),
    )

    with Image.open(output_path) as image:
        assert image.width > 0
        assert image.height > 0


def test_word_top_speakers_chart_rejects_empty_summaries(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "word_top_speakers.png"

    with pytest.raises(ValueError, match="summaries"):
        exporters.generate_word_top_speakers_chart([], str(output_path))


def test_chart_orders_by_share_and_uses_percentage_axis_without_mutating_input(
) -> None:
    summaries = [
        WordSpeakerSummary("低占比", 100, "甲", 40, 40.0),
        WordSpeakerSummary("并列先出现", 100, "乙", 75, 75.0),
        WordSpeakerSummary("并列后出现", 100, "丙", 75, 75.0),
        WordSpeakerSummary("最高占比", 100, "丁", 90, 90.0),
    ]
    original_order = list(summaries)

    ordered = exporters._order_word_top_speaker_summaries(summaries)

    assert [summary.word for summary in ordered] == [
        "最高占比",
        "并列先出现",
        "并列后出现",
        "低占比",
    ]
    assert summaries == original_order

    figure, axes = exporters.plt.subplots()
    try:
        font = FontProperties(fname=str(_available_chinese_font()))
        exporters._draw_word_top_speakers_axes(axes, ordered, font)

        assert [bar.get_width() for bar in axes.patches] == [
            90.0,
            75.0,
            75.0,
            40.0,
        ]
        assert [label.get_text() for label in axes.get_yticklabels()] == [
            "最高占比 — 丁",
            "并列先出现 — 乙",
            "并列后出现 — 丙",
            "低占比 — 甲",
        ]
        assert axes.get_ylim()[0] > axes.get_ylim()[1]
        assert axes.get_xlim() == pytest.approx((0.0, 100.0))
        assert axes.get_xlabel() == "主要发送者占该词总次数的比例（%）"
        assert axes.get_title() == "高频词主要发送者占比 Top 25"
    finally:
        exporters.plt.close(figure)


def test_chart_ordering_selects_overall_top_twenty_five_before_share_sort(
) -> None:
    summaries = [
        WordSpeakerSummary(f"整体词{index:02d}", 100, "虚构用户", 50, 50.0)
        for index in range(25)
    ]
    summaries.append(
        WordSpeakerSummary("范围外高占比", 1, "范围外用户", 1, 100.0)
    )

    ordered = exporters._order_word_top_speaker_summaries(summaries)

    assert len(ordered) == 25
    assert all(summary.word != "范围外高占比" for summary in ordered)


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
