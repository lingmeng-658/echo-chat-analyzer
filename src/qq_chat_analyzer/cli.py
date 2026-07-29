"""Command-line entry point for the local QQ chat analysis pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
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
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_STOPWORD_FILES = {
    "default": "stopwords.txt",
    "topic": "stopwords_topic.txt",
    "culture": "stopwords_culture.txt",
}


@dataclass(frozen=True)
class CliConfiguration:
    """Validated CLI settings shared by simplified and legacy invocation styles."""

    input_path: Path
    output_directory: Path
    stopwords_path: Path
    font_path: str | None
    top: int


class CliUsageError(ValueError):
    """A user-facing command-line validation error."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete local analysis pipeline."""
    try:
        configuration = _parse_cli_configuration(argv)
    except CliUsageError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    except SystemExit as error:
        return int(error.code)

    if not configuration.input_path.exists():
        print(
            f"错误：输入路径不存在（找不到输入路径）："
            f"{configuration.input_path}",
            file=sys.stderr,
        )
        return 2

    json_files = _find_json_files(configuration.input_path)
    if not json_files:
        print(
            "错误：未找到可处理的 JSON 或 JSONL 文件："
            f"{configuration.input_path}",
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
            message_tokens = tokenize(
                cleaned_text,
                str(configuration.stopwords_path),
            )
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

    ranked_words = top_words(tokens, configuration.top)
    word_sender_counts = count_word_speakers(sender_tokens)
    speaker_summaries = top_word_speaker_summary(word_sender_counts)
    if not ranked_words:
        print("没有可输出的词频，不生成输出文件。")
        return 0

    output_directory = configuration.output_directory
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
            configuration.font_path,
        )
        generate_wordcloud(
            ranked_words,
            str(wordcloud_path),
            configuration.font_path,
        )
    except (OSError, ValueError) as error:
        print(f"错误：生成输出失败：{error}", file=sys.stderr)
        return 1

    print(f"Top {configuration.top} 词频:")
    for word, count in ranked_words:
        print(f"{word}\t{count}")

    return 0


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qqchat",
        description="Analyze QQChatExporter JSON and JSONL files entirely offline."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="JSON/JSONL file or directory (simplified form).",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        help="Stopwords profile: default, topic, or culture.",
    )
    parser.add_argument(
        "positional_top",
        nargs="?",
        help="Number of top words in simplified form (default: 100).",
    )
    parser.add_argument(
        "--input",
        dest="input_option",
        help="JSON/JSONL file or directory containing JSON/JSONL files.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (legacy default: output).",
    )
    parser.add_argument(
        "--stopwords",
        default=None,
        help="Explicit stopwords file; overrides the selected profile.",
    )
    parser.add_argument(
        "--font-path",
        default=None,
        help="Optional local Chinese font file.",
    )
    parser.add_argument(
        "--top",
        default=None,
        help="Number of top words to output (legacy default: 50).",
    )
    return parser


def _parse_cli_configuration(
    argv: Sequence[str] | None = None,
) -> CliConfiguration:
    arguments = _build_argument_parser().parse_args(argv)
    simplified = arguments.input_path is not None

    if simplified and arguments.input_option is not None:
        raise CliUsageError("不能同时使用位置输入路径和 --input。")
    if not simplified and arguments.input_option is None:
        raise CliUsageError("请提供输入路径，例如：qqchat PATH。")

    profile = arguments.profile or "default"
    if profile not in PROFILE_STOPWORD_FILES:
        available = ", ".join(PROFILE_STOPWORD_FILES)
        raise CliUsageError(
            f"无效 profile：{profile}。可用值：{available}。"
        )

    if arguments.positional_top is not None and arguments.top is not None:
        raise CliUsageError("不能同时使用位置 top 和 --top。")

    top_value = arguments.positional_top or arguments.top
    default_top = 100 if simplified else 50
    top = _parse_positive_top(top_value, default_top)

    input_path = Path(arguments.input_path or arguments.input_option)
    if arguments.output_dir is not None:
        output_directory = Path(arguments.output_dir)
    elif simplified:
        output_directory = _automatic_output_directory(input_path)
    else:
        output_directory = Path("output")

    if arguments.stopwords is not None:
        stopwords_path = Path(arguments.stopwords)
    elif not simplified:
        stopwords_path = Path("stopwords.txt")
    else:
        stopwords_path = PROJECT_ROOT / PROFILE_STOPWORD_FILES[profile]

    return CliConfiguration(
        input_path=input_path,
        output_directory=output_directory,
        stopwords_path=stopwords_path,
        font_path=arguments.font_path,
        top=top,
    )


def _parse_positive_top(value: str | None, default: int) -> int:
    if value is None:
        return default

    try:
        top = int(value)
    except ValueError as error:
        raise CliUsageError(
            f"top 必须是大于 0 的整数，收到：{value}。"
        ) from error

    if top <= 0:
        raise CliUsageError(f"top 必须是大于 0 的整数，收到：{value}。")
    return top


def _automatic_output_directory(input_path: Path) -> Path:
    if input_path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
        input_name = input_path.stem.strip()
    else:
        input_name = input_path.name.strip()
    if input_name in {"", ".", ".."}:
        input_name = "analysis"
    return Path("output") / input_name


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
