"""Regression guards for the wcdb_cli clean-clone native build (bootstrap + CMake).

These are static checks only; the real build validation is performed by
scripts/bootstrap_wechat_native.ps1 on a machine with VS2022 + CMake + Git.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SQLCIPHER_PIN = "f049bed66ca26741f09a6e4f0603ed3af195ac96"
ZSTD_PIN = "69036dffe50f385bd3b7b187e3fd230f4b2ef97e"


def _cmake_text() -> str:
    path = ROOT / "src" / "qq_chat_analyzer" / "native" / "wcdb_cli" / "CMakeLists.txt"
    return path.read_text(encoding="utf-8")


def test_cmake_lists_uses_parameterized_wcdb_inputs() -> None:
    text = _cmake_text()
    assert "WCDB_SOURCE_DIR" in text
    assert "WCDB_LIBRARY" in text


def test_cmake_lists_has_no_hardcoded_machine_paths() -> None:
    text = _cmake_text()
    assert "third_party/wcdb-2.1.15" not in text
    assert "wcdb-2.1.15-official" not in text
    assert "runtime/wechat" not in text


def test_bootstrap_script_exists_and_pins_wcdb_inputs() -> None:
    path = ROOT / "scripts" / "bootstrap_wechat_native.ps1"
    assert path.is_file()
    text = path.read_text(encoding="utf-8-sig")
    assert "v2.1.15" in text
    assert SQLCIPHER_PIN in text
    assert ZSTD_PIN in text
    assert "build\\cache" in text or "build/cache" in text