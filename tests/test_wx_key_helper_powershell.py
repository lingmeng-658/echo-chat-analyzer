"""Behavior tests for wx_key_helper.cjs PowerShell enumeration resolution.

The bundled Node must start with the real ``SystemRoot``, so tests inject the
Windows PowerShell base through ``ECHO_WX_KEY_POWERSHELL_BASE``. Production
uses ``%SystemRoot%`` and never sets this variable. A marker-controlled
``powershell.exe`` shim stands in for PowerShell; no real PowerShell, WeChat
process, DLL, or key is touched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WECHAT_RUNTIME = PROJECT_ROOT / "runtime" / "wechat"
BUNDLED_NODE = WECHAT_RUNTIME / "node.exe"
HELPER = WECHAT_RUNTIME / "wx_key_helper.cjs"
POWERSHELL_BASE_ENV = "ECHO_WX_KEY_POWERSHELL_BASE"

# Full-only: real subprocess integration that launches bundled Node together
# with a PowerShell shim. Excluded from the Fast Suite (see pyproject.toml).
pytestmark = pytest.mark.slow_integration


def _fake_powershell(tmp_path: Path, directory: Path) -> Path:
    """Compile a tiny fake powershell.exe whose behavior is marker-driven."""
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("gcc is unavailable for the helper enumeration shim")
    directory.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "fake_powershell.c"
    source.write_text(
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "int main(void) {\n"
        "  const char* marker_path = getenv(\"WX_KEY_ENUMERATION_MARKER\");\n"
        "  FILE* marker = marker_path ? fopen(marker_path, \"rb\") : NULL;\n"
        "  if (marker) {\n"
        "    int fail_code = 1;\n"
        "    fscanf(marker, \"%d\", &fail_code);\n"
        "    fclose(marker);\n"
        "    return fail_code;\n"
        "  }\n"
        "  printf(\"%d\\n\", 4242);\n"
        "  return 0;\n"
        "}\n",
        encoding="ascii",
    )
    executable = directory / "powershell.exe"
    compiled = subprocess.run(
        [gcc, str(source), "-O1", "-s", "-o", str(executable)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr
    return executable


def _run_helper(
    *,
    powershell_base: Path,
    path: str,
    marker: Path,
    dll: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env[POWERSHELL_BASE_ENV] = str(powershell_base)
    env["PATH"] = path
    env["WX_KEY_ENUMERATION_MARKER"] = str(marker)
    return subprocess.run(
        [
            str(BUNDLED_NODE),
            str(HELPER),
            "--dll",
            str(dll),
            "--timeout-ms",
            "1",
        ],
        cwd=WECHAT_RUNTIME,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


def _require_bundled_node() -> None:
    if os.name != "nt" or not BUNDLED_NODE.is_file():
        pytest.skip("bundled Windows Node.js is required")


def test_helper_prefers_systemroot_powershell_over_path(tmp_path: Path) -> None:
    _require_bundled_node()
    system_root = tmp_path / "fake system root"
    marker = tmp_path / "enumeration-marker"
    _fake_powershell(
        tmp_path,
        directory=(
            system_root / "System32" / "WindowsPowerShell" / "v1.0"
        ),
    )
    fake_path = tmp_path / "fake-path"
    fake_path.mkdir()
    (fake_path / "powershell.exe").write_bytes(b"MZ")

    completed = _run_helper(
        powershell_base=system_root,
        path=str(fake_path),
        marker=marker,
        dll=tmp_path / "fictional.dll",
    )

    assert "process_found=true, process_count=1" in completed.stderr


def test_helper_falls_back_to_path_powershell(tmp_path: Path) -> None:
    _require_bundled_node()
    empty_system_root = tmp_path / "empty-system-root"
    empty_system_root.mkdir()
    fake_path = tmp_path / "fake-path"
    marker = tmp_path / "enumeration-marker"
    _fake_powershell(tmp_path, directory=fake_path)

    completed = _run_helper(
        powershell_base=empty_system_root,
        path=str(fake_path),
        marker=marker,
        dll=tmp_path / "fictional.dll",
    )

    assert "process_found=true, process_count=1" in completed.stderr


def test_helper_enumeration_without_weixin_process_is_not_found(
    tmp_path: Path,
) -> None:
    _require_bundled_node()
    if not (WECHAT_RUNTIME / "wx_key.dll").is_file():
        pytest.skip("bundled wx_key.dll is required")
    system_root = tmp_path / "fake system root"
    marker = tmp_path / "enumeration-marker"
    _fake_powershell(
        tmp_path,
        directory=(
            system_root / "System32" / "WindowsPowerShell" / "v1.0"
        ),
    )
    marker.write_text("0", encoding="utf-8")

    completed = _run_helper(
        powershell_base=system_root,
        path=str(tmp_path),
        marker=marker,
        dll=WECHAT_RUNTIME / "wx_key.dll",
    )

    assert "process_found=false, process_count=0" in completed.stderr
    assert "no Weixin process" in completed.stderr


def test_helper_enumeration_failure_keeps_stage_and_fails(
    tmp_path: Path,
) -> None:
    _require_bundled_node()
    system_root = tmp_path / "fake system root"
    marker = tmp_path / "enumeration-marker"
    _fake_powershell(
        tmp_path,
        directory=(
            system_root / "System32" / "WindowsPowerShell" / "v1.0"
        ),
    )
    marker.write_text("9", encoding="utf-8")

    completed = _run_helper(
        powershell_base=system_root,
        path=str(tmp_path),
        marker=marker,
        dll=tmp_path / "fictional.dll",
    )

    assert completed.returncode != 0
    assert "helper_stage=process_enumeration" in completed.stderr
    assert "process_found=" not in completed.stderr
    assert "helper_stage=dll_load" not in completed.stderr


def test_helper_powershell_resolution_prefers_absolute_system_root_path() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert "SystemRoot" in source
    assert "System32" in source
    assert "WindowsPowerShell" in source
    assert "v1.0" in source
    assert "existsSync" in source or "accessSync" in source
    assert source.count("powershell.exe") >= 2
