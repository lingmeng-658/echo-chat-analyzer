"""Run directly with the project .venv Python for standalone visual review."""
import sys
from pathlib import Path

# Direct execution must load this worktree, even if the restored environment
# has an editable install pointing at another worktree.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from PySide6.QtCore import QEvent
from qq_chat_analyzer.gui.processing_animation_model import AnalysisPhase
from qq_chat_analyzer.gui.processing_animation_widget import ProcessingAnimationWidget


class ProcessingPreview(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Echo · 原生 Processing 动画预览")
        self.setStyleSheet("background:#fbf9f4;color:#352f29;")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Echo · 书页与回响"))
        self.animation = ProcessingAnimationWidget(self)
        layout.addWidget(self.animation, 1)
        controls = QHBoxLayout()
        self.reading_button = QPushButton("读取")
        self.analysis_button = QPushButton("分析与报告")
        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.stop_button = QPushButton("停止")
        self.restart_button = QPushButton("重新开始")
        self.reduced_motion_box = QCheckBox("减少动态效果")
        for control in (self.reading_button, self.analysis_button, self.pause_button,
                        self.stop_button, self.restart_button, self.reduced_motion_box):
            controls.addWidget(control)
        layout.addLayout(controls)
        layout.addWidget(QLabel("手动切换展示阶段；动画节奏不代表真实任务进度。"))
        self.reading_button.clicked.connect(lambda: self.animation.set_phase(AnalysisPhase.READING))
        self.analysis_button.clicked.connect(lambda: self.animation.set_phase(AnalysisPhase.ANALYZING_REPORT))
        self.pause_button.toggled.connect(self.animation.set_paused)
        self.pause_button.toggled.connect(lambda paused: self.pause_button.setText("继续" if paused else "暂停"))
        self.stop_button.clicked.connect(self.animation.stop)
        self.restart_button.clicked.connect(self._restart)
        self.reduced_motion_box.toggled.connect(self.animation.set_reduced_motion)
        self.resize(860, 580)

    def _restart(self):
        self.pause_button.setChecked(False)
        self.animation.start()

    def closeEvent(self, event):
        self.animation.close()
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    preview = ProcessingPreview()
    preview.show()
    try:
        return app.exec()
    finally:
        preview.close()
        preview.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    raise SystemExit(main())
