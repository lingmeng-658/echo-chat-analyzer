"""QQ-specific workspace ownership for one transient QCE export.

QQChatExporter only accepts an ``outputDir`` below its own exports tree, and
the only part of that tree Echo may ever touch is a namespace it created
itself::

    <QCE exports root>\\
    |-- other QCE / user files      <- Echo never reads, scans or deletes
    `-- Echo\\
        `-- <run-id>\\              <- one analysis run; the only removable part

The exports root is resolved once, here, by :func:`default_qce_exports_root`.
No other module repeats that path and no configuration layer exists for it.
Deleting this module removes the whole QCE-owned temporary layout with it;
report, snapshot and history storage are unaffected.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from .errors import ApplicationServiceError


_ECHO_NAMESPACE = "Echo"
_QCE_EXPORTS_RELATIVE_PATH = Path("Documents") / "QQChatExporter" / "exports"

_VERBATIM_PREFIX = "\\\\?\\"
_VERBATIM_UNC_PREFIX = "\\\\?\\UNC\\"


def default_qce_exports_root() -> Path:
    """Return the only root QCE accepts as an export destination.

    Windows-first: QCE keeps its exports below the user profile's
    ``Documents`` folder, so the root is derived from the OS user profile and
    never from ``LOCALAPPDATA`` (which QCE rejects outright).
    """
    return Path.home() / _QCE_EXPORTS_RELATIVE_PATH


class QQTransientExportOwnershipError(ApplicationServiceError):
    """Raised when QCE reports a path outside Echo's current export run."""

    code = "qq_export_outside_owned_workspace"
    public_message = "QQ 导出文件不在 Echo 的临时目录中。"


class QQTransientExportCleanupError(ApplicationServiceError):
    """Raised when Echo cannot remove one of its own transient export runs."""

    code = "qq_export_cleanup_failed"
    public_message = "QQ 临时导出文件清理失败。"


def _strip_windows_verbatim_prefix(value: str) -> str:
    """Remove one well-formed Windows verbatim prefix, if there is one.

    QCE reports ``filePath`` in extended-length form: ``\\\\?\\C:\\...``, or
    ``\\\\?\\UNC\\server\\share\\...`` for a network share. On Windows
    ``Path.resolve()`` keeps that form verbatim, so an owned file can never
    look relative to a normally anchored directory.

    Exactly one leading prefix is removed, and only when the remainder is a
    usable absolute path. Every other value is returned untouched: this is a
    prefix inspection, not a replacement over arbitrary text. The result is
    still resolved and ownership-checked afterwards, so removing the prefix
    cannot widen what counts as owned.
    """
    if value.startswith(_VERBATIM_UNC_PREFIX):
        remainder = value[len(_VERBATIM_UNC_PREFIX):]
        if "\\" in remainder:
            return "\\\\" + remainder
        return value
    if value.startswith(_VERBATIM_PREFIX):
        remainder = value[len(_VERBATIM_PREFIX):]
        if _is_absolute_drive_path(remainder):
            return remainder
    return value


def _is_absolute_drive_path(value: str) -> bool:
    """Return whether ``value`` looks like a ``C:\\...`` absolute path."""
    return (
        len(value) >= 3
        and value[0].isalpha()
        and value[1] == ":"
        and value[2] == "\\"
    )


class QQTransientExportLease:
    """Own exactly one direct child of the Echo namespace below QCE exports."""

    def __init__(self, namespace_root: Path, output_directory: Path) -> None:
        self._namespace_root = namespace_root.resolve()
        self._output_directory = output_directory.resolve()

    @property
    def output_directory(self) -> Path:
        """Return the directory forwarded to QCE as ``outputDir``."""
        return self._output_directory

    def require_owned_export_file(self, returned_path: str | Path) -> Path:
        """Resolve one QCE result and accept only a real file in this run.

        Only QCE's produced payload may become the import source, so the run
        directory itself, a directory inside the run, and any path that
        resolves outside the run (including through a symlink or junction) are
        all rejected. A Windows verbatim prefix is removed first, so a real
        owned path reported that way is not mistaken for a foreign one.
        """
        try:
            candidate = Path(
                _strip_windows_verbatim_prefix(str(Path(returned_path)))
            ).resolve()
        except (OSError, TypeError, ValueError) as exc:
            raise QQTransientExportOwnershipError() from exc
        if not candidate.is_relative_to(self._output_directory):
            raise QQTransientExportOwnershipError()
        if candidate == self._output_directory:
            raise QQTransientExportOwnershipError()
        if not candidate.is_file():
            raise QQTransientExportOwnershipError()
        return candidate

    def cleanup(self) -> None:
        """Remove this run after proving it remains a direct owned child.

        Only ``<exports root>\\Echo\\<run-id>`` is ever removed. The Echo
        namespace, the exports root, sibling runs and every other QCE or user
        file are left exactly as they were.
        """
        target = self._output_directory.resolve()
        if target.parent != self._namespace_root:
            raise QQTransientExportCleanupError()
        try:
            if target.exists():
                shutil.rmtree(target)
        except OSError as exc:
            raise QQTransientExportCleanupError() from exc


class QQTransientExportWorkspace:
    """Allocate per-run QCE output directories below the Echo namespace."""

    def __init__(self, exports_root: str | Path | None = None) -> None:
        self._configured_exports_root = (
            Path(exports_root) if exports_root is not None else None
        )

    def begin_run(self) -> QQTransientExportLease:
        """Create one unique QCE output directory owned by Echo."""
        namespace_root = self._echo_namespace()
        namespace_root.mkdir(parents=True, exist_ok=True)
        while True:
            output_directory = namespace_root / uuid4().hex
            try:
                output_directory.mkdir()
            except FileExistsError:
                continue
            return QQTransientExportLease(namespace_root, output_directory)

    def _echo_namespace(self) -> Path:
        return self._exports_root() / _ECHO_NAMESPACE

    def _exports_root(self) -> Path:
        if self._configured_exports_root is not None:
            return self._configured_exports_root.resolve()
        return default_qce_exports_root().resolve()


__all__ = [
    "QQTransientExportCleanupError",
    "QQTransientExportLease",
    "QQTransientExportOwnershipError",
    "QQTransientExportWorkspace",
    "default_qce_exports_root",
]
