"""Facade-level tests for the WeChat setup entry point.

Privacy: all configuration values here are fabricated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qq_chat_analyzer.application.facade import (
    ChatAnalyzerFacade,
    ChatSource,
    FacadeError,
    SourceUnavailable,
)
from qq_chat_analyzer.application.wechat_environment_config import (
    WeChatConfigWriteFailed,
    WeChatEnvironmentConfig,
)


class _StubSetupService:
    def __init__(
        self,
        *,
        status: object = None,
        error: Exception | None = None,
        detected_root: Path | None = None,
    ):
        self.status = status
        self.error = error
        self.detected_root = detected_root
        self.saved: list[WeChatEnvironmentConfig] = []
        self.checks = 0
        self.detects = 0

    def check_setup(self) -> object:
        self.checks += 1
        if self.error is not None:
            raise self.error
        return self.status

    def detect_wechat_data_root(self) -> Path | None:
        self.detects += 1
        if self.error is not None:
            raise self.error
        return self.detected_root

    def save_environment(self, config: WeChatEnvironmentConfig) -> object:
        if self.error is not None:
            raise self.error
        self.saved.append(config)
        return self.status


class _ProgressCapturingSetupService(_StubSetupService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.progress_callbacks = []

    def acquire_db_key(self, progress=None):
        self.progress_callbacks.append(progress)
        if progress is not None:
            progress("relayed progress")
        return "a" * 64


def _config(tmp_path: Path) -> WeChatEnvironmentConfig:
    return WeChatEnvironmentConfig(
        data_root=tmp_path / "fake_root",
        db_key="abcd1234",
    )


def test_facade_saves_wechat_environment(tmp_path: Path) -> None:
    sentinel = object()
    setup = _StubSetupService(status=sentinel)
    facade = ChatAnalyzerFacade(wechat_setup_service=setup)

    result = facade.setup_wechat_environment(_config(tmp_path))

    assert result is sentinel
    assert setup.saved == [_config(tmp_path)]


def test_facade_reports_wechat_setup_status(tmp_path: Path) -> None:
    sentinel = object()
    facade = ChatAnalyzerFacade(
        wechat_setup_service=_StubSetupService(status=sentinel)
    )

    assert facade.get_wechat_setup_status() is sentinel


def test_facade_detects_wechat_data_root(tmp_path: Path) -> None:
    detected = tmp_path / "xwechat_files"
    setup = _StubSetupService(detected_root=detected)
    facade = ChatAnalyzerFacade(wechat_setup_service=setup)

    assert facade.detect_wechat_data_root() == detected
    assert setup.detects == 1


def test_facade_detect_requires_setup_service() -> None:
    facade = ChatAnalyzerFacade()

    with pytest.raises(SourceUnavailable):
        facade.detect_wechat_data_root()


def test_facade_translates_detect_failure(tmp_path: Path) -> None:
    facade = ChatAnalyzerFacade(
        wechat_setup_service=_StubSetupService(
            error=RuntimeError("home 0xdeadbeef")
        )
    )

    with pytest.raises(FacadeError) as caught:
        facade.detect_wechat_data_root()

    assert caught.value.source is ChatSource.WECHAT
    assert isinstance(caught.value.public_message, str)


def test_facade_requires_setup_service(tmp_path: Path) -> None:
    facade = ChatAnalyzerFacade()

    with pytest.raises(SourceUnavailable):
        facade.setup_wechat_environment(_config(tmp_path))

    with pytest.raises(SourceUnavailable):
        facade.get_wechat_setup_status()


def test_facade_translates_setup_errors(tmp_path: Path) -> None:
    facade = ChatAnalyzerFacade(
        wechat_setup_service=_StubSetupService(
            error=WeChatConfigWriteFailed()
        )
    )

    with pytest.raises(FacadeError) as caught:
        facade.setup_wechat_environment(_config(tmp_path))

    assert caught.value.code == "wechat_config_write_failed"
    assert caught.value.source is ChatSource.WECHAT
    assert caught.value.public_message


def test_facade_translates_unexpected_setup_failure(tmp_path: Path) -> None:
    facade = ChatAnalyzerFacade(
        wechat_setup_service=_StubSetupService(
            error=RuntimeError("native 0xdeadbeef")
        )
    )

    with pytest.raises(FacadeError) as caught:
        facade.get_wechat_setup_status()

    assert caught.value.source is ChatSource.WECHAT
    assert isinstance(caught.value.public_message, str)


def test_composition_root_wires_setup_service() -> None:
    from qq_chat_analyzer.gui import app as gui_app

    facade = gui_app.build_facade()

    status = facade.get_wechat_setup_status()
    assert hasattr(status, "state")
    assert hasattr(status, "message")


def test_composition_root_shares_factory_with_setup() -> None:
    from qq_chat_analyzer.gui import app as gui_app

    facade = gui_app.build_facade()

    setup = facade._wechat_setup_service
    connection = facade._wechat_connection_service
    assert setup._provider_factory is connection._shared_factory


def test_facade_passes_progress_to_acquire_db_key(tmp_path: Path) -> None:
    """The facade must relay the progress callback to the setup service."""
    service = _ProgressCapturingSetupService()
    facade = ChatAnalyzerFacade(wechat_setup_service=service)

    seen = []
    facade.acquire_wechat_db_key(progress=seen.append)

    assert service.progress_callbacks
    assert callable(service.progress_callbacks[0])
