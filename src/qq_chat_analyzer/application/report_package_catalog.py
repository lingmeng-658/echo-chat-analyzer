"""List package-owned metadata and delete complete, bounded report assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
from pathlib import Path
import re
import shutil
import stat

from ..resources import user_data_dir
from .echo_report_export import ECHO_REPORT_HTML_NAME, _require_no_reparse_points
from .scope_filter import AnalysisScope, AnalysisScopeMode

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.report_package")
_PACKAGE_NAME = re.compile(r"Echo_Report_[0-9]{8}_[0-9]{6}(?:_(?:[2-9]|[1-9][0-9]+))?\Z")
MAX_REPORT_PACKAGES = 50


@dataclass(frozen=True, slots=True)
class ReportPackageSummary:
    package_name: str
    generated_at: datetime
    source: str
    conversation_name: str
    message_count: int
    analysis_scope: AnalysisScope
    conversation_kind: str = "unknown"


@dataclass(frozen=True, slots=True)
class ReportPackageIssue:
    package_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class ReportPackageListing:
    reports: tuple[ReportPackageSummary, ...] = ()
    issues: tuple[ReportPackageIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportPackageRetentionResult:
    total_before: int
    selected_for_removal: tuple[str, ...]
    deleted: tuple[str, ...]
    failures: tuple[ReportPackageIssue, ...]
    total_after: int

    @property
    def complete(self) -> bool:
        return not self.failures and self.total_after <= MAX_REPORT_PACKAGES


class ReportPackageClearError(RuntimeError):
    """At least one owned candidate could not be safely deleted."""


class ReportPackageCatalog:
    def __init__(self, reports_root: Path | None = None) -> None:
        self._reports_root = reports_root

    def _root(self) -> Path:
        root = Path(self._reports_root or (user_data_dir() / "reports")).absolute()
        _require_no_reparse_points(root)
        return root.resolve()

    @property
    def reports_root(self) -> Path:
        """Expose the validated canonical root for same-root publishing."""
        return self._root()

    def enforce_retention(
        self, *, published_package: Path | None = None,
    ) -> ReportPackageRetentionResult:
        """Keep at most 50 owned packages, protecting this analysis's publication."""
        root = self._root()
        protected = None
        if published_package is not None:
            published = Path(published_package).absolute()
            _require_no_reparse_points(published)
            if published.parent.resolve() != root:
                raise ValueError("Published report is outside the catalog root.")
            protected = root / published.name
            _check_package(root, protected)
        candidates = _candidates(root)
        excess = max(0, len(candidates) - MAX_REPORT_PACKAGES)
        if not excess:
            return ReportPackageRetentionResult(len(candidates), (), (), (), len(candidates))

        known, unknown = [], []
        for package in candidates:
            if package == protected:
                continue
            try:
                _check_package(root, package)
                known.append((package, _retention_generated_at(package)))
            except Exception:
                _LOGGER.warning("Retention time unknown package=%s", package, exc_info=True)
                unknown.append(package)
        # Keep the listing's newest-first, name-ascending order. Its reverse
        # is the eviction order; unknown-time packages are evicted first.
        known.sort(key=lambda item: item[0].name)
        known.sort(key=lambda item: item[1], reverse=True)
        unknown.sort(key=lambda package: package.name)
        selected = (unknown + [package for package, _ in reversed(known)])[:excess]
        deleted, failures = [], []
        _LOGGER.info("Report retention started root=%s total=%d selected=%d",
                     root, len(candidates), len(selected))
        for package in selected:
            try:
                _delete_package(root, package)
                deleted.append(package.name)
                _LOGGER.info("Report retention deleted path=%s", package)
            except Exception:
                failures.append(ReportPackageIssue(package.name, "retention_delete_failed"))
                _LOGGER.exception("Report retention could not delete path=%s", package)
        total_after = len(_candidates(root))
        _LOGGER.info("Report retention finished root=%s deleted=%d failures=%d remaining=%d",
                     root, len(deleted), len(failures), total_after)
        return ReportPackageRetentionResult(
            len(candidates), tuple(package.name for package in selected),
            tuple(deleted), tuple(failures), total_after,
        )

    def resolve_html_path(self, package_name: str) -> Path:
        """Locate an owned package's regular HTML file without reading it."""
        if not isinstance(package_name, str) or not _is_package_name(package_name):
            raise ValueError("Invalid report package name.")
        root = self._root()
        package = root / package_name
        identity = _check_package(root, package)
        html = package / ECHO_REPORT_HTML_NAME
        _require_no_reparse_points(html)
        if not stat.S_ISREG(html.lstat().st_mode):
            raise ValueError("Report HTML is not a regular file.")
        resolved = html.resolve(strict=True)
        if resolved.parent != package or _check_package(root, package) != identity:
            raise ValueError("Report package changed during resolution.")
        return resolved

    def list_reports(self) -> ReportPackageListing:
        root = self._root()
        reports, issues = [], []
        candidates = _candidates(root)
        _LOGGER.info("Report catalog scan root=%s candidates=%d", root, len(candidates))
        for package in candidates:
            try:
                _check_package(root, package)
                for name in ("echo-report.html", "echo-report.json", "metadata.json", "README.txt"):
                    artifact = package / name
                    _require_no_reparse_points(artifact)
                    if not stat.S_ISREG(artifact.lstat().st_mode):
                        raise ValueError("Incomplete report package.")
                metadata = package / "metadata.json"
                _require_no_reparse_points(metadata)
                reports.append(_read_summary(package.name, metadata))
            except Exception:
                _LOGGER.warning("Unreadable report package: %s", package, exc_info=True)
                issues.append(ReportPackageIssue(package.name, "metadata_unreadable"))
        # Newest generated time first; equal times use ascending package name.
        reports.sort(key=lambda report: report.package_name)
        reports.sort(key=lambda report: report.generated_at, reverse=True)
        _LOGGER.info("Report catalog scan finished root=%s reports=%d issues=%d",
                     root, len(reports), len(issues))
        return ReportPackageListing(tuple(reports), tuple(issues))

    def delete_package(self, package_name: str) -> None:
        """Delete one complete owned package, without following reparse points."""
        if not isinstance(package_name, str) or not _is_package_name(package_name):
            raise ValueError("Invalid report package name.")
        root = self._root()
        _delete_package(root, root / package_name)

    def clear_all(self) -> None:
        root = self._root()
        failed = False
        candidates = _candidates(root)
        deleted = 0
        _LOGGER.info("Report package clear started root=%s candidates=%d", root, len(candidates))
        for package in candidates:
            try:
                _LOGGER.info("Report package delete validating path=%s", package)
                _LOGGER.info("Report package delete attempting path=%s", package)
                _delete_package(root, package)
                deleted += 1
                _LOGGER.info("Report package delete finished path=%s", package)
            except Exception:
                failed = True
                _LOGGER.exception("Report package could not be deleted: %s", package)
        _LOGGER.info("Report package clear finished root=%s candidates=%d deleted=%d failed=%s",
                     root, len(candidates), deleted, failed)
        if failed:
            raise ReportPackageClearError("Some report packages could not be deleted.")


def _candidates(root: Path) -> list[Path]:
    """Enumerate directories without following links; unsafe entries stay visible."""
    if not root.exists():
        return []
    candidates = []
    for package in sorted(root.iterdir(), key=lambda child: child.name):
        if not _is_package_name(package.name):
            continue
        try:
            info = package.lstat()
        except OSError:
            # An inaccessible directory cannot safely be discounted.
            candidates.append(package)
            continue
        if stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            candidates.append(package)
    return candidates


def _retention_generated_at(package: Path) -> datetime:
    metadata = package / "metadata.json"
    _require_no_reparse_points(metadata)
    if not stat.S_ISREG(metadata.lstat().st_mode):
        raise ValueError("Report metadata is not a regular file.")
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if data["schema_version"] != "echo-report-meta.v1":
        raise ValueError("Unsupported report metadata.")
    generated_at = datetime.fromisoformat(data["generated_at"])
    if generated_at.utcoffset() is None:
        raise ValueError("Report time requires a timezone.")
    return generated_at


def _is_package_name(name: str) -> bool:
    if not _PACKAGE_NAME.fullmatch(name):
        return False
    try:
        datetime.strptime(name[len("Echo_Report_"):len("Echo_Report_") + 15], "%Y%m%d_%H%M%S")
    except ValueError:
        return False
    return True


def _check_package(root: Path, package: Path) -> tuple[int, int]:
    _require_no_reparse_points(package)
    if package.parent != root or not _is_package_name(package.name):
        raise ValueError("Report package is outside the catalog boundary.")
    info = package.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Report package is not a directory.")
    return info.st_dev, info.st_ino


def _check_tree(directory: Path) -> None:
    for child in directory.iterdir():
        _require_no_reparse_points(child)
        if stat.S_ISDIR(child.lstat().st_mode):
            _check_tree(child)


def _delete_package(root: Path, package: Path) -> None:
    identity = _check_package(root, package)
    _check_tree(package)
    if _check_package(root, package) != identity:
        raise RuntimeError("Report package changed during deletion.")
    shutil.rmtree(package)


def _read_summary(package_name: str, path: Path) -> ReportPackageSummary:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["schema_version"] != "echo-report-meta.v1":
        raise ValueError("Unsupported report metadata.")
    generated_at = datetime.fromisoformat(data["generated_at"])
    if generated_at.utcoffset() is None:
        raise ValueError("Report time requires a timezone.")
    if data["source"] not in {"qq", "wechat"}:
        raise ValueError("Unsupported report source.")
    if not isinstance(data["conversation_name"], str):
        raise ValueError("Invalid conversation name.")
    if type(data["message_count"]) is not int or data["message_count"] < 0:
        raise ValueError("Invalid report message count.")
    raw_scope = data["analysis_scope"]
    mode = AnalysisScopeMode(raw_scope["mode"])
    start = date.fromisoformat(raw_scope["start_date"]) if raw_scope["start_date"] is not None else None
    end = date.fromisoformat(raw_scope["end_date"]) if raw_scope["end_date"] is not None else None
    if mode is AnalysisScopeMode.ALL:
        if start is not None or end is not None:
            raise ValueError("All scope cannot have date filters.")
    elif start is None or end is None or start > end:
        raise ValueError("Invalid report scope.")
    kind = data.get("conversation_kind", "unknown")
    return ReportPackageSummary(package_name, generated_at, data["source"],
                                data["conversation_name"], data["message_count"],
                                AnalysisScope(mode, start, end),
                                kind if isinstance(kind, str) else "unknown")
