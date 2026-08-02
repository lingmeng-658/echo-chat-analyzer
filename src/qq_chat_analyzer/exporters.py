"""Export analyzed word frequencies to local files."""

from __future__ import annotations

import csv
import os
from collections.abc import Sequence
from pathlib import Path

from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import PercentFormatter
from wordcloud import WordCloud

from .analyzer import WordSpeakerSummary


_FONT_FILENAMES = (
    "msyh.ttc",
    "msyhbd.ttc",
    "simhei.ttf",
    "simsun.ttc",
    "simsun.ttf",
)
_CROSS_PLATFORM_FONT_PATHS = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
)


def export_word_frequency_csv(
    words: list[tuple[str, int]],
    output_path: str,
) -> None:
    """Write word frequencies as a UTF-8-with-BOM CSV file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("word", "count"))
        writer.writerows(words)


def export_word_speaker_summary_csv(
    summaries: Sequence[WordSpeakerSummary],
    output_path: str,
) -> None:
    """Write top-speaker summaries as a UTF-8-with-BOM CSV file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            (
                "word",
                "total_count",
                "top_speaker",
                "top_speaker_count",
                "top_speaker_share_percent",
            )
        )
        for summary in summaries:
            writer.writerow(
                (
                    summary.word,
                    summary.total_count,
                    summary.top_speaker,
                    summary.top_speaker_count,
                    f"{summary.top_speaker_share_percent:.2f}",
                )
            )


def export_word_speaker_frequency_csv(
    rows: Sequence[tuple[str, str, int]],
    output_path: str,
) -> None:
    """Write preordered word-speaker frequency rows as UTF-8 BOM CSV."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("word", "speaker", "count"))
        writer.writerows(rows)


def generate_wordcloud(
    words: list[tuple[str, int]],
    output_path: str,
    font_path: str | None = None,
) -> None:
    """Generate a PNG word cloud using an available local Chinese font."""
    frequencies = {
        word: count
        for word, count in words
        if word and count > 0
    }
    if not frequencies:
        raise ValueError("Cannot generate a word cloud without positive frequencies.")

    resolved_font = _resolve_font_path(font_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    wordcloud = WordCloud(
        font_path=str(resolved_font),
        width=1600,
        height=900,
        background_color="#EAF6FF",
        max_font_size=180,
        min_font_size=24,
        collocations=False,
        random_state=42,
    )
    wordcloud.generate_from_frequencies(frequencies)
    wordcloud.to_file(str(destination))


def generate_word_top_speakers_chart(
    summaries: Sequence[WordSpeakerSummary],
    output_path: str,
    font_path: str | None = None,
) -> None:
    """Generate a horizontal chart for the top word speakers."""
    displayed_summaries = _order_word_top_speaker_summaries(summaries)
    if not displayed_summaries:
        raise ValueError("Cannot generate a chart without summaries.")

    resolved_font = _resolve_font_path(font_path)
    font_properties = FontProperties(fname=str(resolved_font))
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    figure_height = max(6.0, len(displayed_summaries) * 0.5 + 2.5)
    figure = Figure(figsize=(16, figure_height))
    FigureCanvasAgg(figure)
    axes = figure.subplots()

    try:
        _draw_word_top_speakers_axes(
            axes,
            displayed_summaries,
            font_properties,
        )
        figure.tight_layout()
        figure.savefig(destination, dpi=120, bbox_inches="tight")
    finally:
        figure.clear()


def _order_word_top_speaker_summaries(
    summaries: Sequence[WordSpeakerSummary],
) -> list[WordSpeakerSummary]:
    selected = list(summaries[:25])
    return sorted(
        selected,
        key=lambda summary: -summary.top_speaker_share_percent,
    )


def _draw_word_top_speakers_axes(
    axes: Axes,
    summaries: Sequence[WordSpeakerSummary],
    font_properties: FontProperties,
) -> None:
    labels = [
        f"{summary.word} — {summary.top_speaker}"
        for summary in summaries
    ]
    shares = [summary.top_speaker_share_percent for summary in summaries]
    positions = list(range(len(summaries)))
    bars = axes.barh(positions, shares, color="#4A90E2")

    axes.set_yticks(positions)
    axes.set_yticklabels(labels, fontproperties=font_properties)
    axes.invert_yaxis()
    axes.set_xlim(0, 100)
    axes.xaxis.set_major_formatter(PercentFormatter(xmax=100))
    axes.set_xlabel(
        "主要发送者占该词总次数的比例（%）",
        fontproperties=font_properties,
    )
    axes.set_title(
        "高频词主要发送者占比 Top 25",
        fontproperties=font_properties,
    )
    for tick_label in axes.get_xticklabels():
        tick_label.set_fontproperties(font_properties)

    for bar, summary in zip(bars, summaries, strict=True):
        annotation = (
            f"{summary.top_speaker_count} / {summary.total_count} "
            f"({summary.top_speaker_share_percent:.2f}%)"
        )
        axes.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            annotation,
            va="center",
            clip_on=False,
            fontproperties=font_properties,
        )

    axes.grid(axis="x", linestyle="--", alpha=0.25)


def _resolve_font_path(font_path: str | None) -> Path:
    if font_path is not None:
        specified_font = Path(font_path).expanduser()
        if specified_font.is_file():
            return specified_font
        raise FileNotFoundError(
            f"The specified font file does not exist: {specified_font}"
        )

    candidates = list(_local_font_candidates())
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "No local Chinese font was found. Pass font_path explicitly. "
        f"Searched: {searched}"
    )


def _local_font_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []

    windows_directory = Path(os.environ.get("WINDIR", r"C:\Windows"))
    system_fonts = windows_directory / "Fonts"
    candidates.extend(system_fonts / name for name in _FONT_FILENAMES)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        user_fonts = Path(local_app_data) / "Microsoft" / "Windows" / "Fonts"
        candidates.extend(user_fonts / name for name in _FONT_FILENAMES)

    candidates.extend(_CROSS_PLATFORM_FONT_PATHS)
    return tuple(candidates)
