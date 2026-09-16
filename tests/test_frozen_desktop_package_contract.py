"""Frozen Windows desktop package contract for the jieba LAC / numpy pruning.

Full-only: this inspects an already built ``dist/Echo`` tree. Building the
package is a separate step (``scripts/build_windows_exe.ps1``), so the tests
skip when no frozen artifact exists instead of starting a build here.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_APP = PROJECT_ROOT / "dist" / "Echo"
INTERNAL = DIST_APP / "_internal"
EXECUTABLE = DIST_APP / "Echo.exe"

# Retained on purpose: Echo never uses jieba LAC, but plain segmentation and
# the other jieba data files stay in the package.
KEPT_RUNTIME_DIRECTORIES = ("PySide6", "shiboken6", "zstandard")

pytestmark = pytest.mark.slow_integration


def _require_frozen_build() -> None:
    if not EXECUTABLE.is_file():
        pytest.skip(f"no frozen desktop build at {DIST_APP}")


def _frozen_modules() -> dict:
    """Return the module table embedded in the frozen executable's PYZ."""
    _require_frozen_build()
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(EXECUTABLE))
    return reader.open_embedded_archive("PYZ.pyz").toc


def test_frozen_package_does_not_contain_numpy() -> None:
    _require_frozen_build()
    modules = _frozen_modules()

    assert not (INTERNAL / "numpy").exists()
    assert not any(
        entry.name.startswith("numpy-") for entry in INTERNAL.iterdir()
    )
    assert [name for name in modules if name.split(".")[0] == "numpy"] == []


def test_frozen_package_does_not_contain_numpy_native_libraries() -> None:
    _require_frozen_build()

    assert not (INTERNAL / "numpy.libs").exists()


def test_frozen_package_drops_jieba_lac_python_modules() -> None:
    modules = _frozen_modules()

    lac_modules = sorted(
        name
        for name in modules
        if name == "jieba.lac_small" or name.startswith("jieba.lac_small.")
    )

    assert lac_modules == []


def test_frozen_package_keeps_plain_jieba_segmentation_modules() -> None:
    modules = _frozen_modules()

    assert "jieba" in modules
    assert "jieba._compat" in modules
    assert "jieba.finalseg" in modules


def test_frozen_package_keeps_jieba_dictionary_and_probability_data() -> None:
    """Plain segmentation needs dict.txt plus the HMM/POS probability tables."""
    _require_frozen_build()
    jieba_data = INTERNAL / "jieba"

    assert (jieba_data / "dict.txt").is_file()
    assert (jieba_data / "finalseg" / "prob_emit.p").is_file()
    assert (jieba_data / "posseg" / "prob_emit.p").is_file()


def test_frozen_package_keeps_hook_collected_lac_model_data() -> None:
    """Documented boundary: this change does not touch jieba's data files.

    ``hook-jieba`` collects every non-Python file under ``jieba``, including
    ``lac_small/model_baseline``. Removing that data is a separate decision.
    """
    _require_frozen_build()
    model_baseline = INTERNAL / "jieba" / "lac_small" / "model_baseline"

    assert model_baseline.is_dir()
    assert (model_baseline / "word_emb").is_file()


@pytest.mark.parametrize("relative", KEPT_RUNTIME_DIRECTORIES)
def test_frozen_package_keeps_retained_runtime_libraries(relative: str) -> None:
    _require_frozen_build()

    assert (INTERNAL / relative).is_dir()
