"""Package completed Echo report artifacts into a shareable directory."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from ..resources import user_data_dir


ECHO_REPORT_DIRECTORY_PREFIX = "Echo_Report_"
ECHO_REPORT_HTML_NAME = "echo-report.html"
ECHO_REPORT_JSON_NAME = "echo-report.json"
ECHO_REPORT_README_NAME = "README.txt"

ECHO_REPORT_README = """\
Echo 聊天分析报告
=================

这是 Echo 生成的聊天分析报告。

隐私说明：所有数据均在本机处理，不会上传到网络。

文件说明：
- echo-report.html：报告页面，直接用浏览器打开即可查看。
- echo-report.json：报告的结构化数据，可供其他工具阅读。

本目录只包含分析结果，不包含原始聊天数据。
"""


class EchoReportExportError(RuntimeError):
    """Raised when the Echo report directory cannot be packaged."""


def package_echo_report(
    output_directory: Path,
    reports_root: Path | None = None,
    *,
    now: datetime | None = None,
) -> Path:
    """Copy Echo artifacts into one timestamped export directory.

    Only ``echo-report.html``, ``echo-report.json``, and ``README.txt`` are
    written. Intermediate export files that may contain raw chat data are
    never copied.
    """
    source_html = Path(output_directory) / ECHO_REPORT_HTML_NAME
    source_json = Path(output_directory) / ECHO_REPORT_JSON_NAME
    if not source_html.is_file():
        raise EchoReportExportError("Echo report HTML is missing.")

    root = Path(reports_root) if reports_root is not None else user_data_dir() / "reports"
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    target = _next_report_directory(root, stamp)
    target.mkdir(parents=True, exist_ok=False)

    try:
        shutil.copy2(source_html, target / ECHO_REPORT_HTML_NAME)
        if source_json.is_file():
            shutil.copy2(source_json, target / ECHO_REPORT_JSON_NAME)
        (target / ECHO_REPORT_README_NAME).write_text(
            ECHO_REPORT_README,
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _next_report_directory(root: Path, stamp: str) -> Path:
    candidate = root / f"{ECHO_REPORT_DIRECTORY_PREFIX}{stamp}"
    suffix = 2
    while candidate.exists():
        candidate = root / f"{ECHO_REPORT_DIRECTORY_PREFIX}{stamp}_{suffix}"
        suffix += 1
    return candidate


__all__ = [
    "ECHO_REPORT_DIRECTORY_PREFIX",
    "ECHO_REPORT_HTML_NAME",
    "ECHO_REPORT_JSON_NAME",
    "ECHO_REPORT_README_NAME",
    "EchoReportExportError",
    "package_echo_report",
]
