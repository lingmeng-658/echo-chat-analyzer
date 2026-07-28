"""Command-line entry point for the local QQ chat analysis pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .analyzer import (
    count_word_speakers,
    top_word_speaker_summary,
    top_words,
)
from .cleaner import clean_text
from .exporters import (
    export_word_frequency_csv,
    export_word_speaker_frequency_csv,
    export_word_speaker_summary_csv,
    generate_word_top_speakers_chart,
    generate_wordcloud,
)
from .parser import load_messages, parse_messages
from .tokenizer import tokenize


SUPPORTED_INPUT_SUFFIXES = frozenset({".json", ".jsonl"})


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete local analysis pipeline."""
    arguments = _build_argument_parser().parse_args(argv)
    input_path = Path(arguments.input)

    if not input_path.exists():
        print(f"错误：输入路径不存在：{input_path}", file=sys.stderr)
        return 2
    if arguments.top <= 0:
        print("错误：--top 必须是大于 0 的整数。", file=sys.stderr)
        return 2

    json_files = _find_json_files(input_path)
    if not json_files:
        print(
            f"错误：未找到可处理的 JSON 或 JSONL 文件：{input_path}",
            file=sys.stderr,
        )
        return 2

    processed_message_count = 0
    valid_text_count = 0
    tokens: list[str] = []
    sender_tokens: list[tuple[str, list[str]]] = []

    for json_path in json_files:
        raw_messages = load_messages(json_path)
        processed_message_count += len(raw_messages)

        for message in parse_messages(raw_messages):
            cleaned_text = clean_text(message.text)
            if not cleaned_text:
                continue

            valid_text_count += 1
            message_tokens = tokenize(cleaned_text, arguments.stopwords)
            tokens.extend(message_tokens)
            if message_tokens:
                sender_tokens.append((message.sender, message_tokens))

    print(f"处理消息数量: {processed_message_count}")
    print(f"有效文本数量: {valid_text_count}")

    if valid_text_count == 0:
        print("没有有效文本，不生成输出文件。")
        return 0
    if not tokens:
        print("有效文本未产生可统计词语，不生成输出文件。")
        return 0

    ranked_words = top_words(tokens, arguments.top)
    word_sender_counts = count_word_speakers(sender_tokens)
    speaker_summaries = top_word_speaker_summary(word_sender_counts)
    if not ranked_words:
        print("没有可输出的词频，不生成输出文件。")
        return 0

    output_directory = Path(arguments.output_dir)
    csv_path = output_directory / "word_frequency.csv"
    wordcloud_path = output_directory / "wordcloud.png"
    speaker_summary_path = output_directory / "word_speaker_summary.csv"
    speaker_frequency_path = output_directory / "word_speaker_frequency.csv"
    speaker_chart_path = output_directory / "word_top_speakers.png"
    speaker_frequency_rows = [
        (summary.word, sender, count)
        for summary in speaker_summaries
        for sender, count in sorted(
            word_sender_counts[summary.word].items(),
            key=lambda item: -item[1],
        )
    ]

    try:
        export_word_frequency_csv(ranked_words, str(csv_path))
        export_word_speaker_summary_csv(
            speaker_summaries,
            str(speaker_summary_path),
        )
        export_word_speaker_frequency_csv(
            speaker_frequency_rows,
            str(speaker_frequency_path),
        )
        generate_word_top_speakers_chart(
            speaker_summaries,
            str(speaker_chart_path),
            arguments.font_path,
        )
        generate_wordcloud(
            ranked_words,
            str(wordcloud_path),
            arguments.font_path,
        )
    except (OSError, ValueError) as error:
        print(f"错误：生成输出失败：{error}", file=sys.stderr)
        return 1

    print(f"Top {arguments.top} 词频:")
    for word, count in ranked_words:
        print(f"{word}\t{count}")

    return 0


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze QQChatExporter JSON and JSONL files entirely offline."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="JSON/JSONL file or directory containing JSON/JSONL files.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Output directory (default: output).",
    )
    parser.add_argument(
        "--stopwords",
        default="stopwords.txt",
        help="Stopwords file (default: stopwords.txt).",
    )
    parser.add_argument(
        "--font-path",
        default=None,
        help="Optional local Chinese font file.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Number of top words to output (default: 50).",
    )
    return parser


def _find_json_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
            return [input_path]
        return []
    if not input_path.is_dir():
        return []

    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )


if __name__ == "__main__":
    raise SystemExit(main())
