"""Home page with three source entry points."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class HomePage(QWidget):
    """Landing page offering QQ, WeChat, and local data management."""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("\u4f59\u97f3 Echo")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("\u9009\u62e9\u804a\u5929\u6765\u6e90\u5f00\u59cb\u5206\u6790")
        subtitle.setStyleSheet("font-size: 14px; color: #666;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(24)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(12)
        button_layout.setAlignment(Qt.AlignCenter)

        self._qq_btn = QPushButton("QQ")
        self._qq_btn.setMinimumWidth(200)
        self._qq_btn.setMinimumHeight(48)
        self._qq_btn.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self._qq_btn.clicked.connect(lambda: self.navigate_requested.emit("qq"))
        button_layout.addWidget(self._qq_btn, alignment=Qt.AlignCenter)

        self._wechat_btn = QPushButton("\u5fae\u4fe1")
        self._wechat_btn.setMinimumWidth(200)
        self._wechat_btn.setMinimumHeight(48)
        self._wechat_btn.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self._wechat_btn.clicked.connect(lambda: self.navigate_requested.emit("wechat"))
        button_layout.addWidget(self._wechat_btn, alignment=Qt.AlignCenter)

        self._local_data_btn = QPushButton("\u672c\u5730\u6570\u636e")
        self._local_data_btn.setMinimumWidth(200)
        self._local_data_btn.setMinimumHeight(48)
        self._local_data_btn.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed))
        self._local_data_btn.clicked.connect(lambda: self.navigate_requested.emit("local_data"))
        button_layout.addWidget(self._local_data_btn, alignment=Qt.AlignCenter)

        layout.addLayout(button_layout)
        layout.addStretch(1)
