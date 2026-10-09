"""Safely wrap a fresh build; never build, execute or clean its source tree.

Requires Python 3.11+ (stdlib tomllib). From the repository root:
    .venv/Scripts/python.exe scripts/package_windows_portable.py

Defaults: dist/Echo -> dist/Echo-<project.version>-windows-x64.zip and
<zip-name>.sha256. Existing outputs are never overwritten. Native asset pins
and MSVC completeness remain the responsibility of build_windows_exe.ps1;
this wrapper checks presence, release state and archive/source consistency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import tomllib
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FILE = PROJECT_ROOT / "scripts/windows_runtime_manifest.json"
DIAGNOSTIC_SCRIPT = "scripts/run_wechat_wcdb_diagnostic.ps1"

# Conservative state classification, consistent with the build script's
# Test-MutableRuntimePath. These are patterns, not another runtime asset list.
STATE_FILE = re.compile(
    r"\.(?:db(?:-(?:wal|shm|journal))?|sqlite3?|jsonl|log)$|^\.env$|"
    r"^(?:token|key|cookie|password|passphrase|credentials|security|session|auth|account)"
    r"(?:[._-].*)?\.(?:json|txt|ini|env)$", re.IGNORECASE,
)
STATE_DIRECTORY = re.compile(
    r"^(?:output|logs|cache|temp|tmp|staging|generations|decrypted|scratch|"
    r"reports|\.codex|session|sessions|auth)$", re.IGNORECASE,
)


class PackageError(Exception):
    """The release cannot be packaged safely."""


def _no_links(path: Path) -> None:
    for ancestor in (path, *path.parents):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise PackageError("Symbolic link or reparse point is not allowed")


def _manifest_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise PackageError("Invalid manifest path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {".", "..", ""} for part in value.split("/")):
        raise PackageError("Invalid manifest path")
    return value


def _signature(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns


def _inventory(root: Path) -> dict[str, tuple[Path, tuple]]:
    _no_links(root)
    if not root.is_dir():
        raise PackageError("Echo source directory is missing")
    result = {}
    folded = set()
    pending = [root]
    while pending:
        for path in sorted(pending.pop().iterdir()):
            _no_links(path)
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if "\\" in relative or ":" in relative:
                raise PackageError("Unsafe archive path")
            if relative.casefold() in folded:
                raise PackageError("Case-insensitive archive path collision")
            folded.add(relative.casefold())
            if stat.S_ISDIR(info.st_mode):
                name = relative + "/"
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                name = relative
            else:
                raise PackageError("Only regular files and directories may ship")
            result[name] = path, _signature(info)
    return result


def _validate_release(entries: dict, contract: dict) -> None:
    paths = {name.rstrip("/").casefold() for name in entries}
    private = [_manifest_path(p) for p in contract["releaseTreePrivatePaths"]]
    private += ["runtime/" + _manifest_path(e["path"]) for e in contract["privatePaths"]]
    private += ["runtime/" + _manifest_path(p) for p in contract["forbiddenPaths"]]
    for blocked in private:
        if blocked.casefold() in paths:
            raise PackageError("Release contains forbidden or private state: " + blocked)

    def require(name: str, kind: str) -> None:
        if kind == "file":
            valid = name in entries
        elif kind == "non-empty-directory":
            valid = name + "/" in entries and any(
                key.startswith(name + "/") and key != name + "/" for key in entries
            )
        else:
            raise PackageError("Unsupported manifest requirement type")
        if not valid:
            raise PackageError("Missing or empty release component: " + name)

    require("Echo.exe", "file")
    require("_internal", "non-empty-directory")
    require("runtime", "non-empty-directory")
    require(DIAGNOSTIC_SCRIPT, "file")
    files = set()
    directories = set()
    sources = set()
    for entry in contract["requirements"]:
        relative = _manifest_path(entry["path"])
        source = _manifest_path(entry["source"])
        if not relative.startswith(source + "/"):
            raise PackageError("Manifest asset is outside its source")
        sources.add(source)
        require("runtime/" + relative, entry["type"])
        if entry["type"] == "file":
            files.add("runtime/" + relative)
    for entry in contract["packageDirectories"]:
        relative = _manifest_path(entry["path"])
        if entry["type"] != "directory" or not relative.startswith(entry["source"] + "/"):
            raise PackageError("Invalid manifest program directory")
        require("runtime/" + relative, "non-empty-directory")
        directories.add("runtime/" + relative)

    for name in entries:
        path = name.rstrip("/")
        parts = path.split("/")
        if not name.endswith("/") and STATE_FILE.search(parts[-1]):
            raise PackageError("Release contains a state file")
        directory_parts = parts if name.endswith("/") else parts[:-1]
        if any(STATE_DIRECTORY.fullmatch(part) for part in directory_parts):
            raise PackageError("Release contains a state directory")
        if parts[0] == "runtime" and "data" in {p.casefold() for p in directory_parts}:
            raise PackageError("Runtime contains a data directory")
        if parts[0] == "_internal":
            continue
        if path in {"Echo.exe", "runtime", "scripts", DIAGNOSTIC_SCRIPT}:
            continue
        if parts[0] != "runtime":
            raise PackageError("Unexpected release member: " + path)
        if path in files or any(path == d or path.startswith(d + "/") for d in directories):
            continue
        # The build adds app-local MSVC DLLs at each runtime source root.
        # Accept those DLLs without duplicating its names/version/hash contract.
        if len(parts) == 3 and parts[1] in sources and path.lower().endswith(".dll"):
            continue
        if name.endswith("/") and any(
            allowed.startswith(path + "/") for allowed in files | directories
        ):
            continue
        raise PackageError("Unexpected runtime member: " + path)


def _digest(stream) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    _no_links(path)
    with path.open("rb") as stream:
        return _digest(stream)


def _verify_archive(archive: Path, root: Path, entries: dict, hashes: dict, contract: dict) -> None:
    current = _inventory(root)
    _validate_release(current, contract)
    if current != entries:
        raise PackageError("Source tree changed during packaging")
    expected = {"Echo/"} | {"Echo/" + name for name in entries}
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(expected) or set(names) != expected:
            raise PackageError("Archive file list differs from source")
        for name, digest in hashes.items():
            if _file_digest(entries[name][0]) != digest:
                raise PackageError("Source content changed during packaging")
            with zipped.open("Echo/" + name) as stream:
                if _digest(stream) != digest:
                    raise PackageError("Archive content differs from source")


def package_portable(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    project_file: Path = PROJECT_ROOT / "pyproject.toml",
    manifest_file: Path = MANIFEST_FILE,
) -> tuple[Path, Path]:
    published = []
    try:
        root = Path(os.path.abspath(source_dir))
        output = Path(os.path.abspath(output_dir))
        _no_links(root)
        _no_links(output)
        if output == root or root in output.parents:
            raise PackageError("Output directory must be outside the source tree")
        version = tomllib.loads(Path(project_file).read_text(encoding="utf-8"))["project"]["version"]
        if not isinstance(version, str) or not re.fullmatch(
            r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version
        ):
            raise PackageError("Project version is not a safe release version")
        contract = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
        archive = output / f"Echo-{version}-windows-x64.zip"
        checksum = output / (archive.name + ".sha256")
        if os.path.lexists(archive) or os.path.lexists(checksum):
            raise PackageError("Release output already exists; refusing to overwrite")
        entries = _inventory(root)
        _validate_release(entries, contract)
        hashes = {name: _file_digest(path) for name, (path, _) in entries.items()
                  if not name.endswith("/")}
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".echo-package-", dir=output) as scratch:
            staged_archive = Path(scratch) / archive.name
            staged_checksum = Path(scratch) / checksum.name
            with zipfile.ZipFile(staged_archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
                zipped.writestr("Echo/", b"")
                for name, (path, _) in sorted(entries.items()):
                    zipped.write(path, "Echo/" + name)
            _verify_archive(staged_archive, root, entries, hashes, contract)
            digest = _file_digest(staged_archive)
            staged_checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
            # The ZIP is the final success marker: never expose it without its
            # checksum, even if the process is killed between these renames.
            for staged, target in ((staged_checksum, checksum), (staged_archive, archive)):
                _publish_file(staged, target)
                published.append(target)
        return archive, checksum
    except BaseException as error:
        for target in reversed(published):
            target.unlink()
        if isinstance(error, (KeyboardInterrupt, SystemExit, PackageError)):
            raise
        raise PackageError("Portable packaging failed: " + str(error)) from error


def _publish_file(source, target):
    # Windows rename fails if the destination exists; POSIX rename overwrites.
    if os.name == "nt":
        os.rename(source, target)
    else:
        os.link(source, target)
        source.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT / "dist/Echo")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args(argv)
    try:
        archive, checksum = package_portable(args.source, args.output)
    except PackageError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
