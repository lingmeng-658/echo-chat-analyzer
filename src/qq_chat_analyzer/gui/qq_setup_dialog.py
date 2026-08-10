"""Minimal QQ environment setup dialog.

This dialog only collects user input and turns it into a
:class:`~qq_chat_analyzer.application.facade.QQEnvironmentConfig`.
Deployment, runtime lifecycle, and persistence stay in the facade.
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

from ..application.facade import QQEnvironmentConfig


class QQSetupDialog(QDialog):
    """Collect the QQ environment fields from a user."""

    def __init__(
        self,
        parent: Any = None,
        *,
        setup_status: Any = None,
        config: QQEnvironmentConfig | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("QQ \u73af\u5883\u8bbe\u7f6e")
        self.setMinimumWidth(560)

        self._qq_install_edit = QLineEdit()
        self._runtime_dir_edit = QLineEdit()
        self._qce_path_edit = QLineEdit()
        self._qce_config_dir_edit = QLineEdit()
        self._base_url_edit = QLineEdit("http://127.0.0.1:40653")
        self._security_path_edit = QLineEdit()
        self._bridge_url_edit = QLineEdit("http://127.0.0.1:40654")
        self._version_edit = QLineEdit()

        form = QFormLayout()
        form.addRow(
            "QQ \u5b89\u88c5\u8def\u5f84",
            self._path_row(
                self._qq_install_edit,
                lambda: self._browse_directory(self._qq_install_edit),
            ),
        )
        form.addRow(
            "\u8fd0\u884c\u73af\u5883\u76ee\u5f55",
            self._path_row(
                self._runtime_dir_edit,
                lambda: self._browse_directory(self._runtime_dir_edit),
            ),
        )
        form.addRow(
            "qce-server \u8def\u5f84",
            self._path_row(
                self._qce_path_edit,
                lambda: self._browse_file(self._qce_path_edit),
            ),
        )
        form.addRow(
            "QCE \u914d\u7f6e\u76ee\u5f55",
            self._path_row(
                self._qce_config_dir_edit,
                lambda: self._browse_directory(self._qce_config_dir_edit),
            ),
        )
        form.addRow("QCE base_url", self._base_url_edit)
        form.addRow(
            "security.json \u8def\u5f84",
            self._path_row(
                self._security_path_edit,
                lambda: self._browse_file(self._security_path_edit),
            ),
        )
        form.addRow("NapCat bridge \u5730\u5740", self._bridge_url_edit)
        form.addRow("\u7248\u672c\u4fe1\u606f", self._version_edit)

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

        self._prefill(config)

    def _prefill(self, config: QQEnvironmentConfig | None) -> None:
        """Fill technical fields from the effective facade config."""
        if config is None:
            return
        self._qq_install_edit.setText(
            _path_text(config.qq_install_path)
        )
        self._runtime_dir_edit.setText(
            _path_text(config.runtime_directory)
        )
        self._qce_path_edit.setText(_path_text(config.qce_path))
        self._qce_config_dir_edit.setText(
            _path_text(config.qce_config_directory)
        )
        self._base_url_edit.setText(config.base_url or "")
        self._security_path_edit.setText(
            _path_text(config.security_path)
        )
        self._bridge_url_edit.setText(config.napcat_bridge_url or "")
        self._version_edit.setText(config.version or "")

    def config(self) -> QQEnvironmentConfig:
        """Return the entered values as an application-layer config."""
        return QQEnvironmentConfig(
            qq_install_path=_path_or_none(self._qq_install_edit.text()),
            runtime_directory=_path_or_none(self._runtime_dir_edit.text()),
            qce_path=_path_or_none(self._qce_path_edit.text()),
            qce_config_directory=_path_or_none(
                self._qce_config_dir_edit.text()
            ),
            base_url=(
                self._base_url_edit.text().strip()
                or "http://127.0.0.1:40653"
            ),
            security_path=_path_or_none(self._security_path_edit.text()),
            napcat_bridge_url=(
                self._bridge_url_edit.text().strip()
                or "http://127.0.0.1:40654"
            ),
            version=_text_or_none(self._version_edit.text()),
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

    def _browse_directory(self, edit: QLineEdit) -> None:  # pragma: no cover
        path = QFileDialog.getExistingDirectory(
            self,
            "\u9009\u62e9\u76ee\u5f55",
        )
        if path:
            edit.setText(path)

    def _browse_file(self, edit: QLineEdit) -> None:  # pragma: no cover
        path, _ = QFileDialog.getOpenFileName(
            self,
            "\u9009\u62e9\u6587\u4ef6",
            "",
            "All files (*)",
        )
        if path:
            edit.setText(path)

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


def _path_text(value: Path | None) -> str:
    return "" if value is None else str(value)
