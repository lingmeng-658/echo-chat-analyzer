"""Independent native processing animation. No MainWindow/business wiring."""
import weakref

from PySide6.QtCore import QElapsedTimer, QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .processing_animation import paint_processing_frame
from .processing_animation_model import AnalysisPhase, ProcessingAnimationModel


class ProcessingAnimationWidget(QWidget):
    """One model clock, driven by elapsed deltas from a precise Qt timer.

    Pause/visibility/reduced-motion/stop halt the timer and invalidate elapsed
    time. Resuming starts a fresh measurement, so hidden time is discarded.
    Reduced motion is an explicit setting, usable by a future preferences UI.
    """

    def __init__(self, parent=None, *, reduced_motion=False):
        super().__init__(parent)
        self.model = ProcessingAnimationModel()
        self.model.set_reduced_motion(reduced_motion)
        self.model.set_hidden(True)
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._on_timeout)
        self._observed_window = None
        self.setAccessibleName("书页汇集与音符笔书写动画")

    def sizeHint(self):
        return QSize(800, 460)

    def set_phase(self, phase: AnalysisPhase):
        self.model.set_phase(phase)
        self._sync_timer()
        self.update()

    def set_paused(self, paused: bool):
        self.model.set_paused(paused)
        self._sync_timer()
        self.update()

    def set_reduced_motion(self, reduced: bool):
        self.model.set_reduced_motion(reduced)
        self._sync_timer()
        self.update()

    def stop(self):
        self.model.stop()
        self._sync_timer()
        self.update()

    def start(self, phase: AnalysisPhase = AnalysisPhase.READING):
        self.model.reset()
        self.model.set_paused(False)
        self.model.set_phase(phase)
        self._elapsed.invalidate()
        self._timer.stop()
        self._sync_visibility()
        self.update()

    def _sync_timer(self):
        run = self.model.active and not (
            self.model.paused or self.model.hidden or self.model.reduced_motion)
        if run:
            if not self._timer.isActive():
                self._elapsed.start()
                self._timer.start()
        else:
            self._timer.stop()
            self._elapsed.invalidate()

    def _sync_visibility(self):
        window = self.window()
        self.model.set_hidden(not self.isVisible() or not window.isVisible() or window.isMinimized())
        self._sync_timer()

    def _on_timeout(self):
        self._sync_visibility()
        if not self._timer.isActive():
            return
        if not self._elapsed.isValid():
            self._elapsed.start()
            return
        delta_ms = self._elapsed.nsecsElapsed()/1_000_000
        self._elapsed.start()
        self.model.advance(delta_ms)  # the model owns the 50ms cap
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        window = self.window()
        observed = self._observed_window() if self._observed_window is not None else None
        if window is not observed:
            self._remove_window_observer()
            if window is not self:
                # Do not keep the parent window (or self) alive through a cycle.
                self._observed_window = weakref.ref(window)
                window.installEventFilter(self)
        self._sync_visibility()

    def hideEvent(self, event):
        self.model.set_hidden(True)
        self._sync_timer()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        observed = self._observed_window() if self._observed_window is not None else None
        if watched is observed and event.type() in (
            QEvent.Type.WindowStateChange, QEvent.Type.Show, QEvent.Type.Hide):
            self._sync_visibility()
        return super().eventFilter(watched, event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_visibility()

    def _remove_window_observer(self):
        observed = self._observed_window() if self._observed_window is not None else None
        if observed is not None:
            observed.removeEventFilter(self)
        self._observed_window = None

    def closeEvent(self, event):
        self.stop()
        self._remove_window_observer()
        super().closeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor("#fbf9f4"))
            paint_processing_frame(painter, QRectF(self.rect()), self.model)
        finally:
            painter.end()
