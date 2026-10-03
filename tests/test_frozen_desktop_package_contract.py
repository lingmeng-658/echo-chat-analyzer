"""Frozen Windows desktop package contract for the jieba LAC / numpy pruning.

Full-only: this inspects an already built ``dist/Echo`` tree. Building the
package is a separate step (``scripts/build_windows_exe.ps1``), so the tests
skip when no frozen artifact exists instead of starting a build here.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json

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


def test_frozen_package_uses_pinned_echo_napcat_without_qce() -> None:
    _require_frozen_build()
    runtime = DIST_APP / 'runtime'
    manifest = json.loads((PROJECT_ROOT / 'scripts/windows_runtime_manifest.json').read_text())
    for entry in manifest['requirements']:
        assert (runtime / entry['path']).exists(), entry['path']
    assert not (runtime / 'qq').exists()
    assert not list(DIST_APP.rglob('qce-server.exe'))
    assert not list(DIST_APP.rglob('napcat-plugin-qce'))
    assert not (runtime / 'qq-napcat-candidate/static/qce').exists()
    pins = json.loads((PROJECT_ROOT / 'scripts/qq_napcat_runtime_pins.json').read_text())
    candidate = runtime / 'qq-napcat-candidate'
    assert hashlib.sha256((candidate / 'napcat.mjs').read_bytes()).hexdigest() == pins['napcatPatch']['patchedSha256']
    for template in pins['templates']:
        assert hashlib.sha256((candidate / template['target']).read_bytes()).hexdigest() == template['sha256']
    assert json.loads((candidate / 'config/plugins.json').read_text()) == {'napcat-plugin-echo': True}


def test_frozen_import_graph_contains_napcat_provider() -> None:
    assert 'qq_chat_analyzer.providers.napcat_qq_provider' in _frozen_modules()


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
