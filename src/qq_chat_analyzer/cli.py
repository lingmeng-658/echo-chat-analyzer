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
    ApplicationServiceError,
    ArtifactGenerationFailed,
    InputPathNotFound,
    InvalidAnalysisRequest,
    NoSupportedInput,
    QQExportImportRequest,
    QQExportImportService,
)
from .application.analysis_service import AnalysisApplicationService
from .resources import resource_path


SUPPORTED_INPUT_SUFFIXES = frozenset({".json", ".jsonl"})
QCE_COMMAND = "qce"
QCE_SUBCOMMANDS = ("list", "analyze")
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
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == QCE_COMMAND:
        return _run_qce_command(arguments[1:])

    try:
        configuration = _parse_cli_configuration(arguments)
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
        stopwords_path = resource_path(PROFILE_STOPWORD_FILES[profile])

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




# ------------------------------------------------------------------ qce commands


def _build_qce_service() -> QQExportImportService:
    """Build the QCE application service.

    Isolated in one function so tests can substitute a stub-backed service
    without touching a real QCE instance. Importing the provider lazily keeps
    the default CLI path free of provider import cost.
    """
    from .providers import QQChatExporterProvider

    return QQExportImportService(QQChatExporterProvider())


def _run_qce_command(arguments: list[str]) -> int:
    """Dispatch the ``qce`` sub-commands ahead of the legacy parser."""
    if not arguments:
        print(_qce_usage_message(), file=sys.stderr)
        return 2

    subcommand, rest = arguments[0], arguments[1:]
    if subcommand == "list":
        return _run_qce_list(rest)
    if subcommand == "analyze":
        return _run_qce_analyze(rest)

    print(
        f"\u9519\u8bef\uff1a\u672a\u77e5\u7684 qce \u5b50\u547d\u4ee4 {subcommand!r}\u3002",
        file=sys.stderr,
    )
    print(_qce_usage_message(), file=sys.stderr)
    return 2


def _qce_usage_message() -> str:
    return "\u7528\u6cd5\uff1aqqchat qce {list|analyze --group <group_code>}"


def _run_qce_list(arguments: list[str]) -> int:
    """Print the groups the local QCE service can export."""
    if arguments:
        print(
            "\u9519\u8bef\uff1aqce list \u4e0d\u63a5\u53d7\u989d\u5916\u53c2\u6570\u3002",
            file=sys.stderr,
        )
        return 2

    try:
        groups = _build_qce_service().list_groups()
    except ApplicationServiceError as error:
        return _report_qce_error(error)

    if not groups:
        print("\u672a\u627e\u5230\u53ef\u5bfc\u51fa\u7684\u7fa4\u804a\u3002")
        return 0

    print(f"\u5171 {len(groups)} \u4e2a\u7fa4\u804a\uff1a")
    for group in groups:
        code = getattr(group, "group_code", "")
        name = getattr(group, "group_name", "") or "(\u672a\u547d\u540d)"
        member_count = getattr(group, "member_count", None)
        if member_count is None:
            print(f"  {code}  {name}")
        else:
            print(f"  {code}  {name}  ({member_count} \u4eba)")
    return 0


def _run_qce_analyze(arguments: list[str]) -> int:
    """Export one group through QCE and analyse the resulting JSON."""
    parser = argparse.ArgumentParser(
        prog="qqchat qce analyze",
        description="\u5bfc\u51fa\u5e76\u5206\u6790\u4e00\u4e2a QQ \u7fa4\u804a\u3002",
        add_help=False,
    )
    parser.add_argument("--group", dest="group_code")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--profile", dest="profile", default="default")
    known, unknown = parser.parse_known_args(arguments)
    if unknown:
        print(
            f"\u9519\u8bef\uff1a\u4e0d\u8ba4\u8bc6\u7684\u53c2\u6570 {unknown[0]!r}\u3002",
            file=sys.stderr,
        )
        return 2

    group_code = (known.group_code or """""").strip()
    if not group_code:
        print(
            "\u9519\u8bef\uff1a\u7f3a\u5c11 --group \u53c2\u6570\uff0c"
            "\u8bf7\u5148\u8fd0\u884c qqchat qce list \u67e5\u770b\u7fa4\u53f7\u3002",
            file=sys.stderr,
        )
        return 2

    try:
        export_path = _build_qce_service().export_only(
            QQExportImportRequest(group_code=group_code, force_refresh=True)
        )
    except ApplicationServiceError as error:
        return _report_qce_error(error)

    print(f"\u5df2\u5bfc\u51fa\uff1a{export_path}")

    forwarded = [str(export_path)]
    if known.profile:
        forwarded.append(known.profile)
    if known.output_dir:
        forwarded += ["--output-dir", known.output_dir]
    return main(forwarded)


def _report_qce_error(error: ApplicationServiceError) -> int:
    """Render an application-layer failure as a Chinese CLI message.

    Provider and orchestration errors already carry a user-facing message, so
    the CLI only prefixes it and maps everything to a single exit status.
    """
    message = getattr(error, "public_message", "") or str(error)
    print(f"\u9519\u8bef\uff1a{message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
