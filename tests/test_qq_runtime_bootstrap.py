"""Stage 3B contract tests for the QQ runtime bootstrap.

A clean clone has to restore the complete ``runtime/qq`` tree from a single
official source: the QCE ``NapCat-QCE-Windows-x64-v6.2.3.zip`` release asset.
Everything the bootstrap may install is pinned in ``scripts/qq_runtime_pins.json``
(version, archive URL, archive SHA256, launcher patch, required member hashes)
and everything it must never install is declared either in the shared runtime
contract manifest or in the pin file's exclusion list.

The launcher identity is pinned three ways: the upstream ``launcher-user.bat``
SHA256, the deterministic Echo patch (one exact anchor block, replaced once) and
the final patched SHA256.

Everything here is fictional, offline and isolated: the bootstrap is always run
from a temporary copy of the script, against a temporary project root, with a
temporary archive and a temporary pin file. No real QCE asset is downloaded,
no account state is involved, and the repository ``runtime`` directory is never
touched.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "scripts" / "bootstrap_qq_runtime.ps1"
PINS_PATH = PROJECT_ROOT / "scripts" / "qq_runtime_pins.json"
MANIFEST_PATH = PROJECT_ROOT / "scripts" / "windows_runtime_manifest.json"
GITIGNORE = PROJECT_ROOT / ".gitignore"

# ------------------------------------------------------------- pinned facts
QCE_VERSION = "6.2.3"
NAPCAT_VERSION = "4.18.18"
QCE_PROJECT = "shuakami/qq-chat-exporter"
QCE_RELEASE_URL = f"https://github.com/{QCE_PROJECT}/releases/tag/v{QCE_VERSION}"
QCE_ARCHIVE_URL = (
    f"https://github.com/{QCE_PROJECT}/releases/download/v{QCE_VERSION}/"
    f"NapCat-QCE-Windows-x64-v{QCE_VERSION}.zip"
)
QCE_ARCHIVE_SHA256 = (
    "d079d3dd92e8b0314ede0a53bf1f528729af71acefde8cceabdfca456b597e49"
)
QCE_ARCHIVE_SIZE_BYTES = 41809798
QCE_ARCHIVE_ROOT = "NapCat-QCE-Windows-x64"

UPSTREAM_LAUNCHER_SHA256 = (
    "60d916cc816be13a16e77419590239e7b8bd410b72020abc8c549ba4352ea993"
)
PATCHED_LAUNCHER_SHA256 = (
    "9134df029f4eb67b5d4680e3e9defbafb80c23c8d65ec749516db90734763df7"
)
QQNT_SEED_SHA256 = (
    "45346fc8694c6c14a7eb74c290f2de31072d9848ba08807c127770b028e920d6"
)
FIND_QQ_SHA256 = (
    "721a672078619ee2303d62bc0d6129a5fc08eb8f6a1d9476319df466916670c6"
)

LAUNCHER_PATH = "launcher-user.bat"
LAUNCHER_ANCHOR = ":end_script\r\n\r\npause\r\nexit /b\r\n"
LAUNCHER_ADDED_LINE = 'if "%ECHO_MODE%"=="1" exit /b'
LAUNCHER_REPLACEMENT = (
    ':end_script\n\nif "%ECHO_MODE%"=="1" exit /b\npause\nexit /b\n'
)

# The Direct DB helper seam: the upstream QCE plugin entry is patched once (the
# anchor must occur exactly once in the upstream file), and Echo's own snapshot
# helper is injected from a tracked template. Neither value is an upstream
# archive member, so neither may appear under ``requiredFiles``.
INDEX_PATH = "plugins/napcat-plugin-qce/index.mjs"
INDEX_ANCHOR = (
    "    apiLauncher = new QQChatExporterApiLauncher(runtimeCore);\r\n"
    "    await apiLauncher.startApiServer();\r\n"
    "  } catch (error) {\r\n"
)
INDEX_ADDED_LINE = (
    "const { registerEchoSnapshotApi } = "
    "await import('./direct_db_research/snapshot.mjs');"
)
INDEX_REPLACEMENT = (
    "    apiLauncher = new QQChatExporterApiLauncher(runtimeCore);\r\n"
    "    await apiLauncher.startApiServer();\r\n"
    "\r\n"
    "    // Echo-injected Direct DB snapshot seam. Registers an explicit\r\n"
    "    // acquire/cleanup/recover API on runtimeCore.apis and never decrypts at\r\n"
    "    // startup; the local-only helper owns a single-flight decrypt + atomic publish.\r\n"
    "    const { registerEchoSnapshotApi } = await import('./direct_db_research/snapshot.mjs');\r\n"
    "    registerEchoSnapshotApi(runtimeCore);\r\n"
    "  } catch (error) {\r\n"
)

NAPCAT_PATH = "napcat.mjs"
NAPCAT_REPLACEMENTS = [
    {
        "anchor": "  let a;\n  if (r.onCmd(\"OidbSvcTrpcTcp.0xcde_2\"",
        "replacement": "  let a, core;\n  if (r.onCmd(\"OidbSvcTrpcTcp.0xcde_2\"",
    },
    {
        "anchor": "D.inner?.value && (a = D.inner.value, e.log(",
        "replacement": "D.inner?.value && (a = D.inner.value, core && (core.dbPassphrase = a), e.log(",
    },
    {
        "anchor": "  a && (Y.core.dbPassphrase = a), await Y.InitNapCat();",
        "replacement": "  core = Y.core, a && (core.dbPassphrase = a), await Y.InitNapCat();",
    },
    {
        "anchor": "function LE(t, e, n) {\n  const r = Ge.readFileSync(t), i = UE(r, e);",
        "replacement": (
            "function LE(t, e, n) {\n"
            "  const echoFileState = (p) => { try { const s = Ge.statSync(p); "
            "return { present: s.isFile(), bytes: s.isFile() ? s.size : 0, mtimeMs: s.mtimeMs }; "
            "} catch { return { present: false, bytes: 0, mtimeMs: 0 }; } }, "
            "echoBefore = { database: echoFileState(t), wal: echoFileState(`${t}-wal`), "
            "shm: echoFileState(`${t}-shm`) }, r = Ge.readFileSync(t), "
            "echoAfter = { database: echoFileState(t), wal: echoFileState(`${t}-wal`), "
            "shm: echoFileState(`${t}-shm`) };\n"
            "  globalThis.__ECHO_DIRECT_DB_READ_STATE__ = { "
            "databaseBefore: echoBefore.database, databaseAfter: echoAfter.database, "
            "walBefore: echoBefore.wal, walAfter: echoAfter.wal, "
            "shmBefore: echoBefore.shm, shmAfter: echoAfter.shm, readBytes: r.length };\n"
            "  const i = UE(r, e);"
        ),
    },
]

SNAPSHOT_TARGET_PATH = "plugins/napcat-plugin-qce/direct_db_research/snapshot.mjs"
SNAPSHOT_TEMPLATE_PATH = "qq_direct_db_snapshot/snapshot.mjs"
SNAPSHOT_TEMPLATE = (
    b"// fictional Direct DB snapshot helper for the Stage 3B test suite\n"
    b"export async function createSnapshotFromNapCatCore(core) {}\n"
)

# Upstream members the bootstrap patches, pinned via launcherPatch/indexPatch
# instead of requiredFiles; and members the bootstrap injects from a tracked
# Echo template, which are never upstream archive members at all.
PATCHED_UPSTREAM_PATHS = {LAUNCHER_PATH, INDEX_PATH}
SNAPSHOT_DEPENDENCIES = ('main_wal.mjs', 'workspace.mjs')
ECHO_INJECTED_PATHS = {SNAPSHOT_TARGET_PATH} | {
    f'plugins/napcat-plugin-qce/direct_db_research/{name}' for name in SNAPSHOT_DEPENDENCIES
}

OFFICIAL_SOURCE_HOST = "github.com"
OFFICIAL_REDIRECT_HOSTS = {"github.com", "objects.githubusercontent.com"}

MIRROR_MARKERS = (
    "npmmirror",
    "taobao",
    "cnpm",
    "jsdelivr",
    "unpkg",
    "gitee",
    "gitcode",
    "ghproxy",
)

# Runtime state and upstream per-install config the bootstrap must never install.
PINS_EXCLUDED_PATHS = (
    "cache",
    "config/napcat.json",
    "config/onebot11.json",
    "config/plugins",
    "loadNapCat.js",
    "logs",
    "qce-notification-icon.png",
)

# Machine-local members the fictional archive deliberately ships so the test can
# prove they never survive a bootstrap run.
MACHINE_STATE_MEMBERS = (
    "cache/qrcode.png",
    "config/qq_path.txt",
    "config/webui.json",
    "loadNapCat.js",
    "logs/napcat.log",
    "qce-notification-icon.png",
)

# Upstream attribution the bootstrap must keep byte for byte.
ATTRIBUTION_MEMBERS = ("README.txt", "LICENSE")

FORBIDDEN_SCRIPT_FRAGMENTS = (
    "npm install",
    "npm ci",
    "npx",
    "Invoke-Expression",
    "Start-Process",
    "Get-Command node",
    "dist\\",
    "dist/",
    "C:\\",
)

# The restore itself lives in a top-level try/catch/finally at the bottom of the
# script, *after* the helper functions. Helpers carry try/finally pairs of their
# own, so anything asserted about the runtime body has to be located from this
# anchor rather than from the head of the file.
BOOTSTRAP_BODY_ANCHOR = "$PinsPath = Join-Path $PSScriptRoot 'qq_runtime_pins.json'"
SUCCESS_BANNER = "bootstrap_qq_runtime.ps1 完成"
TEMP_CLEANUP_COMMAND = "Remove-Item -LiteralPath $Path -Recurse -Force"


# ------------------------------------------------------------------ helpers
def _script_text() -> str:
    assert BOOTSTRAP_SCRIPT.is_file(), (
        "QQ runtime bootstrap is missing: scripts/bootstrap_qq_runtime.ps1"
    )
    return BOOTSTRAP_SCRIPT.read_text(encoding="utf-8-sig")


def _bootstrap_body(script: str) -> str:
    assert BOOTSTRAP_BODY_ANCHOR in script, (
        "the bootstrap body no longer starts at the pin-file wiring"
    )
    start = script.index(BOOTSTRAP_BODY_ANCHOR)
    return script[start : script.index(SUCCESS_BANNER, start)]


def _brace_block(text: str, start: int) -> str:
    opening = text.index("{", start)
    depth = 0
    for position in range(opening, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                return text[opening : position + 1]
    raise AssertionError("unbalanced braces in the bootstrap body")


def _pins() -> dict:
    assert PINS_PATH.is_file(), (
        "QQ runtime pin file is missing: scripts/qq_runtime_pins.json"
    )
    return json.loads(PINS_PATH.read_text(encoding="utf-8"))


def _manifest() -> dict:
    assert MANIFEST_PATH.is_file(), (
        "runtime contract manifest is missing: "
        "scripts/windows_runtime_manifest.json"
    )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _manifest_qq_file_paths() -> list[str]:
    """Every QQ file the runtime contract requires, relative to ``qq/``."""
    return sorted(
        str(entry["path"])[len("qq/") :]
        for entry in _manifest()["requirements"]
        if entry["source"] == "qq" and entry["type"] == "file"
    )


def _manifest_qq_private_paths() -> list[str]:
    return sorted(
        str(entry["path"])[len("qq/") :]
        for entry in _manifest()["privatePaths"]
        if entry["source"] == "qq"
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fictional_launcher(*, tail: bytes = LAUNCHER_ANCHOR.encode()) -> bytes:
    """Miniature stand-in for the upstream QCE ``launcher-user.bat``."""
    return (
        b"@echo off\r\n"
        b"rem fictional QCE launcher for the Stage 3B test suite\r\n"
        b"if not exist qqnt.json goto :reset\r\n"
        b"goto :eof\r\n"
        b"\r\n"
        + tail
    )


def _fictional_index(*, tail: bytes = INDEX_ANCHOR.encode()) -> bytes:
    """Miniature stand-in for the upstream QCE plugin ``index.mjs``."""
    return (
        b"// fictional QCE plugin entry for the Stage 3B test suite\r\n"
        b"export async function plugin_init() {\r\n"
        + tail
        + b"    console.error('fictional catch');\r\n"
        b"  }\r\n"
        b"}\r\n"
    )


def _fictional_archive_members(
    *,
    drop: tuple[str, ...] = (),
    extra: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    """The upstream payload every fictional archive ships, keyed by relative path."""
    members = {
        relative: f"fictional runtime payload: {relative}\n".encode()
        for relative in _manifest_qq_file_paths()
        if relative not in ECHO_INJECTED_PATHS
    }
    members[LAUNCHER_PATH] = _fictional_launcher()
    members[INDEX_PATH] = _fictional_index()
    members[NAPCAT_PATH] = (
        b"// fictional pinned NapCat source\n"
        b"  let a;\n  if (r.onCmd(\"OidbSvcTrpcTcp.0xcde_2\"\n"
        b"    D.inner?.value && (a = D.inner.value, e.log(\"ready\"));\n"
        b"  a && (Y.core.dbPassphrase = a), await Y.InitNapCat();\n"
        b"function LE(t, e, n) {\n  const r = Ge.readFileSync(t), i = UE(r, e);\n"
    )
    for relative in ATTRIBUTION_MEMBERS + MACHINE_STATE_MEMBERS:
        members[relative] = f"fictional upstream file: {relative}\n".encode()
    members["config/napcat.json"] = b'{"fictional": "upstream config"}\n'
    members["config/onebot11.json"] = b'{"fictional": "upstream config"}\n'
    members["config/plugins/napcat-plugin-builtin/config.json"] = (
        b'{"fictional": "upstream plugin config"}\n'
    )
    if extra:
        members.update(extra)
    for relative in drop:
        members.pop(relative, None)
    return members


def _write_archive(
    destination: Path,
    members: dict[str, bytes],
    *,
    root: str = QCE_ARCHIVE_ROOT,
    traversal_members: tuple[str, ...] = (),
) -> Path:
    with zipfile.ZipFile(destination, "w") as archive:
        for relative, payload in members.items():
            archive.writestr(f"{root}/{relative}", payload)
        for name in traversal_members:
            archive.writestr(name, b"fictional traversal payload\n")
    return destination


def _pin_payload(
    *,
    archive_sha256: str,
    archive_size_bytes: int,
    upstream_launcher_sha256: str,
    patched_launcher_sha256: str,
    upstream_index_sha256: str,
    patched_index_sha256: str,
    upstream_napcat_sha256: str,
    patched_napcat_sha256: str,
    snapshot_template_sha256: str,
    required_files: dict[str, str],
    archive_url: str = QCE_ARCHIVE_URL,
    release_url: str = QCE_RELEASE_URL,
    archive_root: str = QCE_ARCHIVE_ROOT,
    excluded_paths: tuple[str, ...] = PINS_EXCLUDED_PATHS,
) -> dict:
    return {
        "qce": {
            "version": QCE_VERSION,
            "project": QCE_PROJECT,
            "license": "GPL-3.0",
            "releaseUrl": release_url,
            "archiveUrl": archive_url,
            "archiveSha256": archive_sha256,
            "archiveSizeBytes": archive_size_bytes,
            "archiveRoot": archive_root,
            "bundledNapCatVersion": NAPCAT_VERSION,
            "bundledNapCatProject": "NapNeko/NapCatQQ",
            "bundledNapCatLicense": "Limited Redistribution License for NapCat",
        },
        "launcherPatch": {
            "path": LAUNCHER_PATH,
            "upstreamSha256": upstream_launcher_sha256,
            "patchedSha256": patched_launcher_sha256,
            "anchor": LAUNCHER_ANCHOR,
            "replacement": LAUNCHER_REPLACEMENT,
            "addedLine": LAUNCHER_ADDED_LINE,
        },
        "indexPatch": {
            "path": INDEX_PATH,
            "upstreamSha256": upstream_index_sha256,
            "patchedSha256": patched_index_sha256,
            "anchor": INDEX_ANCHOR,
            "replacement": INDEX_REPLACEMENT,
            "addedLine": INDEX_ADDED_LINE,
        },
        "napcatPatch": {
            "path": NAPCAT_PATH,
            "upstreamSha256": upstream_napcat_sha256,
            "patchedSha256": patched_napcat_sha256,
            "replacements": NAPCAT_REPLACEMENTS,
        },
        "directDbSnapshot": {
            "templatePath": SNAPSHOT_TEMPLATE_PATH,
            "templateSha256": snapshot_template_sha256,
            "targetPath": SNAPSHOT_TARGET_PATH,
            "dependencies": [
                {"templatePath": f'qq_direct_db_snapshot/{name}',
                 "templateSha256": _sha256(f'// fictional {name}\n'.encode()),
                 "targetPath": f'plugins/napcat-plugin-qce/direct_db_research/{name}'}
                for name in SNAPSHOT_DEPENDENCIES
            ],
        },
        "requiredFiles": required_files,
        "excludedPaths": list(excluded_paths),
    }


def _required_file_pins(members: dict[str, bytes]) -> dict[str, str]:
    return {
        relative: _sha256(members[relative])
        for relative in _manifest_qq_file_paths()
        if relative not in PATCHED_UPSTREAM_PATHS and relative in members
    }


def _stage_workspace(
    tmp_path: Path,
    *,
    members: dict[str, bytes] | None = None,
    archive_url: str = QCE_ARCHIVE_URL,
    release_url: str = QCE_RELEASE_URL,
    archive_root: str = QCE_ARCHIVE_ROOT,
    pinned_archive_root: str | None = None,
    archive_sha256: str | None = None,
    archive_size_bytes: int | None = None,
    upstream_launcher_sha256: str | None = None,
    patched_launcher_sha256: str | None = None,
    upstream_index_sha256: str | None = None,
    patched_index_sha256: str | None = None,
    snapshot_template_sha256: str | None = None,
    required_files: dict[str, str] | None = None,
    traversal_members: tuple[str, ...] = (),
) -> tuple[Path, Path, dict[str, bytes]]:
    """Stage an isolated copy of the bootstrap plus its own pins and manifest."""
    assert BOOTSTRAP_SCRIPT.is_file(), (
        "QQ runtime bootstrap is missing: scripts/bootstrap_qq_runtime.ps1"
    )
    payload = members if members is not None else _fictional_archive_members()
    archive = _write_archive(
        tmp_path / "NapCat-QCE-Windows-x64-v6.2.3.zip",
        payload,
        root=archive_root,
        traversal_members=traversal_members,
    )
    launcher = payload.get(LAUNCHER_PATH, b"")
    patched = launcher.replace(
        LAUNCHER_ANCHOR.encode(), LAUNCHER_REPLACEMENT.encode(), 1
    )
    index_entry = payload.get(INDEX_PATH, b"")
    patched_index = index_entry.replace(
        INDEX_ANCHOR.encode(), INDEX_REPLACEMENT.encode(), 1
    )
    napcat_entry = payload.get(NAPCAT_PATH, b"")
    patched_napcat = napcat_entry
    for edit in NAPCAT_REPLACEMENTS:
        patched_napcat = patched_napcat.replace(
            edit["anchor"].encode(), edit["replacement"].encode(), 1
        )
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BOOTSTRAP_SCRIPT, scripts / BOOTSTRAP_SCRIPT.name)
    shutil.copy2(MANIFEST_PATH, scripts / MANIFEST_PATH.name)
    template_dir = scripts / "qq_direct_db_snapshot"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "snapshot.mjs").write_bytes(SNAPSHOT_TEMPLATE)
    for name in SNAPSHOT_DEPENDENCIES:
        (template_dir / name).write_bytes(f'// fictional {name}\n'.encode())
    (scripts / "qq_runtime_pins.json").write_text(
        json.dumps(
            _pin_payload(
                archive_sha256=archive_sha256 or _sha256(archive.read_bytes()),
                archive_size_bytes=(
                    archive_size_bytes
                    if archive_size_bytes is not None
                    else archive.stat().st_size
                ),
                upstream_launcher_sha256=(
                    upstream_launcher_sha256 or _sha256(launcher)
                ),
                patched_launcher_sha256=(
                    patched_launcher_sha256 or _sha256(patched)
                ),
                upstream_index_sha256=(
                    upstream_index_sha256 or _sha256(index_entry)
                ),
                patched_index_sha256=(
                    patched_index_sha256 or _sha256(patched_index)
                ),
                upstream_napcat_sha256=_sha256(napcat_entry),
                patched_napcat_sha256=_sha256(patched_napcat),
                snapshot_template_sha256=(
                    snapshot_template_sha256 or _sha256(SNAPSHOT_TEMPLATE)
                ),
                required_files=(
                    required_files
                    if required_files is not None
                    else _required_file_pins(payload)
                ),
                archive_url=archive_url,
                release_url=release_url,
                archive_root=pinned_archive_root or archive_root,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    return scripts / BOOTSTRAP_SCRIPT.name, archive, payload


def _is_excluded(relative: str, excluded: set[str]) -> bool:
    return any(
        relative == entry or relative.startswith(f"{entry}/") for entry in excluded
    )


def _expected_installed_members(payload: dict[str, bytes]) -> list[str]:
    excluded = set(PINS_EXCLUDED_PATHS) | set(_manifest_qq_private_paths())
    installed = {
        relative for relative in payload if not _is_excluded(relative, excluded)
    }
    # The Direct DB helper is injected from a tracked template, so it is never
    # part of the upstream payload but must still land in the installed runtime.
    installed.update(ECHO_INJECTED_PATHS)
    return sorted(installed)


def _seed_stale_runtime(project_root: Path) -> None:
    """Pre-existing runtime tree the bootstrap must replace wholesale."""
    runtime = project_root / "runtime" / "qq"
    stale_files = (
        "static/qce/index.html",
        "static/qce/_next/static/chunks/stale-old-build.js",
        "static/qce/stale-build-id/index.html",
        "node_modules/stale-package/package.json",
        "plugins/stale-plugin/index.mjs",
        "plugins/napcat-plugin-qce/direct_db_research/snapshot.mjs",
        "launcher-user.bat",
        "qqnt.json",
        "README.txt",
        "loadNapCat.js",
        "qce-notification-icon.png",
        "cache/qrcode.png",
        "logs/napcat.log",
        "config/qq_path.txt",
        "config/webui.json",
        "config/plugins/napcat-plugin-builtin/config.json",
    )
    for relative in stale_files:
        target = runtime / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"stale {relative}\n".encode())


def _run_bootstrap(
    script: Path,
    project_root: Path,
    *extra_arguments: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ProjectRootOverride",
        str(project_root),
        *extra_arguments,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _offline_archive(archive: Path) -> list[str]:
    return ["-QceArchivePath", str(archive)]


def _output(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stdout + completed.stderr


def _relative_files(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def _tree_hashes(root: Path) -> dict[str, str]:
    return {relative: _sha256((root / relative).read_bytes()) for relative in _relative_files(root)}


def _bootstrap_temp_entries() -> set[str]:
    return {
        entry.name for entry in Path(tempfile.gettempdir()).glob("echo-qq-runtime-*")
    }


def _runtime_leftovers(project_root: Path) -> list[str]:
    runtime = project_root / "runtime"
    if not runtime.is_dir():
        return []
    return sorted(
        entry.name
        for entry in runtime.iterdir()
        if entry.name.startswith(".qq-bootstrap-")
    )


# ------------------------------------------------------ pinned source facts
def test_pins_lock_the_official_qce_release() -> None:
    qce = _pins()["qce"]

    assert qce["version"] == QCE_VERSION
    assert qce["project"] == QCE_PROJECT
    assert qce["releaseUrl"] == QCE_RELEASE_URL
    assert qce["archiveUrl"] == QCE_ARCHIVE_URL
    assert qce["archiveSha256"].lower() == QCE_ARCHIVE_SHA256
    assert qce["archiveSizeBytes"] == QCE_ARCHIVE_SIZE_BYTES
    assert qce["archiveRoot"] == QCE_ARCHIVE_ROOT


def test_pins_record_the_bundled_upstream_attribution() -> None:
    qce = _pins()["qce"]

    assert qce["bundledNapCatVersion"] == NAPCAT_VERSION
    assert qce["bundledNapCatProject"] == "NapNeko/NapCatQQ"
    assert qce["bundledNapCatLicense"] == "Limited Redistribution License for NapCat"
    assert qce["license"] == "GPL-3.0"


def test_pins_lock_the_echo_launcher_patch() -> None:
    patch = _pins()["launcherPatch"]

    assert patch["path"] == LAUNCHER_PATH
    assert patch["upstreamSha256"].lower() == UPSTREAM_LAUNCHER_SHA256
    assert patch["patchedSha256"].lower() == PATCHED_LAUNCHER_SHA256
    assert patch["upstreamSha256"] != patch["patchedSha256"]
    assert patch["addedLine"] == LAUNCHER_ADDED_LINE
    assert patch["anchor"] == LAUNCHER_ANCHOR
    assert patch["replacement"] == LAUNCHER_REPLACEMENT
    assert patch["replacement"].count(patch["addedLine"]) == 1
    assert patch["anchor"].endswith("pause\r\nexit /b\r\n")
    assert patch["replacement"].endswith("pause\nexit /b\n")


def test_pins_lock_the_echo_index_patch() -> None:
    patch = _pins()["indexPatch"]

    assert patch["path"] == INDEX_PATH
    assert patch["anchor"] == INDEX_ANCHOR
    assert patch["replacement"] == INDEX_REPLACEMENT
    assert patch["addedLine"] == INDEX_ADDED_LINE
    assert patch["replacement"].count(patch["addedLine"]) == 1
    assert patch["anchor"].count(patch["addedLine"]) == 0
    assert patch["anchor"].count("await apiLauncher.startApiServer();") == 1
    assert patch["upstreamSha256"] != patch["patchedSha256"]
    assert len(patch["upstreamSha256"]) == 64
    assert len(patch["patchedSha256"]) == 64
    # The Direct DB helper is an Echo asset, never an upstream archive member.
    assert INDEX_PATH not in _pins()["requiredFiles"]


def test_pinned_napcat_patch_updates_core_when_passphrase_arrives_after_login() -> None:
    pins = _pins()
    patch = pins["napcatPatch"]
    assert patch["path"] == "napcat.mjs"
    assert len(patch["replacements"]) == 4
    assert any("core.dbPassphrase = a" in item["replacement"] for item in patch["replacements"])
    assert any("core = Y.core" in item["replacement"] for item in patch["replacements"])
    assert patch["upstreamSha256"] == pins["requiredFiles"]["napcat.mjs"]

    # Execute the exact pinned expressions with fictional bytes in both orderings.
    node = shutil.which("node")
    if node is None:
        pytest.skip("the NapCat passphrase race test requires Node")
    declaration = patch["replacements"][0]["replacement"].split("\n", 1)[0]
    packet_expression = patch["replacements"][1]["replacement"]
    login_expression = patch["replacements"][2]["replacement"]
    script = (
        f"{declaration}\n"
        "const e = { log() {} };\n"
        "const Y = { core: {} };\n"
        "function onPacket(value) { const D = { inner: { value } }; "
        f"{packet_expression}'ready')); }}\n"
        "async function init() { Y.InitNapCat = async () => {}; "
        f"{login_expression} }}\n"
        "const fictional = Buffer.from('fictional');\n"
        "onPacket(fictional); init().then(() => {\n"
        "  if (!Y.core.dbPassphrase?.equals(fictional)) throw Error('early packet lost');\n"
        "  a = undefined; core = undefined; Y.core.dbPassphrase = undefined;\n"
        "  return init();\n"
        "}).then(() => {\n"
        "  onPacket(fictional);\n"
        "  if (!Y.core.dbPassphrase?.equals(fictional)) throw Error('late packet lost');\n"
        "});\n"
    )
    completed = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_pinned_napcat_patch_captures_only_safe_exact_read_window_state(
    tmp_path: Path,
) -> None:
    patch = _pins()["napcatPatch"]["replacements"][3]
    assert "readFileSync(t)" in patch["anchor"]
    assert "__ECHO_DIRECT_DB_READ_STATE__" in patch["replacement"]
    assert "readBytes" in patch["replacement"]
    assert "passphrase" not in patch["replacement"].lower()

    source = tmp_path / "fictional.db"
    source.write_bytes(b"fictional-main")
    (tmp_path / "fictional.db-wal").write_bytes(b"fictional-wal")
    (tmp_path / "fictional.db-shm").write_bytes(b"fictional-shm")
    node = shutil.which("node")
    if node is None:
        pytest.skip("the NapCat exact-read diagnostic test requires Node")
    function_source = patch["anchor"].replace(
        "function LE(t, e, n) {\n  const r = Ge.readFileSync(t), i = UE(r, e);",
        patch["replacement"],
    )
    script = (
        "const Ge = require('node:fs'); const UE = (value) => value;\n"
        f"{function_source}\n return i; }}\n"
        f"LE({json.dumps(str(source))}, null, null);\n"
        "const state = globalThis.__ECHO_DIRECT_DB_READ_STATE__;\n"
        "if (state.readBytes !== 14) throw Error('wrong read size');\n"
        "if (!state.walBefore.present || !state.shmAfter.present) throw Error('missing sidecar state');\n"
        "if ('path' in state || JSON.stringify(state).includes('fictional.db')) throw Error('path leaked');\n"
    )
    completed = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_pins_lock_the_direct_db_snapshot_template() -> None:
    pins = _pins()
    snapshot = pins["directDbSnapshot"]

    assert snapshot["templatePath"] == SNAPSHOT_TEMPLATE_PATH
    assert snapshot["targetPath"] == SNAPSHOT_TARGET_PATH
    assert len(snapshot["templateSha256"]) == 64
    assert snapshot["templateSha256"] == snapshot["templateSha256"].lower()
    # The injected helper must never be presented as an upstream archive member.
    assert SNAPSHOT_TARGET_PATH not in pins["requiredFiles"]
    template = PROJECT_ROOT / "scripts" / "qq_direct_db_snapshot" / "snapshot.mjs"
    assert template.is_file(), (
        "the Direct DB helper template is missing: scripts/qq_direct_db_snapshot/snapshot.mjs"
    )
    assert _sha256(template.read_bytes()) == snapshot["templateSha256"]
    assert {Path(item['templatePath']).name for item in snapshot['dependencies']} == set(SNAPSHOT_DEPENDENCIES)
    for item in snapshot['dependencies']:
        assert _sha256((PROJECT_ROOT / 'scripts' / item['templatePath']).read_bytes()) == item['templateSha256']


def test_pins_lock_the_qqnt_seed_and_the_launcher_detector() -> None:
    required = _pins()["requiredFiles"]

    assert required["qqnt.json"].lower() == QQNT_SEED_SHA256
    assert required["find-qq.ps1"].lower() == FIND_QQ_SHA256


def test_pins_cover_every_contract_file_requirement() -> None:
    """A new contract requirement must be pinned before it can be bootstrapped."""
    pins = _pins()
    pinned = (
        set(pins["requiredFiles"])
        | {pins["launcherPatch"]["path"]}
        | {pins["indexPatch"]["path"]}
        | {pins["directDbSnapshot"]["targetPath"]}
        | {item['targetPath'] for item in pins['directDbSnapshot']['dependencies']}
    )

    missing = sorted(set(_manifest_qq_file_paths()) - pinned)
    assert missing == [], (
        "runtime contract requirements without a pinned upstream hash: "
        + ", ".join(missing)
    )
    for relative, digest in pins["requiredFiles"].items():
        assert len(digest) == 64, relative
        assert digest == digest.lower(), relative


def test_pins_declare_the_agreed_exclusions() -> None:
    pins = _pins()

    assert set(pins["excludedPaths"]) == set(PINS_EXCLUDED_PATHS)
    # config/plugins.json is a contract seed and must never be excluded, while
    # the per-install config/plugins directory must always be.
    assert "config/plugins.json" not in pins["excludedPaths"]
    assert "config/plugins" in pins["excludedPaths"]
    assert "qce-notification-icon.png" in pins["excludedPaths"]


def test_pins_declare_only_the_agreed_fields() -> None:
    pins = _pins()

    assert set(pins) == {
        "qce",
        "launcherPatch",
        "indexPatch",
        "napcatPatch",
        "directDbSnapshot",
        "requiredFiles",
        "excludedPaths",
    }
    assert set(pins["qce"]) == {
        "version",
        "project",
        "license",
        "releaseUrl",
        "archiveUrl",
        "archiveSha256",
        "archiveSizeBytes",
        "archiveRoot",
        "bundledNapCatVersion",
        "bundledNapCatProject",
        "bundledNapCatLicense",
    }
    assert set(pins["launcherPatch"]) == {
        "path",
        "upstreamSha256",
        "patchedSha256",
        "anchor",
        "replacement",
        "addedLine",
    }
    assert set(pins["indexPatch"]) == {
        "path",
        "upstreamSha256",
        "patchedSha256",
        "anchor",
        "replacement",
        "addedLine",
    }
    assert set(pins["napcatPatch"]) == {
        "path", "upstreamSha256", "patchedSha256", "replacements",
    }
    assert set(pins["directDbSnapshot"]) == {
        "templatePath",
        "templateSha256",
        "targetPath",
        "dependencies",
    }


def test_pins_only_reference_the_official_release() -> None:
    pins = _pins()
    payload = json.dumps(pins).lower()

    for url in (pins["qce"]["archiveUrl"], pins["qce"]["releaseUrl"]):
        assert url.startswith("https://")
        host = url.split("/", 3)[2]
        assert host in OFFICIAL_REDIRECT_HOSTS, url
    assert pins["qce"]["archiveUrl"].split("/", 3)[2] == OFFICIAL_SOURCE_HOST

    for mirror in MIRROR_MARKERS:
        assert mirror not in payload, mirror
    # No fallback source of any kind: neither a build output nor a local runtime.
    for fragment in ("dist/", "dist\\", "../", "runtime/qq"):
        assert fragment not in payload, fragment


def test_pins_carry_no_credentials_or_machine_paths() -> None:
    payload = json.dumps(_pins()).lower()

    for fragment in ("token", "cookie", "password", "secret", "db_key", "wxid"):
        assert fragment not in payload, fragment
    for fragment in ("c:\\", "c:/", "/users/", "\\users\\"):
        assert fragment not in payload, fragment


def test_gitignore_tracks_the_pin_file() -> None:
    """``*.json`` is ignored repo-wide, so the pin file needs a negation."""
    lines = [
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert "!scripts/qq_runtime_pins.json" in lines, (
        "scripts/qq_runtime_pins.json is matched by the global '*.json' ignore "
        "rule and would never be tracked"
    )


# ------------------------------------------------------- bootstrap structure
def test_bootstrap_reads_the_tracked_pins_and_the_shared_contract() -> None:
    script = _script_text()

    assert "qq_runtime_pins.json" in script
    assert "windows_runtime_manifest.json" in script
    assert "$PSScriptRoot" in script, (
        "the pin file and the contract must be resolved next to the script itself"
    )


def test_bootstrap_restores_only_the_qq_runtime_target() -> None:
    script = _script_text()

    assert "$QqTargetRelativePath = 'runtime\\qq'" in script
    assert "'.." not in script, "runtime targets must stay inside the project root"


def test_bootstrap_keeps_no_second_copy_of_the_pinned_values() -> None:
    """Versions and hashes live in the pin file, never in the script."""
    script = _script_text()

    for value in (
        QCE_VERSION,
        QCE_ARCHIVE_SHA256,
        UPSTREAM_LAUNCHER_SHA256,
        PATCHED_LAUNCHER_SHA256,
        QQNT_SEED_SHA256,
        QCE_ARCHIVE_ROOT,
        "NapCat-QCE",
        LAUNCHER_ADDED_LINE,
    ):
        assert value not in script, value


def test_bootstrap_verifies_everything_before_it_touches_the_target() -> None:
    """A verification failure must leave the installed runtime untouched."""
    script = _script_text()

    assert script.index("function Assert-QceArchiveFile") < script.index(
        "function Install-QqRuntime"
    )
    assert script.index("function Assert-QceArchiveEntries") < script.index(
        "function Expand-QceArchive"
    )
    assert script.index("function Update-LauncherUserBatch") < script.index(
        "function Install-QqRuntime"
    )
    body = _bootstrap_body(script)
    ordered = (
        "Assert-QceArchiveFile -ArchivePath",
        "Assert-QceArchiveEntries -ArchivePath",
        "Expand-QceArchive -ArchivePath",
        "Remove-ExcludedRuntimeState -RuntimeRoot",
        "Update-LauncherUserBatch -RuntimeRoot",
        "Assert-PinnedRuntimeFiles -RuntimeRoot",
        "Assert-QqRuntimeContract -Root",
        "Install-QqRuntime -PreparedRoot",
    )
    positions = [body.index(call) for call in ordered]
    assert positions == sorted(positions), ordered


def test_bootstrap_swaps_the_runtime_instead_of_copying_over_it() -> None:
    """The prepared tree is staged next to the target and swapped into place."""
    script = _script_text()

    assert "$StagingRoot" in script
    assert "$BackupRoot" in script
    assert "Move-Item -LiteralPath $StagingRoot -Destination $TargetRoot" in script


def test_bootstrap_reuses_a_verified_local_archive_without_downloading() -> None:
    script = _script_text()

    assert "$QceArchivePath" in script


def test_bootstrap_supports_an_isolated_target_root() -> None:
    script = _script_text()

    assert "$ProjectRootOverride" in script


def test_bootstrap_never_runs_a_package_manager_or_shells_out() -> None:
    script = _script_text()

    for fragment in FORBIDDEN_SCRIPT_FRAGMENTS:
        assert fragment not in script, fragment
    assert "npm" not in script.lower(), (
        "the upstream asset already ships node_modules; npm must never run"
    )


def test_bootstrap_cleans_up_its_temporary_directory() -> None:
    script = _script_text()
    body = _bootstrap_body(script)

    assert "[System.IO.Path]::GetTempPath()" in body
    assert body.index("try {") < body.index("finally")
    cleanup = _brace_block(body, body.index("finally"))
    assert TEMP_CLEANUP_COMMAND in cleanup, (
        "the top-level finally does not release the temporary directory"
    )
    assert "SilentlyContinue" in cleanup, (
        "a cleanup failure must not mask the original bootstrap error"
    )
    assert script.index(TEMP_CLEANUP_COMMAND) < script.index(SUCCESS_BANNER), (
        "the temporary directory must be released before the script reports success"
    )


def test_bootstrap_fails_closed_with_a_nonzero_exit_code() -> None:
    script = _script_text()

    assert "exit 1" in script


# --------------------------------------------------------- offline behaviour
def test_bootstrap_restores_the_runtime_from_a_verified_archive(
    tmp_path: Path,
) -> None:
    script, archive, payload = _stage_workspace(tmp_path)
    _seed_stale_runtime(tmp_path)
    temp_entries = _bootstrap_temp_entries()

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "qq"

    # Exactly the upstream payload, minus everything the pins exclude.
    assert _relative_files(runtime) == _expected_installed_members(payload)
    # The upstream launcher is patched deterministically, exactly once.
    launcher = (runtime / LAUNCHER_PATH).read_bytes()
    assert launcher == payload[LAUNCHER_PATH].replace(
        LAUNCHER_ANCHOR.encode(), LAUNCHER_REPLACEMENT.encode(), 1
    )
    assert launcher.count(LAUNCHER_ADDED_LINE.encode()) == 1
    # The Direct DB helper is injected from the tracked template, byte for byte.
    snapshot = (runtime / SNAPSHOT_TARGET_PATH).read_bytes()
    assert snapshot == SNAPSHOT_TEMPLATE
    # The upstream QCE plugin entry is patched deterministically, exactly once.
    index = (runtime / INDEX_PATH).read_bytes()
    assert index == payload[INDEX_PATH].replace(
        INDEX_ANCHOR.encode(), INDEX_REPLACEMENT.encode(), 1
    )
    assert index.count(INDEX_ADDED_LINE.encode()) == 1
    napcat = payload[NAPCAT_PATH]
    for edit in NAPCAT_REPLACEMENTS:
        napcat = napcat.replace(edit["anchor"].encode(), edit["replacement"].encode(), 1)
    assert (runtime / NAPCAT_PATH).read_bytes() == napcat
    # Upstream attribution survives.
    for relative in ATTRIBUTION_MEMBERS:
        assert (runtime / relative).read_bytes() == payload[relative]
    # The QQNT patch-package seed is the upstream seed, not a machine copy.
    assert _sha256((runtime / "qqnt.json").read_bytes()) == _sha256(
        payload["qqnt.json"]
    )
    assert (runtime / "config" / "plugins.json").is_file()
    assert _bootstrap_temp_entries() == temp_entries
    assert _runtime_leftovers(tmp_path) == []


def test_bootstrap_replaces_a_previous_runtime_completely(tmp_path: Path) -> None:
    """Stale frontend builds and old payloads must never survive a bootstrap."""
    script, archive, payload = _stage_workspace(tmp_path)
    _seed_stale_runtime(tmp_path)

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "qq"
    for stale in (
        "static/qce/_next/static/chunks/stale-old-build.js",
        "static/qce/stale-build-id/index.html",
        "node_modules/stale-package/package.json",
        "plugins/stale-plugin/index.mjs",
    ):
        assert not (runtime / stale).exists(), stale
    assert _relative_files(runtime) == _expected_installed_members(payload)


def test_bootstrap_removes_machine_local_state_from_the_target(
    tmp_path: Path,
) -> None:
    script, archive, payload = _stage_workspace(tmp_path)
    _seed_stale_runtime(tmp_path)

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "qq"
    for private in PINS_EXCLUDED_PATHS + tuple(_manifest_qq_private_paths()):
        assert not (runtime / private).exists(), private
    assert "loadNapCat.js" not in payload or not (runtime / "loadNapCat.js").exists()


def test_bootstrap_rejects_an_archive_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    script, archive, _ = _stage_workspace(tmp_path, archive_sha256="0" * 64)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")
    temp_entries = _bootstrap_temp_entries()

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "SHA256" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before
    assert _bootstrap_temp_entries() == temp_entries


def test_bootstrap_rejects_an_archive_with_a_different_size(
    tmp_path: Path,
) -> None:
    script, archive, _ = _stage_workspace(tmp_path, archive_size_bytes=1)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "size" in _output(completed).lower()
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_a_launcher_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    script, archive, _ = _stage_workspace(
        tmp_path, upstream_launcher_sha256="1" * 64
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "launcher-user.bat" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_a_launcher_without_the_expected_anchor(
    tmp_path: Path,
) -> None:
    members = _fictional_archive_members()
    members[LAUNCHER_PATH] = _fictional_launcher(tail=b"exit /b\r\n")
    script, archive, _ = _stage_workspace(tmp_path, members=members)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "launcher" in _output(completed).lower()
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_an_ambiguous_launcher_anchor(tmp_path: Path) -> None:
    members = _fictional_archive_members()
    members[LAUNCHER_PATH] = _fictional_launcher() + LAUNCHER_ANCHOR.encode()
    script, archive, _ = _stage_workspace(tmp_path, members=members)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "launcher" in _output(completed).lower()
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_an_archive_missing_a_pinned_member(
    tmp_path: Path,
) -> None:
    members = _fictional_archive_members(drop=("qce-server.exe",))
    script, archive, _ = _stage_workspace(tmp_path, members=members)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "qce-server.exe" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_a_runtime_that_violates_the_contract(
    tmp_path: Path,
) -> None:
    drop = ("static/qce/index.html",)
    members = _fictional_archive_members(drop=drop)
    script, archive, _ = _stage_workspace(
        tmp_path,
        members=members,
        required_files=_required_file_pins(members),
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    output = _output(completed).replace("/", "\\")
    assert "static\\qce\\index.html" in output
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_an_archive_with_path_traversal(tmp_path: Path) -> None:
    script, archive, _ = _stage_workspace(
        tmp_path, traversal_members=("../escape.txt",)
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "escape.txt" in _output(completed) or "out" in _output(completed)
    assert not (tmp_path / "escape.txt").exists()
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_a_non_official_source_host(tmp_path: Path) -> None:
    script, archive, _ = _stage_workspace(
        tmp_path,
        archive_url=(
            "https://registry.npmmirror.com/-/binary/qce/"
            "NapCat-QCE-Windows-x64-v6.2.3.zip"
        ),
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "npmmirror.com" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_an_archive_outside_the_pinned_root(
    tmp_path: Path,
) -> None:
    script, archive, _ = _stage_workspace(
        tmp_path, pinned_archive_root="Other-Root"
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "Other-Root" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    script, archive, payload = _stage_workspace(tmp_path)
    _seed_stale_runtime(tmp_path)
    sources = _offline_archive(archive)

    first = _run_bootstrap(script, tmp_path, *sources)
    assert first.returncode == 0, _output(first)
    runtime = tmp_path / "runtime" / "qq"
    after_first = _tree_hashes(runtime)

    second = _run_bootstrap(script, tmp_path, *sources)
    assert second.returncode == 0, _output(second)

    assert _tree_hashes(runtime) == after_first
    assert _relative_files(runtime) == _expected_installed_members(payload)
    launcher = (runtime / LAUNCHER_PATH).read_bytes()
    assert launcher.count(LAUNCHER_ADDED_LINE.encode()) == 1
    # Re-running the bootstrap never stacks a second Direct DB patch or helper.
    index = (runtime / INDEX_PATH).read_bytes()
    assert index.count(INDEX_ADDED_LINE.encode()) == 1
    snapshot = (runtime / SNAPSHOT_TARGET_PATH).read_bytes()
    assert snapshot == SNAPSHOT_TEMPLATE
    assert _runtime_leftovers(tmp_path) == []


def test_bootstrap_injects_the_direct_db_helper_on_a_clean_bootstrap(
    tmp_path: Path,
) -> None:
    """A clean bootstrap restores both the helper and the patched entry."""
    script, archive, payload = _stage_workspace(tmp_path)

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "qq"
    snapshot = runtime / SNAPSHOT_TARGET_PATH
    assert snapshot.is_file()
    assert snapshot.read_bytes() == SNAPSHOT_TEMPLATE
    index = (runtime / INDEX_PATH).read_bytes()
    assert index == payload[INDEX_PATH].replace(
        INDEX_ANCHOR.encode(), INDEX_REPLACEMENT.encode(), 1
    )
    assert index.count(INDEX_ADDED_LINE.encode()) == 1


def test_bootstrap_replaces_a_stale_direct_db_helper(tmp_path: Path) -> None:
    """Wholesale replacement restores the helper even over a stale runtime."""
    script, archive, _ = _stage_workspace(tmp_path)
    _seed_stale_runtime(tmp_path)
    stale = tmp_path / "runtime" / "qq" / SNAPSHOT_TARGET_PATH
    assert stale.read_bytes() != SNAPSHOT_TEMPLATE

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "qq"
    assert (runtime / SNAPSHOT_TARGET_PATH).read_bytes() == SNAPSHOT_TEMPLATE


def test_bootstrap_rejects_an_index_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    script, archive, _ = _stage_workspace(
        tmp_path, upstream_index_sha256="1" * 64
    )
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "index.mjs" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_an_index_without_the_expected_anchor(
    tmp_path: Path,
) -> None:
    members = _fictional_archive_members()
    members[INDEX_PATH] = _fictional_index(
        tail=b"    console.error('no anchor');\r\n"
    )
    script, archive, _ = _stage_workspace(tmp_path, members=members)
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    assert "index.mjs" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_bootstrap_rejects_a_tampered_snapshot_template(tmp_path: Path) -> None:
    script, archive, _ = _stage_workspace(tmp_path)
    template = tmp_path / "scripts" / "qq_direct_db_snapshot" / "snapshot.mjs"
    template.write_bytes(b"// tampered template\n")
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "qq")

    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))

    assert completed.returncode != 0
    # PowerShell writes to the console in the OEM codepage, so only the ASCII
    # part of the failure label is reliably decodable by subprocess.run.
    assert "Direct DB helper" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "qq") == before


def test_runtime_contract_requires_the_direct_db_snapshot_helper() -> None:
    """The helper is a runtime contract requirement, not an optional extra."""
    assert SNAPSHOT_TARGET_PATH in _manifest_qq_file_paths()
    assert ECHO_INJECTED_PATHS <= set(_manifest_qq_file_paths())


@pytest.mark.parametrize('name', SNAPSHOT_DEPENDENCIES)
@pytest.mark.slow_integration
def test_bootstrap_rejects_tampered_snapshot_dependency(tmp_path: Path, name: str) -> None:
    script, archive, _ = _stage_workspace(tmp_path)
    (tmp_path / 'scripts/qq_direct_db_snapshot' / name).write_bytes(b'// tampered\n')
    _seed_stale_runtime(tmp_path)
    before = _tree_hashes(tmp_path / 'runtime/qq')
    completed = _run_bootstrap(script, tmp_path, *_offline_archive(archive))
    assert completed.returncode != 0
    assert 'Direct DB dependency' in _output(completed)
    assert _tree_hashes(tmp_path / 'runtime/qq') == before
