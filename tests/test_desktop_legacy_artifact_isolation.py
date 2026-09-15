"""Packaging contract: the desktop import graph stays free of the legacy stack.

The pre-Echo CSV/chart artifacts (word-frequency CSVs, word cloud, top-speaker
chart) only remain as legacy CLI output. Their libraries (matplotlib, wordcloud,
Pillow, pandas) must therefore never be reachable from the desktop entry point,
because PyInstaller collects whatever the import graph references -- including
imports written inside function bodies.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "qq_chat_analyzer"

# Libraries that only the legacy CLI artifacts need.
LEGACY_LIBRARY_MODULES = (
    "matplotlib",
    "wordcloud",
    "pandas",
    "PIL",
)

# The two files allowed to reference them: the legacy exporter itself and the
# CLI-only adapter that calls it.
ALLOWED_LEGACY_IMPORTERS = {
    "qq_chat_analyzer/exporters.py",
    "qq_chat_analyzer/application/legacy_word_artifacts.py",
}


def _import_targets(path: Path) -> set[str]:
    """Return every absolute module name imported by one package source file."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    package_parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if package_parts[-1] == "__init__":
        package_parts.pop()
    else:
        package_parts.pop()

    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            base = package_parts[: len(package_parts) - (node.level - 1)]
        else:
            base = []
        if node.module:
            base = [*base, *node.module.split(".")]
        if not base:
            continue
        module_name = ".".join(base)
        targets.add(module_name)
        targets.update(f"{module_name}.{alias.name}" for alias in node.names)
    return targets


def test_desktop_analysis_import_does_not_load_legacy_libraries(
    tmp_path: Path,
) -> None:
    """Importing the desktop analysis service must stay off the legacy stack."""
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SRC_ROOT), existing_pythonpath) if part
    )
    environment["MPLCONFIGDIR"] = str(tmp_path / "matplotlib-config")
    import_check = f"""
import sys

import qq_chat_analyzer.application.analysis_service  # noqa: F401

legacy_modules = [
    name
    for name in {list(LEGACY_LIBRARY_MODULES)!r}
    if name in sys.modules
]
if legacy_modules:
    raise SystemExit("legacy libraries imported: " + ",".join(legacy_modules))
if "qq_chat_analyzer.exporters" in sys.modules:
    raise SystemExit("legacy exporters module imported")
"""

    completed = subprocess.run(
        [sys.executable, "-c", import_check],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_only_legacy_modules_import_the_legacy_graphics_stack() -> None:
    """No desktop module may even reference the legacy libraries.

    A source level check on purpose: PyInstaller follows imports that live
    inside function bodies, so a deferred ``import`` would still package
    matplotlib and wordcloud into Echo.
    """
    offenders: set[str] = set()
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(SRC_ROOT).as_posix()
        if relative in ALLOWED_LEGACY_IMPORTERS:
            continue
        for target in _import_targets(path):
            if target == "qq_chat_analyzer.exporters" or (
                target.split(".")[0] in LEGACY_LIBRARY_MODULES
            ):
                offenders.add(f"{relative} -> {target}")

    assert offenders == set()


def test_legacy_importer_allowlist_matches_real_files() -> None:
    """Keep the allowlist honest when the legacy modules are renamed."""
    for relative in sorted(ALLOWED_LEGACY_IMPORTERS):
        assert (SRC_ROOT / relative).is_file(), relative
