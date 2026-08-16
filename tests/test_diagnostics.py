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


def test_runtime_root_uses_frozen_executable_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "Echo" / "Echo.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert diagnostics.runtime_root() == executable.parent
    assert diagnostics.log_path() == executable.parent / "logs" / "echo.log"


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
