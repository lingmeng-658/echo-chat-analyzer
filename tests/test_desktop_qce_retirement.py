"""Desktop retirement contracts; CLI compatibility remains independently owned."""
from dataclasses import fields
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from qq_chat_analyzer.application import qq_environment_config as env
from qq_chat_analyzer.application.qq_connection_service import QQConnectionStatus
from qq_chat_analyzer.gui import app
from qq_chat_analyzer.providers.napcat_qq_provider import NapCatQQProvider
from qq_chat_analyzer.runtime import QQRuntimeConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('model', [env.QQEnvironmentConfig, QQConnectionStatus, QQRuntimeConfig])
def test_desktop_models_have_no_qce_runtime_or_auth_fields(model):
    names = {field.name for field in fields(model)}
    assert not names & {'runtime_backend', 'qce_path', 'qce_config_directory',
                        'qce_running', 'authenticated', 'security_path',
                        'config_directory', 'static_directory', 'bridge_url'}


@pytest.mark.parametrize('selection', ['qce', 'invalid'])
def test_old_rollback_environment_cannot_select_desktop_provider(selection, monkeypatch, tmp_path):
    monkeypatch.setenv('ECHO_QQ_RUNTIME', selection)
    monkeypatch.setattr(env, 'user_data_dir', lambda: tmp_path)
    assert isinstance(app._qq_provider_factory().create(), NapCatQQProvider)


def test_old_saved_qce_settings_cannot_reintroduce_old_runtime(tmp_path, monkeypatch):
    candidate = tmp_path / 'runtime/qq-napcat-candidate'
    monkeypatch.setattr(env, 'default_qq_runtime_directory', lambda: candidate)
    path = tmp_path / 'qq.json'
    path.write_text(json.dumps({'runtime_backend': 'qce', 'qq_install_path': 'D:/fictional/QQ.exe',
        'runtime_directory': str(tmp_path / 'runtime/qq'), 'qce_path': 'qce-server.exe',
        'base_url': 'http://127.0.0.1:40653', 'napcat_bridge_url': 'http://127.0.0.1:40654',
        'security_path': 'security.json'}), encoding='utf-8')
    loader = env.QQEnvironmentConfigLoader(path)
    config = loader.load_or_default()
    assert config.runtime_directory == candidate
    assert config.qq_install_path == Path('D:/fictional/QQ.exe')
    assert config.napcat_bridge_url == 'http://127.0.0.1:40655'
    env.QQEnvironmentConfigWriter(path).save(config)
    assert set(json.loads(path.read_text())) == {
        'qq_install_path', 'runtime_directory', 'napcat_bridge_url', 'version'}


@pytest.mark.parametrize('relative', ['scripts/bootstrap_qq_runtime.ps1',
    'scripts/qq_runtime_pins.json', 'scripts/qq_qce_compat_runtime_manifest.json',
    'src/qq_chat_analyzer/application/qq_webui_config.py',
    'src/qq_chat_analyzer/gui/qq_setup_dialog.py'])
def test_unconsumed_desktop_qce_surface_is_retired(relative):
    assert not (ROOT / relative).exists()


def test_desktop_metadata_requires_no_qce_pagination_or_provider_type_branch():
    from qq_chat_analyzer.application.qq_direct_database_import_service import QQDirectDatabaseImportService
    calls = []
    class Provider:
        def list_groups(self):
            calls.append('groups')
            return [SimpleNamespace(group_code='12345', group_name='Fictional Group')]
        def list_friends(self):
            calls.append('friends')
            return [SimpleNamespace(uin='23456', display_name='Fictional Friend')]
    service = QQDirectDatabaseImportService(provider_factory=SimpleNamespace(create=Provider))
    assert service._metadata_names() == ({'12345': 'Fictional Group'}, {'23456': 'Fictional Friend'})
    assert calls == ['groups', 'friends']
