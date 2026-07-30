"""Print aggregate Smart Profile statistics for local acceptance checks."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.decision_engine import create_filter_decisions
from qq_chat_analyzer.detectors import (
    detect_robot_candidates,
    detect_template_candidates,
)
from qq_chat_analyzer.parser import (
    ParsedMessage,
    load_messages,
    parse_messages,
)
from qq_chat_analyzer.smart_profile import run_smart_profile


SUPPORTED_INPUT_SUFFIXES = frozenset({".json", ".jsonl"})


@dataclass(frozen=True, slots=True)
class ProfileReport:
    """Aggregate counts that do not expose chat content or identities."""

    input_file_count: int
    raw_message_count: int
    parsed_message_count: int
    robot_sender_candidate_count: int
    template_candidate_count: int
    welcome_template_candidate_count: int
    repeated_template_candidate_count: int
    unknown_template_candidate_count: int
    filter_decision_count: int
    ignore_count: int
    review_count: int
    filtered_message_count: int
    kept_message_count: int


def collect_profile_statistics(
    input_path: str | Path,
) -> ProfileReport:
    """Collect aggregate Smart Profile statistics from local exports."""
    input_files = _find_input_files(Path(input_path))
    if not input_files:
        raise ValueError("No supported input files were found.")

    raw_message_count = 0
    parsed_messages: list[ParsedMessage] = []
    for path in input_files:
        raw_messages = load_messages(path)
        raw_message_count += len(raw_messages)
        parsed_messages.extend(parse_messages(raw_messages))

    robot_candidates = detect_robot_candidates(parsed_messages)
    template_candidates = detect_template_candidates(parsed_messages)
    welcome_template_candidate_count = sum(
        candidate.candidate_type == "welcome_template"
        for candidate in template_candidates
    )
    repeated_template_candidate_count = sum(
        candidate.candidate_type == "repeated_template"
        for candidate in template_candidates
    )
    unknown_template_candidate_count = (
        len(template_candidates)
        - welcome_template_candidate_count
        - repeated_template_candidate_count
    )
    decisions = create_filter_decisions(
        [*robot_candidates, *template_candidates]
    )
    filtering_result = run_smart_profile(parsed_messages)

    return ProfileReport(
        input_file_count=len(input_files),
        raw_message_count=raw_message_count,
        parsed_message_count=len(parsed_messages),
        robot_sender_candidate_count=len(robot_candidates),
        template_candidate_count=len(template_candidates),
        welcome_template_candidate_count=welcome_template_candidate_count,
        repeated_template_candidate_count=(
            repeated_template_candidate_count
        ),
        unknown_template_candidate_count=(
            unknown_template_candidate_count
        ),
        filter_decision_count=len(decisions),
        ignore_count=sum(
            decision.action == "ignore"
            for decision in decisions
        ),
        review_count=sum(
            decision.action == "review"
            for decision in decisions
        ),
        filtered_message_count=len(filtering_result.filtered_messages),
        kept_message_count=len(filtering_result.kept_messages),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local aggregate report without exposing chat values."""
    parser = argparse.ArgumentParser(
        description="Smart Profile 本地验收统计报告",
    )
    parser.add_argument(
        "input_path",
        metavar="聊天记录位置",
        help="QQChatExporter JSON/JSONL 文件或目录。",
    )
    arguments = parser.parse_args(argv)

    try:
        report = collect_profile_statistics(arguments.input_path)
    except (OSError, TypeError, ValueError):
        print(
            "错误：未找到可处理的 JSON 或 JSONL 输入。",
            file=sys.stderr,
        )
        return 2

    _print_report(report)
    return 0


def _find_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
            return [input_path]
        return []
    if not input_path.is_dir():
        return []

    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )


def _print_report(report: ProfileReport) -> None:
    print(f"输入文件数量: {report.input_file_count}")
    print(f"原始消息数量: {report.raw_message_count}")
    print(f"ParsedMessage 数量: {report.parsed_message_count}")
    print(
        "robot_sender candidate 数量: "
        f"{report.robot_sender_candidate_count}"
    )
    print(
        "template candidate 数量: "
        f"{report.template_candidate_count}"
    )
    print("Template Candidate:")
    print(
        "welcome_template: "
        f"{report.welcome_template_candidate_count}"
    )
    print(
        "repeated_template: "
        f"{report.repeated_template_candidate_count}"
    )
    print(f"unknown: {report.unknown_template_candidate_count}")
    print(f"FilterDecision 数量: {report.filter_decision_count}")
    print(f"ignore 数量: {report.ignore_count}")
    print(f"review 数量: {report.review_count}")
    print(
        "filtered_messages 数量: "
        f"{report.filtered_message_count}"
    )
    print(f"kept_messages 数量: {report.kept_message_count}")


if __name__ == "__main__":
    raise SystemExit(main())
