"""Minimal local data management page skeleton."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LocalDataPage(QWidget):
    """Placeholder page for future local data management.

    This page is only a navigation target. It does not implement any
    snapshot, history, cache, or storage logic.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("本地数据管理")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = QLabel(
            "这里将提供历史 Echo、"
            "数据快照、缓存和存储管理。\n"
            "当前正在开发中，敬请期待。"
        )
        description.setStyleSheet("font-size: 14px; color: #666;")
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        layout.addSpacing(24)

        self._back_button = QPushButton("返回首页")
        self._back_button.setMinimumWidth(160)
        self._back_button.clicked.connect(self._on_back_clicked)
        layout.addWidget(self._back_button, alignment=Qt.AlignCenter)

        layout.addStretch(1)

    def _on_back_clicked(self) -> None:
        """Emit or handle navigation via parent navigation signal."""
        main_window = self.window()
        if hasattr(main_window, "show_home_page"):
            main_window.show_home_page()
