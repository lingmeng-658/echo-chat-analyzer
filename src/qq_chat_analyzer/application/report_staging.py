"""Recover only identity-bound, inactive report publication workspaces."""

from contextlib import contextmanager
import errno
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
from uuid import uuid4

from .echo_report_export import EchoReportExportError, _require_no_reparse_points

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.report_package")
_MARKER_SUFFIX = ".owner.json"
_MARKER_NAME = re.compile(r"\.echo-report-[0-9a-f]{32}\.owner\.json\Z")
_ARTIFACTS = {"echo-report.html", "echo-report.json", "metadata.json", "README.txt"}
_SCHEMA = "echo-report-staging.v1"


def _identity(info):
    return [info.st_dev, info.st_ino]


def _try_lock(stream):
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return False
        raise
    return True


def _read_proof(root, marker, stream):
    _require_no_reparse_points(marker)
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise EchoReportExportError("Invalid staging ownership file.")
    stream.seek(0)
    proof = json.loads(stream.read(4097))
    staging = root / marker.name.removesuffix(_MARKER_SUFFIX)
    if proof != {
        "schema": _SCHEMA, "staging": staging.name,
        "root_identity": _identity(root.lstat()),
        "directory_identity": proof.get("directory_identity"),
        "marker_identity": _identity(info),
    } or _identity(marker.lstat()) != _identity(info):
        raise EchoReportExportError("Staging ownership does not match this root.")
    identity = proof["directory_identity"]
    if not isinstance(identity, list) or len(identity) != 2 or any(type(value) is not int for value in identity):
        raise EchoReportExportError("Invalid staging directory identity.")
    return staging, proof


def _delete_staging(root, marker, stream):
    staging, proof = _read_proof(root, marker, stream)
    _require_no_reparse_points(staging)
    try:
        info = staging.lstat()
    except FileNotFoundError:
        return  # Already published/deleted; the ownership sidecar can be removed.
    if not stat.S_ISDIR(info.st_mode) or _identity(info) != proof["directory_identity"]:
        raise EchoReportExportError("Staging directory identity changed.")
    # Validate every member before deleting any of them. Unknown members stay intact.
    for child in staging.iterdir():
        _require_no_reparse_points(child)
        if child.name not in _ARTIFACTS or not stat.S_ISREG(child.lstat().st_mode):
            raise EchoReportExportError("Unexpected staging member.")
    _read_proof(root, marker, stream)
    if _identity(staging.lstat()) != proof["directory_identity"]:
        raise EchoReportExportError("Staging directory changed during cleanup.")
    shutil.rmtree(staging)


def _remove_marker(marker, identity):
    _require_no_reparse_points(marker)
    if _identity(marker.lstat()) != identity:
        raise EchoReportExportError("Staging ownership file changed.")
    marker.unlink()


def _remove_empty_staging(staging, identity):
    _require_no_reparse_points(staging)
    if _identity(staging.lstat()) != identity:
        raise EchoReportExportError("Staging directory identity changed.")
    staging.rmdir()


@contextmanager
def owned_report_staging(root: Path):
    """Hold an OS lease through publication/cleanup; keep proof if cleanup fails."""
    _require_no_reparse_points(root)
    root = root.resolve(strict=True)
    while True:
        staging = root / f".echo-report-{uuid4().hex}"
        marker = root / (staging.name + _MARKER_SUFFIX)
        try:
            # Preserve root ACL inheritance; Python 3.13 mkdtemp changes Windows ACLs.
            staging.mkdir()
        except FileExistsError:
            continue
        directory_identity = _identity(staging.lstat())
        try:
            stream = marker.open("x+b")
        except OSError as error:
            try:
                _remove_empty_staging(staging, directory_identity)
            except Exception as cleanup_error:
                _LOGGER.warning("Report staging cleanup failed error_type=%s", type(cleanup_error).__name__)
            if isinstance(error, FileExistsError):
                continue
            raise
        break
    identity = _identity(os.fstat(stream.fileno()))
    cleaned = False
    proof_ready = False
    try:
        with stream:
            if not _try_lock(stream):
                raise EchoReportExportError("Cannot lease report staging.")
            proof = {
                "schema": _SCHEMA, "staging": staging.name,
                "root_identity": _identity(root.lstat()),
                "directory_identity": directory_identity,
                "marker_identity": identity,
            }
            stream.write(json.dumps(proof, separators=(",", ":")).encode("utf-8"))
            stream.flush()
            proof_ready = True
            try:
                yield staging
            finally:
                try:
                    _delete_staging(root, marker, stream)
                    cleaned = True
                except Exception as error:
                    _LOGGER.warning("Report staging cleanup failed error_type=%s", type(error).__name__)
    finally:
        if not proof_ready:
            try:
                _remove_empty_staging(staging, directory_identity)
                cleaned = True
            except Exception as error:
                _LOGGER.warning("Report staging cleanup failed error_type=%s", type(error).__name__)
        if cleaned:
            try:
                _remove_marker(marker, identity)
            except Exception as error:
                _LOGGER.warning("Report staging ownership cleanup failed error_type=%s", type(error).__name__)


def recover_report_staging(root: Path) -> bool:
    """Retry proven orphan cleanup without touching active or unknown entries."""
    _require_no_reparse_points(root)
    if not root.exists():
        return True
    root = root.resolve(strict=True)
    complete = True
    for marker in root.iterdir():
        if not _MARKER_NAME.fullmatch(marker.name):
            continue
        try:
            _require_no_reparse_points(marker)
            if not stat.S_ISREG(marker.lstat().st_mode):
                raise EchoReportExportError("Invalid staging ownership entry.")
            with marker.open("r+b") as stream:
                if not _try_lock(stream):
                    continue  # A live publisher/recovery owns this workspace.
                identity = _identity(os.fstat(stream.fileno()))
                _delete_staging(root, marker, stream)
            _remove_marker(marker, identity)
        except Exception as error:
            complete = False
            _LOGGER.warning("Report staging recovery failed error_type=%s", type(error).__name__)
    return complete
