"""QQ desktop wiring selects the Direct DB acquisition service."""

from __future__ import annotations

from qq_chat_analyzer.application.qq.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
)
from qq_chat_analyzer.gui.app import _optional_qq_service


def test_gui_qq_service_uses_direct_database_acquisition() -> None:
    service = _optional_qq_service(provider_factory=object())

    assert isinstance(service, QQDirectDatabaseImportService)
