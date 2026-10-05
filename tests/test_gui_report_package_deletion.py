"""Exercise the desktop deletion chain with fictional, disk-backed packages."""

import os
from pathlib import Path
import shutil
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from qq_chat_analyzer.application.echo_report_export import package_echo_report
from qq_chat_analyzer.gui.app import build_facade
from qq_chat_analyzer.gui.local_data_page import LocalDataPage
from qq_chat_analyzer.gui import workers


def _drain(app, pending):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        app.processEvents()
        if not pending:
            return
        time.sleep(0.01)
    pytest.fail("Local data background work did not finish")


@pytest.mark.slow_integration
@pytest.mark.parametrize("fail_one", [False, True])
def test_desktop_delete_all_changes_disk_and_refreshes_remaining_packages(
    tmp_path, monkeypatch, fail_one,
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    root = tmp_path / "local-app-data" / "LocalChatAnalyzer" / "reports"
    source = tmp_path / "fictional-output"
    source.mkdir()
    for name in ("echo-report.html", "echo-report.json"):
        (source / name).write_text("fictional", encoding="utf-8")
    metadata = {
        "schema_version": "echo-report-meta.v1",
        "generated_at": "2026-10-04T12:00:00+00:00",
        "source": "qq", "conversation_name": "Fictional Conversation",
        "message_count": 1,
        "analysis_scope": {"mode": "all", "start_date": None, "end_date": None},
    }
    # Use the default publisher root and default desktop composition, rather
    # than injecting a catalog or stubbing the facade's deletion operation.
    packages = [package_echo_report(source, metadata=metadata) for _ in range(21)]
    for package in packages[1:]:
        (package / "metadata.json").write_text("broken", encoding="utf-8")
    unknown = root / "manual-report"
    unknown.mkdir()
    sentinel = unknown / "keep.txt"
    sentinel.write_text("fictional", encoding="utf-8")

    original_read = Path.read_text
    def metadata_only(path, *args, **kwargs):
        assert path.name == "metadata.json", "Report bodies must not be read"
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", metadata_only)
    attempted = []
    original_delete = shutil.rmtree
    def delete(path, *args, **kwargs):
        attempted.append(Path(path))
        if fail_one and Path(path) == packages[0]:
            raise PermissionError("Fictional locked package")
        return original_delete(path, *args, **kwargs)
    monkeypatch.setattr(shutil, "rmtree", delete)

    app = QApplication.instance() or QApplication([])
    facade = build_facade()
    assert facade._report_package_catalog._root() == root.resolve()
    pending = set()
    def submit(operation, *, on_success, on_error):
        # Track this page's real workers, independently of relay objects left
        # by other tests that intentionally destroy their Qt signal sources.
        worker = workers.submit(
            operation, on_success=on_success, on_error=on_error,
            on_finished=lambda: pending.discard(worker),
        )
        pending.add(worker)
        return worker
    opened = []
    page = LocalDataPage(
        facade, executor=submit, confirm_clear_reports=lambda: True,
        report_opener=lambda path: opened.append(path) or True,
    )
    try:
        page.refresh()
        _drain(app, pending)
        assert page._history_table.rowCount() == 1
        assert len(facade.list_report_packages().issues) == 20
        page._history_table.selectRow(0)
        page._open_report_button.click()
        _drain(app, pending)
        assert opened == [packages[0] / "echo-report.html"]
        assert page._status_label.text() == ""
        page._clear_reports_button.click()
        _drain(app, pending)
        assert set(attempted) == set(packages)
        assert sentinel.exists()
        assert all(not package.exists() for package in packages[1:])
        assert packages[0].exists() is fail_one
        assert page._history_table.rowCount() == int(fail_one)
        assert page._issues_label.isHidden()
        assert bool(page._status_label.text()) is fail_one
        assert set(root.iterdir()) == ({unknown, packages[0]} if fail_one else {unknown})
    finally:
        page.deleteLater()
        app.processEvents()


@pytest.mark.slow_integration
@pytest.mark.parametrize("fail_delete", [False, True])
def test_desktop_selected_delete_preserves_search_other_reports_and_reopen(tmp_path, monkeypatch, fail_delete):
    source = tmp_path / "fictional-output"
    source.mkdir()
    for name in ("echo-report.html", "echo-report.json"):
        (source / name).write_text("fictional", encoding="utf-8")
    metadata = {
        "schema_version": "echo-report-meta.v1",
        "generated_at": "2026-10-04T12:00:00+00:00",
        "source": "qq", "conversation_name": "Fictional Alpha",
        "message_count": 1,
        "analysis_scope": {"mode": "all", "start_date": None, "end_date": None},
    }
    other = package_echo_report(source, metadata=metadata)
    metadata["conversation_name"] = "Fictional Beta"
    selected = package_echo_report(source, metadata=metadata)
    root = selected.parent
    sibling = root / "manual.txt"
    sibling.write_bytes(b"fictional sibling")
    named_file = root / "Echo_Report_20261004_120000_999"
    named_file.write_bytes(b"fictional named file")
    original_read = Path.read_text
    def metadata_only(path, *args, **kwargs):
        assert path.name == "metadata.json", "Report bodies must not be read"
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", metadata_only)
    original_delete = shutil.rmtree
    attempted = []
    def delete(path, *args, **kwargs):
        attempted.append(Path(path))
        if fail_delete and Path(path) == selected:
            raise PermissionError("Fictional locked package")
        return original_delete(path, *args, **kwargs)
    monkeypatch.setattr(shutil, "rmtree", delete)
    app = QApplication.instance() or QApplication([])
    facade = build_facade()
    pending = set()
    def submit(operation, *, on_success, on_error):
        worker = workers.submit(
            operation, on_success=on_success, on_error=on_error,
            on_finished=lambda: pending.discard(worker),
        )
        pending.add(worker)
        return worker
    opened = []
    page = LocalDataPage(
        facade, executor=submit, confirm_delete_report=lambda: True,
        report_opener=lambda path: opened.append(path) or True,
    )
    try:
        page.refresh()
        _drain(app, pending)
        assert page._history_table.rowCount() == 2
        assert page._issues_label.isHidden()
        page._search_input.setText("beta")
        page._history_table.selectRow(0)
        page._delete_report_button.click()
        _drain(app, pending)
        assert attempted == [selected]
        assert selected.exists() is fail_delete
        assert other.is_dir()
        assert sibling.read_bytes() == b"fictional sibling"
        assert named_file.read_bytes() == b"fictional named file"
        assert page._search_input.text() == "beta"
        assert page._history_table.rowCount() == int(fail_delete)
        assert bool(page._status_label.text()) is fail_delete
        if fail_delete:
            assert page._status_label.text() == "这份 Echo 报告未能删除，请稍后重试。"
        page._search_input.setText("alpha")
        page._history_table.selectRow(0)
        page._open_report_button.click()
        _drain(app, pending)
        assert opened == [other / "echo-report.html"]
        assert page._status_label.text() == ""
    finally:
        page.deleteLater()
        app.processEvents()
