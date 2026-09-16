"""Windows portable runtime contract tests.

The portable package must ship every runtime asset the *product* actually
consumes, and must never ship machine-local state. Both properties are
defined once, in ``scripts/windows_runtime_manifest.json``, and consumed by
both ``scripts/build_windows_exe.ps1`` and these tests so the two can never
drift into separate lists.

These checks are static: they read the manifest and the build script, and they
never require the real runtime (or a real build) to be present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "scripts" / "windows_runtime_manifest.json"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_windows_exe.ps1"
GITIGNORE = PROJECT_ROOT / ".gitignore"

ALLOWED_ENTRY_KEYS = {"path", "source", "type", "description"}
ALLOWED_TYPES = {"file", "directory", "non-empty-directory"}
REQUIRED_TYPES = {"file", "non-empty-directory"}
ALLOWED_SOURCES = {"qq", "wechat"}

# Values that must never appear in a tracked contract file: absolute paths,
# endpoints, and credential vocabulary. Legitimate asset names such as
# ``wx_key.dll`` are deliberately not matched here.
FORBIDDEN_VALUE_FRAGMENTS = (
    "token",
    "cookie",
    "password",
    "secret",
    "db_key",
    "uin",
    "C:\\",
    "C:/",
    "/Users/",
    "http://",
    "https://",
)

# --------------------------------------------------------------------- QQ
# Every path below is reachable from the shipped product boot chain.
QQ_REQUIRED_FILES = {
    # launcher-user.bat:6-10,186 — the file Echo itself starts.
    "qq/launcher-user.bat",
    # The QCE launcher's Priority-4 QQ detector; qq_auth_bridge.py:506-511 also
    # calls it before falling back to the registry/common-directory probe.
    "qq/find-qq.ps1",
    "qq/NapCatWinBootMain.exe",
    "qq/NapCatWinBootHook.dll",
    "qq/napcat.mjs",
    # launcher-user.bat:6,189-233 — patch-package seed handed to the hook.
    "qq/qqnt.json",
    # napcat.mjs:52 static import of a `.js` chunk; the chunk uses ESM syntax,
    # so the package.json `type: module` declaration is load bearing.
    "qq/package.json",
    "qq/conout-wiJ7YKRd.js",
    # napcat.mjs:61647 spawns this worker through worker_threads.
    "qq/worker/conoutSocketWorker.mjs",
    # napcat.mjs:65416 reads the plugin enablement file from config/.
    "qq/config/plugins.json",
    # napcat.mjs:64962,65138 read the plugin manifest; index.mjs:248 and
    # ApiLauncher.mjs:4 chain into the QCE runtime modules.
    "qq/plugins/napcat-plugin-qce/package.json",
    "qq/plugins/napcat-plugin-qce/index.mjs",
    "qq/plugins/napcat-plugin-qce/runtime/ApiLauncher.mjs",
    "qq/plugins/napcat-plugin-qce/runtime/rustBridge.mjs",
    # ApiLauncher.mjs:11-21 accepts static/qce only when index.html exists.
    "qq/static/qce/index.html",
    # napcat.mjs:46 imports "express" and :49 imports "ws" as bare specifiers.
    "qq/node_modules/express/package.json",
    "qq/node_modules/ws/package.json",
    # rustBridge.mjs:268-293 looks for qce-server.exe next to the plugin root.
    "qq/qce-server.exe",
}

QQ_REQUIRED_NATIVE_ADDONS = {
    "qq/native/dpapi/win32-x64/@primno+dpapi.node",
    "qq/native/ffmpeg/ffmpegAddon.win32.x64.node",
    "qq/native/napi2native/ffmpeg.dll",
    "qq/native/napi2native/napi2native.win32.x64.node",
    "qq/native/packet/MoeHoo.win32.x64.node",
    "qq/native/pty/win32.x64/conpty.node",
    "qq/native/pty/win32.x64/conpty_console_list.node",
    "qq/native/pty/win32.x64/pty.node",
    "qq/native/pty/win32.x64/winpty-agent.exe",
    "qq/native/pty/win32.x64/winpty.dll",
}

QQ_REQUIRED_DIRECTORIES = {
    "qq/node_modules",
    "qq/plugins",
    "qq/static/qce",
}

# ------------------------------------------------------------------ WeChat
WECHAT_REQUIRED_FILES = {
    "wechat/wcdb_cli.exe",
    "wechat/WCDB.dll",
    "wechat/wx_key.dll",
    "wechat/wx_key_helper.cjs",
    "wechat/node.exe",
    "wechat/node_modules/koffi/index.js",
    "wechat/node_modules/koffi/build/koffi/win32_x64/koffi.node",
}

WECHAT_REQUIRED_DIRECTORIES = {
    "wechat/node_modules",
}

REQUIRED_FILES = QQ_REQUIRED_FILES | QQ_REQUIRED_NATIVE_ADDONS | WECHAT_REQUIRED_FILES
REQUIRED_DIRECTORIES = QQ_REQUIRED_DIRECTORIES | WECHAT_REQUIRED_DIRECTORIES

# Machine-local state that must never become a shipped requirement.
PRIVATE_PATHS = {
    "qq/cache",
    "qq/logs",
    "qq/config/qq_path.txt",
    "qq/config/webui.json",
    "qq/config/plugins",
    "qq/loadNapCat.js",
}

# Filename prefixes NapCat/QCE use for per-install configuration. They carry a
# real QQ identifier, so no contract entry may ever be named like one.
INSTALL_SCOPED_PREFIXES = ("napcat_", "napcat-protocol_", "onebot11_")


def _load_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), (
        "runtime contract manifest is missing: "
        "scripts/windows_runtime_manifest.json"
    )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entries(manifest: dict, key: str) -> list[dict]:
    value = manifest.get(key)
    assert isinstance(value, list), f"manifest field '{key}' must be a list"
    return value


def _paths(manifest: dict, key: str) -> set[str]:
    return {str(entry["path"]) for entry in _entries(manifest, key)}


def _build_script_text() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8-sig")


# ------------------------------------------------------- manifest structure


def test_manifest_uses_the_minimal_agreed_schema() -> None:
    manifest = _load_manifest()

    assert set(manifest) == {"requirements", "privatePaths"}

    for key in ("requirements", "privatePaths"):
        for entry in _entries(manifest, key):
            assert set(entry) <= ALLOWED_ENTRY_KEYS, entry
            assert "path" in entry and "source" in entry and "type" in entry, entry
            assert entry["source"] in ALLOWED_SOURCES, entry
            assert entry["type"] in ALLOWED_TYPES, entry


def test_manifest_uses_presence_types_only_for_requirements() -> None:
    manifest = _load_manifest()

    for entry in _entries(manifest, "requirements"):
        assert entry["type"] in REQUIRED_TYPES, entry
    for entry in _entries(manifest, "privatePaths"):
        assert entry["type"] in {"file", "directory"}, entry


def test_manifest_paths_are_relative_and_normalised() -> None:
    manifest = _load_manifest()

    for key in ("requirements", "privatePaths"):
        for entry in _entries(manifest, key):
            path = str(entry["path"])
            assert not path.startswith(("/", "\\")), path
            assert ":" not in path, path
            assert "\\" not in path, path
            assert ".." not in path.split("/"), path


def test_manifest_entries_belong_to_their_declared_source() -> None:
    manifest = _load_manifest()

    for key in ("requirements", "privatePaths"):
        for entry in _entries(manifest, key):
            assert str(entry["path"]).startswith(f"{entry['source']}/"), entry


def test_manifest_carries_no_endpoints_or_credential_vocabulary() -> None:
    manifest = _load_manifest()
    payload = json.dumps(manifest, ensure_ascii=False).lower()

    for fragment in FORBIDDEN_VALUE_FRAGMENTS:
        assert fragment.lower() not in payload, fragment


def test_manifest_never_names_an_install_scoped_config_file() -> None:
    manifest = _load_manifest()

    for key in ("requirements", "privatePaths"):
        for entry in _entries(manifest, key):
            name = str(entry["path"]).rsplit("/", 1)[-1].lower()
            for prefix in INSTALL_SCOPED_PREFIXES:
                assert not name.startswith(prefix), entry


# -------------------------------------------------------- required coverage


@pytest.mark.parametrize("path", sorted(REQUIRED_FILES))
def test_manifest_requires_every_product_hard_dependency(path: str) -> None:
    manifest = _load_manifest()
    entries = {
        str(entry["path"]): entry for entry in _entries(manifest, "requirements")
    }

    assert path in entries, f"runtime contract is missing required asset: {path}"
    assert entries[path]["type"] == "file", entries[path]


@pytest.mark.parametrize("path", sorted(REQUIRED_DIRECTORIES))
def test_manifest_requires_payload_directories_to_be_non_empty(path: str) -> None:
    manifest = _load_manifest()
    entries = {
        str(entry["path"]): entry for entry in _entries(manifest, "requirements")
    }

    assert path in entries, f"runtime contract is missing required directory: {path}"
    assert entries[path]["type"] == "non-empty-directory", entries[path]


def test_manifest_describes_qq_and_wechat_runtime_separately() -> None:
    manifest = _load_manifest()
    sources = {entry["source"] for entry in _entries(manifest, "requirements")}

    assert sources == {"qq", "wechat"}


# --------------------------------------------------------- privacy contract


@pytest.mark.parametrize("path", sorted(PRIVATE_PATHS))
def test_manifest_declares_machine_local_state_as_private(path: str) -> None:
    manifest = _load_manifest()

    assert path in _paths(manifest, "privatePaths"), (
        f"machine-local state is not declared private: {path}"
    )


def test_private_paths_are_never_shipped_requirements() -> None:
    manifest = _load_manifest()
    requirements = _paths(manifest, "requirements")
    private = _paths(manifest, "privatePaths")

    assert requirements.isdisjoint(private)
    for requirement in requirements:
        for private_path in private:
            assert not requirement.startswith(f"{private_path}/"), (
                f"{requirement} sits under private path {private_path}"
            )


def test_private_contract_covers_cache_logs_and_local_paths() -> None:
    manifest = _load_manifest()
    private = _paths(manifest, "privatePaths")

    for directory in ("qq/cache", "qq/logs"):
        assert directory in private
    assert "qq/config/qq_path.txt" in private
    assert "qq/config/webui.json" in private


# ------------------------------------------- build and tests share one source


def test_gitignore_explicitly_tracks_the_manifest() -> None:
    """``*.json`` is ignored repo-wide, so the contract needs a negation."""
    lines = [
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert "!scripts/windows_runtime_manifest.json" in lines, (
        "scripts/windows_runtime_manifest.json is matched by the global '*.json' "
        "ignore rule and would never be tracked"
    )


def test_build_script_reads_the_same_manifest() -> None:
    script = _build_script_text()

    assert "windows_runtime_manifest.json" in script, (
        "build script does not consume the shared runtime contract manifest"
    )


def test_build_script_keeps_no_parallel_required_path_list() -> None:
    """A second hand-maintained list is exactly what we are removing."""
    script = _build_script_text()

    assert "$RequiredRuntimePaths" not in script, (
        "build script still declares its own required-path array"
    )
    assert "RequiredRuntimePaths" not in script


@pytest.mark.parametrize(
    "filename",
    [
        "napcat.mjs",
        "NapCatWinBootMain.exe",
        "NapCatWinBootHook.dll",
        "launcher-user.bat",
        "conoutSocketWorker.mjs",
        "@primno+dpapi.node",
        "wx_key.dll",
        "wx_key_helper.cjs",
        "wcdb_cli.exe",
        "WCDB.dll",
        "koffi.node",
    ],
)
def test_build_script_does_not_hardcode_runtime_asset_paths(
    filename: str,
) -> None:
    script = _build_script_text()

    assert filename not in script, (
        f"{filename} is restated in the build script instead of being read "
        "from the runtime contract manifest"
    )


def test_build_script_loads_the_contract_before_packaging() -> None:
    script = _build_script_text()

    manifest_index = script.index("windows_runtime_manifest.json")
    pyinstaller_index = script.index("--noconfirm")

    assert manifest_index < pyinstaller_index, (
        "the runtime contract must be validated before packaging starts"
    )
