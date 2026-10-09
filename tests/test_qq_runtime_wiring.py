"""Read-only releases and writable QQ workspaces, using fictional assets only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from qq_chat_analyzer.application.qq import qq_auth_bridge as auth
from qq_chat_analyzer.application.qq import qq_environment_config as env
from qq_chat_analyzer.application.qq import qq_runtime_workspace as workspace
from qq_chat_analyzer.application.qq.qq_setup_service import QQSetupService
from qq_chat_analyzer.application.qq.qq_direct_database_import_service import QQDirectDatabaseImportService
from qq_chat_analyzer.application.connection_models import ConnectionSnapshot, ConnectionState

ROOT = Path(__file__).resolve().parents[1]


def _launch_target():
    return (auth, "launch_owned_process") if auth.os.name == "nt" else (auth.subprocess, "Popen")


@pytest.fixture
def release(tmp_path, monkeypatch):
    program = tmp_path / '发行 中文 # % 空格' / 'runtime/qq-napcat-candidate'
    metadata = tmp_path / 'metadata'
    metadata.mkdir()
    templates = {
        'plugins/napcat-plugin-echo/index.mjs': (ROOT / 'scripts/qq_napcat_plugin/index.mjs').read_bytes(),
        'plugins/napcat-plugin-echo/bridge.mjs': (ROOT / 'scripts/qq_napcat_plugin/bridge.mjs').read_bytes(),
        'plugins/napcat-plugin-echo/snapshot/snapshot.mjs': (ROOT / 'scripts/qq_direct_db_snapshot/snapshot.mjs').read_bytes(),
        'plugins/napcat-plugin-echo/snapshot/main_wal.mjs': (ROOT / 'scripts/qq_direct_db_snapshot/main_wal.mjs').read_bytes(),
        'plugins/napcat-plugin-echo/snapshot/workspace.mjs': (ROOT / 'scripts/qq_direct_db_snapshot/workspace.mjs').read_bytes(),
    }
    assets = {**templates, 'config/plugins.json': b'{"napcat-plugin-echo":true}\n',
              'napcat.mjs': b'globalThis.echoFictionalMain = true;',
              'NapCatWinBootMain.exe': b'fictional boot', 'NapCatWinBootHook.dll': b'fictional hook',
              'native/fictional.node': b'fictional native'}
    for name, content in assets.items():
        p = program / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    digest = lambda value: hashlib.sha256(value).hexdigest()
    (metadata / 'pins.json').write_text(json.dumps({
        'upstream': {'version': '4.18.18'},
        'napcatPatch': {'path': 'napcat.mjs', 'patchedSha256': digest(assets['napcat.mjs'])},
        'templates': [{'target': p, 'sha256': digest(v)} for p, v in templates.items()],
        'pluginConfigSha256': digest(assets['config/plugins.json']),
    }), encoding='utf-8')
    manifest = metadata / 'windows_runtime_manifest.json'
    manifest.write_text(json.dumps({'qqPins': 'pins.json', 'requirements': [
        {'path': 'qq-napcat-candidate/' + p, 'type': 'file'} for p in assets
    ]}), encoding='utf-8')
    monkeypatch.setattr(env, 'default_qq_runtime_directory', lambda: program)
    from qq_chat_analyzer import resources
    monkeypatch.setattr(resources, 'resource_path', lambda p: metadata / Path(p).name)
    from qq_chat_analyzer.application.qq import qq_runtime_paths as paths_module
    monkeypatch.setattr(paths_module, 'user_data_root', lambda: tmp_path / 'u')
    qq = tmp_path / 'fictional QQ/QQ.exe'
    qq.parent.mkdir()
    qq.write_bytes(b'fictional QQ')
    package = qq.parent / 'resources/app/package.json'
    package.parent.mkdir(parents=True)
    package.write_text('{"name":"fictional-QQ","main":"original.js"}', encoding='utf-8')
    loader = env.QQEnvironmentConfigLoader(tmp_path / 'settings/qq.json')
    writer = env.QQEnvironmentConfigWriter(loader.config_path())
    writer.save(env.QQEnvironmentConfig(qq_install_path=qq, runtime_directory=program, runtime_mode='managed'))
    return program, loader, qq


def files(directory):
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob('*') if p.is_file()}


def test_managed_launch_reuses_workspace_and_never_writes_release(release, monkeypatch):
    program, loader, qq = release
    before = files(program)
    seen = []
    process = SimpleNamespace(pid=12345, poll=lambda: None)
    monkeypatch.setattr(*_launch_target(), lambda args, **kw: seen.append((args, kw)) or process)
    real_open = Path.open

    def readonly(path, mode='r', *args, **kwargs):
        if path.is_relative_to(program) and any(c in mode for c in 'wax+'):
            raise PermissionError('fictional read-only installation')
        return real_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(Path, 'open', readonly)
        paths = loader.runtime_paths(prepare=True)
        launch = auth.default_auth_window_launcher(loader.load_or_default(), paths=paths)
        assert launch() is process
        (paths.work_root / 'config/napcat.json').write_bytes(b'{"fileLog":true}')
        assert loader.runtime_paths(prepare=True) == paths
        assert launch() is process
    assert files(program) == before
    assert not (program / 'loadNapCat.js').exists()
    for command, options in seen:
        child = options['env']
        assert command == [str(program / 'NapCatWinBootMain.exe'), str(qq), str(program / 'NapCatWinBootHook.dll')]
        assert options['cwd'] == str(paths.work_root)
        assert child['NAPCAT_WORKDIR'] == str(paths.work_root)
        assert child['NAPCAT_LOAD_PATH'] == str(paths.work_root / 'loadNapCat.js')
        assert child['NAPCAT_PATCH_PACKAGE'] == str(paths.work_root / 'qqnt.echo.json')
        assert child['NAPCAT_MAIN_PATH'] == str(program / 'napcat.mjs')
        assert child['ECHO_SNAPSHOT_ROOT'] == str(paths.snapshot_root)
        assert child['ECHO_RUNTIME_ID'] == paths.runtime_id
    assert json.loads((paths.work_root / 'config/plugins.json').read_text())['napcat-plugin-echo'] is True
    assert (paths.work_root / 'plugins/napcat-plugin-echo/index.mjs').read_bytes() == before['plugins/napcat-plugin-echo/index.mjs']
    assert (paths.work_root / 'config/napcat.json').read_bytes() == b'{"fileLog":true}'
    client = QQDirectDatabaseImportService(config_loader=loader)._require_runtime_client()
    assert client._snapshot_root == paths.snapshot_root
    assert client._runtime_id == paths.runtime_id


def test_prepare_precedes_qr_baseline_and_work_cache_preserves_freshness(release, monkeypatch):
    program, loader, qq = release
    paths = loader.runtime_paths(prepare=True)
    qr = paths.work_root / 'cache/qrcode.png'
    qr.parent.mkdir()
    qr.write_bytes(b'fictional old QR')
    setup = QQSetupService(config_loader=loader)
    manager = SimpleNamespace(get_snapshot=lambda: ConnectionSnapshot(ConnectionState.DISCONNECTED, 'qq', ''),
                              begin_auth_waiting=lambda: None, end_auth_waiting=lambda: None)
    events = []
    real_prepare = workspace.prepare_qq_workspace
    monkeypatch.setattr(workspace, 'prepare_qq_workspace', lambda *a, **kw: events.append('prepare') or real_prepare(*a, **kw))
    bridge = auth.QQAuthBridge(setup_service=setup, manager=manager, window_launcher=lambda: events.append('launch'),
                               runtime_cleaner=lambda p: events.append(('clean', p)))
    real_baseline = bridge._remember_qr_baseline
    monkeypatch.setattr(bridge, '_remember_qr_baseline', lambda: events.append('baseline') or real_baseline())
    assert bridge.start_auth_flow().state is ConnectionState.WAITING_AUTH
    assert events.index('prepare') < events.index('baseline') < events.index('launch')
    assert ('clean', program) in events
    assert bridge._qrcode_cache_path() == qr
    assert not bridge.is_qrcode_ready()
    qr.write_bytes(b'fictional new QR with different bytes')
    assert bridge.is_qrcode_ready()


@pytest.mark.parametrize('failure', ['unknown', 'missing-plugin'])
def test_preparation_failure_cannot_start_or_record_qr_baseline(release, monkeypatch, failure):
    program, loader, qq = release
    paths = loader.runtime_paths(prepare=True)
    if failure == 'unknown':
        (paths.work_root / 'unknown.txt').write_bytes(b'keep fictional state')
    else:
        (paths.work_root / 'plugins/napcat-plugin-echo/index.mjs').unlink()
    before = files(paths.work_root)
    calls = []
    setup = QQSetupService(config_loader=loader)
    manager = SimpleNamespace(get_snapshot=lambda: ConnectionSnapshot(ConnectionState.DISCONNECTED, 'qq', ''),
                              begin_auth_waiting=lambda: None, end_auth_waiting=lambda: None)
    bridge = auth.QQAuthBridge(setup_service=setup, manager=manager, window_launcher=lambda: calls.append('launch'))
    assert bridge.start_auth_flow().state is ConnectionState.ERROR
    assert not bridge._qr_session_started
    assert calls == []
    assert files(paths.work_root) == before


def test_managed_old_path_follows_current_release_but_unknown_config_is_preserved(release):
    program, loader, qq = release
    writer = env.QQEnvironmentConfigWriter(loader.config_path())
    writer.save(env.QQEnvironmentConfig(qq_install_path=qq, runtime_directory=program / 'old', runtime_mode='managed'))
    assert loader.runtime_paths(prepare=True).program_root == program
    writer.save(env.QQEnvironmentConfig(qq_install_path=qq, runtime_directory=program))
    before = loader.config_path().read_bytes()
    with pytest.raises(ValueError):
        loader.runtime_paths(prepare=True)
    assert loader.config_path().read_bytes() == before


@pytest.mark.slow_integration
def test_generated_loader_imports_special_character_program_uri(release, monkeypatch):
    program, loader, qq = release
    node = shutil.which('node')
    assert node, 'Node is required for fictional loader integration'
    paths = loader.runtime_paths(prepare=True)
    with monkeypatch.context() as guard:
        guard.setattr(*_launch_target(), lambda *a, **kw: SimpleNamespace(poll=lambda: None))
        auth.default_auth_window_launcher(loader.load_or_default(), paths=paths)()
    script = paths.work_root / 'loadNapCat.js'
    result = subprocess.run([node, '-e', "require(process.argv[1]); setTimeout(()=>{if(!globalThis.echoFictionalMain)process.exitCode=3},100)", str(script)], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


@pytest.mark.slow_integration
def test_generated_bootstrap_reparse_point_is_refused(release, tmp_path):
    if os.name != 'nt':
        pytest.skip('Windows junction integration')
    program, loader, qq = release
    paths = loader.runtime_paths(prepare=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    link = paths.work_root / 'loadNapCat.js'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
    assert result.returncode == 0
    try:
        with pytest.raises(workspace.QQWorkspaceError):
            loader.runtime_paths(prepare=True)
        assert list(outside.iterdir()) == []
    finally:
        link.rmdir()


@pytest.mark.slow_integration
@pytest.mark.parametrize('snapshot_root', [None, 'relative-root'])
def test_plugin_refuses_missing_or_relative_snapshot_root(release, snapshot_root):
    program, _, _ = release
    node = shutil.which('node')
    assert node, 'Node is required for fictional plugin integration'
    environment = os.environ.copy()
    environment.pop('ECHO_SNAPSHOT_ROOT', None)
    if snapshot_root is not None:
        environment['ECHO_SNAPSHOT_ROOT'] = snapshot_root
    script = '''
const {plugin_init} = await import(process.argv[1]);
try { await plugin_init({core:{apis:{}}}); process.exitCode=3; }
catch (error) { if(error.message !== 'echo_snapshot_root_missing') throw error; }
'''
    result = subprocess.run([node, '--input-type=module', '-e', script,
                             (program / 'plugins/napcat-plugin-echo/index.mjs').as_uri()],
                            env=environment, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def test_managed_auth_refuses_connected_instance_with_another_path_contract(release, monkeypatch):
    _, loader, _ = release
    from qq_chat_analyzer.providers import napcat_qq_provider
    monkeypatch.setattr(napcat_qq_provider, 'NapCatQQProvider', lambda *a, **kw: SimpleNamespace(
        status=lambda: SimpleNamespace(runtime_id='0' * 64)))
    setup = QQSetupService(config_loader=loader)
    manager = SimpleNamespace(get_snapshot=lambda: ConnectionSnapshot(ConnectionState.CONNECTED, 'qq', ''),
                              begin_auth_waiting=lambda: None, end_auth_waiting=lambda: None)
    calls = []
    bridge = auth.QQAuthBridge(setup_service=setup, manager=manager, window_launcher=lambda: calls.append('launch'))
    assert bridge.start_auth_flow().state is ConnectionState.ERROR
    assert calls == []


def test_dead_launcher_revalidates_workspace_before_relaunch(release):
    _, loader, _ = release
    paths = loader.runtime_paths(prepare=True)
    manager = SimpleNamespace(get_snapshot=lambda: ConnectionSnapshot(ConnectionState.WAITING_AUTH, 'qq', ''),
                              begin_auth_waiting=lambda: None, end_auth_waiting=lambda: None)
    calls = []
    bridge = auth.QQAuthBridge(setup_service=QQSetupService(config_loader=loader), manager=manager,
                               window_launcher=lambda: calls.append('launch'))
    assert bridge.start_auth_flow().state is ConnectionState.WAITING_AUTH
    bridge._launched_process = SimpleNamespace(poll=lambda: 1)
    (paths.work_root / 'unknown.txt').write_bytes(b'fictional state requiring review')
    assert bridge.start_auth_flow().state is ConnectionState.ERROR
    assert calls == ['launch']
    assert (paths.work_root / 'unknown.txt').read_bytes() == b'fictional state requiring review'


@pytest.mark.parametrize('failure', ['unknown-workspace', 'old-instance'])
def test_setup_connect_validates_managed_workspace_and_running_identity(release, monkeypatch, failure):
    _, loader, _ = release
    paths = loader.runtime_paths(prepare=True)
    from qq_chat_analyzer.providers import napcat_qq_provider
    from qq_chat_analyzer.application.qq.qq_connection_service import QQConnectionStatus
    monkeypatch.setattr(napcat_qq_provider, 'NapCatQQProvider', lambda *a, **kw: SimpleNamespace(
        status=lambda: SimpleNamespace(runtime_id='0' * 64)))
    if failure == 'unknown-workspace':
        (paths.work_root / 'unknown.txt').write_bytes(b'keep fictional state')
    connection = SimpleNamespace(check_status=lambda: QQConnectionStatus(True, True, True, None, '', ''))
    setup = QQSetupService(config_loader=loader, connection_service=connection)
    expected = workspace.QQWorkspaceError if failure == 'unknown-workspace' else QQSetupService.RuntimeIdentityMismatch
    with pytest.raises(expected):
        setup.connect()


def test_setup_connect_cannot_adopt_an_untagged_configuration(release):
    program, loader, qq = release
    env.QQEnvironmentConfigWriter(loader.config_path()).save(env.QQEnvironmentConfig(
        qq_install_path=qq, runtime_directory=program))
    before = loader.config_path().read_bytes()
    calls = []
    from qq_chat_analyzer.application.qq.qq_runtime_manager import QQRuntimeStatus, QQRuntimeState
    manager = SimpleNamespace(get_status=lambda: QQRuntimeStatus(QQRuntimeState.STOPPED, True),
                              start=lambda: calls.append('start') or QQRuntimeStatus(QQRuntimeState.RUNNING, True))
    setup = QQSetupService(config_loader=loader, runtime_manager=manager)
    with pytest.raises(ValueError):
        setup.connect()
    assert calls == []
    assert loader.config_path().read_bytes() == before


def test_moving_release_keeps_workspace_and_snapshot_but_rebinds_program(release, tmp_path, monkeypatch):
    program, loader, _ = release
    before = loader.runtime_paths(prepare=True)
    moved = tmp_path / 'moved release # % 中文' / 'qq-napcat-candidate'
    shutil.copytree(program, moved)
    monkeypatch.setattr(env, 'default_qq_runtime_directory', lambda: moved)
    after = loader.runtime_paths(prepare=True)
    assert after.program_root == moved
    assert after.work_root == before.work_root
    assert after.snapshot_root == before.snapshot_root
    assert after.runtime_id != before.runtime_id
    seen = []
    monkeypatch.setattr(*_launch_target(), lambda *a, **kw: seen.append((a,kw)) or SimpleNamespace(poll=lambda:None))
    auth.default_auth_window_launcher(loader.load_or_default(), paths=after)()
    assert seen[0][0][0][0] == str(moved / 'NapCatWinBootMain.exe')
    assert seen[0][1]['env']['ECHO_RUNTIME_ID'] == after.runtime_id
    client = QQDirectDatabaseImportService(config_loader=loader)._require_runtime_client()
    assert client._snapshot_root == after.snapshot_root
    assert client._runtime_id == after.runtime_id


def test_setup_runtime_factory_uses_the_shared_paths_and_prepares_before_start(release, monkeypatch):
    program, loader, qq = release
    seen = []
    monkeypatch.setattr(*_launch_target(), lambda *a, **kw: seen.append(kw) or SimpleNamespace(pid=12345,poll=lambda:None))
    setup = QQSetupService(config_loader=loader)
    paths = setup.get_runtime_paths()
    manager = setup._runtime_manager_for(loader.load_or_default())
    manager._runtime._health_checker = lambda _: False  # Never probe a real QQ bridge.
    manager._process_registry = SimpleNamespace(record=lambda _pid: None)
    assert manager._runtime._config.working_directory == paths.work_root
    manager.start()
    assert seen[0]['cwd'] == str(paths.work_root)
    assert (paths.work_root / 'plugins/napcat-plugin-echo/index.mjs').exists()


@pytest.mark.slow_integration
def test_python_and_js_plugin_share_snapshot_root_and_refuse_old_clients(release, tmp_path, monkeypatch):
    import socket
    from qq_chat_analyzer.providers.qq_direct_snapshot_runtime import QQDirectSnapshotRuntimeClient, QQSnapshotRuntimeError
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for fictional plugin integration')
    program, loader, qq = release
    paths = loader.runtime_paths(prepare=True)
    seen = []
    with monkeypatch.context() as guard:
        guard.setattr(*_launch_target(), lambda *a, **kw: seen.append(kw['env']) or SimpleNamespace(poll=lambda: None))
        auth.default_auth_window_launcher(loader.load_or_default(), paths=paths)()
    plugin = tmp_path / 'fictional-plugin'
    shutil.copytree(paths.work_root / 'plugins/napcat-plugin-echo', plugin)
    # This double models only the snapshot boundary: real algorithm regression
    # is covered separately. It refuses any implicit root and writes fake bytes.
    (plugin / 'snapshot/snapshot.mjs').write_text('''
import fs from 'node:fs'; import path from 'node:path';
export function registerEchoSnapshotApi(core, options = {}) {
  if (options.rootDirectory !== process.env.ECHO_SNAPSHOT_ROOT) throw Error('root_not_explicit');
  const root = options.rootDirectory;
  return {
    async recover() { fs.mkdirSync(root, {recursive:true}); return {ok:true}; },
    async acquire() {
      const target = path.join(root,'generations','fictional-generation');
      fs.mkdirSync(target,{recursive:true}); fs.writeFileSync(path.join(target,'snapshot.db'),'fictional snapshot');
      return {ok:true,status:'ready',generation_id:'fictional-generation'};
    },
    async cleanup(id) { fs.rmSync(path.join(root,'generations',id),{recursive:true,force:true}); return {ok:true}; }
  };
}
''', encoding='utf-8')
    driver = tmp_path / 'plugin-driver.mjs'
    driver.write_text('''
import {plugin_init,plugin_cleanup} from './fictional-plugin/index.mjs';
setTimeout(()=>process.exit(7),15000).unref();
await plugin_init({core:{selfInfo:{online:true,uin:'123456'},apis:{}}});
console.log('READY');
process.stdin.once('data',async()=>{await plugin_cleanup();process.exit(0)});
''', encoding='utf-8')
    with socket.socket() as allocator:
        allocator.bind(('127.0.0.1', 0))
        port = allocator.getsockname()[1]
    environment = {**seen[0], 'ECHO_BRIDGE_PORT': str(port)}
    process = subprocess.Popen([node, str(driver)], env=environment, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'READY'
        url = f'http://127.0.0.1:{port}'
        client = QQDirectSnapshotRuntimeClient(url, snapshot_root=paths.snapshot_root, runtime_id=paths.runtime_id, timeout=1)
        client.recover()
        generation = client.acquire()
        assert (client.generation_directory(generation) / 'snapshot.db').read_bytes() == b'fictional snapshot'
        for wrong_id in (None, '0' * 64):
            old = QQDirectSnapshotRuntimeClient(url, snapshot_root=tmp_path / 'old-root', runtime_id=wrong_id, timeout=1)
            with pytest.raises(QQSnapshotRuntimeError):
                old.recover()
        assert (client.generation_directory(generation) / 'snapshot.db').exists()
        client.cleanup(generation)
        assert not client.generation_directory(generation).exists()
        assert not (program.parent / 'output/qq_direct_db_phase35').exists()
    finally:
        _, errors = process.communicate(input='STOP\n', timeout=20)
        assert process.returncode == 0, errors
