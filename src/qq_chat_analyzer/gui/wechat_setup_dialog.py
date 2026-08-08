"""Minimal WeChat environment setup dialog.

This dialog only collects user input and turns it into a
:class:`~qq_chat_analyzer.application.facade.WeChatEnvironmentConfig`.
Persistence, validation, and provider refresh stay in the facade, so this
module never writes JSON and never touches a provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
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


class WeChatSetupDialog(QDialog):
    """Collect the four WeChat environment fields from a user."""

    def __init__(
        self,
        parent: Any = None,
        *,
        setup_status: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e")
        self.setMinimumWidth(520)

        self._data_root_edit = QLineEdit()
        self._db_key_edit = QLineEdit()
        self._db_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._wcdb_cli_edit = QLineEdit()
        self._wcdb_dll_edit = QLineEdit()

        form = QFormLayout()
        form.addRow(
            "\u5fae\u4fe1\u6570\u636e\u76ee\u5f55",
            self._path_row(
                self._data_root_edit,
                self._browse_directory,
            ),
        )
        form.addRow("\u6570\u636e\u5e93\u5bc6\u94a5", self._db_key_edit)
        form.addRow(
            "wcdb_cli \u8def\u5f84",
            self._path_row(self._wcdb_cli_edit, self._browse_file),
        )
        form.addRow(
            "WCDB.dll \u8def\u5f84",
            self._path_row(self._wcdb_dll_edit, self._browse_file),
        )

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
        layout.addWidget(buttons)

    def config(self) -> WeChatEnvironmentConfig:
        """Return the entered values as an application-layer config."""
        return WeChatEnvironmentConfig(
            data_root=_path_or_none(self._data_root_edit.text()),
            db_key=_text_or_none(self._db_key_edit.text()),
            wcdb_cli_path=_path_or_none(self._wcdb_cli_edit.text()),
            wcdb_dll_path=_path_or_none(self._wcdb_dll_edit.text()),
        )

    # ---------------------------------------------------------------- internals

    def _path_row(self, edit: QLineEdit, browse: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(edit, stretch=1)
        button = QPushButton("...")
        button.setToolTip("\u6d4f\u89c8")
        button.clicked.connect(browse)
        row.addWidget(button)
        return row

    def _browse_directory(self) -> None:  # pragma: no cover - real dialog
        path = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5fae\u4fe1\u6570\u636e\u76ee\u5f55")
        if path:
            self._data_root_edit.setText(path)

    def _browse_file(self) -> None:  # pragma: no cover - real dialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "\u9009\u62e9\u6587\u4ef6",
            "",
            "All files (*)",
        )
        if path:
            self._wcdb_cli_edit.setText(path)

    @staticmethod
    def _status_text(setup_status: Any) -> str:
        if setup_status is None:
            return "\u8bf7\u586b\u5199\u4ee5\u4e0b\u4fe1\u606f\u3002"
        parts = [
            getattr(setup_status, "message", "") or "",
            getattr(setup_status, "action_hint", "") or "",
        ]
        text = " ".join(part for part in parts if part)
        return text or "\u8bf7\u586b\u5199\u4ee5\u4e0b\u4fe1\u606f\u3002"


def _text_or_none(value: str) -> str | None:
    text = value.strip()
    return text or None


def _path_or_none(value: str) -> Path | None:
    text = _text_or_none(value)
    if text is None:
        return None
    return Path(text)
