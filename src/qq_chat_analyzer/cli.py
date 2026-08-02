"""Command-line entry point for the local QQ chat analysis pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .application import (
    AnalysisRequestDTO,
    AnalysisStatus,
    ArtifactGenerationFailed,
    InputPathNotFound,
    InvalidAnalysisRequest,
    NoSupportedInput,
)
from .application.analysis_service import AnalysisApplicationService


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


class ChineseArgumentParser(argparse.ArgumentParser):
    """Render argparse's fixed help headings in Chinese."""

    def format_help(self) -> str:
        help_text = super().format_help()
        if help_text.startswith("usage: "):
            _, _, help_text = help_text.partition("\n\n")
        return (
            help_text.replace("位置参数:", "位置参数：")
            .replace("选项:", "选项：")
            .replace("高级参数:", "高级参数：")
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Adapt command-line input and output to the application service."""
    try:
        configuration = _parse_cli_configuration(argv)
    except CliUsageError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    except SystemExit as error:
        return int(error.code)

    request = AnalysisRequestDTO(
        input_path=configuration.input_path,
        output_directory=configuration.output_directory,
        stopwords_path=configuration.stopwords_path,
        font_path=configuration.font_path,
        top=configuration.top,
    )

    try:
        result = AnalysisApplicationService().execute(request)
    except InputPathNotFound:
        print("错误：输入路径不存在。", file=sys.stderr)
        return 2
    except NoSupportedInput:
        print("错误：未找到可处理的 JSON 或 JSONL 文件。", file=sys.stderr)
        return 2
    except InvalidAnalysisRequest:
        print("错误：分析请求无效。", file=sys.stderr)
        return 2
    except ArtifactGenerationFailed:
        print("错误：生成输出失败。", file=sys.stderr)
        return 1

    print(f"处理消息数量: {result.processed_message_count}")
    print(f"有效文本数量: {result.valid_text_count}")

    if result.status is AnalysisStatus.NO_VALID_TEXT:
        print("没有有效文本，不生成输出文件。")
        return 0
    if result.status is AnalysisStatus.NO_TOKENS:
        print("有效文本未产生可统计词语，不生成输出文件。")
        return 0

    print(f"Top {configuration.top} 词频:")
    for word_frequency in result.top_words:
        print(f"{word_frequency.word}\t{word_frequency.count}")

    return 0


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = ChineseArgumentParser(
        prog="qqchat",
        description="""\
QQ Chat Analyzer
本地 QQ 聊天记录分析工具。

用于分析 QQChatExporter 导出的 JSON/JSONL 聊天记录。
所有聊天记录只在本地处理，不会上传。

最简单使用
  qqchat "聊天记录路径"

例如：
  qqchat "C:\\Users\\你的用户名\\Documents\\QQChatExporter\\exports\\group_xxx"

默认行为
  直接运行上述命令时，默认：
  - 使用 default 默认过滤模式；
  - 生成前 100 个高频词；
  - 输出到 output/<聊天记录名称>/；
  - 自动生成词云、高频词统计、发送者分析等结果。

更多用法
  修改生成词数量：

  格式：
    qqchat "聊天记录路径" 过滤模式 数量

  示例：
    qqchat "C:\\xxx\\group_xxx" default 200

过滤模式
  default：默认模式
  topic：主题讨论模式
  culture：群聊文化模式

多功能组合
  qqchat "C:\\xxx\\group_xxx" culture 200

  同时：
  - 使用 culture 模式；
  - 生成前 200 个高频词；
  - 输出完整分析结果。
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser._positionals.title = "位置参数"
    parser._optionals.title = "高级参数"
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="显示帮助并退出。",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        metavar="聊天记录位置",
        help="JSON/JSONL 文件或包含这些文件的目录（简化形式）。",
    )
    parser.add_argument(
        "profile",
        nargs="?",
        metavar="过滤模式",
        help="停用词策略：default、topic 或 culture。",
    )
    parser.add_argument(
        "positional_top",
        nargs="?",
        metavar="生成词数量",
        help="输出高频词数量（简化形式默认：100）。",
    )
    parser.add_argument(
        "--input",
        dest="input_option",
        metavar="聊天记录位置",
        help="指定聊天记录位置。",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="输出目录",
        help="指定输出目录。",
    )
    parser.add_argument(
        "--stopwords",
        default=None,
        metavar="停用词文件",
        help="指定停用词文件。",
    )
    parser.add_argument(
        "--font-path",
        default=None,
        metavar="字体文件",
        help="指定中文字体文件。",
    )
    parser.add_argument(
        "--top",
        default=None,
        metavar="生成词数量",
        help="指定高频词数量。",
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


if __name__ == "__main__":
    raise SystemExit(main())
