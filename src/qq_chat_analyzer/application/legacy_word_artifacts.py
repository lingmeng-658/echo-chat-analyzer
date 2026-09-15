"""Legacy CSV and chart artifacts for the command-line entry point.

Echo's desktop report consumes only ``echo-report.json`` and
``echo-report.html``, so the pre-Echo outputs (word-frequency CSVs, the word
cloud and the top-speaker chart) are produced for the legacy CLI only.

This module is deliberately kept out of the desktop import graph: it is the
only application-layer module that imports :mod:`qq_chat_analyzer.exporters`,
which in turn pulls in matplotlib, wordcloud, Pillow, pandas and numpy.
``cli.py`` imports it; the GUI and the facade never do.
"""

from __future__ import annotations

from pathlib import Path

from ..analyzer import WordSpeakerSummary
from ..exporters import (
    export_word_frequency_csv,
    export_word_speaker_frequency_csv,
    export_word_speaker_summary_csv,
    generate_word_top_speakers_chart,
    generate_wordcloud,
)
from .dto import ArtifactDTO


LEGACY_ARTIFACT_FILENAMES = {
    "word_frequency_csv": "word_frequency.csv",
    "wordcloud": "wordcloud.png",
    "word_speaker_summary_csv": "word_speaker_summary.csv",
    "word_speaker_frequency_csv": "word_speaker_frequency.csv",
    "word_top_speakers_chart": "word_top_speakers.png",
}
LEGACY_ARTIFACTS: tuple[ArtifactDTO, ...] = tuple(
    ArtifactDTO(kind=kind, filename=filename)
    for kind, filename in LEGACY_ARTIFACT_FILENAMES.items()
)


def write_legacy_word_artifacts(
    *,
    output_directory: Path,
    ranked_words: list[tuple[str, int]],
    speaker_summaries: list[WordSpeakerSummary],
    speaker_frequency_rows: list[tuple[str, str, int]],
    font_path: str | None,
) -> tuple[ArtifactDTO, ...]:
    """Write every legacy CLI artifact into ``output_directory``.

    Font resolution and chart rendering failures stay ``OSError``/``ValueError``
    so the calling service can translate them into one safe application error.
    """
    export_word_frequency_csv(
        ranked_words,
        str(
            output_directory
            / LEGACY_ARTIFACT_FILENAMES["word_frequency_csv"]
        ),
    )
    export_word_speaker_summary_csv(
        speaker_summaries,
        str(
            output_directory
            / LEGACY_ARTIFACT_FILENAMES["word_speaker_summary_csv"]
        ),
    )
    export_word_speaker_frequency_csv(
        speaker_frequency_rows,
        str(
            output_directory
            / LEGACY_ARTIFACT_FILENAMES["word_speaker_frequency_csv"]
        ),
    )
    generate_word_top_speakers_chart(
        speaker_summaries,
        str(
            output_directory
            / LEGACY_ARTIFACT_FILENAMES["word_top_speakers_chart"]
        ),
        font_path,
    )
    generate_wordcloud(
        ranked_words,
        str(output_directory / LEGACY_ARTIFACT_FILENAMES["wordcloud"]),
        font_path,
    )
    return LEGACY_ARTIFACTS


__all__ = [
    "LEGACY_ARTIFACT_FILENAMES",
    "LEGACY_ARTIFACTS",
    "write_legacy_word_artifacts",
]
