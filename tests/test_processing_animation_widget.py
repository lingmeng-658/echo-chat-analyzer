"""Qt widget lifecycle, with explicit elapsed deltas instead of sleeping."""
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PySide6.QtCore import QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from qq_chat_analyzer.gui.processing_animation_model import AnalysisPhase


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


class Clock:
    def __init__(self):
        self.valid = False
        self.delta_ns = 0

    def start(self):
        self.valid = True
        self.delta_ns = 0

    def invalidate(self):
        self.valid = False

    def isValid(self):
        return self.valid

    def nsecsElapsed(self):
        return self.delta_ns


@pytest.fixture
def widget(app, monkeypatch):
    from qq_chat_analyzer.gui import processing_animation_widget as module
    monkeypatch.setattr(module, "QElapsedTimer", Clock)
    widget = module.ProcessingAnimationWidget()
    widget.resize(800, 460)
    widget.show()
    yield widget
    widget.stop()
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def tick(widget, ms):
    widget._elapsed.delta_ns = int(ms*1_000_000)
    widget._on_timeout()


def test_timer_consumes_one_capped_delta_and_resets_on_pause_and_hide(widget):
    assert isinstance(widget._timer, QTimer)
    assert widget._timer.isActive()
    tick(widget, 5000)
    assert widget.model.clock_ms == 50
    widget.set_paused(True)
    assert not widget._timer.isActive()
    tick(widget, 5000)
    assert widget.model.clock_ms == 50
    widget.set_paused(False)
    assert widget._elapsed.delta_ns == 0
    tick(widget, 16)
    assert widget.model.clock_ms == 66
    widget.hide()
    tick(widget, 5000)
    assert widget.model.clock_ms == 66
    widget.show()
    assert widget._elapsed.delta_ns == 0
    tick(widget, 16)
    assert widget.model.clock_ms == 82


def test_stop_restart_and_reduced_motion_are_static_when_expected(widget):
    widget.set_phase(AnalysisPhase.ANALYZING_REPORT)
    assert widget.model.is_transitioning
    widget.stop()
    assert not widget._timer.isActive()
    assert not widget.model.active
    assert not widget.model.has_residual_activity
    widget.start()
    assert widget.model.clock_ms == 0
    assert widget.model.active
    assert widget._timer.isActive()
    widget.set_reduced_motion(True)
    assert not widget._timer.isActive()
    assert widget.model.incoming.progress == pytest.approx(.67)
    image = widget.grab().toImage()
    tick(widget, 5000)
    assert widget.grab().toImage() == image
    widget.set_phase(AnalysisPhase.ANALYZING_REPORT)
    assert widget.model.pen_alpha == 1
    assert widget.model.phase is AnalysisPhase.ANALYZING_REPORT
    widget.set_reduced_motion(False)
    assert widget._timer.isActive()
    tick(widget, 16)
    assert widget.model.clock_ms == 16


def test_minimized_window_suspends_the_same_model(widget):
    widget.showMinimized()
    QApplication.sendEvent(widget, QEvent(QEvent.Type.WindowStateChange))
    assert widget.model.hidden
    assert not widget._timer.isActive()
    tick(widget, 5000)
    assert widget.model.clock_ms == 0
    widget.showNormal()
    QApplication.sendEvent(widget, QEvent(QEvent.Type.WindowStateChange))
    assert not widget.model.hidden
    assert widget._elapsed.delta_ns == 0


def test_preview_controls_drive_widget_without_business_tasks(app):
    from qq_chat_analyzer.gui.processing_animation_preview import ProcessingPreview
    preview = ProcessingPreview()
    try:
        preview.analysis_button.click()
        assert preview.animation.model.requested_phase is AnalysisPhase.ANALYZING_REPORT
        preview.pause_button.click()
        assert preview.animation.model.paused
        preview.reduced_motion_box.setChecked(True)
        assert preview.animation.model.reduced_motion
        preview.restart_button.click()
        assert preview.animation.model.requested_phase is AnalysisPhase.READING
        preview.stop_button.click()
        assert not preview.animation.model.active
    finally:
        preview.close()
        preview.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_real_qt_timer_drives_model_in_an_event_loop(app):
    from qq_chat_analyzer.gui.processing_animation_widget import ProcessingAnimationWidget
    widget = ProcessingAnimationWidget()
    loop = QEventLoop()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    observed = []

    def after_tick():
        observed.append(widget.model.clock_ms)
        if len(observed) >= 4:
            loop.quit()

    widget._timer.timeout.connect(after_tick)
    try:
        widget.show()
        watchdog.start(1000)
        loop.exec()
        assert len(observed) == 4
        assert observed[0] > 0
        assert all(0 < b-a <= 50 for a, b in zip(observed, observed[1:]))
        assert not widget.grab().isNull()
    finally:
        watchdog.stop()
        widget.stop()
        widget.close()
        widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.slow_integration
def test_native_preview_process_exits_cleanly_after_playing_and_closing():
    root = Path(__file__).resolve().parents[1]
    program = f"""
import sys
sys.path.insert(0, {str(root / 'src')!r})
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from qq_chat_analyzer.gui.processing_animation_preview import ProcessingPreview
app = QApplication([])
preview = ProcessingPreview()
ticks = []
def after_tick():
    ticks.append(preview.animation.model.clock_ms)
    if len(ticks) == 4:
        preview.close()
        app.quit()
preview.animation._timer.timeout.connect(after_tick)
preview.show()
app.exec()
assert len(ticks) == 4 and ticks[-1] > 0
preview.deleteLater()
app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
print('preview played and closed')
"""
    result = subprocess.run([sys.executable, "-X", "faulthandler", "-c", program],
                            cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "preview played and closed" in result.stdout
