"""Portable Runtime copy tests using only fictional package directories."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_windows_exe.ps1"
KOFFI_SOURCE = PROJECT_ROOT / "runtime" / "wechat" / "node_modules" / "koffi"


def _write(path: Path, content: str = "fictional") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
    return runtime


def _copy_runtime(project_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BUILD_SCRIPT),
            "-ProjectRootOverride",
            str(project_root),
            "-RuntimeOnly",
        ],
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


def test_runtime_build_rejects_koffi_without_entrypoint(tmp_path: Path) -> None:
    _fictional_runtime(tmp_path, koffi_index=False)

    completed = _copy_runtime(tmp_path)

    assert completed.returncode != 0
    assert "runtime\\wechat\\node_modules\\koffi\\index.js" in (
        completed.stderr + completed.stdout
    )


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
