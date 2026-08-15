"""Behavior tests for packaging completed Echo report artifacts."""

from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path

import pytest


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.echo_report_export"
    )


def _output_directory(tmp_path: Path) -> Path:
    output = tmp_path / "generated-output"
    output.mkdir()
    (output / "echo-report.html").write_text(
        "<html>fictional echo report</html>",
        encoding="utf-8",
    )
    (output / "echo-report.json").write_text(
        '{"schema_version": "echo-report.v0.7"}',
        encoding="utf-8",
    )
    (output / "raw-chat-export.json").write_text(
        '{"messages": [{"text": "fictional raw chat"}]}',
        encoding="utf-8",
    )
    return output


def test_package_creates_echo_report_directory_with_expected_files(
    tmp_path: Path,
) -> None:
    module = _module()
    output = _output_directory(tmp_path)
    reports_root = tmp_path / "reports"

    target = module.package_echo_report(
        output,
        reports_root,
        now=datetime(2026, 8, 15, 14, 30, 12),
    )

    assert target == reports_root / "Echo_Report_20260815_143012"
    assert target.is_dir()
    assert (target / "echo-report.html").is_file()
    assert (target / "echo-report.json").is_file()
    assert (target / "README.txt").is_file()


def test_package_never_copies_raw_chat_data(tmp_path: Path) -> None:
    module = _module()
    output = _output_directory(tmp_path)

    target = module.package_echo_report(
        output,
        tmp_path / "reports",
        now=datetime(2026, 8, 15, 14, 30, 12),
    )

    names = {path.name for path in target.iterdir()}
    assert names == {"echo-report.html", "echo-report.json", "README.txt"}
    assert "raw-chat-export.json" not in names


def test_readme_explains_the_report_and_local_processing(tmp_path: Path) -> None:
    module = _module()
    output = _output_directory(tmp_path)

    target = module.package_echo_report(
        output,
        tmp_path / "reports",
        now=datetime(2026, 8, 15, 14, 30, 12),
    )

    readme = (target / "README.txt").read_text(encoding="utf-8")
    assert "这是 Echo 生成的聊天分析报告" in readme
    assert "本机处理" in readme
    assert "直接用浏览器打开即可查看" in readme
    assert "不包含原始聊天数据" in readme


def test_package_appends_suffix_when_timestamp_directory_exists(
    tmp_path: Path,
) -> None:
    module = _module()
    output = _output_directory(tmp_path)
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    (reports_root / "Echo_Report_20260815_143012").mkdir()

    target = module.package_echo_report(
        output,
        reports_root,
        now=datetime(2026, 8, 15, 14, 30, 12),
    )

    assert target == reports_root / "Echo_Report_20260815_143012_2"
    assert target.is_dir()


def test_package_requires_the_echo_html_artifact(tmp_path: Path) -> None:
    module = _module()
    output = tmp_path / "generated-output"
    output.mkdir()
    (output / "echo-report.json").write_text("{}", encoding="utf-8")

    with pytest.raises(module.EchoReportExportError):
        module.package_echo_report(output, tmp_path / "reports")

