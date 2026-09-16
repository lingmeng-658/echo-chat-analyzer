"""Stage 2B contract tests for the WeChat Node.js + Koffi bootstrap.

The bootstrap has to restore, for a clean clone, exactly
``runtime/wechat/node.exe`` plus the three whitelisted Koffi package members,
from official sources whose identity is pinned in
``scripts/wechat_runtime_pins.json``.

Everything here is fictional, offline and isolated: the bootstrap is always run
from a temporary copy of the script, against a temporary project root, with
temporary archives and a temporary pin file. No real WeChat asset, database key
or account data is involved, and the repository ``runtime`` directory is never
touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "scripts" / "bootstrap_wechat_runtime.ps1"
PINS_PATH = PROJECT_ROOT / "scripts" / "wechat_runtime_pins.json"
GITIGNORE = PROJECT_ROOT / ".gitignore"

# ------------------------------------------------------------- pinned facts
NODE_VERSION = "24.16.0"
NODE_ARCHIVE_URL = (
    "https://nodejs.org/download/release/v24.16.0/node-v24.16.0-win-x64.zip"
)
NODE_ARCHIVE_SHA256 = (
    "edaca9bd58ec8e92037dac4e877d52f6b8f430b81c18b57e264b4e2fb111cd56"
)
NODE_ARCHIVE_ROOT = "node-v24.16.0-win-x64"
NODE_EXECUTABLE_SHA256 = (
    "b3094d0b49f9ad602262a9921551737bb97637c05dd357a06ae98188d7290aa3"
)

KOFFI_VERSION = "2.16.2"
KOFFI_TARBALL_URL = "https://registry.npmjs.org/koffi/-/koffi-2.16.2.tgz"
KOFFI_INTEGRITY = (
    "sha512-owU0MRwv6xkrVqCd+33uw6BaYppkTRXbO/rVdJNI2dvZG0gzyRhYwW25eWtc5pauw"
    "K8TGh3AbkFONSezdykfSA=="
)
KOFFI_SHASUM = "9b1420c131f5daa0e561b00687c2222f2e452367"

OFFICIAL_SOURCE_HOSTS = {"nodejs.org", "registry.npmjs.org"}

# The only WeChat runtime files this stage may produce, relative to
# ``runtime/wechat``.
BOOTSTRAP_TARGET_FILES = (
    "node.exe",
    "node_modules/koffi/index.js",
    "node_modules/koffi/build/koffi/win32_x64/koffi.node",
    "node_modules/koffi/LICENSE.txt",
)

# Upstream tarball member -> installed path, relative to ``node_modules/koffi``.
# koffi ships its license as ``LICENSE.txt``; the upstream name is preserved.
KOFFI_WHITELIST = (
    ("package/index.js", "index.js"),
    ("package/build/koffi/win32_x64/koffi.node", "build/koffi/win32_x64/koffi.node"),
    ("package/LICENSE.txt", "LICENSE.txt"),
)

# WeChat runtime assets owned by other pipelines. This bootstrap must never
# download, overwrite or delete them.
UNTOUCHED_WECHAT_ASSETS = (
    "wx_key.dll",
    "wx_key_helper.cjs",
    "WCDB.dll",
    "wcdb_cli.exe",
)

FORBIDDEN_SCRIPT_FRAGMENTS = (
    "wx_key",
    "WCDB",
    "wcdb_cli",
    "npm install",
    "npm ci",
    "npx",
    "Start-Process",
    "Invoke-Expression",
)

FICTIONAL_NODE_EXECUTABLE = b"fictional node.exe for the Stage 2B test suite\r\n"

# The restore itself lives in a top-level try/catch/finally at the bottom of the
# script, *after* the helper functions. The helpers carry try/finally pairs of
# their own, so anything asserted about the runtime body has to be located from
# this anchor rather than from the head of the file.
BOOTSTRAP_BODY_ANCHOR = "$PinsPath = Join-Path $PSScriptRoot 'wechat_runtime_pins.json'"
SUCCESS_BANNER = "bootstrap_wechat_runtime.ps1 完成"
TEMP_CLEANUP_COMMAND = "Remove-Item -LiteralPath $TempRoot -Recurse -Force"


# ------------------------------------------------------------------ helpers
def _script_text() -> str:
    assert BOOTSTRAP_SCRIPT.is_file(), (
        "WeChat Node/Koffi bootstrap is missing: "
        "scripts/bootstrap_wechat_runtime.ps1"
    )
    return BOOTSTRAP_SCRIPT.read_text(encoding="utf-8-sig")


def _bootstrap_body(script: str) -> str:
    """Return the top-level restore body, with the helper functions cut off.

    Assertions about the runtime flow (temporary directory, exit status) must be
    scoped to this slice: the helpers above it legitimately contain their own
    try/finally pairs, so a file-wide search can match the wrong block.
    """
    assert BOOTSTRAP_BODY_ANCHOR in script, (
        "the bootstrap body no longer starts at the pin-file wiring"
    )
    start = script.index(BOOTSTRAP_BODY_ANCHOR)
    return script[start : script.index(SUCCESS_BANNER, start)]


def _brace_block(text: str, start: int) -> str:
    """Return the brace-matched ``{...}`` block opening at or after ``start``."""
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
        "WeChat runtime pin file is missing: scripts/wechat_runtime_pins.json"
    )
    return json.loads(PINS_PATH.read_text(encoding="utf-8"))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha1(payload: bytes) -> str:
    return hashlib.sha1(payload).hexdigest()


def _sha512_integrity(payload: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()


def _fictional_node_archive(destination: Path) -> Path:
    """Miniature stand-in for the official Node.js win-x64 zip."""
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr(
            f"{NODE_ARCHIVE_ROOT}/node.exe", FICTIONAL_NODE_EXECUTABLE
        )
        # Members the product never needs: the bootstrap must not install them.
        archive.writestr(f"{NODE_ARCHIVE_ROOT}/npm.cmd", "@echo off\r\n")
        archive.writestr(f"{NODE_ARCHIVE_ROOT}/npx.cmd", "@echo off\r\n")
        archive.writestr(f"{NODE_ARCHIVE_ROOT}/nodevars.bat", "@echo off\r\n")
        archive.writestr(f"{NODE_ARCHIVE_ROOT}/LICENSE", "fictional license\n")
        archive.writestr(
            f"{NODE_ARCHIVE_ROOT}/node_modules/corepack/package.json", "{}\n"
        )
    return destination


def _add_tar_member(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, BytesIO(payload))


def _fictional_koffi_tarball(
    destination: Path,
    *,
    members: tuple[tuple[str, str], ...] = KOFFI_WHITELIST,
) -> Path:
    """Miniature stand-in for the official npm tarball of koffi."""
    with tarfile.open(destination, "w:gz") as archive:
        for source, _ in members:
            _add_tar_member(
                archive, source, f"fictional koffi payload: {source}\n".encode()
            )
        # Foreign platform addons and package internals: none may be installed.
        _add_tar_member(
            archive,
            "package/build/koffi/linux_x64/koffi.node",
            b"foreign linux addon",
        )
        _add_tar_member(
            archive,
            "package/build/koffi/darwin_arm64/koffi.node",
            b"foreign darwin addon",
        )
        _add_tar_member(archive, "package/src/koffi/src/ffi.cc", b"// source\n")
        _add_tar_member(archive, "package/README.md", b"# koffi\n")
        _add_tar_member(archive, "package/package.json", b'{"name": "koffi"}\n')
    return destination


def _write_pins(scripts: Path, payload: dict) -> None:
    (scripts / "wechat_runtime_pins.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _pin_payload(
    *,
    node_archive_sha256: str,
    node_executable_sha256: str = _sha256(FICTIONAL_NODE_EXECUTABLE),
    node_archive_url: str = NODE_ARCHIVE_URL,
    node_archive_root: str = NODE_ARCHIVE_ROOT,
    koffi_integrity: str,
    koffi_sha1: str,
    koffi_tarball_url: str = KOFFI_TARBALL_URL,
) -> dict:
    return {
        "node": {
            "version": NODE_VERSION,
            "archiveUrl": node_archive_url,
            "archiveSha256": node_archive_sha256,
            "archiveRoot": node_archive_root,
            "executableSha256": node_executable_sha256,
        },
        "koffi": {
            "version": KOFFI_VERSION,
            "tarballUrl": koffi_tarball_url,
            "tarballIntegrity": koffi_integrity,
            "tarballSha1": koffi_sha1,
        },
    }


def _stage_workspace(
    tmp_path: Path,
    *,
    node_archive: Path,
    koffi_tarball: Path,
    node_archive_sha256: str | None = None,
    node_executable_sha256: str | None = None,
    node_archive_url: str = NODE_ARCHIVE_URL,
    koffi_integrity: str | None = None,
    koffi_sha1: str | None = None,
    koffi_tarball_url: str = KOFFI_TARBALL_URL,
) -> Path:
    """Stage an isolated copy of the bootstrap plus its own pin file."""
    assert BOOTSTRAP_SCRIPT.is_file(), (
        "WeChat Node/Koffi bootstrap is missing: "
        "scripts/bootstrap_wechat_runtime.ps1"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BOOTSTRAP_SCRIPT, scripts / BOOTSTRAP_SCRIPT.name)
    _write_pins(
        scripts,
        _pin_payload(
            node_archive_sha256=node_archive_sha256
            or _sha256(node_archive.read_bytes()),
            node_executable_sha256=node_executable_sha256
            or _sha256(FICTIONAL_NODE_EXECUTABLE),
            node_archive_url=node_archive_url,
            koffi_integrity=koffi_integrity
            or _sha512_integrity(koffi_tarball.read_bytes()),
            koffi_sha1=koffi_sha1 or _sha1(koffi_tarball.read_bytes()),
            koffi_tarball_url=koffi_tarball_url,
        ),
    )
    return scripts / BOOTSTRAP_SCRIPT.name


def _seed_runtime(project_root: Path) -> None:
    """Pre-existing WeChat assets the bootstrap must leave untouched."""
    runtime = project_root / "runtime" / "wechat"
    runtime.mkdir(parents=True, exist_ok=True)
    for asset in UNTOUCHED_WECHAT_ASSETS:
        (runtime / asset).write_bytes(f"fictional {asset} bytes".encode())
    # A stale Koffi installation with foreign platform addons and leftovers.
    stale = runtime / "node_modules" / "koffi"
    (stale / "build" / "koffi" / "linux_x64").mkdir(parents=True, exist_ok=True)
    (stale / "build" / "koffi" / "linux_x64" / "koffi.node").write_bytes(b"stale")
    (stale / "build" / "koffi" / "win32_x64").mkdir(parents=True, exist_ok=True)
    (stale / "build" / "koffi" / "win32_x64" / "koffi.node").write_bytes(b"stale")
    (stale / "index.js").write_bytes(b"stale entry\n")
    (stale / "stale-leftover.txt").write_bytes(b"stale leftover\n")


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


def _offline_sources(node_archive: Path, koffi_tarball: Path) -> list[str]:
    return [
        "-NodeArchivePath",
        str(node_archive),
        "-KoffiTarballPath",
        str(koffi_tarball),
    ]


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
    return {
        relative: _sha256((root / relative).read_bytes())
        for relative in _relative_files(root)
    }


def _bootstrap_temp_entries() -> set[str]:
    return {
        entry.name
        for entry in Path(tempfile.gettempdir()).glob("echo-wechat-runtime-*")
    }


# --------------------------------------------------------- pinned source facts
def test_pins_lock_the_official_node_release() -> None:
    node = _pins()["node"]

    assert node["version"] == NODE_VERSION
    assert node["archiveUrl"] == NODE_ARCHIVE_URL
    assert node["archiveSha256"].lower() == NODE_ARCHIVE_SHA256
    assert node["archiveRoot"] == NODE_ARCHIVE_ROOT
    assert node["executableSha256"].lower() == NODE_EXECUTABLE_SHA256


def test_pins_lock_the_official_koffi_release() -> None:
    koffi = _pins()["koffi"]

    assert koffi["version"] == KOFFI_VERSION
    assert koffi["tarballUrl"] == KOFFI_TARBALL_URL
    assert koffi["tarballIntegrity"] == KOFFI_INTEGRITY
    assert koffi["tarballSha1"].lower() == KOFFI_SHASUM


def test_pins_declare_only_the_agreed_fields() -> None:
    pins = _pins()

    assert set(pins) == {"node", "koffi"}
    assert set(pins["node"]) == {
        "version",
        "archiveUrl",
        "archiveSha256",
        "archiveRoot",
        "executableSha256",
    }
    assert set(pins["koffi"]) == {
        "version",
        "tarballUrl",
        "tarballIntegrity",
        "tarballSha1",
    }


def test_pins_only_reference_official_sources() -> None:
    pins = _pins()
    urls = (pins["node"]["archiveUrl"], pins["koffi"]["tarballUrl"])

    for url in urls:
        assert url.startswith("https://")
        host = url.split("/", 3)[2]
        assert host in OFFICIAL_SOURCE_HOSTS, url

    payload = json.dumps(pins).lower()
    for mirror in ("npmmirror", "taobao", "cnpm", "yarnpkg", "jsdelivr", "unpkg"):
        assert mirror not in payload, mirror


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

    assert "!scripts/wechat_runtime_pins.json" in lines, (
        "scripts/wechat_runtime_pins.json is matched by the global '*.json' "
        "ignore rule and would never be tracked"
    )


# ------------------------------------------------------- bootstrap structure
def test_bootstrap_reads_the_tracked_pin_file() -> None:
    script = _script_text()

    assert "wechat_runtime_pins.json" in script
    assert "$PSScriptRoot" in script, (
        "the pin file must be resolved next to the script itself"
    )


def test_bootstrap_restores_only_the_agreed_targets() -> None:
    script = _script_text()

    assert "$NodeTargetRelativePath = 'runtime\\wechat\\node.exe'" in script
    assert (
        "$KoffiTargetRelativePath = 'runtime\\wechat\\node_modules\\koffi'"
        in script
    )
    assert "'.." not in script, "runtime targets must stay inside the project root"


def test_bootstrap_whitelists_the_koffi_runtime_members() -> None:
    script = _script_text()

    assert script.count("Source = 'package/") == len(KOFFI_WHITELIST)
    for source, target in KOFFI_WHITELIST:
        assert source in script, source
        assert target in script, target


def test_bootstrap_never_touches_other_wechat_runtime_assets() -> None:
    script = _script_text()

    for fragment in FORBIDDEN_SCRIPT_FRAGMENTS:
        assert fragment not in script, fragment


def test_bootstrap_verifies_every_source_before_it_installs_anything() -> None:
    """A verification failure must leave the target runtime untouched."""
    script = _script_text()

    assert script.index("function Assert-NodeArchive") < script.index(
        "function Install-NodeRuntime"
    )
    assert script.index("function Assert-KoffiTarball") < script.index(
        "function Install-KoffiRuntime"
    )
    assert script.index("Assert-NodeArchive -ArchivePath") < script.index(
        "Install-NodeRuntime -VerifiedExecutable"
    )
    assert script.index("Assert-KoffiTarball -TarballPath") < script.index(
        "Install-KoffiRuntime -VerifiedSources"
    )
    assert script.index("Install-NodeRuntime -VerifiedExecutable") < script.index(
        "Install-KoffiRuntime -VerifiedSources"
    )


def test_bootstrap_reuses_a_verified_local_archive_without_downloading() -> None:
    script = _script_text()

    assert "$NodeArchivePath" in script
    assert "$KoffiTarballPath" in script


def test_bootstrap_supports_an_isolated_target_root() -> None:
    script = _script_text()

    assert "$ProjectRootOverride" in script


def test_bootstrap_cleans_up_its_temporary_directory() -> None:
    script = _script_text()
    body = _bootstrap_body(script)

    assert "[System.IO.Path]::GetTempPath()" in body
    assert body.index("try {") < body.index("finally")
    # The cleanup has to sit inside the top-level `finally`, so that it runs on
    # the success path *and* on every failure path. A cleanup that drifted into
    # the catch branch, or past the `finally`, would never run for the other
    # outcome and must fail this test.
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


# ------------------------------------------------------------ offline behaviour
def test_bootstrap_restores_node_and_koffi_from_verified_sources(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path, node_archive=node_archive, koffi_tarball=koffi_tarball
    )
    _seed_runtime(tmp_path)
    untouched = {
        asset: (tmp_path / "runtime" / "wechat" / asset).read_bytes()
        for asset in UNTOUCHED_WECHAT_ASSETS
    }
    temp_entries = _bootstrap_temp_entries()

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode == 0, _output(completed)
    runtime = tmp_path / "runtime" / "wechat"

    # Exactly the agreed files, nothing else from either archive.
    assert _relative_files(runtime) == sorted(
        [*UNTOUCHED_WECHAT_ASSETS, *BOOTSTRAP_TARGET_FILES]
    )
    assert (runtime / "node.exe").read_bytes() == FICTIONAL_NODE_EXECUTABLE
    for asset, payload in untouched.items():
        assert (runtime / asset).read_bytes() == payload, asset
    # The zip's npm/npx/license/node_modules payload never reaches the runtime.
    for ignored in ("npm.cmd", "npx.cmd", "nodevars.bat", "LICENSE"):
        assert not (runtime / ignored).exists(), ignored
    # Foreign platform addons and stale leftovers are gone.
    assert not (runtime / "node_modules/koffi/stale-leftover.txt").exists()
    assert not (
        runtime / "node_modules/koffi/build/koffi/linux_x64"
    ).exists()
    assert _bootstrap_temp_entries() == temp_entries


def test_bootstrap_rejects_a_node_archive_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path,
        node_archive=node_archive,
        koffi_tarball=koffi_tarball,
        node_archive_sha256="0" * 64,
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")
    temp_entries = _bootstrap_temp_entries()

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "Node.js zip SHA256" in _output(completed)
    after = _tree_hashes(tmp_path / "runtime" / "wechat")
    assert after == before
    assert _bootstrap_temp_entries() == temp_entries


def test_bootstrap_rejects_a_node_executable_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path,
        node_archive=node_archive,
        koffi_tarball=koffi_tarball,
        node_executable_sha256="1" * 64,
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "node.exe SHA256" in _output(completed)
    # Nothing was installed: the stale Koffi tree is still the pre-run one.
    assert _tree_hashes(tmp_path / "runtime" / "wechat") == before
    assert not (tmp_path / "runtime" / "wechat" / "node.exe").exists()


def test_bootstrap_rejects_a_koffi_tarball_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path,
        node_archive=node_archive,
        koffi_tarball=koffi_tarball,
        koffi_integrity="sha512-" + base64.b64encode(b"x" * 64).decode(),
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "dist.integrity" in _output(completed)
    # The verified Node archive must not have been installed either: both
    # sources are verified before anything is written.
    assert _tree_hashes(tmp_path / "runtime" / "wechat") == before
    assert not (tmp_path / "runtime" / "wechat" / "node.exe").exists()


def test_bootstrap_rejects_a_koffi_shasum_that_does_not_match_the_pin(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path,
        node_archive=node_archive,
        koffi_tarball=koffi_tarball,
        koffi_sha1="2" * 40,
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "dist.shasum" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "wechat") == before


def test_bootstrap_rejects_a_koffi_tarball_missing_a_whitelisted_member(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    incomplete = tuple(
        (source, target)
        for source, target in KOFFI_WHITELIST
        if not source.endswith("win32_x64/koffi.node")
    )
    koffi_tarball = _fictional_koffi_tarball(
        tmp_path / "koffi-2.16.2.tgz", members=incomplete
    )
    script = _stage_workspace(
        tmp_path, node_archive=node_archive, koffi_tarball=koffi_tarball
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "build/koffi/win32_x64/koffi.node" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "wechat") == before


def test_bootstrap_rejects_a_pin_file_that_is_missing_a_section(
    tmp_path: Path,
) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path, node_archive=node_archive, koffi_tarball=koffi_tarball
    )
    pins = _pin_payload(
        node_archive_sha256=_sha256(node_archive.read_bytes()),
        koffi_integrity=_sha512_integrity(koffi_tarball.read_bytes()),
        koffi_sha1=_sha1(koffi_tarball.read_bytes()),
    )
    pins["koffi"] = {"version": KOFFI_VERSION}
    _write_pins(tmp_path / "scripts", pins)

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "koffi" in _output(completed).lower()
    assert not (tmp_path / "runtime" / "wechat" / "node.exe").exists()
    assert not (tmp_path / "runtime" / "wechat" / "node_modules").exists()


def test_bootstrap_rejects_a_non_official_source_host(tmp_path: Path) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path,
        node_archive=node_archive,
        koffi_tarball=koffi_tarball,
        node_archive_url=(
            "https://registry.npmmirror.com/-/binary/node/v24.16.0/"
            "node-v24.16.0-win-x64.zip"
        ),
    )
    _seed_runtime(tmp_path)
    before = _tree_hashes(tmp_path / "runtime" / "wechat")

    completed = _run_bootstrap(
        script, tmp_path, *_offline_sources(node_archive, koffi_tarball)
    )

    assert completed.returncode != 0
    assert "npmmirror.com" in _output(completed)
    assert _tree_hashes(tmp_path / "runtime" / "wechat") == before


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    node_archive = _fictional_node_archive(tmp_path / "node-win-x64.zip")
    koffi_tarball = _fictional_koffi_tarball(tmp_path / "koffi-2.16.2.tgz")
    script = _stage_workspace(
        tmp_path, node_archive=node_archive, koffi_tarball=koffi_tarball
    )
    _seed_runtime(tmp_path)
    sources = _offline_sources(node_archive, koffi_tarball)

    first = _run_bootstrap(script, tmp_path, *sources)
    assert first.returncode == 0, _output(first)
    runtime = tmp_path / "runtime" / "wechat"
    after_first = _tree_hashes(runtime)

    second = _run_bootstrap(script, tmp_path, *sources)
    assert second.returncode == 0, _output(second)

    assert _tree_hashes(runtime) == after_first
    assert _relative_files(runtime) == sorted(
        [*UNTOUCHED_WECHAT_ASSETS, *BOOTSTRAP_TARGET_FILES]
    )


def test_bootstrap_does_not_depend_on_a_system_node_installation() -> None:
    """Only the pinned archive may provide Node; never the build machine."""
    script = _script_text()

    for fragment in ("Get-Command node", "Get-Command npm", "where.exe"):
        assert fragment not in script, fragment


@pytest.mark.parametrize("asset", UNTOUCHED_WECHAT_ASSETS)
def test_unaffected_wechat_asset_is_documented_as_out_of_scope(asset: str) -> None:
    assert asset not in _script_text()
