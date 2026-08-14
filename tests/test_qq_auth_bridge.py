"""Behavior tests for the QQ authorization bridge.

Everything here is fictional. No real QQ process, launcher, or login window
is started; runtime launch is stubbed and the default window launcher is
exercised against temp files with ``subprocess.Popen`` mocked.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
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


def _config_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_environment_config"
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
        config_missing=False,
    ):
        self._connect_status = connect_status
        self._error = error
        self._runtime_status = runtime_status
        self._config = config
        self._config_missing = config_missing
        self.connect_calls = 0
        self.config_calls = 0
        self.save_calls = 0
        self.start_runtime_calls = 0

    def connect(self):
        self.connect_calls += 1
        if self._error is not None:
            raise self._error
        return self._connect_status

    def save_environment(self, config):
        self.save_calls += 1
        if self._error is not None:
            raise self._error
        self._config = config
        self._config_missing = False
        return self._connect_status

    def get_environment_config(self):
        self.config_calls += 1
        if self._error is not None:
            raise self._error
        if self._config_missing:
            raise _config_module().QQConfigNotFound()
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
    config_preparer=None,
    qrcode_path=None,
    runtime_cleaner=None,
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
        config_preparer=config_preparer or (lambda: True),
        qrcode_path=qrcode_path,
        runtime_cleaner=runtime_cleaner,
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


def test_start_auth_flow_opens_login_window_without_pre_starting_runtime() -> None:
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

    assert setup.connect_calls == 0
    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_start_auth_flow_does_not_pre_start_qce_server_before_launcher() -> None:
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

    assert setup.connect_calls == 0
    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_start_auth_flow_prepares_webui_config_before_launch() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=False, authenticated=False)
    )
    setup = _StubSetupService(runtime_status=_runtime_status())
    launcher = _RecordingLauncher()
    calls: list[str] = []

    def _preparer() -> bool:
        calls.append("prepared")
        return True

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
        config_preparer=_preparer,
    ).start_auth_flow()

    assert calls == ["prepared"]
    assert launcher.calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_start_auth_flow_rejects_pre_existing_qrcode_until_session_update(
    tmp_path: Path,
) -> None:
    module = _connection_module()
    qr_path = tmp_path / "cache" / "qrcode.png"
    qr_path.parent.mkdir()
    qr_path.write_bytes(b"stale-qr-before-session")
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
        config=_runtime_config(tmp_path),
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=_RecordingLauncher(),
    )

    snapshot = bridge.start_auth_flow()

    assert snapshot.state is module.ConnectionState.WAITING_AUTH
    assert bridge.is_qrcode_ready() is False

    qr_path.write_bytes(b"fresh-qr-from-this-session")
    assert bridge.is_qrcode_ready() is True


def test_start_auth_flow_logs_qr_baseline_and_acceptance_fingerprints(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    qr_path = tmp_path / "cache" / "qrcode.png"
    qr_path.parent.mkdir()
    qr_path.write_bytes(b"stale-qr-before-session")
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
        config=_runtime_config(tmp_path),
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=_RecordingLauncher(),
    )

    with caplog.at_level("INFO", logger="qq_chat_analyzer.desktop.qq_auth_bridge"):
        bridge.start_auth_flow()
        assert bridge.is_qrcode_ready() is False
        qr_path.write_bytes(b"fresh-qr-from-this-session")
        assert bridge.is_qrcode_ready() is True

    messages = [record.message for record in caplog.records]
    assert any("qr baseline exists" in message for message in messages)
    assert any("sha256=" in message for message in messages)
    assert any("qr accepted" in message for message in messages)


def test_start_auth_flow_reports_existing_backend_stages() -> None:
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
    progress: list[str] = []

    _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=_RecordingLauncher(),
    ).start_auth_flow(progress=progress.append)

    assert progress == [
        "正在检查 QQ 运行环境...",
        "正在启动 QQ 环境...",
        "正在加载 NapCat...",
        "等待 QQ 登录...",
    ]


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


def test_start_auth_flow_does_not_launch_twice_while_waiting() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=True)
    )
    setup = _StubSetupService(runtime_status=_runtime_status())
    launcher = _RecordingLauncher()
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
    )

    first = bridge.start_auth_flow()
    second = bridge.start_auth_flow()

    assert first.state is module.ConnectionState.WAITING_AUTH
    assert second.state is module.ConnectionState.WAITING_AUTH
    assert launcher.calls == 1


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
    assert snapshot.state is module.ConnectionState.WAITING_AUTH
    assert (
        _bridge(
            setup_service=setup,
            connection_service=service,
            window_launcher=launcher,
        ).get_snapshot().state
        is module.ConnectionState.CONNECTED
    )


def test_polling_after_auth_launch_keeps_waiting_until_qce_ready() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        queue=[
            _status(available=False, qce_running=False),
            _status(available=False, qce_running=False),
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
        runtime_status=_runtime_status("stopped"),
    )
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=_RecordingLauncher(),
    )

    bridge.start_auth_flow()

    assert bridge.get_snapshot().state is module.ConnectionState.WAITING_AUTH
    assert bridge.get_snapshot().state is module.ConnectionState.WAITING_AUTH
    assert bridge.get_snapshot().state is module.ConnectionState.CONNECTED


def test_start_auth_flow_stops_previous_runtime_before_relaunch(
    tmp_path: Path,
) -> None:
    module = _connection_module()
    events: list[str] = []

    def cleaner(directory: Path) -> None:
        events.append(f"clean:{directory}")

    def launcher() -> None:
        events.append("launch")

    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
        config=_runtime_config(tmp_path),
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
        runtime_cleaner=cleaner,
    )

    snapshot = bridge.start_auth_flow()

    assert snapshot.state is module.ConnectionState.WAITING_AUTH
    assert events == [f"clean:{tmp_path}", "launch"]


def test_disconnect_stops_runtime_and_returns_disconnected(
    tmp_path: Path,
) -> None:
    module = _connection_module()
    events: list[str] = []

    class _RecordingRegistry:
        def __init__(self) -> None:
            self.terminate_calls = 0

        def terminate_all(self) -> int:
            self.terminate_calls += 1
            return 1

    def cleaner(directory: Path) -> None:
        events.append(f"clean:{directory}")

    registry = _RecordingRegistry()
    setup = _StubSetupService(
        config=_runtime_config(tmp_path),
        runtime_status=_runtime_status("running"),
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=True)
    )
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        process_registry=registry,
        runtime_cleaner=cleaner,
    )

    snapshot = bridge.disconnect()

    assert snapshot.state is module.ConnectionState.DISCONNECTED
    assert registry.terminate_calls == 1
    assert events == [f"clean:{tmp_path}"]


def test_start_auth_flow_does_not_clean_runtime_when_reusing_launcher(
    tmp_path: Path,
) -> None:
    module = _connection_module()
    events: list[str] = []

    def cleaner(directory: Path) -> None:
        events.append(f"clean:{directory}")

    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        ),
        runtime_status=_runtime_status(),
        config=_runtime_config(tmp_path),
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=False)
    )
    launcher = _RecordingLauncher()
    bridge = _bridge(
        setup_service=setup,
        connection_service=service,
        window_launcher=launcher,
        runtime_cleaner=cleaner,
    )

    first = bridge.start_auth_flow()
    second = bridge.start_auth_flow()

    assert first.state is module.ConnectionState.WAITING_AUTH
    assert second.state is module.ConnectionState.WAITING_AUTH
    assert launcher.calls == 1
    assert events == [f"clean:{tmp_path}"]


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
    (tmp_path / "launcher-user.bat").write_text(
        "@echo off\n",
        encoding="utf-8",
    )
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
    monkeypatch.setattr(bridge.os, "name", "posix")
    monkeypatch.setenv("ECHO_MODE", "inherited-parent-value")

    def _fake_popen(args, **kwargs):
        spawned["args"] = list(args)
        spawned["kwargs"] = kwargs
        return _FakeProcess(pid=4242)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    bridge.default_auth_window_launcher(config)()

    assert spawned["args"] == [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        "launcher-user.bat",
    ]
    assert spawned["kwargs"]["cwd"] == str(tmp_path)
    assert "creationflags" not in spawned["kwargs"]
    assert spawned["kwargs"]["env"]["NAPCAT_QQ_PATH"] == str(
        (tmp_path / "QQ.exe").resolve()
    )
    assert "ECHO_MODE" not in spawned["kwargs"]["env"]


def _start_launcher_exit_fixture(tmp_path: Path, *, echo_mode: bool):
    runtime = tmp_path / "runtime" / "qq"
    runtime.mkdir(parents=True)
    launcher = runtime / "launcher-user.bat"
    shutil.copy2(PROJECT_ROOT / "runtime" / "qq" / "launcher-user.bat", launcher)
    qq_path = tmp_path / "Bin" / "QQ.exe"
    qq_path.parent.mkdir()
    qq_path.write_text("fictional", encoding="utf-8")
    environment = os.environ.copy()
    environment["NAPCAT_QQ_PATH"] = str(qq_path)
    if echo_mode:
        environment["ECHO_MODE"] = "1"
    else:
        environment.pop("ECHO_MODE", None)
    return subprocess.Popen(
        ["cmd.exe", "/d", "/s", "/c", "call", str(launcher)],
        cwd=runtime,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
    )


def test_launcher_user_exits_without_pause_in_echo_mode(tmp_path: Path) -> None:
    process = _start_launcher_exit_fixture(tmp_path, echo_mode=True)
    try:
        assert process.wait(timeout=2) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_launcher_user_keeps_pause_for_interactive_mode(tmp_path: Path) -> None:
    process = _start_launcher_exit_fixture(tmp_path, echo_mode=False)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.2)
        assert process.stdin is not None
        process.stdin.write("\n")
        process.stdin.flush()
        assert process.wait(timeout=2) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_default_launcher_hides_napcat_console_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)
    spawned = {}

    def _fake_popen(args, **kwargs):
        spawned["args"] = list(args)
        spawned["kwargs"] = kwargs
        return _FakeProcess(pid=4245)

    monkeypatch.setattr(bridge.os, "name", "nt")
    monkeypatch.setattr(
        bridge.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    bridge.default_auth_window_launcher(config)()

    assert spawned["args"] == [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        "launcher-user.bat",
    ]
    assert spawned["kwargs"]["cwd"] == str(tmp_path)
    assert spawned["kwargs"]["creationflags"] == 0x08000000
    assert spawned["kwargs"]["stdin"] is bridge.subprocess.DEVNULL
    assert spawned["kwargs"]["stdout"] is bridge.subprocess.PIPE
    assert spawned["kwargs"]["stderr"] is bridge.subprocess.PIPE


def test_default_launcher_rejects_immediate_batch_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)

    class _FailedProcess(_FakeProcess):
        def poll(self):
            return 7

    monkeypatch.setattr(
        bridge.subprocess,
        "Popen",
        lambda args, **kwargs: _FailedProcess(pid=4246),
    )

    with pytest.raises(bridge.QQAuthWindowUnavailable):
        bridge.default_auth_window_launcher(config)()


@pytest.mark.parametrize("portable_name", ["Echo Portable", "Echo(2)", "余音安装包"])
@pytest.mark.skipif(sys.platform != "win32", reason="Windows cmd.exe only")
def test_launcher_command_runs_batch_from_portable_directory_with_special_path(
    tmp_path: Path,
    portable_name: str,
) -> None:
    bridge = _bridge_module()
    runtime = tmp_path / portable_name / "Echo" / "runtime" / "qq"
    runtime.mkdir(parents=True)
    launcher = runtime / "launcher-user.bat"
    qq_path = tmp_path / "QQ Install" / "QQ.exe"
    qq_path.parent.mkdir()
    qq_path.write_text("fictional", encoding="utf-8")
    launcher.write_text(
        "@echo off\n"
        '> "%~dp0result.txt" echo STARTED\n'
        "exit /b 0\n",
        encoding="utf-8",
    )

    process = bridge._launch_auth_window(runtime, launcher, qq_path)

    assert process.wait(timeout=5) == 0
    assert (runtime / "result.txt").read_text(encoding="ascii").strip() == (
        "STARTED"
    )


def test_default_launcher_logs_completed_stdout_and_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)

    class _CompletedProcess(_FakeProcess):
        def poll(self):
            return 0

        def communicate(self):
            return ("launcher output", "launcher warning")

    monkeypatch.setattr(
        bridge.subprocess,
        "Popen",
        lambda args, **kwargs: _CompletedProcess(pid=4247),
    )

    with caplog.at_level("INFO", logger="qq_chat_analyzer.desktop.qq_auth_bridge"):
        bridge.default_auth_window_launcher(config)()

    assert "returncode=0" in caplog.text
    assert "stdout=launcher output" in caplog.text
    assert "stderr=launcher warning" in caplog.text


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
    assert "qq_path=" in caplog.text
    assert "launch result pid=4243 returncode=None" in caplog.text
    assert "launcher-user.bat" in caplog.text
    assert "NapCatWinBootMain.exe" not in caplog.text


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
    (tmp_path / "launcher-user.bat").write_text("@echo off\n", encoding="utf-8")
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
        spawned["kwargs"] = kwargs
        return _FakeProcess(pid=4244)

    monkeypatch.setattr(bridge.subprocess, "Popen", _fake_popen)

    bridge.default_auth_window_launcher(config)()

    assert spawned["args"][-1] == "launcher-user.bat"
    assert str(configured) not in spawned["args"]
    assert spawned["kwargs"]["env"]["NAPCAT_QQ_PATH"] == str(
        configured.resolve()
    )


def test_find_qq_script_hides_powershell_console_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    script = tmp_path / "find-qq.ps1"
    script.write_text("Write-Output 'fictional'", encoding="utf-8")
    calls = []

    class _Completed:
        stdout = ""

    def _fake_run(command, **options):
        calls.append((command, options))
        return _Completed()

    monkeypatch.setattr(bridge.os, "name", "nt")
    monkeypatch.setattr(
        bridge.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    monkeypatch.setattr(bridge.subprocess, "run", _fake_run)

    assert bridge._detect_qq_path_with_script(script) is None

    assert calls[0][0] == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]
    assert calls[0][1]["creationflags"] == 0x08000000


def test_runtime_cleaner_targets_bundled_napcat_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    monkeypatch.setattr(bridge.os, "name", "nt")
    monkeypatch.setattr(
        bridge.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    calls = []

    def _fake_run(command, **options):
        calls.append((command, options))

    monkeypatch.setattr(bridge.subprocess, "run", _fake_run)

    bridge.terminate_bundled_runtime_sessions(tmp_path)

    assert calls
    command, options = calls[0]
    assert command[0] == "powershell"
    assert "NapCatWinBootMain.exe" in command[-1]
    assert "taskkill" in command[-1]
    assert "Wait-Process" in command[-1]
    assert options["env"]["QCE_RUNTIME_DIR"] == str(
        (tmp_path / "NapCatWinBootMain.exe").resolve()
    )
    assert options["creationflags"] == 0x08000000


def test_runtime_cleaner_skips_non_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    monkeypatch.setattr(bridge.os, "name", "posix")
    calls = []
    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args),
    )

    bridge.terminate_bundled_runtime_sessions(tmp_path)

    assert calls == []


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


# ------------------------------------------------------------ config recovery


def test_launch_window_recovers_missing_qq_config_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    config = _runtime_config(tmp_path)
    setup = _StubSetupService(config_missing=True)
    launcher = _RecordingLauncher()

    class _FakeLoader:
        @staticmethod
        def load_or_default():
            return config

    monkeypatch.setattr(bridge, "QQEnvironmentConfigLoader", _FakeLoader)
    monkeypatch.setattr(bridge, "default_auth_window_launcher", lambda _: launcher)

    instance = _bridge(setup_service=setup)
    instance._launch_window()

    assert setup.config_calls == 2
    assert setup.save_calls == 1
    assert setup.connect_calls == 0
    assert launcher.calls == 1
    assert instance._auth_launch_started is True


def test_launch_window_keeps_existing_config_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    setup = _StubSetupService(config=_runtime_config(tmp_path))
    launcher = _RecordingLauncher()

    monkeypatch.setattr(bridge, "default_auth_window_launcher", lambda _: launcher)

    instance = _bridge(setup_service=setup)
    instance._launch_window()

    assert setup.config_calls == 1
    assert setup.save_calls == 0
    assert setup.connect_calls == 0
    assert launcher.calls == 1


def test_start_auth_flow_missing_config_recovery_failure_returns_friendly_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _connection_module()
    bridge = _bridge_module()
    config_error = _config_module().QQConfigNotFound()
    setup = _StubSetupService(error=config_error, config_missing=True)
    service = _StubConnectionService(
        _status(available=False, qce_running=False, authenticated=False)
    )
    launcher = _RecordingLauncher()

    class _FakeLoader:
        @staticmethod
        def load_or_default():
            raise _config_module().QQConfigNotFound()

    monkeypatch.setattr(bridge, "QQEnvironmentConfigLoader", _FakeLoader)
    monkeypatch.setattr(bridge, "default_auth_window_launcher", lambda _: launcher)

    snapshot = _bridge(
        setup_service=setup,
        connection_service=service,
    ).start_auth_flow()

    assert snapshot.state is module.ConnectionState.ERROR
    assert snapshot.message == "未找到可用的 QQ 运行组件，请确认 Echo 安装完整后重试。"
    assert setup.save_calls == 0
    assert setup.connect_calls == 0
    assert launcher.calls == 0


# ------------------------------------------------------- launcher relaunch


class _ExitableProcess:
    """Launcher process stub whose exit state can change between launches."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self._exited = False

    def mark_exited(self) -> None:
        self._exited = True

    def poll(self):
        return 1 if self._exited else None


class _ProcessReturningLauncher:
    """Count calls and return the same process stub each time."""

    def __init__(self, process):
        self.calls = 0
        self._process = process

    def __call__(self):
        self.calls += 1
        return self._process


def test_launch_window_relaunches_after_launcher_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge_module()
    setup = _StubSetupService(config=_runtime_config(tmp_path))
    process = _ExitableProcess()
    launcher = _ProcessReturningLauncher(process)

    monkeypatch.setattr(bridge, "default_auth_window_launcher", lambda _: launcher)

    instance = _bridge(setup_service=setup)
    instance._launch_window()

    assert launcher.calls == 1
    assert instance._auth_launch_started is True

    process.mark_exited()
    instance._launch_window()

    assert launcher.calls == 2
    assert instance._auth_launch_started is True
