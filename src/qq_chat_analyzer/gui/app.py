"""Compose the desktop application and its facade.

This is the only place that knows how to build a real facade with real
providers. Keeping it separate means the widgets stay injectable and testable
with stubs.
"""

from __future__ import annotations

import sys
from typing import Any

from ..application.facade import ChatAnalyzerFacade
from ..resources import resources_dir, user_data_dir
from .desktop_runtime import (
    STARTUP_FAILED_MESSAGE,
    configure_logging,
    install_global_exception_handler,
    log_startup,
)


APP_VERSION = "0.8.0"
HEADLESS_ANALYSIS_FLAG = "--headless-analyze"


def build_facade() -> ChatAnalyzerFacade:
    """Create a facade with whatever providers this machine can offer.

    Provider construction is optional by design: a machine without QQ or
    WeChat tooling still gets a working window with those sources disabled.
    """
    from ..application.analysis_service import AnalysisApplicationService

    wechat_provider_factory = _wechat_provider_factory()

    return ChatAnalyzerFacade(
        qq_service=_optional_qq_service(),
        qq_connection_service=_optional_qq_connection_service(),
        wechat_service=_optional_wechat_service(wechat_provider_factory),
        wechat_connection_service=_optional_wechat_connection_service(
            wechat_provider_factory
        ),
        analysis_service=AnalysisApplicationService(),
        stopwords_directory=resources_dir(),
    )


def _optional_qq_service() -> Any:
    provider = _optional_qq_provider()
    if provider is None:
        return None
    from ..application.qq_export_import_service import QQExportImportService

    return QQExportImportService(provider)


def _optional_qq_connection_service() -> Any:
    provider = _optional_qq_provider()
    if provider is None:
        return None
    from ..application.qq_connection_service import QQConnectionService

    return QQConnectionService(provider)


def _optional_qq_provider() -> Any:
    try:
        from ..providers import QQChatExporterProvider

        return QQChatExporterProvider()
    except Exception:
        return None


def _wechat_provider_factory() -> Any:
    """Build the one factory both WeChat services share.

    Status checks and session reads must agree, so they are given the same
    factory rather than each constructing a provider of their own.
    """
    from ..application.wechat_provider_factory import WeChatProviderFactory

    return WeChatProviderFactory()


def _optional_wechat_service(provider_factory: Any) -> Any:
    from ..application.wechat_export_import_service import (
        WeChatExportImportService,
    )

    return WeChatExportImportService(provider_factory=provider_factory)


def _optional_wechat_connection_service(provider_factory: Any) -> Any:
    from ..application.wechat_connection_service import (
        WeChatConnectionService,
    )

    return WeChatConnectionService(provider_factory=provider_factory)


def main(argv: list[str] | None = None) -> int:
    """Start the Qt event loop with the main window."""
    configure_logging()
    install_global_exception_handler()
    log_startup(APP_VERSION)

    arguments = list(sys.argv[1:] if argv is None else argv)
    if HEADLESS_ANALYSIS_FLAG in arguments:
        return _run_headless_analysis(arguments)

    from PySide6.QtWidgets import QApplication, QMessageBox

    try:
        from .main_window import MainWindow

        app = QApplication(arguments)
        window = MainWindow(build_facade())
        window.resize(960, 720)
        window.show()
        return app.exec()
    except Exception as error:
        configure_logging().exception("desktop startup failed", exc_info=error)
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(None, "\u9519\u8bef", STARTUP_FAILED_MESSAGE)
        return 1


def _run_headless_analysis(arguments: list[str]) -> int:
    """Run one local file analysis for packaging validation."""
    try:
        index = arguments.index(HEADLESS_ANALYSIS_FLAG)
        input_path = arguments[index + 1] if index + 1 < len(arguments) else ""
    except ValueError:
        return 2
    if not input_path:
        return 2

    from ..application.facade import AnalysisConfig

    try:
        outcome = build_facade().analyze_file(
            input_path,
            AnalysisConfig(output_directory=user_data_dir() / "validation"),
        )
    except Exception as error:
        configure_logging().exception("headless analysis failed", exc_info=error)
        return 1

    result = getattr(outcome, "result", None)
    processed = getattr(result, "processed_message_count", 0)
    valid = getattr(result, "valid_text_count", 0)
    artifact_directory = getattr(outcome, "artifact_directory", None)
    configure_logging().info(
        "headless analysis completed processed=%s valid=%s artifacts=%s",
        processed,
        valid,
        artifact_directory,
    )
    print(
        f"processed={processed} valid={valid} "
        f"artifacts={artifact_directory}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
