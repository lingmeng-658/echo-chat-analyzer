"""Behavior tests for the WeChat DB key acquisition service.

No real WeChat process, DLL, or key is touched. Every native call is replaced
by a fake adapter and a fake process finder.
"""

from __future__ import annotations

import importlib
import json
import logging
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_key_service"
    )


class _FakeHookApi:
    def __init__(
        self,
        *,
        key: str | None = None,
        hook_ok: bool = True,
        poll_raises: bool = False,
    ) -> None:
        self.key = key
        self.hook_ok = hook_ok
        self.poll_raises = poll_raises
        self.initialize_calls: list[int] = []
        self.poll_calls = 0
        self.cleanup_calls = 0

    def initialize(self, pid: int) -> bool:
        self.initialize_calls.append(pid)
        return self.hook_ok

    def poll_key(self, buffer, size: int) -> bool:
        self.poll_calls += 1
        if self.poll_raises:
            raise RuntimeError("native poll exploded with secret")
        if self.key is None:
            return False
        payload = self.key.encode("ascii")
        buffer[: len(payload)] = payload
        return True

    def cleanup(self) -> bool:
        self.cleanup_calls += 1
        return True

    def error_message(self) -> bytes:
        return b"hook denied by wechat process"


def _service(
    tmp_path: Path,
    *,
    api: _FakeHookApi,
    pids: list[int],
    timeout: float = 5.0,
    monotonic=None,
):
    dll_path = tmp_path / "wx_key.dll"
    dll_path.write_bytes(b"fake")
    module = _module()
    return module.WeChatKeyService(
        dll_path=dll_path,
        process_finder=lambda: pids,
        dll_loader=lambda _path: api,
        buffer_factory=lambda size: bytearray(size),
        sleep=lambda _seconds: None,
        monotonic=monotonic or (lambda: 0.0),
        timeout=timeout,
    )


def test_acquire_returns_valid_key(tmp_path: Path) -> None:
    key = "ab12" * 16
    api = _FakeHookApi(key=key)
    service = _service(tmp_path, api=api, pids=[123])

    acquired = service.acquire()

    assert acquired == key.lower()
    assert api.initialize_calls == [123]
    assert api.cleanup_calls == 1


def test_acquire_missing_dll_is_user_safe(tmp_path: Path) -> None:
    module = _module()
    service = module.WeChatKeyService(
        dll_path=tmp_path / "absent.dll",
        process_finder=lambda: [123],
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_environment_missing"
    assert caught.value.public_message
    assert "Traceback" not in caught.value.public_message


def test_acquire_without_weixin_process_is_user_safe(tmp_path: Path) -> None:
    module = _module()
    dll_path = tmp_path / "wx_key.dll"
    dll_path.write_bytes(b"fake")
    service = module.WeChatKeyService(
        dll_path=dll_path,
        process_finder=lambda: [],
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_not_running"
    assert "\u672a\u68c0\u6d4b\u5230\u5fae\u4fe1" in caught.value.public_message


def test_hook_failure_is_normalized(tmp_path: Path) -> None:
    module = _module()
    api = _FakeHookApi(key=None, hook_ok=False)
    service = _service(tmp_path, api=api, pids=[456])

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_hook_failed"
    assert "无法获取微信登录密钥" in caught.value.public_message
    assert "微信版本或环境不支持" in caught.value.public_message
    assert "hook denied" not in caught.value.public_message
    assert "Traceback" not in caught.value.public_message


def test_hook_success_without_key_is_not_captured(tmp_path: Path) -> None:
    module = _module()
    api = _FakeHookApi(key=None)
    service = _service(tmp_path, api=api, pids=[789], timeout=0.0)

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_key_not_captured"
    assert "无法获取微信登录密钥" in caught.value.public_message
    assert api.cleanup_calls == 1


def test_poll_exception_does_not_leak(tmp_path: Path) -> None:
    module = _module()
    api = _FakeHookApi(key=None, poll_raises=True)
    clock = iter([0.0, 1.0])
    service = _service(
        tmp_path,
        api=api,
        pids=[111],
        timeout=1.0,
        monotonic=lambda: next(clock),
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_key_not_captured"
    assert "native poll exploded with secret" not in caught.value.public_message
    assert "Traceback" not in caught.value.public_message


def test_extract_key_rejects_invalid_length() -> None:
    module = _module()

    assert module._extract_key(bytearray(b"too-short")) is None
    assert module._extract_key(bytearray(b"z" * 64)) is None
    assert module._extract_key(bytearray(b"a" * 64)) == "a" * 64


def test_default_dll_path_points_at_bundled_runtime() -> None:
    module = _module()
    service = module.WeChatKeyService(process_finder=lambda: [])

    assert service._dll_path == (
        PROJECT_ROOT / "runtime" / "wechat" / "wx_key.dll"
    )

class _Completed:
    def __init__(self, code=0, stdout="", stderr=""):
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def _helper_service(
    tmp_path: Path,
    result=None,
    runner=None,
    *,
    node_finder=lambda _name: "node",
):
    dll = tmp_path / "wx_key.dll"
    helper = tmp_path / "wx_key_helper.cjs"
    dll.write_bytes(b"fake")
    helper.write_text("", encoding="utf-8")
    module = _module()
    return module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        subprocess_runner=runner or (lambda *_args, **_kwargs: result),
        node_finder=node_finder,
    )


def test_helper_success_returns_key(tmp_path: Path):
    module = _module()
    service = _helper_service(tmp_path, _Completed(stdout="AB12" * 16 + "\n"))
    assert service.acquire() == "ab12" * 16


def test_helper_failure_is_normalized(tmp_path: Path):
    module = _module()
    service = _helper_service(tmp_path, _Completed(1, stderr="no Weixin process"))
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert "未检测到微信" in caught.value.public_message


def test_helper_empty_stdout_is_rejected(tmp_path: Path):
    module = _module()
    service = _helper_service(tmp_path, _Completed())
    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()


def test_helper_short_payload_is_rejected(tmp_path: Path):
    module = _module()
    service = _helper_service(tmp_path, _Completed(stdout="not-a-key"))
    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()


def test_helper_subprocess_exception_is_normalized(tmp_path: Path):
    module = _module()
    def fail(*_args, **_kwargs):
        raise OSError("node missing")
    service = _helper_service(tmp_path, runner=fail)
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert "\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6" in caught.value.public_message


def test_helper_hook_failure_is_normalized(tmp_path: Path):
    module = _module()
    service = _helper_service(
        tmp_path,
        _Completed(1, stderr="InitializeHook(4321) -> false"),
    )
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert caught.value.code == "wechat_hook_failed"
    assert "无法获取微信登录密钥" in caught.value.public_message


def test_helper_key_unavailable_is_not_captured(tmp_path: Path):
    module = _module()
    service = _helper_service(
        tmp_path,
        _Completed(
            1,
            stderr=(
                "Weixin PIDs: 101, 202\n"
                "InitializeHook(101) -> true\n"
                "key unavailable"
            ),
        ),
    )
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert caught.value.code == "wechat_key_not_captured"
    assert "无法获取微信登录密钥" in caught.value.public_message


def test_helper_early_runtime_failure_is_classified_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A helper crash before process enumeration must not collapse silently."""
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _helper_service(
        tmp_path,
        _Completed(
            1,
            stderr=(
                "Error: Cannot find module 'koffi'\n"
                "Require stack:\n"
                "- D:\\secret\\install\\runtime\\wechat\\wx_key_helper.cjs\n"
                "    at Module._resolveFilename "
                "(node:internal/modules/cjs/loader.js:1:1)\n"
            ),
        ),
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_environment_missing"
    assert "微信连接组件加载失败" in caught.value.public_message
    assert (
        "wechat.key.capture success=false error_type=WeChatKeyUnavailable "
        "code=wechat_environment_missing"
    ) in caplog.text
    assert "process_found=null process_count=null" in caplog.text
    assert "hook_success=null" in caplog.text
    assert "key_capture_success=false" in caplog.text
    assert "wechat_process_incompatible" not in caplog.text
    assert "koffi" not in caplog.text
    assert "secret" not in caplog.text
    assert "wx_key_helper.cjs" not in caplog.text
    assert "ab12" * 16 not in caplog.text


def test_helper_dll_load_failure_logs_exit_code_and_stage(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _helper_service(
        tmp_path,
        _Completed(
            1,
            stderr=(
                "helper_stage=node_start\n"
                "helper_stage=koffi_load\n"
                "helper_stage=process_enumeration\n"
                "helper_stage=dll_load\n"
                "Error: Dynamic Linking Error: Win32 error 126\n"
            ),
        ),
    )

    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()

    assert (
        "wechat.key.helper helper_exit_code=1 helper_stage=dll_load "
        "helper_error_category=dll_load_failed"
    ) in caplog.text
    assert "process_found=null process_count=null" in caplog.text
    for leaked in ("Dynamic Linking Error", "Win32 error", "secret", "wx_key.dll"):
        assert leaked not in caplog.text


def test_helper_default_timeout_is_600_seconds(tmp_path: Path):
    calls = []
    def runner(command, **options):
        calls.append((command, options))
        return _Completed(stdout="a" * 64)
    service = _helper_service(tmp_path, runner=runner)
    service.acquire()
    command, options = calls[0]
    assert command[command.index("--timeout-ms") + 1] == "600000"
    assert options["timeout"] == 605.0


def test_helper_hides_node_console_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    calls = []

    def runner(command, **options):
        calls.append((command, options))
        return _Completed(stdout="a" * 64)

    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(
        module.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    _helper_service(tmp_path, runner=runner).acquire()

    command, options = calls[0]
    assert command[0] == "node"
    assert command[1] == str(tmp_path / "wx_key_helper.cjs")
    assert options["creationflags"] == 0x08000000
    assert options["cwd"] == str(tmp_path)
    assert options["env"]["NODE_PATH"] == str(tmp_path / "node_modules")
    assert options["timeout"] == 605.0


@pytest.mark.parametrize(
    "install_dir",
    [
        "WeChat/Weixin",
        "软件之学习工作/微信/Weixin",
        "we chat install/Weixin",
    ],
)
def test_helper_invocation_preserves_path_characters(
    tmp_path: Path,
    install_dir: str,
) -> None:
    module = _module()
    runtime_dir = tmp_path / install_dir
    runtime_dir.mkdir(parents=True)
    dll = runtime_dir / "wx_key.dll"
    helper = runtime_dir / "wx_key_helper.cjs"
    node = runtime_dir / "node.exe"
    dll.write_bytes(b"fake")
    helper.write_text("", encoding="utf-8")
    node.write_bytes(b"fake")
    service = module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        koffi_module_path=runtime_dir / "node_modules",
        node_finder=lambda _name: str(node),
    )

    command, options = service._build_helper_invocation(30.0)

    assert command == [
        str(node),
        str(helper),
        "--dll",
        str(dll),
        "--timeout-ms",
        "30000",
    ]
    assert options["cwd"] == str(runtime_dir)
    assert options["env"]["NODE_PATH"] == str(runtime_dir / "node_modules")
    assert options.get("shell", False) is False


def test_helper_invocation_never_uses_wechat_install_path(
    tmp_path: Path,
) -> None:
    module = _module()
    dll = tmp_path / "wx_key.dll"
    helper = tmp_path / "wx_key_helper.cjs"
    dll.write_bytes(b"fake")
    helper.write_text("", encoding="utf-8")
    service = module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        node_finder=lambda _name: "node",
    )

    command, options = service._build_helper_invocation(30.0)

    assert command[0] == "node"
    assert command[1] == str(helper)
    assert command[2:4] == ["--dll", str(dll)]
    assert command[4:6] == ["--timeout-ms", "30000"]
    assert "Weixin.exe" not in str(command)
    assert str(Path("D:/软件之学习工作/微信/Weixin")) not in str(command)
    assert "Weixin.exe" not in str(options.get("cwd", ""))


def test_helper_missing_path_is_user_safe(tmp_path: Path) -> None:
    module = _module()
    dll = tmp_path / "wx_key.dll"
    dll.write_bytes(b"fake")
    service = module.WeChatKeyService(
        dll_path=dll,
        helper_path=tmp_path / "不存在的路径" / "wx_key_helper.cjs",
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_environment_missing"


@pytest.mark.skipif(
    os.name != "nt"
    or not (PROJECT_ROOT / "runtime" / "wechat" / "node.exe").is_file(),
    reason="bundled Windows Node.js is required",
)
def test_node_subprocess_round_trips_chinese_and_space_paths(
    tmp_path: Path,
) -> None:
    module = _module()
    runtime_dir = tmp_path / "软件之学习工作 微信空间" / "Echo Runtime"
    runtime_dir.mkdir(parents=True)
    dll = runtime_dir / "wx_key.dll"
    helper = runtime_dir / "wx_key_helper.cjs"
    dll.write_bytes(b"fake")
    helper.write_text(
        "const path = require('path');"
        "const dll = process.argv[process.argv.indexOf('--dll') + 1];"
        "process.stdout.write(JSON.stringify({ dll: dll, cwd: process.cwd(), "
        "resolved: path.resolve(dll) }) + '\\n');",
        encoding="utf-8",
    )
    node = PROJECT_ROOT / "runtime" / "wechat" / "node.exe"
    service = module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        koffi_module_path=PROJECT_ROOT / "runtime" / "wechat" / "node_modules",
        node_finder=lambda _name: str(node),
    )

    command, options = service._build_helper_invocation(5.0)
    options["capture_output"] = True
    options["check"] = False
    options["timeout"] = 20.0
    result = subprocess.run(command, **options)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["dll"] == str(dll)
    assert payload["resolved"] == str(dll.resolve())
    assert payload["cwd"] == str(runtime_dir)


@pytest.mark.skipif(
    os.name != "nt"
    or not (PROJECT_ROOT / "runtime" / "wechat" / "node.exe").is_file()
    or not (PROJECT_ROOT / "runtime" / "wechat" / "node_modules" / "koffi").is_dir()
    or not (PROJECT_ROOT / "runtime" / "wechat" / "wx_key.dll").is_file(),
    reason="bundled Windows Node.js, koffi and wx_key.dll are required",
)
def test_koffi_loads_dll_from_chinese_and_space_path(tmp_path: Path) -> None:
    module = _module()
    runtime_dir = tmp_path / "软件之学习工作 微信空间"
    runtime_dir.mkdir()
    source_dll = PROJECT_ROOT / "runtime" / "wechat" / "wx_key.dll"
    dll = runtime_dir / "wx_key.dll"
    shutil.copy2(source_dll, dll)
    helper = runtime_dir / "probe.cjs"
    helper.write_text(
        "const koffi = require('koffi');"
        "const dll = process.argv[process.argv.indexOf('--dll') + 1];"
        "const lib = koffi.load(dll);"
        "process.stdout.write(JSON.stringify({ loaded: !!lib, dll: dll }) + '\\n');",
        encoding="utf-8",
    )
    node = PROJECT_ROOT / "runtime" / "wechat" / "node.exe"
    service = module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        koffi_module_path=PROJECT_ROOT / "runtime" / "wechat" / "node_modules",
        node_finder=lambda _name: str(node),
    )

    command, options = service._build_helper_invocation(5.0)
    options["capture_output"] = True
    options["check"] = False
    options["timeout"] = 20.0
    result = subprocess.run(command, **options)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["loaded"] is True
    assert payload["dll"] == str(dll)


def test_helper_prefers_bundled_node_when_system_node_is_unavailable(
    tmp_path: Path,
) -> None:
    calls = []

    def runner(command, **options):
        calls.append((command, options))
        return _Completed(stdout="a" * 64)

    bundled_node = tmp_path / "node.exe"
    bundled_node.write_bytes(b"fictional node")
    service = _helper_service(
        tmp_path,
        runner=runner,
        node_finder=lambda _name: None,
    )

    assert service.acquire() == "a" * 64
    assert calls[0][0][0] == str(bundled_node)


def test_helper_reports_missing_node_runtime_before_launch(
    tmp_path: Path,
) -> None:
    module = _module()
    launched = False

    def runner(*_args, **_kwargs):
        nonlocal launched
        launched = True
        return _Completed(stdout="a" * 64)

    service = _helper_service(
        tmp_path,
        runner=runner,
        node_finder=lambda _name: None,
    )

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert "Node.js" in caught.value.public_message
    assert launched is False


def test_helper_omits_windows_creation_flags_on_non_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    calls = []

    def runner(command, **options):
        calls.append((command, options))
        return _Completed(stdout="a" * 64)

    service = _helper_service(tmp_path, runner=runner)
    monkeypatch.setattr(module.os, "name", "posix")
    service.acquire()

    command, options = calls[0]
    assert command[0] == "node"
    assert "creationflags" not in options


def test_legacy_multiple_pids_each_get_independent_timeout(tmp_path: Path):
    module = _module()
    api = _FakeHookApi(key=None)
    clock = iter([10.0, 11.0, 20.0, 21.0])
    service = _service(
        tmp_path,
        api=api,
        pids=[101, 202],
        timeout=1.0,
        monotonic=lambda: next(clock),
    )
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert caught.value.code == "wechat_key_not_captured"
    assert api.initialize_calls == [101, 202]
    assert api.cleanup_calls == 2


def test_helper_accepts_non_hex_payload_of_verified_length(tmp_path: Path):
    payload = "z" * 64 + "ignored"
    service = _helper_service(tmp_path, _Completed(stdout=payload))
    assert service.acquire() == "z" * 64


def test_helper_source_uses_one_global_timeout_for_all_pids():
    source = (PROJECT_ROOT / "runtime" / "wechat" / "wx_key_helper.cjs").read_text(encoding="utf-8")
    loop = source.index("for (const [index, pid] of ids.entries())")
    deadline = source.index("const deadline = Date.now() + timeoutMs")
    assert deadline < loop


def test_helper_stage_markers_precede_native_bootstrap_operations() -> None:
    source = (
        PROJECT_ROOT / "runtime" / "wechat" / "wx_key_helper.cjs"
    ).read_text(encoding="utf-8")

    assert source.index("helper_stage=node_start") < source.index("require('koffi')")
    assert source.index("helper_stage=koffi_load") < source.index("require('koffi')")
    assert source.index("helper_stage=process_enumeration") < source.index(": pids()")
    assert source.index("helper_stage=dll_load") < source.index("koffi.load(dll)")


@pytest.mark.skipif(
    os.name != "nt"
    or not (PROJECT_ROOT / "runtime" / "wechat" / "node.exe").is_file(),
    reason="bundled Windows Node.js is required",
)
def test_bundled_helper_reaches_process_enumeration_before_dll_load(
    tmp_path: Path,
) -> None:
    invalid_dll = tmp_path / "fictional-invalid.dll"
    invalid_dll.write_bytes(b"not a native library")
    completed = subprocess.run(
        [
            str(PROJECT_ROOT / "runtime" / "wechat" / "node.exe"),
            str(PROJECT_ROOT / "runtime" / "wechat" / "wx_key_helper.cjs"),
            "--dll",
            str(invalid_dll),
            "--pid",
            "1",
            "--timeout-ms",
            "1",
        ],
        cwd=PROJECT_ROOT / "runtime" / "wechat",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode != 0
    stderr = completed.stderr
    markers = [
        "helper_stage=node_start",
        "helper_stage=koffi_load",
        "helper_stage=process_enumeration",
        "process_found=true, process_count=1",
        "helper_stage=dll_load",
    ]
    positions = [stderr.index(marker) for marker in markers]
    assert positions == sorted(positions)


# --------------------------------------------------------------- streaming


class _FakePopen:
    """Minimal Popen stand-in for the streaming helper path."""

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr_lines: tuple[str, ...] = (),
        returncode: int = 0,
        timeout_after: bool = False,
    ) -> None:
        self.stdout = io.StringIO(stdout)
        stderr_text = "".join(line + "\n" for line in stderr_lines)
        self.stderr = io.StringIO(stderr_text)
        self._stderr_size = len(stderr_text)
        self.returncode = returncode
        self._timeout_after = timeout_after
        self.killed = False
        self.waited = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def communicate(self, timeout=None):
        if self._timeout_after:
            import subprocess

            raise subprocess.TimeoutExpired(cmd="node", timeout=timeout or 0)
        # A real helper exits only after its stderr is written; mirror that so
        # the reader thread is not raced by an instant return.
        while self.stderr.tell() < self._stderr_size:
            time.sleep(0.005)
        return self.stdout.read(), ""

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        if self._timeout_after:
            import subprocess

            raise subprocess.TimeoutExpired(cmd="node", timeout=timeout or 0)
        return self.returncode


class _DelayedStdoutPopen:
    """Popen stand-in whose stdout opens only after stderr is written.

    Mirrors the real helper: stderr lines arrive while the process is still
    running, and the key appears on stdout only at the very end.
    """

    def __init__(
        self,
        *,
        key: str,
        stderr_lines: tuple[str, ...],
    ) -> None:
        self._key = key
        self._stderr_lines = stderr_lines
        self.stderr = _BlockingLineStream()
        self.stdout = _DelayedStringIO()
        self.returncode = None
        self.killed = False
        self.waited = False

    def wait(self, timeout=None):
        self.waited = True
        for line in self._stderr_lines:
            time.sleep(0.01)
            self.stderr.write_line(line + "\n")
        self.stderr.close()
        self.returncode = 0
        self.stdout.release(self._key + "\n")
        return self.returncode

    def kill(self):
        self.killed = True


class _DelayedStringIO:
    """StringIO whose content appears only after ``release`` is called."""

    def __init__(self) -> None:
        self._content: list[str] = []
        self._released = False

    def release(self, content: str) -> None:
        self._content.append(content)
        self._released = True

    def readline(self) -> str:
        while not self._released:
            time.sleep(0.005)
        if not self._content:
            return ""
        return self._content.pop(0)


class _BlockingLineStream:
    """A stream that blocks on readline until each line is written."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._closed = False

    def write_line(self, line: str) -> None:
        self._lines.append(line)

    def close(self) -> None:
        self._closed = True

    def readline(self) -> str:
        while not self._lines:
            if self._closed:
                return ""
            time.sleep(0.005)
        return self._lines.pop(0)


def _streaming_service(tmp_path: Path, popen, progress=None):
    dll = tmp_path / "wx_key.dll"
    helper = tmp_path / "wx_key_helper.cjs"
    dll.write_bytes(b"fake")
    helper.write_text("", encoding="utf-8")
    module = _module()
    return module.WeChatKeyService(
        dll_path=dll,
        helper_path=helper,
        process_launcher=popen,
        progress_callback=progress,
        node_finder=lambda _name: "node",
    )


def test_streaming_reports_progress_per_stderr_line(tmp_path: Path):
    seen: list[str] = []
    proc = _FakePopen(
        stdout="cd34" * 16 + "\n",
        stderr_lines=(
            "2026-08-09T00:00:00.000Z elapsed=5s, waiting for key...",
            "2026-08-09T00:00:05.000Z elapsed=10s, waiting for key...",
        ),
    )
    service = _streaming_service(
        tmp_path, lambda *_a, **_k: proc, progress=seen.append
    )
    assert service.acquire() == "cd34" * 16
    assert len(seen) == 2
    assert "5" in seen[0] and "10" in seen[1]


def test_streaming_reader_keeps_receiving_lines_until_exit(tmp_path: Path):
    """The stderr reader must keep draining while stdout is still open."""
    seen: list[str] = []
    proc = _FakePopen(
        stdout="ab12" * 16 + "\n",
        stderr_lines=(
            "2026-08-09T00:00:00.000Z elapsed=1s, waiting for key...",
            "2026-08-09T00:00:01.000Z elapsed=2s, waiting for key...",
            "2026-08-09T00:00:02.000Z elapsed=3s, waiting for key...",
        ),
    )
    service = _streaming_service(
        tmp_path, lambda *_a, **_k: proc, progress=seen.append
    )

    assert service.acquire() == "ab12" * 16
    assert len(seen) == 3
    assert "1" in seen[0] and "2" in seen[1] and "3" in seen[2]


def test_streaming_communicate_does_not_steal_stderr(tmp_path: Path):
    """communicate() must not consume stderr lines meant for the reader."""
    seen: list[str] = []
    proc = _DelayedStdoutPopen(
        key="ef56" * 16,
        stderr_lines=(
            "2026-08-09T00:00:00.000Z elapsed=5s, waiting for key...",
            "2026-08-09T00:00:05.000Z elapsed=10s, waiting for key...",
        ),
    )
    service = _streaming_service(
        tmp_path, lambda *_a, **_k: proc, progress=seen.append
    )

    assert service.acquire() == "ef56" * 16
    assert len(seen) == 2
    assert "5" in seen[0] and "10" in seen[1]
    assert proc.killed is False


def test_streaming_progress_never_leaks_internal_terms(tmp_path: Path):
    seen: list[str] = []
    proc = _FakePopen(
        stdout="ef56" * 16 + "\n",
        stderr_lines=(
            "DLL: C:\\secret\\path\\wx_key.dll",
            "InitializeHook(4321) -> true",
            "exports loaded: InitializeHook, PollKeyData, CleanupHook",
        ),
    )
    service = _streaming_service(
        tmp_path, lambda *_a, **_k: proc, progress=seen.append
    )
    service.acquire()
    joined = " ".join(seen).lower()
    for leaked in ("dll", "initializehook", "koffi", "secret", "pollkeydata"):
        assert leaked not in joined


def test_streaming_timeout_is_distinct_from_node_failure(tmp_path: Path):
    module = _module()
    proc = _FakePopen(timeout_after=True)
    service = _streaming_service(tmp_path, lambda *_a, **_k: proc)
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert caught.value.code == "wechat_key_timeout"
    message = caught.value.public_message
    assert "Node.js" not in message
    assert "\u8d85\u65f6" in message or "\u65f6\u9650" in message
    assert proc.killed


def test_streaming_node_missing_still_mentions_node(tmp_path: Path):
    module = _module()

    def launcher(*_args, **_kwargs):
        raise FileNotFoundError("node not on PATH")

    service = _streaming_service(tmp_path, launcher)
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert "\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6" in caught.value.public_message


def test_streaming_failure_uses_collected_stderr(tmp_path: Path):
    module = _module()
    proc = _FakePopen(
        stdout="",
        stderr_lines=("no Weixin process",),
        returncode=1,
    )
    service = _streaming_service(tmp_path, lambda *_a, **_k: proc)
    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()
    assert "\u672a\u68c0\u6d4b\u5230\u5fae\u4fe1" in caught.value.public_message


def test_streaming_early_runtime_failure_logs_stage_fields(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    proc = _FakePopen(
        stdout="",
        stderr_lines=("Error: Cannot find module 'koffi'",),
        returncode=1,
    )
    service = _streaming_service(tmp_path, lambda *_a, **_k: proc)

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_environment_missing"
    assert "process_found=null process_count=null" in caplog.text
    assert "hook_success=null" in caplog.text
    assert "key_capture_success=false" in caplog.text
    assert "wechat_process_incompatible" not in caplog.text
    assert "koffi" not in caplog.text
    assert "secret" not in caplog.text
    assert "ab12" * 16 not in caplog.text


def test_streaming_initialized_pid_without_key_reports_not_captured(
    tmp_path: Path,
):
    module = _module()
    proc = _FakePopen(
        stdout="",
        stderr_lines=(
            "Weixin PIDs: 101, 202",
            "InitializeHook(101) -> true",
            "key unavailable",
        ),
        returncode=1,
    )
    service = _streaming_service(tmp_path, lambda *_a, **_k: proc)

    with pytest.raises(module.WeChatKeyUnavailable) as caught:
        service.acquire()

    assert caught.value.code == "wechat_key_not_captured"
    assert "无法获取微信登录密钥" in caught.value.public_message
    assert "\u91cd\u65b0\u5b89\u88c5" not in caught.value.public_message


def test_streaming_and_injected_runner_share_invocation(tmp_path: Path):
    calls = []

    def launcher(command, **options):
        calls.append((command, options))
        return _FakePopen(stdout="ab12" * 16)

    service = _streaming_service(tmp_path, launcher)
    service.acquire()
    command, options = calls[0]
    assert command[command.index("--timeout-ms") + 1] == "600000"
    assert options["cwd"] == str(tmp_path)
    assert options["env"]["NODE_PATH"] == str(tmp_path / "node_modules")
# ------------------------------------------------------------------ key bridge

@pytest.fixture(autouse=True)
def _clean_key_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let ECHO_WX_DB_KEY leak between tests."""
    monkeypatch.delenv(_module().KEY_ENVIRONMENT_VARIABLE, raising=False)


def test_acquire_exposes_key_to_process_environment(tmp_path: Path) -> None:
    key = "ab12" * 16
    service = _service(tmp_path, api=_FakeHookApi(key=key), pids=[1000])
    assert service.acquire() == key
    assert os.environ.get(_module().KEY_ENVIRONMENT_VARIABLE) == key


def test_acquire_logs_never_contain_the_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    key = "cd34" * 16
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _service(tmp_path, api=_FakeHookApi(key=key), pids=[1000])
    service.acquire()
    assert key not in caplog.text
    assert "wechat.connect.start" in caplog.text
    assert "wechat.key.capture success=true" in caplog.text
    assert "process_found=true process_count=1" in caplog.text
    assert "hook_success=true" in caplog.text
    assert "key_capture_success=true" in caplog.text


def test_acquire_failure_logs_safe_event_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _service(tmp_path, api=_FakeHookApi(key=None), pids=[])

    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()

    assert "wechat.connect.start" in caplog.text
    assert "wechat.key.capture success=false error_type=WeChatKeyUnavailable" in (
        caplog.text
    )
    assert "process_found=false process_count=0" in caplog.text
    assert "hook denied" not in caplog.text


def test_helper_failure_logs_safe_diagnostics(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _helper_service(
        tmp_path,
        _Completed(
            1,
            stderr=(
                "Weixin PIDs: 101, 202\n"
                "InitializeHook(101) -> true\n"
                "key unavailable"
            ),
        ),
    )

    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()

    assert "process_found=true process_count=2" in caplog.text
    assert "hook_success=true" in caplog.text
    assert "key_capture_success=false" in caplog.text
    assert "101" not in caplog.text
    assert "202" not in caplog.text


def test_helper_hook_failure_logs_safe_diagnostics(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    module = _module()
    caplog.set_level(
        logging.INFO,
        logger="qq_chat_analyzer.desktop.wechat_key_service",
    )
    service = _helper_service(
        tmp_path,
        _Completed(
            1,
            stderr=(
                "Weixin PIDs: 456\n"
                "InitializeHook(456) -> false"
            ),
        ),
    )

    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()

    assert "process_found=true process_count=1" in caplog.text
    assert "hook_success=false" in caplog.text
    assert "456" not in caplog.text


def test_acquire_failure_does_not_expose_key(tmp_path: Path) -> None:
    module = _module()
    service = _service(tmp_path, api=_FakeHookApi(key=None), pids=[])
    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()
    assert module.KEY_ENVIRONMENT_VARIABLE not in os.environ


def test_acquire_failure_clears_stale_key(tmp_path: Path) -> None:
    module = _module()
    os.environ[module.KEY_ENVIRONMENT_VARIABLE] = "00" * 32
    service = _service(tmp_path, api=_FakeHookApi(key=None, hook_ok=False), pids=[1000])
    with pytest.raises(module.WeChatKeyUnavailable):
        service.acquire()
    assert module.KEY_ENVIRONMENT_VARIABLE not in os.environ


def test_acquire_repeated_uses_newest_key(tmp_path: Path) -> None:
    module = _module()
    first = "ef56" * 16
    second = "7890" * 16
    service = _service(tmp_path, api=_FakeHookApi(key=first), pids=[1000])
    assert service.acquire() == first
    assert os.environ.get(module.KEY_ENVIRONMENT_VARIABLE) == first

    service = _service(tmp_path, api=_FakeHookApi(key=second), pids=[1000])
    assert service.acquire() == second
    assert os.environ.get(module.KEY_ENVIRONMENT_VARIABLE) == second
