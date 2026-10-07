import json
from pathlib import Path

import pytest


def _catalog(root):
    from qq_chat_analyzer.application.report_package_catalog import ReportPackageCatalog
    return ReportPackageCatalog(root)


def _package(root, name="Echo_Report_20261004_120000", generated_at="2026-10-04T12:00:00+00:00"):
    package = root / name
    package.mkdir(parents=True)
    metadata = {
        "schema_version": "echo-report-meta.v1", "generated_at": generated_at,
        "source": "qq", "conversation_name": "Fictional Conversation",
        "conversation_kind": "group", "message_count": 120, "active_days": 8,
        "participant_count": 5, "message_start_timestamp": None,
        "message_end_timestamp": None,
        "analysis_scope": {"mode": "all", "start_date": None, "end_date": None},
    }
    (package / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (package / "echo-report.json").write_text("not readable report JSON", encoding="utf-8")
    (package / "echo-report.html").write_text("fictional", encoding="utf-8")
    (package / "README.txt").write_text("fictional", encoding="utf-8")
    return package


def test_lists_only_metadata_in_stable_generated_time_order(tmp_path, monkeypatch):
    _package(tmp_path)
    _package(tmp_path, "Echo_Report_20261004_120000_2")
    _package(tmp_path, "Echo_Report_20261003_120000", "2026-10-03T12:00:00+00:00")
    (tmp_path / "unknown").mkdir()
    for name in ("Echo_Report_99999999_999999", "Echo_Report_20261004_120000_1"):
        (tmp_path / name).mkdir()
    original = Path.read_text
    def guarded(path, *args, **kwargs):
        assert path.name == "metadata.json"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded)
    listing = _catalog(tmp_path).list_reports()
    assert [r.package_name for r in listing.reports] == [
        "Echo_Report_20261004_120000", "Echo_Report_20261004_120000_2",
        "Echo_Report_20261003_120000"]
    assert listing.reports[0].message_count == 120
    assert listing.reports[0].conversation_name == "Fictional Conversation"
    assert not listing.issues


def test_fixed_01_metadata_survives_list_reopen_and_retention_without_rewrite(tmp_path):
    # Literal historical fixture: never generate this via the current writer.
    old = _package(tmp_path)
    (old / "metadata.json").write_text('''{
      "schema_version": "echo-report-meta.v1",
      "generated_at": "2026-10-04T12:00:00+00:00",
      "source": "qq", "conversation_name": "Fictional 0.1 Conversation",
      "conversation_kind": "group", "message_count": 120,
      "active_days": 8, "participant_count": 5,
      "message_start_timestamp": null, "message_end_timestamp": null,
      "analysis_scope": {"mode": "all", "start_date": null, "end_date": null}
    }''', encoding="utf-8")
    before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in old.iterdir()}
    # 51 packages exercise eviction, with the old readable fixture in the middle.
    for index in range(50):
        package = _package(
            tmp_path, f"Echo_Report_20261004_120000_{index + 2}",
            "2026-10-03T12:00:00+00:00" if index == 0 else "2026-10-05T12:00:00+00:00",
        )
        path = package / "metadata.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(app_version="0.2.0", report_schema_version="echo-report.v0.7",
                    analysis_revision="echo-analysis.v2", future_optional_field=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    catalog = _catalog(tmp_path)
    listing = catalog.list_reports()
    assert len(listing.reports) == 51 and not listing.issues
    summary = next(report for report in listing.reports if report.package_name == old.name)
    assert summary.conversation_name == "Fictional 0.1 Conversation"
    assert summary.conversation_kind == "group"
    assert catalog.resolve_html_path(old.name) == old / "echo-report.html"
    retention = catalog.enforce_retention()
    assert retention.complete and retention.total_after == 50
    assert retention.deleted == ("Echo_Report_20261004_120000_2",)
    assert old.name in {report.package_name for report in catalog.list_reports().reports}
    assert catalog.resolve_html_path(old.name) == old / "echo-report.html"
    assert {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in old.iterdir()} == before


@pytest.mark.parametrize("content", [None, "broken", '{}'])
def test_damaged_metadata_remains_visible_and_can_be_deleted(tmp_path, content):
    package = _package(tmp_path)
    metadata = package / "metadata.json"
    if content is None:
        metadata.unlink()
    else:
        metadata.write_text(content, encoding="utf-8")
    catalog = _catalog(tmp_path)
    listing = catalog.list_reports()
    assert not listing.reports
    assert len(listing.issues) == 1
    assert listing.issues[0].package_name == package.name
    catalog.clear_all()
    assert not package.exists()


@pytest.mark.parametrize("kind", ["group", "private", "unknown", None])
def test_catalog_projects_conversation_kind_from_existing_metadata(tmp_path, kind):
    package = _package(tmp_path)
    metadata = package / "metadata.json"
    data = json.loads(metadata.read_text(encoding="utf-8"))
    if kind is None:
        del data["conversation_kind"]
    else:
        data["conversation_kind"] = kind
    metadata.write_text(json.dumps(data), encoding="utf-8")
    listing = _catalog(tmp_path).list_reports()
    assert listing.reports[0].conversation_kind == (kind or "unknown")
    assert not listing.issues


def test_clear_deletes_whole_packages_and_preserves_unknown_siblings(tmp_path):
    package = _package(tmp_path)
    (package / "echo-share.png").write_bytes(b"fictional")
    (package / "future-artifact.txt").write_text("fictional", encoding="utf-8")
    unknown = tmp_path / "Echo_Report_not_owned"
    unknown.mkdir()
    invalid_name = tmp_path / "Echo_Report_99999999_999999"
    invalid_name.mkdir()
    external = tmp_path / "manual.json"
    external.write_text("fictional", encoding="utf-8")
    _catalog(tmp_path).clear_all()
    assert not package.exists()
    assert unknown.is_dir()
    assert invalid_name.is_dir()
    assert external.exists()


def test_named_regular_file_is_ignored_by_all_package_operations(tmp_path):
    package = _package(tmp_path)
    named_file = tmp_path / "Echo_Report_20261004_120000_2"
    named_file.write_bytes(b"fictional sentinel")
    before = named_file.stat()
    catalog = _catalog(tmp_path)
    listing = catalog.list_reports()
    assert [report.package_name for report in listing.reports] == [package.name]
    assert not listing.issues
    retention = catalog.enforce_retention()
    assert retention.total_before == retention.total_after == 1
    catalog.clear_all()
    assert not package.exists()
    assert named_file.read_bytes() == b"fictional sentinel"
    assert named_file.stat().st_mtime_ns == before.st_mtime_ns


def test_delete_package_removes_only_selected_package_and_preserves_siblings(tmp_path):
    selected = _package(tmp_path)
    other = _package(tmp_path, "Echo_Report_20261004_120000_2")
    (selected / "extra.txt").write_text("fictional", encoding="utf-8")
    unknown = tmp_path / "manual.txt"
    unknown.write_bytes(b"fictional sibling")
    catalog = _catalog(tmp_path)
    catalog.delete_package(selected.name)
    assert not selected.exists()
    assert catalog.resolve_html_path(other.name) == other / "echo-report.html"
    assert unknown.read_bytes() == b"fictional sibling"


@pytest.mark.parametrize("name", ["../Echo_Report_20261004_120000", "manual", "Echo_Report_99999999_999999", "Echo_Report_20261004_120000_1", "", None])
def test_delete_package_rejects_invalid_identity(tmp_path, name):
    package = _package(tmp_path)
    with pytest.raises(ValueError):
        _catalog(tmp_path).delete_package(name)
    assert package.is_dir()


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_delete_package_rejects_non_package(tmp_path, kind):
    path = tmp_path / "Echo_Report_20261004_120000"
    if kind == "file":
        path.write_bytes(b"fictional sentinel")
    with pytest.raises((ValueError, FileNotFoundError)):
        _catalog(tmp_path).delete_package(path.name)
    if kind == "file":
        assert path.read_bytes() == b"fictional sentinel"


@pytest.mark.parametrize("location", ["root", "package", "inside"])
def test_delete_package_rejects_windows_junction_without_following(tmp_path, location):
    from qq_chat_analyzer.application.echo_report_export import EchoReportExportError
    import subprocess
    import sys
    if sys.platform != "win32":
        pytest.skip("Windows junction regression")
    root = tmp_path / "reports"
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_bytes(b"fictional external")
    name = "Echo_Report_20261004_120000"
    if location == "root":
        link = root
    else:
        package = _package(root, name)
        if location == "package":
            __import__("shutil").rmtree(package)
            link = package
        else:
            link = package / "linked"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)], check=True, capture_output=True)
    try:
        with pytest.raises(EchoReportExportError):
            _catalog(root).delete_package(name)
        assert sentinel.read_bytes() == b"fictional external"
        assert link.exists()
    finally:
        link.rmdir()


def test_clear_continues_after_failure_and_reports_failure(tmp_path, monkeypatch):
    import shutil
    first = _package(tmp_path)
    second = _package(tmp_path, "Echo_Report_20261004_120000_2")
    original = shutil.rmtree
    def fail_first(path, *args, **kwargs):
        if Path(path) == first:
            raise PermissionError("fictional failure")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(shutil, "rmtree", fail_first)
    with pytest.raises(RuntimeError):
        _catalog(tmp_path).clear_all()
    assert first.exists()
    assert not second.exists()


def test_reparse_candidate_is_an_issue_and_clear_fails_without_following(tmp_path, monkeypatch):
    import stat
    package = _package(tmp_path)
    original = Path.lstat
    class ReparseStat:
        st_file_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT
        st_mode = stat.S_IFDIR
    def reparse(path, *args, **kwargs):
        return ReparseStat() if path == package else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", reparse)
    catalog = _catalog(tmp_path)
    assert len(catalog.list_reports().issues) == 1
    with pytest.raises(RuntimeError):
        catalog.clear_all()
    assert (package / "metadata.json").exists()


def test_missing_root_is_empty_and_not_created(tmp_path):
    root = tmp_path / "reports"
    assert not _catalog(root).list_reports().reports
    _catalog(root).clear_all()
    assert not root.exists()


@pytest.mark.parametrize("location", ["root", "package", "inside"])
def test_windows_junction_never_deletes_external_target(tmp_path, location):
    import sys
    import subprocess
    if sys.platform != "win32":
        pytest.skip("Windows junction regression")
    root = tmp_path / "reports"
    root.mkdir()
    target = tmp_path / "external"
    target.mkdir()
    original = target / "original.json"
    original.write_text("fictional original", encoding="utf-8")
    if location == "root":
        root.rmdir()
        junction = root
    elif location == "package":
        junction = root / "Echo_Report_20261004_120000"
    else:
        junction = _package(root) / "external"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)],
                   check=True, capture_output=True)
    try:
        catalog = _catalog(root)
        if location == "package":
            assert len(catalog.list_reports().issues) == 1
        with pytest.raises(RuntimeError):
            catalog.clear_all()
        assert original.read_text(encoding="utf-8") == "fictional original"
    finally:
        junction.rmdir()


def test_incomplete_package_is_an_issue_but_still_owned(tmp_path):
    package = _package(tmp_path)
    (package / "echo-report.html").unlink()
    catalog = _catalog(tmp_path)
    assert len(catalog.list_reports().issues) == 1
    catalog.clear_all()
    assert not package.exists()


@pytest.mark.parametrize("suffix", ["", "_2", "_10"])
def test_resolve_html_path_uses_package_identity_without_reading_reports(tmp_path, monkeypatch, suffix):
    package = _package(tmp_path, "Echo_Report_20261004_120000" + suffix)
    (package / "metadata.json").write_text("broken", encoding="utf-8")
    def forbidden_read(*args, **kwargs):
        pytest.fail("Resolving a report must not read its contents or metadata")
    monkeypatch.setattr(Path, "read_text", forbidden_read)
    assert _catalog(tmp_path).resolve_html_path(package.name) == package / "echo-report.html"


def test_resolve_html_path_uses_canonical_root(tmp_path):
    package = _package(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    assert _catalog(nested / "..").resolve_html_path(package.name) == package / "echo-report.html"


def _retention_packages(root, count, same_time=False):
    return [_package(
        root, "Echo_Report_20261004_120000" + (f"_{index + 1}" if index else ""),
        "2020-01-01T00:00:00+00:00" if same_time else f"2020-01-01T00:00:{index:02d}+00:00",
    ) for index in range(count)]


@pytest.mark.parametrize("count", [0, 1, 49, 50])
def test_retention_at_or_below_50_never_deletes(tmp_path, monkeypatch, count):
    _retention_packages(tmp_path, count)
    def forbidden(*args, **kwargs):
        pytest.fail("Retention must not delete at or below 50")
    monkeypatch.setattr("shutil.rmtree", forbidden)
    result = _catalog(tmp_path).enforce_retention()
    assert result.total_before == result.total_after == count
    assert result.selected_for_removal == result.deleted == result.failures == ()
    assert result.complete


def test_retention_removes_oldest_metadata_time_without_reading_report_bodies(tmp_path, monkeypatch):
    import os
    packages = _retention_packages(tmp_path, 51)
    for index, package in enumerate(packages):
        os.utime(package, (2000000000 - index, 2000000000 - index))
    original = Path.read_text
    def metadata_only(path, *args, **kwargs):
        assert path.name == "metadata.json"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", metadata_only)
    result = _catalog(tmp_path).enforce_retention()
    assert result.total_before == 51 and result.total_after == 50
    assert result.selected_for_removal == result.deleted == (packages[0].name,)
    assert result.complete
    assert not packages[0].exists()
    assert all(package.exists() for package in packages[1:])


def test_retention_equal_times_use_catalog_name_order_stably(tmp_path):
    removed = []
    for folder in ("a", "b"):
        root = tmp_path / folder
        packages = _retention_packages(root, 51, same_time=True)
        result = _catalog(root).enforce_retention()
        expected = sorted(package.name for package in packages)[-1]
        assert result.deleted == (expected,)
        removed.append(result.deleted)
        assert _catalog(root).enforce_retention().selected_for_removal == ()
    assert removed[0] == removed[1]


@pytest.mark.parametrize("damage", ["missing", "broken", "missing_time", "naive_time", "metadata_directory"])
def test_retention_unknown_time_counts_and_is_removed_first(tmp_path, damage):
    packages = _retention_packages(tmp_path, 51)
    metadata = packages[-1] / "metadata.json"
    if damage in {"missing", "metadata_directory"}:
        metadata.unlink()
        if damage == "metadata_directory":
            metadata.mkdir()
    elif damage == "broken":
        metadata.write_text("broken", encoding="utf-8")
    else:
        data = json.loads(metadata.read_text(encoding="utf-8"))
        if damage == "missing_time":
            del data["generated_at"]
        else:
            data["generated_at"] = "2020-01-01T00:00:00"
        metadata.write_text(json.dumps(data), encoding="utf-8")
    result = _catalog(tmp_path).enforce_retention()
    assert result.total_before == 51 and result.total_after == 50
    assert result.deleted == (packages[-1].name,)
    assert packages[0].exists()


def test_retention_missing_html_does_not_discard_trustworthy_time(tmp_path):
    packages = _retention_packages(tmp_path, 51)
    (packages[-1] / "echo-report.html").unlink()
    result = _catalog(tmp_path).enforce_retention()
    assert result.deleted == (packages[0].name,)
    assert packages[-1].exists()


def test_retention_unknown_siblings_staging_and_named_files_are_untouched(tmp_path):
    _retention_packages(tmp_path, 50)
    siblings = [tmp_path / name for name in ("manual", ".echo-report-staging", "Echo_Report_not_owned")]
    for directory in siblings:
        directory.mkdir()
        (directory / "keep.txt").write_text("fictional", encoding="utf-8")
    named_file = tmp_path / "Echo_Report_20261005_120000"
    named_file.write_text("fictional", encoding="utf-8")
    result = _catalog(tmp_path).enforce_retention()
    assert result.total_before == result.total_after == 50
    assert not result.selected_for_removal
    assert all((directory / "keep.txt").exists() for directory in siblings)
    assert named_file.is_file()


def test_retention_failure_does_not_expand_original_removal_set(tmp_path, monkeypatch):
    packages = _retention_packages(tmp_path, 53)
    for package in packages[:2]:
        (package / "metadata.json").write_text("broken", encoding="utf-8")
    original = __import__("shutil").rmtree
    attempted = []
    def fail_one(path, *args, **kwargs):
        attempted.append(Path(path))
        if Path(path) == packages[0]:
            raise PermissionError("fictional locked package")
        return original(path, *args, **kwargs)
    monkeypatch.setattr("shutil.rmtree", fail_one)
    result = _catalog(tmp_path).enforce_retention()
    assert set(result.selected_for_removal) == {p.name for p in packages[:3]}
    assert set(attempted) == set(packages[:3])
    assert len(result.deleted) == 2
    assert [failure.package_name for failure in result.failures] == [packages[0].name]
    assert result.total_after == 51 and not result.complete
    assert packages[0].exists()
    assert all(package.exists() for package in packages[3:])


@pytest.mark.parametrize("location", ["package", "inside"])
def test_retention_windows_reparse_failure_preserves_external_and_continues(tmp_path, location):
    import sys
    import subprocess
    if sys.platform != "win32":
        pytest.skip("Windows junction regression")
    root = tmp_path / "reports"
    packages = _retention_packages(root, 52)
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("fictional", encoding="utf-8")
    if location == "package":
        __import__("shutil").rmtree(packages[0])
        link = packages[0]
    else:
        link = packages[0] / "linked"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                   check=True, capture_output=True)
    try:
        result = _catalog(root).enforce_retention()
        assert sentinel.exists()
        assert packages[0].exists()
        assert not packages[1].exists()
        assert all(package.exists() for package in packages[2:])
        assert result.total_after == 51 and not result.complete
        assert [failure.package_name for failure in result.failures] == [packages[0].name]
    finally:
        link.rmdir()


def test_retention_protects_published_package_even_if_clock_is_behind(tmp_path):
    packages = _retention_packages(tmp_path, 51)
    result = _catalog(tmp_path).enforce_retention(published_package=packages[0])
    assert packages[0].exists()
    assert result.deleted == (packages[1].name,)
    assert result.total_after == 50


def test_retention_rejects_published_package_from_different_root(tmp_path):
    root = tmp_path / "reports"
    packages = _retention_packages(root, 51)
    outside = _package(tmp_path / "outside")
    with pytest.raises(ValueError):
        _catalog(root).enforce_retention(published_package=outside)
    assert all(package.exists() for package in packages)


@pytest.mark.parametrize("name", [
    "", "Echo_Report_not_owned", "Echo_Report_99999999_999999",
    "Echo_Report_20261004_120000_1", "Echo_Report_20261004_120000_02",
    "../Echo_Report_20261004_120000", "..\\Echo_Report_20261004_120000",
    "Echo_Report_20261004_120000/../outside", "Echo_Report_20261004_120000\\outside",
    "Echo_Report_20261004_120000\n", None,
])
def test_resolve_html_path_rejects_invalid_identity(tmp_path, name):
    with pytest.raises((ValueError, OSError, RuntimeError)):
        _catalog(tmp_path).resolve_html_path(name)


def test_resolve_html_path_rejects_absolute_identity(tmp_path):
    package = _package(tmp_path / "outside")
    with pytest.raises((ValueError, OSError, RuntimeError)):
        _catalog(tmp_path / "reports").resolve_html_path(str(package))


@pytest.mark.parametrize("damage", ["missing_package", "package_file", "missing_html", "html_directory"])
def test_resolve_html_path_rejects_missing_or_non_file_html(tmp_path, damage):
    name = "Echo_Report_20261004_120000"
    if damage == "package_file":
        (tmp_path / name).write_text("fictional", encoding="utf-8")
    elif damage != "missing_package":
        package = _package(tmp_path, name)
        html = package / "echo-report.html"
        html.unlink()
        if damage == "html_directory":
            html.mkdir()
    with pytest.raises((ValueError, OSError, RuntimeError)):
        _catalog(tmp_path).resolve_html_path(name)


@pytest.mark.parametrize("location", ["root", "package", "html"])
def test_resolve_html_path_rejects_reparse_points(tmp_path, monkeypatch, location):
    import stat
    package = _package(tmp_path)
    target = {"root": tmp_path, "package": package, "html": package / "echo-report.html"}[location]
    original = Path.lstat
    class ReparseStat:
        st_file_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT
        st_mode = stat.S_IFDIR if location != "html" else stat.S_IFREG
    def reparse(path, *args, **kwargs):
        return ReparseStat() if path == target else original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(RuntimeError):
        _catalog(tmp_path).resolve_html_path(package.name)


@pytest.mark.parametrize("location", ["root", "package", "html"])
def test_resolve_html_path_windows_junction_never_follows_external(tmp_path, location):
    import sys
    import subprocess
    if sys.platform != "win32":
        pytest.skip("Windows junction regression")
    root = tmp_path / "reports"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "echo-report.html").write_text("fictional", encoding="utf-8")
    name = "Echo_Report_20261004_120000"
    if location == "root":
        root.rmdir()
        link = root
    elif location == "package":
        link = root / name
    else:
        package = _package(root, name)
        link = package / "echo-report.html"
        link.unlink()
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)],
                   check=True, capture_output=True)
    try:
        with pytest.raises(RuntimeError):
            _catalog(root).resolve_html_path(name)
        assert (external / "echo-report.html").exists()
    finally:
        link.rmdir()
