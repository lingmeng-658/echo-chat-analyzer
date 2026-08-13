"""Behavior tests for desktop startup hardening and logging."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from unittest import mock

import pytest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))


def _desktop_runtime():
    return importlib.import_module("qq_chat_analyzer.gui.desktop_runtime")


def test_user_data_dir_uses_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    assert module.user_data_dir() == local / "LocalChatAnalyzer"


def test_log_directory_is_created_under_user_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    directory = module.log_directory()

    assert directory == local / "LocalChatAnalyzer" / "logs"
    assert directory.is_dir()


def test_configure_logging_creates_file_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    logger = module.configure_logging()

    assert (local / "LocalChatAnalyzer" / "logs" / "desktop.log").is_file()
    assert any(
        isinstance(handler, logging.FileHandler) for handler in logger.handlers
    )


def test_wechat_database_provider_diagnostics_are_written_to_desktop_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    desktop_logger = logging.getLogger(module.LOGGER_NAME)
    provider_logger = logging.getLogger(
        "qq_chat_analyzer.providers.wechat_database_provider"
    )
    original_desktop_handlers = desktop_logger.handlers[:]
    original_provider_handlers = provider_logger.handlers[:]
    original_provider_level = provider_logger.level
    try:
        desktop_logger.handlers.clear()
        provider_logger.handlers.clear()

        module.configure_logging()
        module.configure_logging()
        provider_logger.info(
            "[wechat db] query failed wcdb_stage=open error_type=RuntimeError"
        )
        for handler in provider_logger.handlers:
            handler.flush()

        log_text = (
            local / "LocalChatAnalyzer" / "logs" / "desktop.log"
        ).read_text(encoding="utf-8")
        assert log_text.count("[wechat db] query failed") == 1
        assert "wcdb_stage=open" in log_text
    finally:
        for handler in desktop_logger.handlers + provider_logger.handlers:
            if handler not in (
                original_desktop_handlers + original_provider_handlers
            ):
                handler.close()
        desktop_logger.handlers[:] = original_desktop_handlers
        provider_logger.handlers[:] = original_provider_handlers
        provider_logger.setLevel(original_provider_level)


def test_uncaught_exception_is_logged_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _desktop_runtime()
    records: list[logging.LogRecord] = []

    class _RecordingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger(module.LOGGER_NAME)
    original_level = logger.level
    original_propagate = logger.propagate
    try:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = _RecordingHandler()
        logger.addHandler(handler)

        module._handle_uncaught_exception(
            RuntimeError,
            RuntimeError("secret desktop crash"),
            None,
        )

        assert records
        text = records[0].getMessage()
        assert "secret desktop crash" in text
        assert "RuntimeError" in text
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_global_exception_handler_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _desktop_runtime()
    original = sys.excepthook
    try:
        module.install_global_exception_handler()
        assert sys.excepthook is module._handle_uncaught_exception
    finally:
        sys.excepthook = original


def test_headless_analysis_mode_writes_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = importlib.import_module("qq_chat_analyzer.gui.app")
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    class _FakeResult:
        processed_message_count = 4
        valid_text_count = 3

    class _FakeOutcome:
        result = _FakeResult()
        artifact_directory = tmp_path / "artifacts"

    class _FakeFacade:
        def analyze_file(self, path, config=None):
            return _FakeOutcome()

    monkeypatch.setattr(app, "build_facade", lambda: _FakeFacade())

    exit_code = app._run_headless_analysis(
        [app.HEADLESS_ANALYSIS_FLAG, str(tmp_path / "fictional.json")]
    )

    assert exit_code == 0


def test_headless_analysis_mode_rejects_missing_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = importlib.import_module("qq_chat_analyzer.gui.app")

    assert app._run_headless_analysis([app.HEADLESS_ANALYSIS_FLAG]) == 2


def test_pyinstaller_entry_imports_with_absolute_imports() -> None:
    """The packaged entry must import cleanly when run as a top-level script."""
    sys.path.insert(0, str(SRC_ROOT))
    project_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "desktop_entry",
        project_root / "desktop_entry.py",
    )
    assert spec is not None and spec.loader is not None
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    app = importlib.import_module("qq_chat_analyzer.gui.app")

    assert entry.main is app.main
