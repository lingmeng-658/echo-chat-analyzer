"""Layout and lifecycle of the production processing page, with no chat data."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from qq_chat_analyzer.application.analysis_phase import AnalysisPhase


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app):
    from qq_chat_analyzer.gui.processing_page import ProcessingPage
    page = ProcessingPage(reduced_motion=False)
    page.resize(780, 530)
    page.show()
    yield page
    page.close()
    page.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_page_starts_in_reading_and_only_typed_phases_update_the_title(page):
    assert not page.animation.model.active
    page.start()
    assert page.phase is AnalysisPhase.READING
    assert page.animation._timer.isActive()
    page.set_phase("正在分析聊天内容...")
    assert page.phase is AnalysisPhase.READING
    page.set_phase(AnalysisPhase.ANALYZING_REPORT)
    assert page.status_label.text() == "正在分析与生成报告"
    page.animation.model.advance(16)
    elapsed = page.animation.model.transition_elapsed_ms
    page.set_phase(AnalysisPhase.ANALYZING_REPORT)
    assert page.animation.model.transition_elapsed_ms == elapsed
    page.stop()
    assert not page.animation._timer.isActive()
    assert not page.animation.model.active
    page.set_phase(AnalysisPhase.READING)
    assert page.phase is AnalysisPhase.ANALYZING_REPORT
    page.start()
    assert page.phase is AnalysisPhase.READING
    assert page.animation.model.clock_ms == 0


@pytest.mark.parametrize("size", [(780, 530), (1180, 690), (1900, 1000)])
def test_processing_page_layout_keeps_animation_and_cancel_inside_page(page, size):
    page.resize(*size)
    page.start()
    QApplication.processEvents()
    for child in (page.animation, page.status_label, page.subtitle_label, page.cancel_button):
        assert child.isVisibleTo(page)
        assert child.width() > 0 and child.height() > 0
        assert page.rect().contains(child.geometry())
    assert page.animation.width() <= 800
    assert page.cancel_button.text() == "取消分析"
    assert page.findChildren(QPushButton) == [page.cancel_button]
    assert page.animation.geometry().bottom() < page.status_label.geometry().top()
    assert page.status_label.geometry().bottom() < page.cancel_button.geometry().top()


def test_reduced_motion_keeps_business_phase_live_without_a_timer(page):
    page.set_reduced_motion(True)
    page.start()
    page.set_phase(AnalysisPhase.ANALYZING_REPORT)
    assert page.phase is AnalysisPhase.ANALYZING_REPORT
    assert page.animation.model.pen_alpha == 1
    assert not page.animation._timer.isActive()
    called = []
    page.cancel_requested.connect(lambda: called.append(True))
    page.cancel_button.click()
    assert called == [True]


def test_page_respects_system_reduced_motion_without_a_debug_control(app, monkeypatch):
    from qq_chat_analyzer.gui import processing_page
    monkeypatch.setattr(processing_page, "system_reduced_motion", lambda: True)
    page = processing_page.ProcessingPage()
    try:
        page.start()
        assert page.animation.model.reduced_motion
    finally:
        page.close()
        page.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_processing_surface_stays_paper_colored_under_the_app_stylesheet(app):
    from qq_chat_analyzer.gui.processing_page import ProcessingPage
    from qq_chat_analyzer.gui.theme import BASE_QSS
    host = QWidget()
    host.setStyleSheet(BASE_QSS)
    page = ProcessingPage(host)
    host.resize(800, 600)
    page.setGeometry(10, 10, 780, 580)
    try:
        host.show()
        QApplication.processEvents()
        assert host.grab().toImage().pixelColor(15, 15).name() == "#fbf9f4"
    finally:
        page.stop()
        host.close()
        host.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
