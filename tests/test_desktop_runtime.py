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

from qq_chat_analyzer import diagnostics as diagnostics_module


def _desktop_runtime():
    return importlib.import_module("qq_chat_analyzer.gui.desktop_runtime")


@pytest.fixture(autouse=True)
def _isolated_diagnostic_loggers() -> None:
    names = (
        diagnostics_module.LOGGER_NAME,
        "qq_chat_analyzer.desktop",
        "qq_chat_analyzer.providers.wechat_database_provider",
    )
    states = []
    for name in names:
        logger = logging.getLogger(name)
        states.append((logger, logger.handlers[:], logger.level, logger.propagate))
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
    yield
    for logger, original_handlers, original_level, original_propagate in states:
        for handler in tuple(logger.handlers):
            if handler not in original_handlers:
                handler.close()
        logger.handlers[:] = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_log_directory_is_created_under_echo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    root = tmp_path / "Echo"
    monkeypatch.setattr(diagnostics_module, "runtime_root", lambda: root)

    directory = module.log_directory()

    assert directory == root / "logs"
    assert directory.is_dir()


def test_configure_logging_creates_file_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    root = tmp_path / "Echo"
    monkeypatch.setattr(diagnostics_module, "runtime_root", lambda: root)

    logger = module.configure_logging()

    assert (root / "logs" / "echo.log").is_file()
    assert any(
        isinstance(handler, logging.FileHandler) for handler in logger.handlers
    )


def test_desktop_log_is_written_as_utf8(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    root = tmp_path / "Echo"
    monkeypatch.setattr(diagnostics_module, "runtime_root", lambda: root)
    logger = logging.getLogger(module.LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    try:
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        module.configure_logging()
        logger.info("正在加载 NapCat...")
        for handler in logger.handlers:
            handler.flush()

        log_path = root / "logs" / "echo.log"
        text = log_path.read_bytes().decode("utf-8")
        assert "正在加载 NapCat..." in text
        assert "姝ｅ湪鍔犺浇" not in text
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                handler.close()
        logger.handlers[:] = original_handlers
        logger.setLevel(original_level)


def test_wechat_database_provider_diagnostics_are_written_to_desktop_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _desktop_runtime()
    root = tmp_path / "Echo"
    monkeypatch.setattr(diagnostics_module, "runtime_root", lambda: root)
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
            "wechat.wcdb.failed wcdb_stage=open error_type=RuntimeError"
        )
        for handler in provider_logger.handlers:
            handler.flush()

        log_text = (root / "logs" / "echo.log").read_text(encoding="utf-8")
        assert log_text.count("wechat.wcdb.failed") == 1
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


@pytest.fixture
def desktop_startup(monkeypatch: pytest.MonkeyPatch):
    """Isolate the Qt event loop and forced process exit, keeping main real."""
    from types import SimpleNamespace
    from PySide6 import QtWidgets
    from qq_chat_analyzer.gui import app as entry, main_window

    application = mock.Mock()
    application.exec.return_value = 7
    application_class = mock.Mock(return_value=application)
    application_class.instance.return_value = application
    window = mock.Mock()
    window_class = mock.Mock(return_value=window)
    critical = mock.Mock()
    finish_exit = mock.Mock()
    build_facade = mock.Mock(return_value=object())
    logger = mock.Mock(spec=logging.Logger)
    configure = mock.Mock(return_value=logger)
    monkeypatch.setattr(QtWidgets, "QApplication", application_class)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", critical)
    monkeypatch.setattr(main_window, "MainWindow", window_class)
    monkeypatch.setattr(entry, "build_facade", build_facade)
    monkeypatch.setattr(entry, "_finish_process_exit", finish_exit)
    monkeypatch.setattr(entry, "configure_logging", configure)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    return SimpleNamespace(
        entry=entry, application=application, window=window,
        window_class=window_class, build_facade=build_facade,
        critical=critical, finish_exit=finish_exit, logger=logger,
        configure=configure,
    )


@pytest.mark.parametrize("logging_fails", [False, True])
def test_main_starts_gui_even_when_logging_initialization_fails(
    desktop_startup, logging_fails: bool,
) -> None:
    startup = desktop_startup
    if logging_fails:
        startup.configure.side_effect = PermissionError(
            13, "Permission denied", r"C:\Users\Fictional\Private\logs\echo.log",
        )

    assert startup.entry.main([]) == 7

    startup.window.show.assert_called_once_with()
    startup.application.exec.assert_called_once_with()
    startup.finish_exit.assert_called_once_with(7, window=startup.window)
    startup.critical.assert_not_called()
    startup.configure.assert_called_once_with()


@pytest.mark.parametrize("logging_fails", [False, True])
@pytest.mark.parametrize("failure_stage", ["facade", "window"])
def test_main_startup_failure_is_safe_without_retrying_logging(
    desktop_startup, logging_fails: bool, failure_stage: str,
) -> None:
    startup = desktop_startup
    original = RuntimeError(r"fictional startup failure at C:\Users\Fictional\Private")
    failing_operation = (
        startup.build_facade if failure_stage == "facade" else startup.window_class
    )
    failing_operation.side_effect = original
    if logging_fails:
        startup.configure.side_effect = PermissionError("fictional log write denied")

    assert startup.entry.main([]) == 1

    startup.critical.assert_called_once_with(
        None, "错误", startup.entry.STARTUP_FAILED_MESSAGE,
    )
    startup.application.exec.assert_not_called()
    startup.finish_exit.assert_not_called()
    startup.configure.assert_called_once_with()
    if not logging_fails:
        startup.logger.exception.assert_called_once_with(
            "desktop startup failed", exc_info=original,
        )


def test_main_startup_error_still_returns_failure_if_log_emission_fails(desktop_startup) -> None:
    startup = desktop_startup
    startup.build_facade.side_effect = RuntimeError("fictional startup failure")
    startup.logger.exception.side_effect = PermissionError("fictional log write denied")

    assert startup.entry.main([]) == 1

    startup.critical.assert_called_once_with(
        None, "错误", startup.entry.STARTUP_FAILED_MESSAGE,
    )
    startup.application.exec.assert_not_called()


def test_gui_app_no_longer_exposes_headless_analysis_entry() -> None:
    """The legacy headless local-file entry point is removed with LOCAL_FILE."""
    app = importlib.import_module("qq_chat_analyzer.gui.app")

    assert not hasattr(app, "HEADLESS_ANALYSIS_FLAG")
    assert not hasattr(app, "_run_headless_analysis")


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
