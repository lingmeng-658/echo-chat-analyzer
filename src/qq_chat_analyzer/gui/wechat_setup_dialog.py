"""Minimal WeChat environment setup dialog.

This dialog only collects the WeChat *data directory* from a user and turns
it into a
:class:`~qq_chat_analyzer.application.facade.WeChatEnvironmentConfig`.
Persistence, validation, and provider refresh stay in the facade, so this
module never writes JSON and never touches a provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..application.facade import WeChatEnvironmentConfig

DATA_ROOT_LABEL = "微信数据位置"
DATA_ROOT_HINT = (
    "如果未自动识别微信数据目录，请点击上方按钮，"
    "选择微信设置中显示的存储文件夹。"
)
BROWSE_CAPTION = "选择微信存储文件夹"


class WeChatSetupDialog(QDialog):
    """Collect the WeChat data directory from a user."""

    def __init__(
        self,
        parent: Any = None,
        *,
        setup_status: Any = None,
        data_root: Any = None,
        data_roots: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("微信连接设置")
        self.setMinimumWidth(520)

        self._data_root_edit = QLineEdit()
        self._data_root_edit.setPlaceholderText(DATA_ROOT_HINT)
        self._data_root_edit.setToolTip(DATA_ROOT_HINT)
        self._data_root_combo: QComboBox | None = None
        self._use_data_roots = bool(data_roots)
        if self._use_data_roots:
            self._data_root_combo = QComboBox()
            for root in data_roots:
                self._data_root_combo.addItem(str(root))

        form = QFormLayout()
        control = self._data_root_combo or self._data_root_edit
        form.addRow(DATA_ROOT_LABEL, self._path_row(control, self._browse_directory))

        self._hint_label = QLabel(DATA_ROOT_HINT)
        self._hint_label.setWordWrap(True)

        self._status_label = QLabel(self._status_text(setup_status))
        self._status_label.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._status_label)
        layout.addLayout(form)
        layout.addWidget(self._hint_label)
        layout.addWidget(buttons)

        if data_root is not None:
            self.set_data_root(data_root)

    def set_data_root(self, path: Any) -> None:
        """Prefill the data directory, typically from auto-detection."""
        text = "" if path is None else str(path)
        if self._use_data_roots and self._data_root_combo is not None:
            index = self._data_root_combo.findText(text)
            if index >= 0:
                self._data_root_combo.setCurrentIndex(index)
            elif text:
                self._data_root_combo.addItem(text)
            return
        self._data_root_edit.setText(text)

    def config(self) -> WeChatEnvironmentConfig:
        """Return the entered values as an application-layer config."""
        return WeChatEnvironmentConfig(
            data_root=_path_or_none(self._control_text())
        )

    # ---------------------------------------------------------------- internals

    def _path_row(self, control: Any, browse: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(control, stretch=1)
        button = QPushButton("...")
        button.setToolTip(BROWSE_CAPTION)
        button.clicked.connect(browse)
        row.addWidget(button)
        return row

    def _browse_directory(self) -> None:  # pragma: no cover - real dialog
        path = QFileDialog.getExistingDirectory(
            self,
            BROWSE_CAPTION,
            self._control_text(),
        )
        if path:
            self.set_data_root(path)

    def _control_text(self) -> str:
        if self._use_data_roots and self._data_root_combo is not None:
            return self._data_root_combo.currentText()
        return self._data_root_edit.text()

    @staticmethod
    def _status_text(setup_status: Any) -> str:
        if setup_status is None:
            return DATA_ROOT_HINT
        parts = [
            getattr(setup_status, "message", "") or "",
            getattr(setup_status, "action_hint", "") or "",
        ]
        text = " ".join(part for part in parts if part)
        return text or DATA_ROOT_HINT


def _text_or_none(value: str) -> str | None:
    text = value.strip()
    return text or None


def _path_or_none(value: str) -> Path | None:
    text = _text_or_none(value)
    if text is None:
        return None
    return Path(text)
