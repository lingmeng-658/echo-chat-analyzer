"""Desktop NapCat defaults and connection lifecycle; all runtimes fictional."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from qq_chat_analyzer.application.qq import qq_environment_config as env
from qq_chat_analyzer.application.qq.qq_connection_service import QQConnectionService
from qq_chat_analyzer.application.qq.qq_direct_database_import_service import QQDirectDatabaseImportService, _group_member_data
from qq_chat_analyzer.application.qq.qq_provider_factory import default_provider_builder
from qq_chat_analyzer.providers.napcat_qq_provider import NapCatQQProvider, NapCatStatus, NapCatFriend, NapCatGroup
from qq_chat_analyzer.gui import app


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    directory=tmp_path/'runtime/qq-napcat-candidate'
    for name in ['napcat.mjs','NapCatWinBootMain.exe','NapCatWinBootHook.dll','plugins/napcat-plugin-echo/index.mjs','plugins/napcat-plugin-echo/bridge.mjs']:
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fictional')
    monkeypatch.setattr(env,'default_qq_runtime_directory',lambda:directory,raising=False)
    monkeypatch.setattr(env,'user_data_dir',lambda:tmp_path)
    monkeypatch.delenv('ECHO_QQ_RUNTIME',raising=False)
    return directory


def status(online=True, passphrase=False, uin='12345678'):
    return NapCatStatus(True,online,{'uin':uin,'uid':'u_self','nickname':'Self'},True,passphrase,True)


def test_default_desktop_uses_candidate_and_shared_config(candidate, monkeypatch):
    factory=app._qq_provider_factory()
    config=factory.config_loader.load_or_default()
    assert config.runtime_directory==candidate
    assert config.napcat_bridge_url=='http://127.0.0.1:40655'
    assert isinstance(factory.create(),NapCatQQProvider)
    service=app._optional_qq_service(factory)
    assert service._config_loader is factory.config_loader
    assert service._require_runtime_client()._base_url==config.napcat_bridge_url
    setup=app._optional_qq_setup_service(factory,app._optional_qq_connection_service(factory))
    assert setup._config_loader is factory.config_loader
    assert setup.check_setup().runtime_available


def test_missing_candidate_never_falls_back_to_qce(candidate, tmp_path, monkeypatch):
    (candidate/'napcat.mjs').unlink()
    old=tmp_path/'qq';old.mkdir();qce=old/'qce-server.exe';qce.write_text('fictional')
    monkeypatch.setattr(env,'bundled_qq_runtime_available',lambda:True)
    factory=app._qq_provider_factory()
    assert isinstance(factory.create(),NapCatQQProvider)
    config=factory.config_loader.load_or_default()
    assert config.runtime_directory==candidate




def test_login_and_direct_db_readiness_are_separate(monkeypatch):
    provider=NapCatQQProvider()
    def forbidden(*args, **kwargs):
        pytest.fail('Default Desktop must not use QCE health or token')
    monkeypatch.setattr(provider, 'health_check', forbidden, raising=False)
    monkeypatch.setattr(provider, 'resolve_token', forbidden, raising=False)
    monkeypatch.setattr(provider,'status',lambda:status())
    service=QQConnectionService(provider)
    result=service.check_status()
    assert result.available and result.runtime_running
    assert not result.direct_db_ready
    monkeypatch.setattr(provider,'status',lambda:status(passphrase=True))
    assert service.check_status().direct_db_ready
    monkeypatch.setattr(provider,'status',lambda:status(uin='u_uid'))
    assert not service.check_status().available
    monkeypatch.setattr(provider,'status',lambda:status(online=False))
    assert not service.check_status().available


def test_metadata_no_qce_pagination_and_members_preserve_identity(monkeypatch):
    provider=NapCatQQProvider();calls=[]
    def groups():calls.append('groups');return [NapCatGroup('23456789','Group',2)]
    def friends():calls.append('friends');return [NapCatFriend('u_friend','34567890','Nick','Remark')]
    monkeypatch.setattr(provider,'list_groups',groups);monkeypatch.setattr(provider,'list_friends',friends)
    service=QQDirectDatabaseImportService(provider_factory=SimpleNamespace(create=lambda:provider))
    assert service._metadata_names()==({'23456789':'Group'},{'34567890':'Remark'})
    assert calls==['groups','friends']
    mapped=_group_member_data({'result':{'infos':{'u_friend':{'uin':'34567890','uid':'u_friend','nick':'Nick','cardName':'Card'}}}})
    assert mapped['names']=={'34567890':'Card'}


def test_connection_state_machine_reuses_retries_and_relogin(candidate,monkeypatch):
    from qq_chat_analyzer.application.qq.qq_auth_bridge import QQAuthBridge
    from qq_chat_analyzer.application.qq.qq_setup_service import QQSetupService
    from qq_chat_analyzer.application.qq.qq_runtime_manager import QQRuntimeStatus,QQRuntimeState
    from qq_chat_analyzer.application.connection_models import ConnectionState
    provider=NapCatQQProvider();current=[status(online=False)]
    monkeypatch.setattr(provider,'status',lambda:current[0])
    config=env.QQEnvironmentConfig(runtime_directory=candidate)
    runtime=SimpleNamespace(get_status=lambda:QQRuntimeStatus(QQRuntimeState.STOPPED,True),stop=lambda:QQRuntimeStatus(QQRuntimeState.STOPPED,True))
    setup=QQSetupService(config_loader=SimpleNamespace(load_or_default=lambda:config),runtime_manager=runtime)
    launched=[]
    def forbidden():
        pytest.fail('NapCat authorization must not prepare QCE/security.json')
    auth=QQAuthBridge(setup_service=setup,connection_service=QQConnectionService(provider),window_launcher=lambda:launched.append(1))
    assert auth.start_auth_flow().state is ConnectionState.WAITING_AUTH
    assert auth.start_auth_flow().state is ConnectionState.WAITING_AUTH
    assert len(launched)==1
    # Cancel before login, then retry through the same state machine.
    assert auth.disconnect().state is ConnectionState.DISCONNECTED
    assert auth.start_auth_flow().state is ConnectionState.WAITING_AUTH
    assert len(launched)==2
    current[0]=status(passphrase=True)
    assert auth.get_snapshot().state is ConnectionState.CONNECTED
    current[0]=status(online=False)
    auth.disconnect()
    assert auth.start_auth_flow().state is ConnectionState.WAITING_AUTH
    assert len(launched)==3
    current[0]=status(uin='45678901')
    assert auth.get_snapshot().state is ConnectionState.CONNECTED


def test_native_launcher_uses_detected_qq_and_never_qce(candidate,tmp_path,monkeypatch):
    from qq_chat_analyzer.application.qq import qq_auth_bridge as auth
    qq=tmp_path/'QQ.exe';qq.write_bytes(b'fictional')
    package=tmp_path/'resources/app/package.json';package.parent.mkdir(parents=True);package.write_text('{"name":"QQ","main":"index.js"}')
    seen=[]
    process=SimpleNamespace(pid=12345,poll=lambda:None)
    monkeypatch.setattr(auth.subprocess,'Popen',lambda command,**options:seen.append((command,options)) or process)
    config=env.QQEnvironmentConfig(qq_install_path=qq,runtime_directory=candidate)
    assert auth.default_auth_window_launcher(config)() is process
    command,options=seen[0]
    assert command[:3]==[str(candidate/'NapCatWinBootMain.exe'),str(qq),str(candidate/'NapCatWinBootHook.dll')]
    assert 'qce-server' not in ' '.join(command)
    assert options['env']['NAPCAT_MAIN_PATH']==str(candidate/'napcat.mjs')
    assert options['env']['ECHO_BRIDGE_PORT']=='40655'


def test_napcat_setup_waiting_status_does_not_claim_qce(candidate):
    from qq_chat_analyzer.application.qq.qq_setup_service import QQSetupService
    from qq_chat_analyzer.application.qq.qq_runtime_manager import QQRuntimeStatus, QQRuntimeState
    config = env.QQEnvironmentConfig(runtime_directory=candidate)
    running = QQRuntimeStatus(QQRuntimeState.RUNNING, True)
    runtime = SimpleNamespace(get_status=lambda: running)
    setup = QQSetupService(
        config_loader=SimpleNamespace(load_or_default=lambda: config),
        config_writer=SimpleNamespace(write=lambda config: None),
        runtime_manager=runtime,
    )
    result = setup.connect()
    assert result.runtime_running
    assert not result.available and not result.direct_db_ready
