"""Privacy and path tests for the shared Echo diagnostic log."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from qq_chat_analyzer import diagnostics


def _close_new_handlers(
    logger: logging.Logger,
    original_handlers: list[logging.Handler],
) -> None:
    for handler in logger.handlers:
        if handler not in original_handlers:
            for target_name in diagnostics.DESKTOP_DIAGNOSTIC_LOGGERS:
                target = logging.getLogger(target_name)
                if handler in target.handlers:
                    target.removeHandler(handler)
            handler.close()
    logger.handlers[:] = original_handlers


def test_configure_diagnostics_creates_echo_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(diagnostics, "runtime_root", lambda: tmp_path / "Echo")
    logger = logging.getLogger(diagnostics.LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    target_loggers = [
        logging.getLogger(name)
        for name in diagnostics.DESKTOP_DIAGNOSTIC_LOGGERS
    ]
    original_target_levels = {target.name: target.level for target in target_loggers}
    try:
        logger.handlers.clear()
        for target in target_loggers:
            target.setLevel(logging.NOTSET)

        configured = diagnostics.configure_diagnostics()
        configured.info("Echo started")
        for handler in configured.handlers:
            handler.flush()

        log_path = tmp_path / "Echo" / "logs" / "echo.log"
        assert log_path.is_file()
        assert "Echo started" in log_path.read_text(encoding="utf-8")
    finally:
        _close_new_handlers(logger, original_handlers)
        logger.setLevel(original_level)
        for target in target_loggers:
            target.setLevel(original_target_levels[target.name])


def test_frozen_log_uses_local_app_data_without_creating_install_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "Echo" / "Echo.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    expected_root = tmp_path / "local-app-data" / "LocalChatAnalyzer"
    assert diagnostics.runtime_root() == expected_root
    assert diagnostics.log_path() == expected_root / "logs" / "echo.log"
    assert not expected_root.exists()
    assert not executable.parent.exists()


def test_source_log_path_remains_predictable(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    expected = Path(diagnostics.__file__).resolve().parents[2] / "Echo/logs/echo.log"
    assert diagnostics.log_path() == expected


def test_frozen_diagnostics_needs_no_write_access_to_install(monkeypatch, tmp_path):
    executable = tmp_path / "Program Files" / "Echo" / "Echo.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    real_mkdir = Path.mkdir
    def deny_install(path, *args, **kwargs):
        if path == executable.parent or executable.parent in path.parents:
            raise PermissionError("fictional read-only install")
        return real_mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", deny_install)
    logger = logging.getLogger(diagnostics.LOGGER_NAME)
    original_handlers = logger.handlers[:]
    original_level = logger.level
    target_levels = {name: logging.getLogger(name).level for name in diagnostics.DESKTOP_DIAGNOSTIC_LOGGERS}
    try:
        logger.handlers.clear()
        configured = diagnostics.configure_diagnostics()
        configured.info("fictional frozen startup")
        for handler in configured.handlers:
            handler.flush()
        location = tmp_path / "local-app-data/LocalChatAnalyzer/logs/echo.log"
        assert "fictional frozen startup" in location.read_text(encoding="utf-8")
        assert not executable.parent.exists()
    finally:
        _close_new_handlers(logger, original_handlers)
        logger.setLevel(original_level)
        for name, level in target_levels.items():
            logging.getLogger(name).setLevel(level)


def test_frozen_log_falls_back_to_isolated_home_without_localappdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA")
    assert diagnostics.log_path() == tmp_path / "test-home/.localchatanalyzer/logs/echo.log"


def test_sensitive_filter_redacts_key_paths_and_helper_stderr() -> None:
    secret_key = "ab12" * 16
    database_path = r"C:\Users\Fictional\Documents\xwechat_files\session.db"
    helper_stderr = "native helper failed for fictional account"
    record = logging.LogRecord(
        name="qq_chat_analyzer.diagnostics.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="key=%s database_path=%s helper_stderr=%s token=%s",
        args=(secret_key, database_path, helper_stderr, "fictional-token"),
        exc_info=None,
    )

    diagnostics.SensitiveDataFilter().filter(record)
    text = record.getMessage()

    assert secret_key not in text
    assert database_path not in text
    assert helper_stderr not in text
    assert "fictional-token" not in text
    assert "[REDACTED]" in text


def test_sensitive_filter_removes_exception_message() -> None:
    try:
        raise RuntimeError("fictional secret exception detail")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="qq_chat_analyzer.diagnostics.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="wechat.import.failed",
        args=(),
        exc_info=exc_info,
    )

    diagnostics.SensitiveDataFilter().filter(record)

    assert record.exc_info is None
    assert record.exc_text is None
    assert "fictional secret exception detail" not in record.getMessage()
