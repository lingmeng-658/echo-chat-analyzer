"""Behavior tests for the WeChat connection layer.

The service under test never reads a real WeChat database. Provider probes are
simulated with stubs so the tests cover data present, data missing, missing
key, missing runtime, and unexpected failures without touching real chat data.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_connection_service"
    )


def _config_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_environment_config"
    )


class _FakeConfigLoader:
    def __init__(self, config=None, error=None):
        self._config = config
        self._error = error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._config


class _RecordingProviderFactory:
    def __init__(self, provider):
        self._provider = provider
        self.calls = []

    def __call__(self, config):
        self.calls.append(config)
        return self._provider


def _provider_module():
    return importlib.import_module(
        "qq_chat_analyzer.providers.wechat_database_provider"
    )


class _FakeProvider:
    """Stand in for WeChatDatabaseProvider with configurable readiness."""

    def __init__(
        self,
        *,
        data: bool = True,
        key: str | None = "fictional-key",
        helper: bool = True,
        library: bool = True,
        unexpected: str | None = None,
    ) -> None:
        self._data = data
        self._key = key
        self._helper = helper
        self._library = library
        self._unexpected = unexpected
        self.data_calls = 0
        self.key_calls = 0
        self.helper_calls = 0
        self.library_calls = 0

    def _session_db_path(self):
        self.data_calls += 1
        if self._unexpected == "data":
            raise RuntimeError("raw data probe failure")
        if not self._data:
            raise _provider_module().DatabaseNotFound()
        return Path("fictional/session.db")

    def _resolve_key(self):
        self.key_calls += 1
        if self._unexpected == "key":
            raise RuntimeError("raw key probe failure")
        if self._key is None:
            raise _provider_module().KeyUnavailable()
        return self._key

    def _resolve_helper(self):
        self.helper_calls += 1
        if self._unexpected == "helper":
            raise RuntimeError("raw helper probe failure")
        if not self._helper:
            raise _provider_module().WcdbHelperNotFound()
        return Path("fictional/wcdb_cli.exe")

    def _resolve_library(self):
        self.library_calls += 1
        if self._unexpected == "library":
            raise RuntimeError("raw library probe failure")
        if not self._library:
            raise _provider_module().WcdbLibraryNotFound()
        return Path("fictional/WCDB.dll")


def _status(**provider_kwargs):
    service = _module().WeChatConnectionService(
        _FakeProvider(**provider_kwargs)
    )
    return service.check_status()


# ------------------------------------------------------------ all available


def test_all_readiness_checks_pass_marks_source_available() -> None:
    status = _status(data=True, key="fictional-key", helper=True, library=True)

    assert status.available is True
    assert status.data_found is True
    assert status.db_key_available is True
    assert status.runtime_available is True
    assert status.message != ""
    assert status.action_hint != ""


# --------------------------------------------------------------- data missing


def test_missing_data_directory_returns_user_facing_message() -> None:
    status = _status(data=False, key="fictional-key")

    assert status.available is False
    assert status.data_found is False
    assert status.db_key_available is True
    assert status.runtime_available is True
    assert (
        "\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55"
        in status.message
    )
    assert status.action_hint != ""


# ------------------------------------------------------------------- key


def test_missing_db_key_returns_user_facing_message() -> None:
    status = _status(data=True, key=None)

    assert status.available is False
    assert status.data_found is True
    assert status.db_key_available is False
    assert status.runtime_available is True
    assert "\u5bc6\u94a5" in status.message
    assert status.action_hint != ""


def test_blank_db_key_counts_as_missing() -> None:
    status = _status(data=True, key="   ")

    assert status.available is False
    assert status.db_key_available is False


# ---------------------------------------------------------------- runtime


@pytest.mark.parametrize("missing", ["helper", "library"])
def test_missing_runtime_returns_user_facing_message(missing: str) -> None:
    provider_kwargs = {
        "data": True,
        "key": "fictional-key",
        "helper": True,
        "library": True,
    }
    provider_kwargs[missing] = False
    status = _status(**provider_kwargs)

    assert status.available is False
    assert status.data_found is True
    assert status.db_key_available is True
    assert status.runtime_available is False
    assert (
        "\u8bfb\u53d6\u7ec4\u4ef6\u4e0d\u5b8c\u6574"
        in status.message
    )
    assert status.action_hint != ""


# ------------------------------------------------------------ error isolation


@pytest.mark.parametrize("stage", ["data", "key", "helper", "library"])
def test_unexpected_probe_error_never_leaks(stage: str) -> None:
    status = _status(unexpected=stage)

    assert status.available is False
    assert "raw" not in status.message
    assert "Traceback" not in status.message
    assert "Exception" not in status.message
    assert status.action_hint != ""


def test_check_status_never_raises_on_unknown_provider_failure() -> None:
    provider = _FakeProvider(unexpected="data")
    service = _module().WeChatConnectionService(provider)

    status = service.check_status()

    assert status.available is False
    assert status.message != ""


# ------------------------------------------------------------ config source


def test_connection_service_builds_provider_from_config() -> None:
    module = _module()
    config_module = _config_module()
    config = config_module.WeChatEnvironmentConfig(
        data_root=Path("C:\\WeChatData"),
        db_key="fictional-key",
        wcdb_cli_path=Path("C:\\tools\\wcdb_cli.exe"),
        wcdb_dll_path=Path("C:\\tools\\WCDB.dll"),
    )
    provider = _FakeProvider()
    factory = _RecordingProviderFactory(provider)
    service = module.WeChatConnectionService(
        config_loader=_FakeConfigLoader(config=config),
        provider_factory=factory,
    )

    status = service.check_status()

    assert status.available is True
    assert factory.calls == [config]
    assert provider.data_calls == 1


def test_missing_config_becomes_user_facing_status() -> None:
    module = _module()
    config_module = _config_module()
    service = module.WeChatConnectionService(
        config_loader=_FakeConfigLoader(
            error=config_module.WeChatConfigNotFound()
        ),
        provider_factory=_RecordingProviderFactory(_FakeProvider()),
    )

    status = service.check_status()

    assert status.available is False
    assert status.data_found is False
    assert status.db_key_available is False
    assert status.runtime_available is False
    assert "\u73af\u5883\u914d\u7f6e" in status.message
    assert status.action_hint != ""


def test_corrupted_config_becomes_user_facing_status() -> None:
    module = _module()
    config_module = _config_module()
    service = module.WeChatConnectionService(
        config_loader=_FakeConfigLoader(
            error=config_module.WeChatConfigCorrupted()
        ),
        provider_factory=_RecordingProviderFactory(_FakeProvider()),
    )

    status = service.check_status()

    assert status.available is False
    assert "\u91cd\u65b0\u8bbe\u7f6e" in status.message
    assert status.action_hint != ""


def test_config_loader_error_never_leaks() -> None:
    module = _module()
    service = module.WeChatConnectionService(
        config_loader=_FakeConfigLoader(
            error=RuntimeError("raw config boom")
        ),
        provider_factory=_RecordingProviderFactory(_FakeProvider()),
    )

    status = service.check_status()

    assert status.available is False
    assert "raw config boom" not in status.message
    assert "Traceback" not in status.message


# ------------------------------------------------------------------- model


def test_status_is_a_frozen_dataclass() -> None:
    module = _module()
    status = module.WeChatConnectionStatus(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u53ef\u7528",
        action_hint="\u5f00\u59cb\u5206\u6790",
    )

    try:
        status.message = "changed"
    except Exception as error:
        assert type(error).__name__ == "FrozenInstanceError"
    else:  # pragma: no cover - guards the immutability contract
        raise AssertionError("WeChatConnectionStatus should be immutable")


def test_service_checks_probes_without_reading_sessions() -> None:
    provider = _FakeProvider()
    service = _module().WeChatConnectionService(provider)

    service.check_status()

    assert provider.data_calls == 1
    assert provider.key_calls == 1
    assert provider.helper_calls == 1
    assert provider.library_calls == 1
