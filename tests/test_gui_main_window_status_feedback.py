"""User-visible feedback for report and share actions on the main window.

The main window owns one header status line. These tests pin the contract the
0.1 release audit found broken: status copy written by report and share actions
must actually reach the user, and a failed action must be announced instead of
only being logged.

All data here is fictional; no real chat records, databases, or network calls
are involved.
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

from qq_chat_analyzer.application.facade import FacadeError

from test_gui import (  # noqa: F401  (qt_app/sources are fixtures re-exported here)
    StubFacade,
    _StubOutcome,
    _dashboard_view,
    _main_window,
    qt_app,
    sources,
)


def _module():
    return importlib.import_module("qq_chat_analyzer.gui.main_window")


def _record_warnings(monkeypatch) -> list[tuple[str, str]]:
    """Capture the modal failure announcements instead of blocking on them."""
    module = _module()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module.QMessageBox,
        "warning",
        lambda _parent, title, message: calls.append((title, message)),
    )
    return calls


def _fictional_report(tmp_path: Path) -> Path:
    path = tmp_path / "fictional-echo-report.html"
    path.write_text("<html>fictional report</html>", encoding="utf-8")
    return path


def test_analysis_completion_status_is_visible(qt_app, sources, tmp_path) -> None:
    """A finished analysis must show its saved-report copy to the user."""
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )

    assert window._status_label.text() == "报告已保存"
    assert window._status_label.isVisibleTo(window) is True


def test_analysis_completion_without_saved_report_status_is_visible(
    qt_app, sources, tmp_path
) -> None:
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report))

    assert window._status_label.text() == "分析完成，报告暂未保存。"
    assert window._status_label.isVisibleTo(window) is True


def test_share_success_status_is_visible(qt_app, sources, tmp_path) -> None:
    report = _fictional_report(tmp_path)
    share = tmp_path / "fictional-share.png"
    share.write_bytes(b"fictional-share-image")
    window = _main_window(
        qt_app, StubFacade(sources=sources, share_image_path=share)
    )
    window._report_opener = lambda path: True
    window._image_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert window._status_label.text() == "分享图片已生成"
    assert window._status_label.isVisibleTo(window) is True


def test_share_failure_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    """A generation failure must be visible and announced, not only logged."""
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    facade = StubFacade(
        sources=sources,
        share_image_error=FacadeError(
            code="share_image_generation_failed",
            public_message="分享图片生成失败，请稍后重试。",
        ),
    )
    window = _main_window(qt_app, facade)
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert window._status_label.text() == "分享图片生成失败，请稍后重试。"
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == "分享图片生成失败，请稍后重试。"


def test_share_without_outcome_is_visible_and_announced(
    qt_app, sources, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.generate_share_image()

    assert window._status_label.text() == "暂时没有可生成分享图片的分析结果。"
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == "暂时没有可生成分享图片的分析结果。"


def test_share_submit_failure_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)

    def _failing_executor(*args, **kwargs):
        raise RuntimeError("fictional executor failure")

    window = _main_window(
        qt_app, StubFacade(sources=sources), executor=_failing_executor
    )
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert window._status_label.text() == "分享图片生成失败，请稍后重试。"
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == "分享图片生成失败，请稍后重试。"


def test_share_image_generated_but_missing_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    """Generation "succeeded" but the file is gone: the user must be told."""
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    missing_share = tmp_path / "fictional-share.png"
    opened: list[Path] = []
    window = _main_window(
        qt_app, StubFacade(sources=sources, share_image_path=missing_share)
    )
    window._report_opener = lambda path: True
    window._image_opener = lambda path: opened.append(path) or True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert opened == []
    assert window._status_label.text() != "分享图片已生成"
    assert "分享图片" in window._status_label.text()
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == window._status_label.text()


def test_share_image_generated_but_unopenable_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    share = tmp_path / "fictional-share.png"
    share.write_bytes(b"fictional-share-image")
    window = _main_window(
        qt_app, StubFacade(sources=sources, share_image_path=share)
    )
    window._report_opener = lambda path: True
    window._image_opener = lambda path: False

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert window._status_label.text() != "分享图片已生成"
    assert "分享图片" in window._status_label.text()
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == window._status_label.text()


def test_share_image_opener_exception_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    share = tmp_path / "fictional-share.png"
    share.write_bytes(b"fictional-share-image")

    def _raising_opener(path):
        raise OSError("fictional image open failure")

    window = _main_window(
        qt_app, StubFacade(sources=sources, share_image_path=share)
    )
    window._report_opener = lambda path: True
    window._image_opener = _raising_opener

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window._generate_share_button.click()

    assert window._status_label.text() != "分享图片已生成"
    assert "分享图片" in window._status_label.text()
    assert window._status_label.isVisibleTo(window) is True
    assert warnings[-1][1] == window._status_label.text()


def test_report_open_failure_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: False

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    window.open_echo_report()

    assert "无法打开" in window._status_label.text()
    assert window._status_label.isVisibleTo(window) is True
    assert "无法打开" in warnings[-1][1]


def test_report_directory_open_failure_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report_directory = tmp_path / "Echo_Report_20260815_143012"
    report_directory.mkdir()
    report_path = report_directory / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")

    def _failing_directory_opener(path):
        raise OSError("fictional directory open failure")

    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True
    window._directory_opener = _failing_directory_opener

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report_path,
            report_directory=report_directory,
        )
    )
    window.open_echo_report_directory()

    assert "无法打开报告目录" in window._status_label.text()
    assert window._status_label.isVisibleTo(window) is True
    assert "无法打开报告目录" in warnings[-1][1]


def test_status_feedback_is_cleared_when_leaving_for_home(
    qt_app, sources, tmp_path
) -> None:
    """Navigating away must not leave a stale action message on the header."""
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    assert window._status_label.isVisibleTo(window) is True

    window.show_home_page()

    assert window._status_label.isVisibleTo(window) is False


def test_cancelled_analysis_status_is_visible(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._active_source = "qq"

    window.cancel_analysis()

    assert window._status_label.text() == "分析已取消。"
    assert window._status_label.isVisibleTo(window) is True


def test_connection_status_does_not_overwrite_visible_feedback(
    qt_app, sources, tmp_path
) -> None:
    """A visible report/share feedback line owns the header until navigation.

    The workspace already prints its own connection copy, so a later
    ``show_status`` must neither replace the feedback nor add a second
    connection line at the top.
    """
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    assert window._status_label.text() == "报告已保存"
    assert window._status_label.isVisibleTo(window) is True

    window.show_status("等待 QQ 登录")
    window.show_status("正在读取聊天记录…")

    assert window._status_label.text() == "报告已保存"
    assert window._status_label.isVisibleTo(window) is True


def test_connection_status_still_updates_the_hidden_status_line(
    qt_app, sources
) -> None:
    """Without action feedback on screen the legacy line keeps updating."""
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_status("等待 QQ 登录")

    assert window._status_label.text() == "等待 QQ 登录"
    assert window._status_label.isVisibleTo(window) is False


def test_open_report_with_deleted_file_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    """A stale entry whose report is gone must be reported, not silently dropped."""
    warnings = _record_warnings(monkeypatch)
    report = _fictional_report(tmp_path)
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report,
            report_directory=tmp_path,
        )
    )
    assert window._open_echo_button.isVisibleTo(window) is True

    report.unlink()
    window.open_echo_report()

    assert window._open_echo_button.isVisibleTo(window) is False
    assert window._generate_share_button.isVisibleTo(window) is False
    assert window._status_label.isVisibleTo(window) is True
    assert "不存在" in window._status_label.text()
    assert warnings[-1][1] == window._status_label.text()


def test_open_report_directory_with_deleted_directory_is_visible_and_announced(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    warnings = _record_warnings(monkeypatch)
    report_directory = tmp_path / "Echo_Report_20260815_143012"
    report_directory.mkdir()
    report_path = report_directory / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report_path,
            report_directory=report_directory,
        )
    )
    assert window._open_report_directory_button.isVisibleTo(window) is True

    shutil.rmtree(report_directory)
    window.open_echo_report_directory()

    assert window._open_report_directory_button.isVisibleTo(window) is False
    assert window._status_label.isVisibleTo(window) is True
    assert "不存在" in window._status_label.text()
    assert warnings[-1][1] == window._status_label.text()
