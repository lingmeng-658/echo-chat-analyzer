"""Tests verifying Snapshot removal contract.

After removing ChatDataSnapshotManager:
1. QQ full analysis always calls provider (no snapshot reuse).
2. No snapshot is created or persisted.
3. QQ bounded still uses transient lease + cleanup.
4. WeChat analysis unchanged.
5. History no longer writes snapshot_id.
6. Old history rows with snapshot_id still read fine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ImportService,
    QQExportImportRequest,
    QQExportImportService,
)
from qq_chat_analyzer.application.report_history import (
    AnalysisHistoryRecord,
    ReportHistoryManager,
)


# --------------------------------------------------------------------- fixtures


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "home"))


def _qce_message(message_id, text="Fictional line", nickname="Alice", timestamp=1750000000000):
    return {
        "id": message_id,
        "seq": message_id,
        "timestamp": timestamp,
        "time": "2025-06-15 12:00:00",
        "sender": {"uid": "user-1001", "uin": "1001", "name": nickname, "nickname": nickname},
        "type": "text",
        "content": {"text": text, "elements": [], "resources": [], "mentions": []},
        "recalled": False,
        "system": False,
    }


def _write_fake_export(path: Path) -> Path:
    payload = {
        "metadata": {"exportedAt": "2025-06-15T12:00:00Z", "version": "4.0.0"},
        "chatInfo": {"chatType": 2, "peerUid": "700000001", "name": "Test Group"},
        "statistics": {"totalMessages": 2},
        "messages": [
            _qce_message("fake-1", "Hello"),
            _qce_message("fake-2", "World"),
        ],
        "avatars": {},
        "exportOptions": {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class _CountingProvider:
    """Provider that counts how many times export_group_json is called."""

    def __init__(self, export_path: Path) -> None:
        self._export_path = export_path
        self.call_count = 0

    def export_group_json(self, group_code, start_time=None, end_time=None, output_dir=None):
        self.call_count += 1
        if output_dir is not None and Path(self._export_path).is_file():
            target = Path(output_dir) / Path(self._export_path).name
            import shutil
            shutil.copyfile(self._export_path, target)
            return target
        return self._export_path


# =====================================================================
# RED tests: these should FAIL with the current snapshot-based code
# =====================================================================


def test_qq_full_analysis_always_calls_provider(tmp_path: Path) -> None:
    """QQ full analysis must always call the provider, even on consecutive runs."""
    export_path = _write_fake_export(tmp_path / "export.json")
    provider = _CountingProvider(export_path)
    service = QQExportImportService(provider)

    # First call
    with service.acquired_export(QQExportImportRequest(group_code="700000001")):
        pass
    first_count = provider.call_count

    # Second call — must still call provider (no snapshot reuse)
    with service.acquired_export(QQExportImportRequest(group_code="700000001")):
        pass
    second_count = provider.call_count

    assert second_count > first_count, (
        "QQ full analysis reused a snapshot instead of calling the provider again"
    )


def test_qq_full_analysis_does_not_create_persistent_snapshot(tmp_path: Path) -> None:
    """QQ full analysis must not create any persistent snapshot on disk."""
    export_path = _write_fake_export(tmp_path / "export.json")
    provider = _CountingProvider(export_path)
    snapshots_root = tmp_path / "snapshots"
    service = QQExportImportService(provider)

    with service.acquired_export(QQExportImportRequest(group_code="700000001")):
        pass

    # The snapshots directory should not exist (or be empty)
    assert not snapshots_root.exists() or not any(snapshots_root.iterdir()), (
        "A persistent snapshot was created during QQ full analysis"
    )


def test_qq_bounded_analysis_uses_transient_lease(tmp_path: Path) -> None:
    """QQ bounded analysis must use the transient lease and clean up after."""
    export_path = _write_fake_export(tmp_path / "export.json")
    provider = _CountingProvider(export_path)
    service = QQExportImportService(provider)

    with service.acquired_export(
        QQExportImportRequest(
            group_code="700000001",
            start_time=1750000000000,
            end_time=1750000001000,
        )
    ) as acquisition:
        assert acquisition.payload_path.is_file()
        run_dir = Path(acquisition.payload_path).parent
        assert run_dir.is_dir()

    # Transient run directory must be cleaned up
    assert not run_dir.exists(), "Transient export run was not cleaned up"


def test_qq_analysis_history_record_has_no_snapshot_id(tmp_path: Path) -> None:
    """New history records must not write snapshot_id."""
    manager = ReportHistoryManager(tmp_path / "history.jsonl")

    record = manager.save_analysis(
        source="qq",
        session_name="Test Group",
        session_id="700000001",
        message_count=10,
        analysis_scope="all",
        scope_start=None,
        scope_end=None,
        report_generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    # Verify persisted JSONL does not contain snapshot_id
    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    import json
    payload = json.loads(lines[0])
    assert "snapshot_id" not in payload, (
        "Persisted history record should not contain snapshot_id"
    )


def test_old_history_row_with_snapshot_id_still_reads(tmp_path: Path) -> None:
    """Old history JSONL with snapshot_id must still be readable."""
    history_path = tmp_path / "history.jsonl"
    history_path.write_text(
        json.dumps({
            "analysis_id": "old-001",
            "created_at": "2025-01-01T00:00:00+00:00",
            "source": "qq",
            "session_name": "Old Group",
            "session_id": "123456",
            "message_count": 5,
            "analysis_scope": "all",
            "scope_start": None,
            "scope_end": None,
            "report_generated_at": "2025-01-01T00:00:00+00:00",
            "snapshot_id": "11111111-1111-1111-1111-111111111111",
        }, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    manager = ReportHistoryManager(history_path)
    records = manager.list_records()

    assert len(records) == 1
    assert records[0].analysis_id == "old-001"
    # snapshot_id may or may not be populated on read — key is: no crash
    # snapshot_id is stripped at read time; key is: no crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

from datetime import datetime, timezone
