"""Portable Runtime copy tests using only fictional package directories."""

from __future__ import annotations

import re
import shutil
import subprocess
import struct
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_windows_exe.ps1"
KOFFI_SOURCE = PROJECT_ROOT / "runtime" / "wechat" / "node_modules" / "koffi"

# NapCat ships native addons for every Node.js platform/arch pair it supports
# and selects exactly one variant at runtime via
# `process.platform + "." + process.arch` (native\ffmpeg, native\napi2native,
# native\packet, native\pty, native\dpapi). A Windows x64 distribution can only
# ever load the win32.x64 addons, so the packaged copy must not carry the
# foreign platform/arch variants. The pattern matches a single path segment
# carrying a foreign platform designator (native\pty\linux.x64,
# native\dpapi\win32-arm64) or a foreign architecture designator for an
# x64-only distribution (MoeHoo.linux.arm64.node).
FOREIGN_NATIVE_SEGMENT = re.compile(
    r"(?:^|[._-])(?:linux|darwin|freebsd|openbsd|netbsd|sunos|aix|android|arm64)"
    r"(?:[._-]|$)"
)

WINDOWS_X64_NATIVE_ASSETS = (
    "dpapi/win32-x64/@primno+dpapi.node",
    "ffmpeg/ffmpegAddon.win32.x64.node",
    "napi2native/ffmpeg.dll",
    "napi2native/napi2native.win32.x64.node",
    "packet/MoeHoo.win32.x64.node",
    "pty/win32.x64/conpty.node",
    "pty/win32.x64/conpty_console_list.node",
    "pty/win32.x64/pty.node",
    "pty/win32.x64/winpty-agent.exe",
    "pty/win32.x64/winpty.dll",
)

FOREIGN_NATIVE_ASSETS = (
    "dpapi/win32-arm64/@primno+dpapi.node",
    "ffmpeg/ffmpegAddon.darwin.arm64.node",
    "ffmpeg/ffmpegAddon.linux.arm64.node",
    "ffmpeg/ffmpegAddon.linux.x64.node",
    "napi2native/napi2native.darwin.arm64.node",
    "napi2native/napi2native.linux.arm64.node",
    "napi2native/napi2native.linux.x64.node",
    "packet/MoeHoo.darwin.arm64.node",
    "packet/MoeHoo.linux.arm64.node",
    "packet/MoeHoo.linux.x64.node",
    "pty/linux.arm64/pty.node",
    "pty/linux.x64/pty.node",
)

# Full-only: build/packaging smoke that runs build_windows_exe.ps1 and loads
# the bundled Node runtime. Excluded from the Fast Suite (see pyproject.toml).
pytestmark = pytest.mark.slow_integration


def _write(path: Path, content: str = "fictional") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fictional_native_tree(runtime: Path) -> None:
    """Mirror the upstream NapCat native addon layout for every platform."""
    native = runtime / "qq" / "native"
    for relative in WINDOWS_X64_NATIVE_ASSETS + FOREIGN_NATIVE_ASSETS:
        _write(native / relative)


def _fictional_runtime(
    project_root: Path,
    *,
    koffi_index: bool = True,
    node_executable: bool = True,
) -> Path:
    runtime = project_root / "runtime"
    for relative in (
        "qq/qce-server.exe",
        "qq/napcat.mjs",
        "qq/NapCatWinBootMain.exe",
        "qq/NapCatWinBootHook.dll",
        "qq/static/qce/index.html",
        "wechat/wcdb_cli.exe",
        "wechat/WCDB.dll",
        "wechat/wx_key.dll",
        "wechat/wx_key_helper.cjs",
    ):
        _write(runtime / relative)
    if node_executable:
        _write(runtime / "wechat/node.exe")
    if koffi_index:
        _write(
            runtime / "wechat/node_modules/koffi/index.js",
            "module.exports = { fictional: true }\n",
        )
        _write(
            runtime
            / "wechat/node_modules/koffi/build/koffi/win32_x64/koffi.node"
        )
    _write(
        runtime / "wechat/node_modules/koffi/nested/sentinel.txt",
        "nested dependency",
    )
    _write(
        runtime / "qq/config/plugins.json",
        '{"napcat-plugin-qce": true}\n',
    )
    _write(
        runtime / "qq/config/napcat_fictional-account.json",
        '{"account": "fictional"}\n',
    )
    # The build script also ships the WeChat WCDB diagnostic runner next to
    # the frozen app; mirror it in the fictional project so RuntimeOnly builds
    # exercise the same runner packaging path as real builds.
    _write(
        project_root / "scripts" / "run_wechat_wcdb_diagnostic.ps1",
        "# fictional diagnostic runner\n",
    )
    _fictional_native_tree(runtime)
    return runtime


def _copy_runtime(
    project_root: Path,
    *,
    msvc_runtime_directory: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT),
            "-ProjectRootOverride",
            str(project_root),
            "-RuntimeOnly",
        ]
    if msvc_runtime_directory is not None:
        command.extend(
            ["-MsvcRuntimeDirectoryOverride", str(msvc_runtime_directory)]
        )
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_runtime_only_build_copies_complete_wechat_node_module(
    tmp_path: Path,
) -> None:
    _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    copied = tmp_path / "dist/Echo/runtime/wechat/node_modules/koffi"
    assert (copied / "index.js").is_file()
    assert (copied / "nested/sentinel.txt").read_text(encoding="utf-8") == (
        "nested dependency"
    )
    shipped_runner = tmp_path / "dist/Echo/scripts/run_wechat_wcdb_diagnostic.ps1"
    assert shipped_runner.is_file()
    assert shipped_runner.read_text(encoding="utf-8").startswith(
        "# fictional diagnostic runner"
    )


def test_runtime_build_ships_wx_key_msvc_runtime_dependencies(
    tmp_path: Path,
) -> None:
    """wx_key.dll must not rely on VC++ being installed system-wide."""
    _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    for runtime_name in ("wechat", "qq"):
        portable_runtime = tmp_path / "dist/Echo/runtime" / runtime_name
        for filename in (
            "msvcp140.dll",
            "vcruntime140.dll",
            "vcruntime140_1.dll",
        ):
            dependency = portable_runtime / filename
            assert dependency.is_file(), (
                f"missing app-local native dependency: {runtime_name}/{filename}"
            )
            assert dependency.stat().st_size > 0


def test_runtime_build_rejects_missing_msvc_runtime_dependency(
    tmp_path: Path,
) -> None:
    _fictional_runtime(tmp_path)
    incomplete_runtime = tmp_path / "fictional-msvc-runtime"
    incomplete_runtime.mkdir()

    completed = _copy_runtime(
        tmp_path,
        msvc_runtime_directory=incomplete_runtime,
    )

    assert completed.returncode != 0
    assert "Required native runtime dependency is missing: msvcp140.dll" in (
        completed.stderr + completed.stdout
    )


def test_runtime_build_enforces_minimum_msvc_runtime_version() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8-sig")

    assert '$MsvcRuntimeMinimumVersion = [Version]"14.43"' in script
    assert "Native runtime dependency is too old" in script


def _pe_machine(path: Path) -> int:
    with path.open("rb") as binary:
        assert binary.read(2) == b"MZ"
        binary.seek(0x3C)
        pe_offset = struct.unpack("<I", binary.read(4))[0]
        binary.seek(pe_offset)
        assert binary.read(4) == b"PE\0\0"
        return struct.unpack("<H", binary.read(2))[0]


def test_key_portable_native_binaries_are_x64() -> None:
    portable = PROJECT_ROOT / "dist" / "Echo"
    required = (
        portable / "Echo.exe",
        portable / "runtime/qq/qce-server.exe",
        portable / "runtime/qq/NapCatWinBootMain.exe",
        portable / "runtime/qq/NapCatWinBootHook.dll",
        portable / "runtime/wechat/node.exe",
        portable / "runtime/wechat/wcdb_cli.exe",
        portable / "runtime/wechat/WCDB.dll",
        portable / "runtime/wechat/wx_key.dll",
        portable
        / "runtime/wechat/node_modules/koffi/build/koffi/win32_x64/koffi.node",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        pytest.skip("built portable runtime is unavailable")

    assert {_pe_machine(path) for path in required} == {0x8664}


def test_runtime_build_rejects_koffi_without_entrypoint(tmp_path: Path) -> None:
    _fictional_runtime(tmp_path, koffi_index=False)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert "runtime\\wechat\\node_modules\\koffi\\index.js" in (
        completed.stderr + completed.stdout
    )


def test_runtime_build_rejects_missing_koffi_windows_addon(
    tmp_path: Path,
) -> None:
    runtime = _fictional_runtime(tmp_path)
    (
        runtime
        / "wechat/node_modules/koffi/build/koffi/win32_x64/koffi.node"
    ).unlink()

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert "koffi\\build\\koffi\\win32_x64\\koffi.node" in (
        completed.stderr + completed.stdout
    )


@pytest.mark.parametrize(
    "filename",
    ["NapCatWinBootMain.exe", "NapCatWinBootHook.dll"],
)
def test_runtime_build_rejects_missing_qq_native_launcher(
    tmp_path: Path,
    filename: str,
) -> None:
    runtime = _fictional_runtime(tmp_path)
    (runtime / "qq" / filename).unlink()

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert filename in completed.stderr + completed.stdout


def test_runtime_build_rejects_missing_bundled_node(tmp_path: Path) -> None:
    _fictional_runtime(tmp_path, node_executable=False)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert "runtime\\wechat\\node.exe" in (
        completed.stderr + completed.stdout
    )


def test_runtime_build_keeps_qce_plugin_enablement_without_account_state(
    tmp_path: Path,
) -> None:
    _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    portable_config = tmp_path / "dist/Echo/runtime/qq/config"
    assert (portable_config / "plugins.json").read_text(encoding="utf-8") == (
        '{"napcat-plugin-qce": true}\n'
    )
    assert not (portable_config / "napcat_fictional-account.json").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_copied_portable_koffi_can_be_loaded_by_node(tmp_path: Path) -> None:
    if not (KOFFI_SOURCE / "index.js").is_file():
        pytest.skip("Koffi Runtime package is unavailable")
    runtime = _fictional_runtime(tmp_path)
    shutil.copytree(
        KOFFI_SOURCE,
        runtime / "wechat/node_modules/koffi",
        dirs_exist_ok=True,
    )
    completed = _copy_runtime(tmp_path)
    assert completed.returncode == 0, completed.stderr

    helper_probe = subprocess.run(
        ["node", "-e", "require('koffi'); process.stdout.write('loaded')"],
        cwd=tmp_path / "dist/Echo/runtime/wechat",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert helper_probe.returncode == 0, helper_probe.stderr
    assert helper_probe.stdout == "loaded"


def _foreign_native_entries(native: Path) -> list[str]:
    """Return packaged native entries carrying a foreign platform designator."""
    foreign: list[str] = []
    for path in native.rglob("*"):
        relative = path.relative_to(native).as_posix()
        if any(
            FOREIGN_NATIVE_SEGMENT.search(segment)
            for segment in relative.split("/")
        ):
            foreign.append(relative)
    return sorted(foreign)


def test_runtime_build_prunes_non_windows_native_addons(tmp_path: Path) -> None:
    """The packaged runtime must only ship the Windows x64 native addons."""
    _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    native = tmp_path / "dist/Echo/runtime/qq/native"
    assert native.is_dir()
    assert _foreign_native_entries(native) == []


def test_runtime_build_ships_windows_x64_native_addons(tmp_path: Path) -> None:
    """Pruning must not remove the addons the Windows x64 runtime loads."""
    _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    native = tmp_path / "dist/Echo/runtime/qq/native"
    missing = [
        relative
        for relative in WINDOWS_X64_NATIVE_ASSETS
        if not (native / relative).is_file()
    ]
    assert missing == []


def test_runtime_build_keeps_repository_native_assets_intact(
    tmp_path: Path,
) -> None:
    """Pruning is a packaging concern: the repository runtime stays complete."""
    runtime = _fictional_runtime(tmp_path)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode == 0, completed.stderr
    missing = [
        relative
        for relative in FOREIGN_NATIVE_ASSETS
        if not (runtime / "qq/native" / relative).is_file()
    ]
    assert missing == []


def test_runtime_build_rejects_missing_windows_native_addon(
    tmp_path: Path,
) -> None:
    """A Windows x64 build must not silently ship an incomplete native set."""
    runtime = _fictional_runtime(tmp_path)
    (runtime / "qq/native/packet/MoeHoo.win32.x64.node").unlink()

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert "MoeHoo.win32.x64.node" in (completed.stderr + completed.stdout)
