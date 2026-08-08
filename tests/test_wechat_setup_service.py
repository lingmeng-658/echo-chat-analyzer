"""Tests for the WeChat setup service and config writer.

Privacy: every path, key, and identifier here is fabricated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qq_chat_analyzer.application.wechat_environment_config import (
    WeChatConfigCorrupted,
    WeChatConfigNotFound,
    WeChatConfigWriteFailed,
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigLoader,
    WeChatEnvironmentConfigWriter,
)
from qq_chat_analyzer.application.wechat_provider_factory import (
    WeChatProviderFactory,
)
from qq_chat_analyzer.application.wechat_setup_service import (
    WeChatSetupService,
    WeChatSetupState,
    WeChatSetupStatus,
)


def _config(tmp_path: Path) -> WeChatEnvironmentConfig:
    return WeChatEnvironmentConfig(
        data_root=tmp_path / "fake_xwechat_files",
        db_key="0f0f0f0f",
        wcdb_cli_path=tmp_path / "runtime" / "wcdb_cli.exe",
        wcdb_dll_path=tmp_path / "runtime" / "WCDB.dll",
    )


class _StubConnectionService:
    def __init__(self, status: object) -> None:
        self._status = status
        self.calls = 0

    def check_status(self) -> object:
        self.calls += 1
        return self._status


# ------------------------------------------------------------------- writer


def test_writer_saves_config_as_stable_json(tmp_path: Path) -> None:
    target = tmp_path / "config" / "wechat.json"
    writer = WeChatEnvironmentConfigWriter(target)

    writer.save(_config(tmp_path))

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["db_key"] == "0f0f0f0f"
    assert payload["data_root"] == str(tmp_path / "fake_xwechat_files")
    assert list(payload) == sorted(payload)


def test_writer_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "config" / "wechat.json"
    writer = WeChatEnvironmentConfigWriter(target)

    writer.save(_config(tmp_path))

    assert target.exists()


def test_writer_round_trips_through_loader(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    original = _config(tmp_path)

    WeChatEnvironmentConfigWriter(target).save(original)
    restored = WeChatEnvironmentConfigLoader(target).load()

    assert restored == original


def test_writer_omits_absent_optional_fields(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    writer = WeChatEnvironmentConfigWriter(target)

    writer.save(WeChatEnvironmentConfig(data_root=tmp_path / "only_root"))

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "data_root" in payload
    assert payload.get("db_key") is None


def test_writer_converts_os_error_to_user_safe_error(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("ENOSPC on device 0xdeadbeef")

    writer = WeChatEnvironmentConfigWriter(target, writer=_explode)

    with pytest.raises(WeChatConfigWriteFailed) as caught:
        writer.save(_config(tmp_path))

    assert caught.value.code == "wechat_config_write_failed"
    assert caught.value.public_message
    assert "0xdeadbeef" not in caught.value.public_message
    assert "ENOSPC" not in caught.value.public_message


# ------------------------------------------------------------- check_setup


def test_check_setup_reports_missing_config(tmp_path: Path) -> None:
    loader = WeChatEnvironmentConfigLoader(tmp_path / "absent.json")
    service = WeChatSetupService(config_loader=loader)

    status = service.check_setup()

    assert isinstance(status, WeChatSetupStatus)
    assert status.state is WeChatSetupState.CONFIG_MISSING
    assert status.configured is False
    assert status.message
    assert status.action_hint


def test_check_setup_reports_ready_config(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    WeChatEnvironmentConfigWriter(target).save(_config(tmp_path))
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target)
    )

    status = service.check_setup()

    assert status.state is WeChatSetupState.CONFIG_READY
    assert status.configured is True


def test_check_setup_reports_invalid_config(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    target.write_text("{ this is not json", encoding="utf-8")
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target)
    )

    status = service.check_setup()

    assert status.state is WeChatSetupState.CONFIG_INVALID
    assert status.configured is False


def test_check_setup_never_raises_loader_errors(tmp_path: Path) -> None:
    class _AngryLoader:
        def config_path(self) -> Path:
            return tmp_path / "wechat.json"

        def load(self) -> WeChatEnvironmentConfig:
            raise RuntimeError("native handle 0xfeedface collapsed")

    status = WeChatSetupService(config_loader=_AngryLoader()).check_setup()

    assert status.state is WeChatSetupState.CONFIG_INVALID
    assert "0xfeedface" not in status.message


def test_check_setup_exposes_config_path(tmp_path: Path) -> None:
    target = tmp_path / "config" / "wechat.json"
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target)
    )

    assert service.check_setup().config_path == target


# --------------------------------------------------------- save_environment


def test_save_environment_persists_config(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target),
    )

    service.save_environment(_config(tmp_path))

    assert WeChatEnvironmentConfigLoader(target).load() == _config(tmp_path)
    assert service.check_setup().state is WeChatSetupState.CONFIG_READY


def test_save_environment_invalidates_provider_factory(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    builds: list[WeChatEnvironmentConfig] = []

    def _builder(config: WeChatEnvironmentConfig) -> object:
        builds.append(config)
        return object()

    WeChatEnvironmentConfigWriter(target).save(
        WeChatEnvironmentConfig(data_root=tmp_path / "first_root")
    )
    factory = WeChatProviderFactory(
        config_loader=WeChatEnvironmentConfigLoader(target),
        provider_builder=_builder,
    )
    factory.create()
    assert builds[0].data_root == tmp_path / "first_root"

    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target),
        provider_factory=factory,
    )
    service.save_environment(
        WeChatEnvironmentConfig(data_root=tmp_path / "second_root")
    )
    factory.create()

    assert len(builds) == 2
    assert builds[1].data_root == tmp_path / "second_root"


def test_save_environment_returns_fresh_connection_status(
    tmp_path: Path,
) -> None:
    target = tmp_path / "wechat.json"
    sentinel = object()
    connection = _StubConnectionService(sentinel)
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target),
        connection_service=connection,
    )

    result = service.save_environment(_config(tmp_path))

    assert result is sentinel
    assert connection.calls == 1


def test_save_environment_without_connection_service(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target),
    )

    assert service.save_environment(_config(tmp_path)) is None


def test_save_environment_rejects_wrong_type(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target),
    )

    with pytest.raises(WeChatSetupService.InvalidEnvironment) as caught:
        service.save_environment({"data_root": "not a config"})

    assert caught.value.public_message


def test_save_environment_propagates_write_failure(tmp_path: Path) -> None:
    target = tmp_path / "wechat.json"

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk 0xbadf00d offline")

    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target, writer=_explode),
    )

    with pytest.raises(WeChatConfigWriteFailed) as caught:
        service.save_environment(_config(tmp_path))

    assert "0xbadf00d" not in caught.value.public_message


def test_save_environment_does_not_invalidate_on_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "wechat.json"

    class _CountingFactory:
        def __init__(self) -> None:
            self.invalidations = 0

        def invalidate(self) -> None:
            self.invalidations += 1

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise OSError("write refused")

    factory = _CountingFactory()
    service = WeChatSetupService(
        config_loader=WeChatEnvironmentConfigLoader(target),
        config_writer=WeChatEnvironmentConfigWriter(target, writer=_explode),
        provider_factory=factory,
    )

    with pytest.raises(WeChatConfigWriteFailed):
        service.save_environment(_config(tmp_path))

    assert factory.invalidations == 0


# ------------------------------------------------------- boundary contracts


def test_setup_service_does_not_touch_database_modules() -> None:
    from qq_chat_analyzer.application import wechat_setup_service as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "WeChatDatabaseProvider" not in source
    assert "wechat_db_adapter" not in source
    assert "import sqlite3" not in source


def test_loader_errors_remain_distinct(tmp_path: Path) -> None:
    missing = WeChatEnvironmentConfigLoader(tmp_path / "nope.json")
    with pytest.raises(WeChatConfigNotFound):
        missing.load()

    broken = tmp_path / "broken.json"
    broken.write_text("[]", encoding="utf-8")
    with pytest.raises(WeChatConfigCorrupted):
        WeChatEnvironmentConfigLoader(broken).load()