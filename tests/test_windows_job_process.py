"""Native lifecycle tests: only short-lived fictional Python processes."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import gc
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job API")


def _module():
    name = "qq_chat_analyzer.runtime.windows_job"
    assert importlib.util.find_spec(name) is not None, "atomic owned-process launcher missing"
    return importlib.import_module(name)


def _command(directory, role="tree", level=2):
    return [sys.executable, str(Path(__file__).resolve()), role, str(directory), str(level)]


def _until(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("fictional process did not reach expected state")


def _native():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, args, result in [
        ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        ("IsProcessInJob", [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        ("GetCurrentProcess", [], wintypes.HANDLE),
        ("GetProcessHandleCount", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
    ]:
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _handle_count():
    # Sample only after closed objects and their Python cycles are released.
    gc.collect()
    api = _native()
    result = wintypes.DWORD()
    assert api.GetProcessHandleCount(api.GetCurrentProcess(), ctypes.byref(result))
    return result.value


def _warmup_owned_process(module):
    # Exercise the same process, pipe and text machinery before every baseline.
    # Function scope releases the process reference before _handle_count's GC.
    process = module.launch_owned_process(
        [sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="strict")
    try:
        process.communicate(timeout=8)
    finally:
        process.close()
    assert process.closed
    assert process.stdout.closed and process.stderr.closed


def _tree_handles(directory):
    # Open handles while workers are alive, never terminate by a PID marker.
    handles = []
    try:
        for level in (2, 1, 0):
            path = directory / f"node-{level}.json"
            _until(lambda: path.exists() and path.stat().st_size)
            pid = json.loads(path.read_text())["pid"]
            handle = _native().OpenProcess(0x100000 | 0x1000, False, pid)
            assert handle
            handles.append(handle)
        return handles
    except BaseException:
        for handle in handles:
            _native().CloseHandle(handle)
        raise


def _dead(handles):
    return all(_native().WaitForSingleObject(handle, 0) == 0 for handle in handles)


@pytest.mark.slow_integration
def test_close_terminates_descendants_after_launcher_exit(tmp_path):
    process = _module().launch_owned_process(_command(tmp_path, "parent-exits"), cwd=tmp_path)
    handles = []
    try:
        handles = _tree_handles(tmp_path)
        (tmp_path / "root-exit").write_text("release fictional launcher")
        assert process.wait(timeout=8) == 0
        assert not _dead(handles[1:])
        assert process.tree_running()
        process.close()
        _until(lambda: _dead(handles))
        process.close()  # idempotent, no PID fallback
        assert not process.tree_running()
    finally:
        process.close()
        for handle in handles:
            _native().CloseHandle(handle)


@pytest.mark.slow_integration
def test_forced_owner_exit_kills_tree_without_touching_other_instance(tmp_path):
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    module = _module()
    owner = module.launch_owned_process(_command(tmp_path, "owner"), cwd=tmp_path)
    other = module.launch_owned_process(_command(other_dir), cwd=other_dir)
    handles = []
    try:
        handles = _tree_handles(tmp_path)
        _until(lambda: (tmp_path / "owner-ready").exists())
        # Terminate only the fictional owner by its retained native handle.
        # Closing its outer safety job would mask a missing inner Job.
        assert module._kernel32().TerminateProcess(owner._process_handle, 77)
        owner.wait(timeout=8)
        _until(lambda: _dead(handles))
        assert other.tree_running()
    finally:
        owner.close()
        other.close()
        for handle in handles:
            _native().CloseHandle(handle)


@pytest.mark.slow_integration
def test_normal_exit_unicode_env_cwd_pipes_and_no_handle_leak(tmp_path):
    module = _module()
    # Windows/Python lazily initialize process/pipe machinery on first use.
    # Measure subsequent complete cycles, not one-time runtime initialization.
    _warmup_owned_process(module)
    before = _handle_count()
    process = module.launch_owned_process(
        _command(tmp_path, "stdio"), cwd=tmp_path,
        env={**os.environ, "FICTIONAL_VALUE": "虚构路径 空格"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="strict")
    try:
        out, err = process.communicate(timeout=8)
        assert json.loads(out) == {"value": "虚构路径 空格", "cwd": str(tmp_path)}
        assert err == "fictional stderr\n"
        assert process.returncode == 0
    finally:
        process.close()
    assert process.closed
    assert process.stdout.closed and process.stderr.closed
    del process
    assert _handle_count() == before


@pytest.mark.slow_integration
def test_timeout_and_terminate_keep_job_until_explicit_close(tmp_path):
    process = _module().launch_owned_process(_command(tmp_path), cwd=tmp_path)
    handles = []
    try:
        handles = _tree_handles(tmp_path)
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.01)
        process.terminate()
        _until(lambda: _dead(handles))
        process.close()
    finally:
        process.close()
        for handle in handles:
            _native().CloseHandle(handle)


@pytest.mark.parametrize("failure", ["CreateJobObjectW", "SetInformationJobObject",
    "InitializeProcThreadAttributeList", "UpdateProcThreadAttribute", "CreateProcessW"])
def test_native_creation_failures_do_not_launch_or_leak(tmp_path, monkeypatch, failure):
    module = _module()
    api = module._kernel32()
    created = []
    class FailingAPI:
        def __getattr__(self, name):
            real = getattr(api, name)
            if name == failure:
                def fail(*args):
                    ctypes.set_last_error(5)
                    return 0
                return fail
            if name == "CreateProcessW":
                def create(*args):
                    created.append(True)
                    return real(*args)
                return create
            return real
    _warmup_owned_process(module)
    before = _handle_count()
    monkeypatch.setattr(module, "_kernel32", lambda: FailingAPI())
    with pytest.raises(OSError):
        module.launch_owned_process(_command(tmp_path), cwd=tmp_path)
    assert created == []
    assert list(tmp_path.iterdir()) == []
    assert _handle_count() == before


@pytest.mark.slow_integration
def test_error_after_native_creation_closes_job_process_and_thread(tmp_path, monkeypatch):
    """Interrupted result handling must not leak the already-created handles."""
    module = _module()
    api = module._kernel32()
    # Warm Windows's process machinery before the resource baseline.
    _warmup_owned_process(module)
    before = _handle_count()
    class FailingResult:
        def __getattr__(self, name):
            if name == "CreateProcessW":
                def create(*args):
                    assert api.CreateProcessW(*args)
                    ctypes.set_last_error(5)
                    return 0  # failure after PROCESS_INFORMATION was populated
                return create
            return getattr(api, name)
    monkeypatch.setattr(module, "_kernel32", lambda: FailingResult())
    with pytest.raises(OSError):
        module.launch_owned_process(_command(tmp_path), cwd=tmp_path)
    assert _handle_count() == before


@pytest.mark.slow_integration
def test_job_membership_exists_before_initial_thread_runs(tmp_path, monkeypatch):
    module = _module()
    api = module._kernel32()
    class SuspendedAPI:
        def __getattr__(self, name):
            if name == "CreateProcessW":
                def create(application, command, pa, ta, inherit, flags, *rest):
                    return api.CreateProcessW(application, command, pa, ta, inherit,
                                              flags | 4, *rest)
                return create
            return getattr(api, name)
    monkeypatch.setattr(module, "_kernel32", lambda: SuspendedAPI())
    process = module.launch_owned_process(_command(tmp_path), cwd=tmp_path)
    try:
        member = wintypes.BOOL()
        assert _native().IsProcessInJob(process._process_handle, process._job_handle,
                                       ctypes.byref(member))
        assert member.value
        assert list(tmp_path.iterdir()) == []
    finally:
        process.close()


@pytest.mark.slow_integration
def test_breakaway_attempt_stays_in_job_or_is_rejected(tmp_path):
    module = _module()
    process = module.launch_owned_process(_command(tmp_path, "breakaway"), cwd=tmp_path)
    handles = []
    try:
        _until(lambda: (tmp_path / "breakaway-result").exists())
        result = (tmp_path / "breakaway-result").read_text()
        if result == "created":
            handles = _tree_handles(tmp_path)
            for handle in handles:
                member = wintypes.BOOL()
                assert _native().IsProcessInJob(handle, process._job_handle, ctypes.byref(member))
                assert member.value, "fictional child escaped the owning Job"
            process.close()
            _until(lambda: _dead(handles))
        else:
            assert result == "5"
    finally:
        process.close()
        for handle in handles:
            _native().CloseHandle(handle)


@pytest.mark.slow_integration
def test_restricted_outer_job_rejects_nested_creation(tmp_path):
    module = _module()
    process = module.launch_owned_process(_command(tmp_path, "restricted-owner"), cwd=tmp_path)
    try:
        _until(lambda: (tmp_path / "owner-ready").exists())
        accounting = module._Accounting()
        api = module._kernel32()
        assert api.QueryInformationJobObject(process._job_handle, 1,
            ctypes.byref(accounting), ctypes.sizeof(accounting), None)
        limits = module._ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8
        limits.BasicLimitInformation.ActiveProcessLimit = accounting.ActiveProcesses
        assert api.SetInformationJobObject(process._job_handle, 9,
            ctypes.byref(limits), ctypes.sizeof(limits))
        (tmp_path / "attempt-launch").write_text("fictional nested launch")
        _until(lambda: (tmp_path / "creation-result").exists())
        assert (tmp_path / "creation-result").read_text() == "rejected"
        assert not (tmp_path / "node-2.json").exists()
    finally:
        process.close()


def _worker(role, directory, level):
    deadline = time.monotonic() + 20  # autonomous safety bound
    if role == "owner":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        process = _module().launch_owned_process(_command(directory), cwd=directory)
        _until(lambda: (directory / "node-0.json").exists())
        (directory / "owner-ready").write_text("fictional owner")
        while time.monotonic() < deadline:
            time.sleep(0.05)
        process.close()
        return
    if role == "restricted-owner":
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        (directory / "owner-ready").write_text("fictional restricted owner")
        _until(lambda: (directory / "attempt-launch").exists())
        try:
            process = _module().launch_owned_process(_command(directory), cwd=directory)
        except OSError:
            (directory / "creation-result").write_text("rejected")
        else:
            process.close()
            (directory / "creation-result").write_text("unmanaged failure")
        return
    if role == "breakaway":
        try:
            child = subprocess.Popen(_command(directory), close_fds=True,
                                     creationflags=0x1000000)
        except OSError as error:
            (directory / "breakaway-result").write_text(str(error.winerror))
        else:
            (directory / "breakaway-result").write_text("created")
            child.wait(timeout=25)
        return
    if role == "stdio":
        print(json.dumps({"value": os.environ["FICTIONAL_VALUE"], "cwd": os.getcwd()}))
        print("fictional stderr", file=sys.stderr)
        return
    child = None
    if level:
        child = subprocess.Popen(_command(directory, "tree", level - 1), close_fds=True)
    (directory / f"node-{level}.json").write_text(json.dumps({"pid": os.getpid()}))
    if role == "parent-exits":
        while time.monotonic() < deadline and not (directory / "root-exit").exists():
            time.sleep(0.02)
        return
    while time.monotonic() < deadline:
        time.sleep(0.05)
    if child:
        child.wait(timeout=5)


if __name__ == "__main__":
    _worker(sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]))
