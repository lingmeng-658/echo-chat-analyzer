"""Export analyzed word frequencies to local files."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from wordcloud import WordCloud


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
