"""RED tests for Phase 8.6.4B: unified WeChat provider configuration.

These tests pin the invariant that the WeChat connection status and the
WeChat session/message reads are built from one configuration source and one
provider instance. No real WeChat data, keys, or databases are involved.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _factory_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_provider_factory"
    )


def _config_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_environment_config"
    )


def _connection_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_connection_service"
    )


def _export_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_export_import_service"
    )


def _write_config(directory: Path, **overrides) -> Path:
    (directory / "wcdb_cli.exe").write_text("fake", encoding="utf-8")
    (directory / "WCDB.dll").write_text("fake", encoding="utf-8")
    payload = {
        "data_root": str(directory / "data"),
        "db_key": "fictional-key",
        "wcdb_cli_path": str(directory / "wcdb_cli.exe"),
        "wcdb_dll_path": str(directory / "WCDB.dll"),
    }
    payload.update(overrides)
    config_path = directory / "wechat.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


class _StubProvider:
    def __init__(self, config):
        self.config = config


def _factory(tmp_path, *, builder=_StubProvider, **overrides):
    config_module = _config_module()
    loader = config_module.WeChatEnvironmentConfigLoader(
        _write_config(tmp_path, **overrides)
    )
    return _factory_module().WeChatProviderFactory(
        config_loader=loader,
        provider_builder=builder,
    )


# ------------------------------------------------------- factory behaviour


def test_factory_builds_provider_from_config(tmp_path):
    factory = _factory(tmp_path)

    provider = factory.create()

    assert isinstance(provider, _StubProvider)
    assert provider.config.data_root == tmp_path / "data"
    assert provider.config.db_key == "fictional-key"
    assert provider.config.wcdb_cli_path == tmp_path / "wcdb_cli.exe"
    assert provider.config.wcdb_dll_path == tmp_path / "WCDB.dll"


def test_factory_reuses_one_provider_instance(tmp_path):
    factory = _factory(tmp_path)

    assert factory.create() is factory.create()


def test_factory_reloads_config_after_invalidate(tmp_path):
    factory = _factory(tmp_path, db_key="first-key")

    first = factory.create()
    assert first.config.db_key == "first-key"

    _write_config(tmp_path, db_key="second-key")
    factory.invalidate()
    second = factory.create()

    assert second is not first
    assert second.config.db_key == "second-key"


def test_factory_missing_config_raises_user_safe_error(tmp_path):
    config_module = _config_module()

    class _MissingLoader:
        def load(self):
            raise config_module.WeChatConfigNotFound()

        def load_or_default(self):
            raise config_module.WeChatConfigNotFound()

    factory = _factory_module().WeChatProviderFactory(
        config_loader=_MissingLoader(),
        provider_builder=_StubProvider,
    )

    with pytest.raises(config_module.WeChatEnvironmentConfigError) as error:
        factory.create()

    assert error.value.public_message
    assert "Traceback" not in error.value.public_message


def test_factory_uses_load_or_default_for_missing_config(tmp_path):
    module = _factory_module()
    config_module = _config_module()
    default_config = config_module.WeChatEnvironmentConfig(
        wcdb_cli_path=tmp_path / "bundled" / "wcdb_cli.exe",
        wcdb_dll_path=tmp_path / "bundled" / "WCDB.dll",
    )

    class _DefaultLoader:
        def load(self):
            raise config_module.WeChatConfigNotFound()

        def load_or_default(self):
            return default_config

    built = []

    def _builder(config):
        built.append(config)
        return _StubProvider(config)

    factory = module.WeChatProviderFactory(
        config_loader=_DefaultLoader(),
        provider_builder=_builder,
    )

    provider = factory.create()

    assert built == [default_config]
    assert provider.config.wcdb_cli_path == (
        tmp_path / "bundled" / "wcdb_cli.exe"
    )
    assert provider.config.wcdb_dll_path == (
        tmp_path / "bundled" / "WCDB.dll"
    )


def test_factory_builder_failure_becomes_user_safe_error(tmp_path):
    def _explode(config):
        raise RuntimeError("wcdb handle 0x7ffd exploded")

    factory = _factory(tmp_path, builder=_explode)

    with pytest.raises(_factory_module().WeChatProviderUnavailable) as error:
        factory.create()

    assert error.value.public_message
    assert "0x7ffd" not in error.value.public_message
    assert "0x7ffd" not in str(error.value)


# ------------------------------------------- shared source across services


def test_connection_and_export_services_share_one_provider(tmp_path):
    factory = _factory(tmp_path)

    connection_service = _connection_module().WeChatConnectionService(
        provider_factory=factory,
    )
    export_service = _export_module().WeChatExportImportService(
        provider_factory=factory,
    )

    assert connection_service.provider() is export_service.provider()


def test_config_change_is_visible_to_both_services(tmp_path):
    factory = _factory(tmp_path, db_key="first-key")

    connection_service = _connection_module().WeChatConnectionService(
        provider_factory=factory,
    )
    export_service = _export_module().WeChatExportImportService(
        provider_factory=factory,
    )

    assert connection_service.provider().config.db_key == "first-key"

    _write_config(tmp_path, db_key="second-key")
    factory.invalidate()

    assert connection_service.provider().config.db_key == "second-key"
    assert export_service.provider().config.db_key == "second-key"
    assert connection_service.provider() is export_service.provider()


def test_export_service_provider_failure_is_user_safe(tmp_path):
    def _explode(config):
        raise RuntimeError("native wcdb crash 0xdeadbeef")

    factory = _factory(tmp_path, builder=_explode)
    export_service = _export_module().WeChatExportImportService(
        provider_factory=factory,
    )

    with pytest.raises(_factory_module().WeChatProviderUnavailable) as error:
        export_service.list_sessions()

    assert "0xdeadbeef" not in error.value.public_message


def test_connection_service_provider_failure_becomes_status(tmp_path):
    def _explode(config):
        raise RuntimeError("native wcdb crash 0xdeadbeef")

    factory = _factory(tmp_path, builder=_explode)
    connection_service = _connection_module().WeChatConnectionService(
        provider_factory=factory,
    )

    status = connection_service.check_status()

    assert status.available is False
    assert status.message
    assert "0xdeadbeef" not in status.message
    assert "0xdeadbeef" not in status.action_hint


# ----------------------------------------------------- architecture guards


def test_gui_package_does_not_reference_wechat_provider():
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"

    for path in gui_directory.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "WeChatDatabaseProvider" not in source, path
        assert "wechat_database_provider" not in source, path


def test_export_import_service_does_not_import_provider_module():
    source = (
        SRC_ROOT
        / "qq_chat_analyzer"
        / "application"
        / "wechat_export_import_service.py"
    ).read_text(encoding="utf-8")

    assert "from ..providers" not in source
