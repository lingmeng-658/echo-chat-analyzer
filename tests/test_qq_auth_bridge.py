"""Behavior tests for the QQ authorization bridge.

Everything here is fictional. No real QQ process, launcher, or login window
is started; runtime launch is stubbed and the default window launcher is
exercised against temp files with ``subprocess.Popen`` mocked.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _bridge_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.connection.qq_auth_bridge"
    )


def _connection_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.connection"
    )


def _status(
    *,
    available=False,
    qce_running=False,
    authenticated=False,
    version=None,
    message="",
    action_hint="",
):
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_connection_service"
    )
    return module.QQConnectionStatus(
        available=available,
        qce_running=qce_running,
        authenticated=authenticated,
        version=version,
        message=message,
        action_hint=action_hint,
    )


class _StubConnectionService:
    def __init__(self, status=None, queue=()):
        self._status = status
        self._queue = list(queue)
        self.check_calls = 0

    def check_status(self):
        self.check_calls += 1
        if self._queue:
            return self._queue.pop(0)
        return self._status


class _StubSetupService:
    def __init__(
        self,
        connect_status=None,
        error=None,
        runtime_status=None,
        config=None,
    ):
        self._connect_status = connect_status
        self._error = error
        self._runtime_status = runtime_status
        self._config = config
        self.connect_calls = 0
        self.config_calls = 0
        self.start_runtime_calls = 0

    def connect(self):
        self.connect_calls += 1
        if self._error is not None:
            raise self._error
        return self._connect_status

    def get_environment_config(self):
        self.config_calls += 1
        if self._error is not None:
            raise self._error
        return self._config

    def get_runtime_status(self):
        return self._runtime_status

    def start_runtime(self):
        self.start_runtime_calls += 1
        raise AssertionError("auth flow must reuse the manager connect path")


def _runtime_status(state: str = "running"):
    runtime = importlib.import_module(
        "qq_chat_analyzer.application.runtime"
    )
    return runtime.QQRuntimeStatus(
        state=runtime.QQRuntimeState(state),
        available=True,
        message="ok",
    )


def _bridge(
    *,
    setup_service=None,
    connection_service=None,
    manager=None,
    window_launcher=None,
    process_registry=None,
):
    if process_registry is None:
        registry_module = importlib.import_module(
            "qq_chat_analyzer.application.qq_process_registry"
        )
        process_registry = registry_module.QQProcessRegistry()
    return _bridge_module().QQAuthBridge(
        setup_service=setup_service,
        connection_service=connection_service,
        manager=manager,
        window_launcher=window_launcher,
        process_registry=process_registry,
    )


class _RecordingLauncher:
    def __init__(self, error=None):
        self.calls = 0
        self._error = error

    def __call__(self):
        self.calls += 1
        if self._error is not None:
            raise self._error


# ------------------------------------------------------------------ connected


def test_start_auth_flow_returns_connected_without_starting_anything() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(
            available=True,
            qce_running=True,
            authenticated=True,
            message="QQ \u5df2\u8fde\u63a5\u3002",
        )
    )
    setup = _StubSetupService()
    launcher = _RecordingLauncher()

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    ).start_auth_flow()

    assert snapshot.state is module.ConnectionState.CONNECTED
    assert setup.connect_calls == 0
    assert launcher.calls == 0


# ---------------------------------------------------------- waiting for auth


def test_start_auth_flow_starts_runtime_and_opens_login_window() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=False, authenticated=False)
    )
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
    )
    launcher = _RecordingLauncher()

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    ).start_auth_flow()

    assert setup.connect_calls == 1
    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_start_auth_flow_reopens_window_when_already_waiting() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=True)
    )
    setup = _StubSetupService(runtime_status=_runtime_status())
    launcher = _RecordingLauncher()

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    ).start_auth_flow()

    assert setup.connect_calls == 0
    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_start_auth_flow_picks_up_login_completed_during_launch() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        queue=[
            _status(available=False, qce_running=False),
            _status(available=False, qce_running=False),
            _status(
                available=True,
                qce_running=True,
                authenticated=True,
                message="QQ \u5df2\u8fde\u63a5\u3002",
            ),
        ]
    )
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
    )
    launcher = _RecordingLauncher()

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    ).start_auth_flow()

    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.CONNECTED


def test_get_snapshot_delegates_to_the_connection_manager() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )

    snapshot = _bridge(connection_service=service).get_snapshot()

    assert snapshot.state is module.ConnectionState.WAITING_AUTH


# -------------------------------------------------------------------- errors


def test_window_launch_failure_returns_a_safe_error_snapshot() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    setup = _StubSetupService(runtime_status=_runtime_status())
    launcher = _RecordingLauncher(error=RuntimeError("login window exploded"))

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    ).start_auth_flow()

    assert snapshot.state is module.ConnectionState.ERROR
    assert "login window exploded" not in snapshot.message
    assert snapshot.action_hint


def test_start_auth_flow_without_setup_service_reports_error() -> None:
    module = _connection_module()

    snapshot = _bridge().start_auth_flow()

    assert snapshot.state is module.ConnectionState.ERROR
    assert snapshot.message


def test_start_auth_flow_logs_the_auth_flow(
    caplog: pytest.LogCaptureFixture,
) -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    setup = _StubSetupService(runtime_status=_runtime_status())
    launcher = _RecordingLauncher()

    with caplog.at_level("INFO", logger="qq_chat_analyzer.desktop.qq_auth_bridge"):
        snapshot = _bridge(
            setup_service=setup,
            connection_service=service,
            window_launcher=launcher,
        ).start_auth_flow()

    assert snapshot.state is module.ConnectionState.WAITING_AUTH
    assert any("start_auth_flow entered" in record.message for record in caplog.records)
    assert any("connect finished" in record.message for record in caplog.records)
    assert any("login window launched" in record.message for record in caplog.records)


# ------------------------------------------------------- default window entry


def _runtime_config(tmp_path: Path, *, with_qq_path: bool = True):
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_environment_config"
    )
    (tmp_path / "NapCatWinBootMain.exe").write_text("fake", encoding="utf-8")
    (tmp_path / "NapCatWinBootHook.dll").write_text("fake", encoding="utf-8")
    (tmp_path / "napcat.mjs").write_text("export {}", encoding="utf-8")
    (tmp_path / "qqnt.json").write_text("{}", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    qq_path = None
    if with_qq_path:
        qq_path = tmp_path / "QQ.exe"
        qq_path.write_text("fake", encoding="utf-8")
        (config_dir / "qq_path.txt").write_text(
            str(qq_path),
            encoding="utf-8",
        )
    return module.QQEnvironmentConfig(
        runtime_directory=tmp_path,
        qq_install_path=qq_path,
    )


def test_default_launcher_opens_the_runtime_login_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)
    spawned = {}

    def _fake_popen(args, **kwargs):
        spawned["args"] = list(args)
        spawned["kwargs"] = kwargs
        return _FakeProcess(pid=4242)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    bridge.default_auth_window_launcher(config)()

    assert spawned["args"][0].endswith("NapCatWinBootMain.exe")
    assert spawned["args"][1] == str(tmp_path / "QQ.exe")
    assert spawned["args"][2].endswith("NapCatWinBootHook.dll")
    assert spawned["kwargs"]["cwd"] == str(tmp_path)
    assert "creationflags" not in spawned["kwargs"]
    env = spawned["kwargs"]["env"]
    assert env["NAPCAT_LOAD_PATH"] == str(tmp_path / "loadNapCat.js")
    assert env["NAPCAT_PATCH_PACKAGE"] == str(tmp_path / "qqnt.json")
    bootstrap = (tmp_path / "loadNapCat.js").read_text(encoding="utf-8")
    assert "file:///" in bootstrap
    assert "napcat.mjs" in bootstrap


def test_default_launcher_logs_the_actual_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)
    spawned = {}

    def _fake_popen(args, **kwargs):
        spawned["args"] = list(args)
        return _FakeProcess(pid=4243)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    with caplog.at_level("INFO", logger="qq_chat_analyzer.desktop.qq_auth_bridge"):
        bridge.default_auth_window_launcher(config)()

    assert "launch command=" in caplog.text
    assert "launch spawned pid=4243" in caplog.text
    assert "NapCatWinBootMain.exe" in caplog.text


def test_auth_flow_records_the_launched_window_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    registry_module = importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )
    config = _runtime_config(tmp_path)
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
        config=config,
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    registry = registry_module.QQProcessRegistry()

    def _fake_popen(args, **kwargs):
        return _FakeProcess(pid=7777)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        process_registry=registry,
    ).start_auth_flow()

    assert snapshot.state is _connection_module().ConnectionState.WAITING_AUTH
    assert registry.recorded() == (7777,)


def test_default_launcher_prefers_the_configured_qq_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_environment_config"
    )
    (tmp_path / "NapCatWinBootMain.exe").write_text("fake", encoding="utf-8")
    (tmp_path / "NapCatWinBootHook.dll").write_text("fake", encoding="utf-8")
    (tmp_path / "napcat.mjs").write_text("export {}", encoding="utf-8")
    configured = tmp_path / "configured-qq.exe"
    configured.write_text("fake", encoding="utf-8")
    saved = tmp_path / "saved-qq.exe"
    saved.write_text("fake", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "qq_path.txt").write_text(str(saved), encoding="utf-8")
    config = module.QQEnvironmentConfig(
        runtime_directory=tmp_path,
        qq_install_path=configured,
    )
    spawned = {}

    def _fake_popen(args, **kwargs):
        spawned["args"] = list(args)
        return _FakeProcess(pid=4244)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    bridge.default_auth_window_launcher(config)()

    assert spawned["args"][1] == str(configured)


class _FakeProcess:
    """Minimal stand-in for a spawned launcher subprocess."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def poll(self):
        return None


def test_default_launcher_rejects_a_missing_qq_install(tmp_path: Path) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path, with_qq_path=False)

    with pytest.raises(bridge.QQAuthWindowUnavailable):
        bridge.default_auth_window_launcher(config)


def test_resolve_qq_install_path_reads_the_saved_launcher_path(
    tmp_path: Path,
) -> None:
    bridge = _bridge_module()
    qq_path = tmp_path / "QQ.exe"
    qq_path.write_text("fake", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "qq_path.txt").write_text(str(qq_path), encoding="utf-8")

    resolved = bridge.resolve_qq_install_path(None, tmp_path)

    assert resolved == qq_path
