import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    QQExportImportRequest,
    QQExportImportService,
)
from qq_chat_analyzer.application.qq_transient_export import QQTransientExportWorkspace


@pytest.fixture(autouse=True)
def _isolate_user_data(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local-app-data'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda _cls: tmp_path / 'home'))


def _write_fake_export(path):
    payload = {
        'metadata': {'exportedAt': '2025-06-15T12:00:00Z', 'version': '4.0.0'},
        'chatInfo': {'chatType': 2, 'peerUid': '700000001', 'name': 'Test Group'},
        'statistics': {'totalMessages': 2},
        'messages': [
            {'id': 'fake-1', 'seq': '1', 'timestamp': 1750000000000, 'time': '2025-06-15 12:00:00',
             'sender': {'uid': 'user-1001', 'uin': '1001', 'name': 'Alice', 'nickname': 'Alice'},
             'type': 'text', 'content': {'text': 'Hello', 'elements': [], 'resources': [], 'mentions': []},
             'recalled': False, 'system': False},
            {'id': 'fake-2', 'seq': '2', 'timestamp': 1750000001000, 'time': '2025-06-15 12:00:01',
             'sender': {'uid': 'user-1002', 'uin': '1002', 'name': 'Bob', 'nickname': 'Bob'},
             'type': 'text', 'content': {'text': 'World', 'elements': [], 'resources': [], 'mentions': []},
             'recalled': False, 'system': False},
        ],
        'avatars': {}, 'exportOptions': {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return path


class _RecordingProvider:
    def __init__(self, export_path):
        self._export_path = export_path
        self.output_dirs = []

    def export_group_json(self, group_code, start_time=None, end_time=None, output_dir=None):
        self.output_dirs.append(output_dir)
        if output_dir is not None and Path(self._export_path).is_file():
            target = Path(output_dir) / Path(self._export_path).name
            import shutil
            shutil.copyfile(self._export_path, target)
            return target
        return self._export_path


def test_full_session_uses_transient_workspace(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)

    with service.acquired_export(QQExportImportRequest(group_code='700000001')):
        pass

    assert len(provider.output_dirs) == 1
    output_dir = provider.output_dirs[0]
    assert output_dir is not None
    expected_root = tmp_path / 'exports' / 'Echo'
    echo_ns = tmp_path / "exports" / "Echo"
    assert Path(output_dir).parent == echo_ns


def test_full_session_payload_exists_during_consumer(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)
    payload_exists = [False]

    with service.acquired_export(QQExportImportRequest(group_code='700000001')) as acquisition:
        payload_exists[0] = Path(acquisition.payload_path).is_file()

    assert payload_exists[0]


def test_full_session_run_cleanup_after_consumer(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)

    with service.acquired_export(QQExportImportRequest(group_code='700000001')) as acquisition:
        run_dir = Path(acquisition.payload_path).parent

    assert not run_dir.exists()


def test_full_session_provider_receives_nonempty_output_dir(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)

    with service.acquired_export(QQExportImportRequest(group_code='700000001')):
        pass

    assert len(provider.output_dirs) == 1
    output_dir = provider.output_dirs[0]
    assert output_dir is not None
    assert str(output_dir).strip()
    echo_ns = tmp_path / 'exports' / 'Echo'
    assert Path(output_dir).is_relative_to(echo_ns)


def test_bounded_session_uses_transient_lease(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)

    with service.acquired_export(QQExportImportRequest(
        group_code='700000001',
        start_time=1750000000000,
        end_time=1750000001000,
    )) as acquisition:
        run_dir = Path(acquisition.payload_path).parent
        assert run_dir.is_dir()

    assert not run_dir.exists()


def test_full_session_exception_still_cleans_up(tmp_path):
    export_path = _write_fake_export(tmp_path / 'export.json')
    provider = _RecordingProvider(export_path)
    workspace = QQTransientExportWorkspace(tmp_path / 'exports')
    service = QQExportImportService(provider, transient_workspace=workspace)

    with pytest.raises(ValueError, match='test error'):
        with service.acquired_export(QQExportImportRequest(group_code='700000001')):
            raise ValueError('test error')

    echo_ns = tmp_path / 'exports' / 'Echo'
    for run_dir in echo_ns.iterdir():
        assert not run_dir.exists(), 'Transient run was not cleaned up after exception'
