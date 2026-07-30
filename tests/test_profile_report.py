"""Tests for the local Smart Profile acceptance report."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from scripts.profile_report import collect_profile_statistics, main


def test_profile_report_counts_cross_file_smart_profile_results(
    tmp_path: Path,
) -> None:
    input_directory = _write_fictional_export(tmp_path)

    report = collect_profile_statistics(input_directory)

    assert report.input_file_count == 2
    assert report.raw_message_count == 38
    assert report.parsed_message_count == 38
    assert report.robot_sender_candidate_count == 1
    assert report.template_candidate_count == 2
    assert report.welcome_template_candidate_count == 1
    assert report.repeated_template_candidate_count == 1
    assert report.unknown_template_candidate_count == 0
    assert report.filter_decision_count == 3
    assert report.ignore_count == 2
    assert report.review_count == 1
    assert report.filtered_message_count == 34
    assert report.kept_message_count == 4


def test_profile_report_output_contains_only_aggregate_statistics(
    tmp_path: Path,
    capsys,
) -> None:
    input_directory = _write_fictional_export(tmp_path)

    exit_code = main([str(input_directory)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "输入文件数量: 2" in captured.out
    assert "原始消息数量: 38" in captured.out
    assert "ParsedMessage 数量: 38" in captured.out
    assert "robot_sender candidate 数量: 1" in captured.out
    assert "template candidate 数量: 2" in captured.out
    assert "Template Candidate:" in captured.out
    assert "welcome_template: 1" in captured.out
    assert "repeated_template: 1" in captured.out
    assert "unknown: 0" in captured.out
    assert "FilterDecision 数量: 3" in captured.out
    assert "ignore 数量: 2" in captured.out
    assert "review 数量: 1" in captured.out
    assert "filtered_messages 数量: 34" in captured.out
    assert "kept_messages 数量: 4" in captured.out

    forbidden_values = [
        "虚构自动播报器",
        "绝密虚构播报正文",
        "虚构欢迎助手",
        "欢迎 虚构成员甲 加入群聊",
        "虚构积分助手",
        "签到成功，积分+10",
        "签到成功，积分+{variable}",
        "虚构普通用户",
        "仅用于验收的正常消息",
    ]
    for value in forbidden_values:
        assert value not in captured.out
        assert value not in captured.err


def _write_fictional_export(tmp_path: Path) -> Path:
    input_directory = tmp_path / "fictional-export"
    chunks_directory = input_directory / "chunks"
    chunks_directory.mkdir(parents=True)

    robot_messages = [
        {
            "timestamp": 1767318000 + index,
            "sender": {"nickname": "虚构自动播报器"},
            "type": "text",
            "content": {"text": "绝密虚构播报正文"},
        }
        for index in range(30)
    ]
    (input_directory / "messages.json").write_text(
        json.dumps({"messages": robot_messages}, ensure_ascii=False),
        encoding="utf-8",
    )

    jsonl_messages = [
        {
            "timestamp": 1767318030 + index,
            "sender": {"nickname": "虚构欢迎助手"},
            "type": "text",
            "content": {"text": f"欢迎 虚构成员{member} 加入群聊"},
        }
        for index, member in enumerate(("甲", "乙", "丙", "丁"))
    ]
    jsonl_messages.extend(
        {
            "timestamp": 1767318034 + index,
            "sender": {"nickname": "虚构积分助手"},
            "type": "text",
            "content": {"text": f"签到成功，积分+{points}"},
        }
        for index, points in enumerate((10, 20, 30))
    )
    jsonl_messages.append(
        {
            "timestamp": 1767318037,
            "sender": {"nickname": "虚构普通用户"},
            "type": "text",
            "content": {"text": "仅用于验收的正常消息"},
        }
    )
    (chunks_directory / "messages.jsonl").write_text(
        "\n".join(
            json.dumps(message, ensure_ascii=False)
            for message in jsonl_messages
        ),
        encoding="utf-8",
    )

    return input_directory
