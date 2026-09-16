"""Packaging contract: the desktop build must not carry jieba LAC or numpy.

``jieba`` reaches ``numpy`` only through ``jieba.lac_small.predict`` and
``jieba.lac_small.utils``. Those two modules are imported lazily from inside
``jieba.Tokenizer.cut``, behind ``use_paddle and is_paddle_installed``, and
Echo never enables paddle. They are therefore dead weight in the frozen
package, and ``LocalChatAnalyzer.spec`` excludes them (and numpy with them)
explicitly.

PyInstaller follows imports that live inside function bodies, so the exclusion
has to be declared in the spec; avoiding the call site would not be enough.
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
SPEC_PATH = PROJECT_ROOT / "LocalChatAnalyzer.spec"

# jieba's only route to numpy.
JIEBA_LAC_SUBPACKAGE = "jieba.lac_small"
# Not a product dependency: numpy is only jieba LAC's optional backend.
UNUSED_TRANSITIVE_MODULES = ("numpy",)


# The probe runs in a fresh interpreter where the excluded modules are really
# gone, so it fails if any production path still needs jieba LAC or numpy.
# Placeholders are substituted with str.replace to keep the source readable.
_NUMPY_FREE_TOKENIZER_PROBE = '''
import sys

BLOCKED_ROOTS = ("numpy", "jieba.lac_small")


class _ExcludedModuleFinder:
    """Simulate the frozen package, where these modules are not shipped."""

    def find_spec(self, fullname, path=None, target=None):
        for root in BLOCKED_ROOTS:
            if fullname == root or fullname.startswith(root + "."):
                raise ModuleNotFoundError(
                    "No module named %r" % fullname, name=fullname
                )
        return None


sys.meta_path.insert(0, _ExcludedModuleFinder())

import jieba
from jieba._compat import check_paddle_install

import qq_chat_analyzer.tokenizer as tokenizer_module

for blocked in ("numpy", "jieba.lac_small", "jieba.lac_small.predict"):
    try:
        __import__(blocked)
    except ImportError:
        pass
    else:
        raise SystemExit("excluded module is still importable: " + blocked)

leaked = sorted(
    name
    for name in (
        "numpy",
        "jieba.lac_small",
        "jieba.lac_small.predict",
        "jieba.lac_small.utils",
    )
    if name in sys.modules
)
if leaked:
    raise SystemExit("excluded modules leaked into sys.modules: " + ",".join(leaked))

if check_paddle_install["is_paddle_installed"]:
    raise SystemExit("paddle mode is unexpectedly enabled")

# Plain jieba segmentation must keep working without numpy.
plain = tokenizer_module.tokenize("我喜欢数据分析")
if plain != ["喜欢", "数据分析"]:
    raise SystemExit("plain jieba segmentation changed: " + repr(plain))

# The jieba.load_userdict path must keep working without numpy.
loaded = tokenizer_module.tokenize(
    "回声协议测试词",
    user_dict_path=__USER_DICT__,
)
if loaded != ["回声协议测试词"]:
    raise SystemExit("user dictionary path changed: " + repr(loaded))

# Stopword filtering must keep working without numpy.
filtered = tokenizer_module.tokenize("我喜欢数据分析", __STOPWORDS__)
if filtered != ["数据分析"]:
    raise SystemExit("stopword filtering changed: " + repr(filtered))

print("PROBE_OK")
'''


def _desktop_excludes() -> list[str]:
    """Return the literal ``desktop_excludes`` list declared by the spec."""
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "desktop_excludes"
            for target in node.targets
        ):
            continue
        return [str(entry) for entry in ast.literal_eval(node.value)]
    raise AssertionError("LocalChatAnalyzer.spec must declare desktop_excludes")


def _import_targets(path: Path) -> set[str]:
    """Return every absolute module name imported by one source file.

    Deferred imports are included on purpose: PyInstaller follows them too.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    if path.is_relative_to(SRC_ROOT):
        package_parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    else:
        # Top-level entry scripts live outside the package, so they carry no
        # package context for relative imports.
        package_parts = [path.stem]
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


def _desktop_sources() -> list[Path]:
    return sorted([*PACKAGE_ROOT.rglob("*.py"), PROJECT_ROOT / "desktop_entry.py"])


def test_spec_excludes_jieba_lac_subpackage_and_numpy() -> None:
    excludes = _desktop_excludes()

    assert JIEBA_LAC_SUBPACKAGE in excludes
    for module in UNUSED_TRANSITIVE_MODULES:
        assert module in excludes


def test_spec_only_excludes_the_lac_subpackage_from_jieba() -> None:
    """Plain jieba segmentation stays in the desktop build."""
    excludes = _desktop_excludes()
    jieba_excludes = [
        entry
        for entry in excludes
        if entry == "jieba" or entry.startswith("jieba.")
    ]

    assert jieba_excludes == [JIEBA_LAC_SUBPACKAGE]


def test_no_desktop_source_references_numpy_or_jieba_lac() -> None:
    offenders: set[str] = set()

    for path in _desktop_sources():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for target in _import_targets(path):
            if (
                target.split(".")[0] in UNUSED_TRANSITIVE_MODULES
                or target == JIEBA_LAC_SUBPACKAGE
                or target.startswith(f"{JIEBA_LAC_SUBPACKAGE}.")
            ):
                offenders.add(f"{relative} -> {target}")

    assert offenders == set()


def test_desktop_source_never_enables_jieba_paddle_mode() -> None:
    """`enable_paddle` would turn numpy from dead weight into a hard need."""
    offenders: set[str] = set()

    for path in _desktop_sources():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "enable_paddle":
                offenders.add(f"{relative} -> enable_paddle")
            if isinstance(node, ast.keyword) and node.arg == "use_paddle":
                offenders.add(f"{relative} -> use_paddle")

    assert offenders == set()


def test_real_jieba_tokenization_survives_without_numpy(tmp_path: Path) -> None:
    """Behaviour guard: real jieba still tokenizes when numpy is absent."""
    user_dict_path = tmp_path / "user-dict.txt"
    user_dict_path.write_text("回声协议测试词 100000 n\n", encoding="utf-8")
    stopwords_path = tmp_path / "stopwords.txt"
    stopwords_path.write_text("我\n喜欢\n", encoding="utf-8")

    probe = (
        _NUMPY_FREE_TOKENIZER_PROBE
        .replace("__USER_DICT__", repr(str(user_dict_path)))
        .replace("__STOPWORDS__", repr(str(stopwords_path)))
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_ROOT)
    environment["PYTHONUTF8"] = "1"

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PROBE_OK" in completed.stdout
