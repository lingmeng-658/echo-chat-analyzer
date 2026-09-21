"""RED tests for Echo-owned QQChatExporter transient exports.

All paths are created under ``tmp_path``.  In particular, the fake QCE default
exports directory is only used as an ownership-boundary fixture; these tests
never contact QCE or touch a real user directory.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ApplicationServiceError,
    ChatDataSnapshotManager,
    QQExportImportRequest,
    QQExportImportService,
    SnapshotSaveError,
)


def _transient_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_transient_export"
    )


# The pinned ownership layout, agreed with the QCE integration:
#
#   Documents\QQChatExporter\exports\
#   |-- other QCE / user files     <- Echo never touches these
#   `-- Echo\<run-id>\             <- Echo owns and deletes only this
#
# QCE refuses any ``outputDir`` outside ``Documents\QQChatExporter\exports``,
# so ``exports\Echo`` is the only physical root Echo may allocate under.
_QCE_EXPORTS_RELATIVE_ROOT = Path("Documents") / "QQChatExporter" / "exports"
_ECHO_NAMESPACE = "Echo"


def _exports_root(tmp_path: Path) -> Path:
    """Return the QCE-accepted exports root used by these tests."""
    return tmp_path / _QCE_EXPORTS_RELATIVE_ROOT


def _echo_namespace(tmp_path: Path) -> Path:
    """Return the ``exports\\Echo`` namespace Echo exclusively owns."""
    return _exports_root(tmp_path) / _ECHO_NAMESPACE


def _write_qce_export(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "metadata": {"version": "fictional"},
                "chatInfo": {"chatType": 2, "peerUid": "fictional-session"},
                "statistics": {"totalMessages": 1},
                "messages": [
                    {
                        "id": "fictional-message",
                        "timestamp": 1750000000000,
                        "sender": {"uid": "fictional-user"},
                        "type": "text",
                        "content": {"text": "fictional", "elements": []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


class _WritingProvider:
    """A local QCE boundary fake that writes only to the supplied output dir."""

    def __init__(self) -> None:
        self.output_directories: list[Path] = []
        self.returned_paths: list[Path] = []

    def export_chat_json(self, _peer_uid, *, output_dir, **_kwargs) -> Path:
        destination = Path(output_dir)
        self.output_directories.append(destination)
        result = _write_qce_export(destination / "qce-export.json")
        self.returned_paths.append(result)
        return result


class _SnapshotSaveFailure:
    def find_latest_available(self, **_kwargs):
        return None

    def save_snapshot(self, *_args, **_kwargs):
        raise SnapshotSaveError("fictional save failure")


class _SnapshotValidationFailure:
    def find_latest_available(self, **_kwargs):
        return None

    def save_snapshot(self, *_args, **_kwargs):
        return type("Snapshot", (), {"id": "fictional-snapshot"})()

    def resolve_payload_path(self, _snapshot_id):
        return None


class _SnapshotHit:
    def __init__(self, payload_path: Path) -> None:
        self._payload_path = payload_path

    def find_latest_available(self, **_kwargs):
        snapshot = type(
            "Snapshot",
            (),
            {
                "id": "existing-snapshot",
                "acquired_at": None,
            },
        )()
        return type(
            "Validation",
            (),
            {
                "snapshot": snapshot,
                "payload_path": self._payload_path,
            },
        )()


class _WorkspaceThatMustNotAllocate:
    def begin_run(self):
        raise AssertionError("snapshot hit must not allocate a transient run")


def _workspace(tmp_path: Path):
    """Inject the QCE exports root so no test resolves a real user path."""
    module = _transient_module()
    return module.QQTransientExportWorkspace(_exports_root(tmp_path))


def _lease(tmp_path: Path, name: str = "run-1"):
    """Build one lease whose run directory already exists below the namespace."""
    module = _transient_module()
    namespace_root = _echo_namespace(tmp_path)
    run_directory = namespace_root / name
    run_directory.mkdir(parents=True, exist_ok=True)
    return module.QQTransientExportLease(namespace_root, run_directory)


def _service(workspace, provider, snapshot_manager):
    return QQExportImportService(
        provider,
        snapshot_manager=snapshot_manager,
        transient_workspace=workspace,
    )


def test_workspace_creates_one_owned_run_below_the_echo_namespace(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)

    lease = workspace.begin_run()

    assert lease.output_directory.is_dir()
    assert lease.output_directory.parent == _echo_namespace(tmp_path)
    lease.cleanup()
    assert not lease.output_directory.exists()


def test_workspace_rejects_qce_default_export_without_touching_it(
    tmp_path: Path,
) -> None:
    module = _transient_module()
    default_export = _write_qce_export(_exports_root(tmp_path) / "group.json")
    workspace = _workspace(tmp_path)
    lease = workspace.begin_run()

    with pytest.raises(module.QQTransientExportOwnershipError):
        lease.require_owned_export_file(default_export)

    lease.cleanup()
    assert default_export.is_file()
    assert default_export.parent == _exports_root(tmp_path)
    assert default_export.parent.name == "exports"


def test_bounded_export_remains_available_until_successful_consumer_returns(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    service = _service(
        workspace,
        provider,
        ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer"),
    )
    request = QQExportImportRequest(
        group_code="fictional-session",
        start_time=1750000000000,
        end_time=1750000001000,
    )

    with service.acquired_export(request) as acquisition:
        assert acquisition.payload_path.is_file()
        assert acquisition.payload_path == provider.returned_paths[0]
        run_directory = provider.output_directories[0]
        assert run_directory.is_dir()

    assert not run_directory.exists()


def test_bounded_export_is_released_when_its_consumer_raises(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    service = _service(
        workspace,
        provider,
        ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer"),
    )

    with pytest.raises(RuntimeError, match="fictional analysis failure"):
        with service.acquired_export(
            QQExportImportRequest(
                group_code="fictional-session",
                start_time=1750000000000,
                end_time=1750000001000,
            )
        ) as acquisition:
            assert acquisition.payload_path.is_file()
            run_directory = provider.output_directories[0]
            raise RuntimeError("fictional analysis failure")

    assert not run_directory.exists()


def test_full_snapshot_hit_does_not_create_a_qce_transient_run(
    tmp_path: Path,
) -> None:
    snapshot_payload = _write_qce_export(
        tmp_path / "LocalChatAnalyzer" / "data" / "snapshots" / "qq" / "existing.json"
    )
    provider = _WritingProvider()
    service = _service(
        _WorkspaceThatMustNotAllocate(),
        provider,
        _SnapshotHit(snapshot_payload),
    )

    with service.acquired_export(
        QQExportImportRequest(group_code="fictional-session")
    ) as acquisition:
        assert acquisition.payload_path == snapshot_payload
        assert acquisition.reused_snapshot is True

    assert provider.output_directories == []


def test_full_export_keeps_snapshot_after_releasing_qce_transient_run(
    tmp_path: Path,
) -> None:
    user_data = tmp_path / "LocalChatAnalyzer"
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    snapshot_manager = ChatDataSnapshotManager(user_data)
    service = _service(workspace, provider, snapshot_manager)

    with service.acquired_export(
        QQExportImportRequest(group_code="fictional-session")
    ) as acquisition:
        assert acquisition.snapshot_id is not None
        assert acquisition.payload_path.is_file()
        assert acquisition.payload_path.is_relative_to(user_data / "data" / "snapshots")
        run_directory = provider.output_directories[0]
        assert not run_directory.exists()

    assert acquisition.payload_path.is_file()
    assert not run_directory.exists()


@pytest.mark.parametrize(
    "snapshot_manager",
    [_SnapshotSaveFailure(), _SnapshotValidationFailure()],
)
def test_snapshot_failure_keeps_qce_transient_payload_until_consumer_exits(
    tmp_path: Path,
    snapshot_manager,
) -> None:
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    service = _service(workspace, provider, snapshot_manager)

    with service.acquired_export(
        QQExportImportRequest(group_code="fictional-session")
    ) as acquisition:
        run_directory = provider.output_directories[0]
        assert acquisition.snapshot_id is None
        assert acquisition.payload_path == provider.returned_paths[0]
        assert acquisition.payload_path.is_file()
        assert run_directory.is_dir()

    assert not run_directory.exists()


# --------------------------------------- Stage 1.1 cleanup failure policy


def _bounded_request() -> QQExportImportRequest:
    return QQExportImportRequest(
        group_code="fictional-session",
        start_time=1750000000000,
        end_time=1750000001000,
    )


def _break_cleanup(monkeypatch) -> None:
    """Make the real ``shutil.rmtree`` fail the way a locked file would."""

    def _refuse(_path, *args, **kwargs):
        raise OSError("fictional locked transient export")

    monkeypatch.setattr(_transient_module().shutil, "rmtree", _refuse)


def _cleanup_warnings(caplog) -> list[str]:
    """Return the warnings emitted while cleanup was failing.

    The design pins the level (a cleanup failure must never be silent)
    but deliberately leaves the wording to the implementation, so this
    stays wording-agnostic: in these scenarios a failed cleanup is the
    only possible warning source.
    """
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]


def test_cleanup_failure_does_not_fail_a_successful_consumer(
    tmp_path: Path,
    caplog,
    monkeypatch,
) -> None:
    """Cleanup is best-effort maintenance: it must never fail a good run."""
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    service = _service(
        workspace,
        provider,
        ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer"),
    )
    _break_cleanup(monkeypatch)

    with caplog.at_level(logging.WARNING):
        with service.acquired_export(_bounded_request()) as acquisition:
            consumed = json.loads(
                acquisition.payload_path.read_text(encoding="utf-8")
            )

    assert consumed["messages"]
    assert _cleanup_warnings(caplog)
    assert provider.output_directories[0].is_dir()
    assert provider.returned_paths[0].is_file()


def test_consumer_exception_is_not_replaced_by_a_cleanup_failure(
    tmp_path: Path,
    caplog,
    monkeypatch,
) -> None:
    workspace = _workspace(tmp_path)
    provider = _WritingProvider()
    service = _service(
        workspace,
        provider,
        ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer"),
    )
    _break_cleanup(monkeypatch)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match="fictional analysis failure"):
            with service.acquired_export(_bounded_request()) as acquisition:
                assert acquisition.payload_path.is_file()
                raise RuntimeError("fictional analysis failure")

    assert _cleanup_warnings(caplog)


def test_cleanup_never_deletes_outside_its_owned_run_root(
    tmp_path: Path,
) -> None:
    """Fail-closed: a mismatched run root is refused, never widened."""
    module = _transient_module()
    owned_root = _echo_namespace(tmp_path)
    foreign_run = tmp_path / "elsewhere" / "Echo" / "run-1"
    foreign_run.mkdir(parents=True)
    foreign_payload = _write_qce_export(foreign_run / "other-run.json")
    lease = module.QQTransientExportLease(owned_root, foreign_run)

    try:
        lease.cleanup()
    except ApplicationServiceError:
        pass  # refusing is fine; deleting outside the owned run is not

    assert foreign_payload.is_file()
    assert foreign_run.is_dir()


# --------------------------------------- Stage 1.1 ownership boundaries


def test_owned_export_file_rejects_the_run_directory_itself(
    tmp_path: Path,
) -> None:
    module = _transient_module()
    lease = _workspace(tmp_path).begin_run()

    with pytest.raises(module.QQTransientExportOwnershipError):
        lease.require_owned_export_file(lease.output_directory)

    lease.cleanup()


def test_owned_export_file_rejects_a_directory_inside_the_run(
    tmp_path: Path,
) -> None:
    module = _transient_module()
    lease = _workspace(tmp_path).begin_run()
    nested = lease.output_directory / "nested"
    nested.mkdir()

    with pytest.raises(module.QQTransientExportOwnershipError):
        lease.require_owned_export_file(nested)

    lease.cleanup()


def test_owned_export_file_accepts_a_real_file_inside_the_run(
    tmp_path: Path,
) -> None:
    lease = _workspace(tmp_path).begin_run()
    export_file = _write_qce_export(lease.output_directory / "export.json")

    assert lease.require_owned_export_file(export_file) == export_file.resolve()

    lease.cleanup()


class _DirectoryReturningProvider:
    """A QCE boundary fake that reports its output directory, not a file."""

    def __init__(self) -> None:
        self.output_directories: list[Path] = []

    def export_chat_json(self, _peer_uid, *, output_dir, **_kwargs) -> Path:
        destination = Path(output_dir)
        self.output_directories.append(destination)
        return destination


def test_provider_reporting_the_run_directory_is_never_used_as_a_payload(
    tmp_path: Path,
) -> None:
    module = _transient_module()
    provider = _DirectoryReturningProvider()
    service = _service(
        _workspace(tmp_path),
        provider,
        ChatDataSnapshotManager(tmp_path / "LocalChatAnalyzer"),
    )

    with pytest.raises(module.QQTransientExportOwnershipError):
        with service.acquired_export(_bounded_request()) as acquisition:
            pytest.fail(
                "the run directory must not be accepted as a payload: "
                f"{acquisition.payload_path}"
            )

    assert not provider.output_directories[0].exists()


class _OutputDirRecordingProvider:
    """Record exactly which directory QCE was told to write into."""

    def __init__(self) -> None:
        self.output_directories: list[object] = []

    def export_chat_json(
        self,
        _peer_uid,
        *,
        output_dir=None,
        **_kwargs,
    ) -> Path:
        self.output_directories.append(output_dir)
        destination = Path(output_dir)
        return _write_qce_export(destination / "qce-export.json")


def test_qq_acquisition_never_lets_qce_use_its_default_exports_folder(
    tmp_path: Path,
) -> None:
    """Stage 1 invariant: every acquisition names an Echo-owned output dir.

    If any entry point stopped forwarding ``output_dir``, QCE would fall
    back to its own ``exports`` folder, which Echo must never scan or
    delete. Both production entry points are exercised here.
    """
    user_data = tmp_path / "LocalChatAnalyzer"
    transient_root = _echo_namespace(tmp_path)
    provider = _OutputDirRecordingProvider()
    service = _service(
        _workspace(tmp_path),
        provider,
        ChatDataSnapshotManager(user_data),
    )

    service.execute(_bounded_request())
    assert service.get_session_message_range("fictional-session") is not None

    assert len(provider.output_directories) == 2
    for output_dir in provider.output_directories:
        assert output_dir is not None
        assert Path(output_dir).resolve().parent == transient_root.resolve()
    assert list(transient_root.iterdir()) == []


# ------------------------------- Stage 1.2 QCE-accepted physical root


def test_each_run_is_a_direct_child_of_the_echo_namespace(
    tmp_path: Path,
) -> None:
    """QCE only accepts an ``outputDir`` under its Documents exports folder.

    Echo therefore owns exactly ``exports\\Echo\\<run-id>``: one namespace
    level, and nothing else in that tree.
    """
    lease = _workspace(tmp_path).begin_run()

    assert lease.output_directory.is_dir()
    assert lease.output_directory.parent == _echo_namespace(tmp_path)
    assert _echo_namespace(tmp_path).parent == _exports_root(tmp_path)

    lease.cleanup()


def test_default_workspace_root_is_the_qce_documents_echo_namespace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """RED before the fix: the default root lived in LocalAppData.

    Real QCE rejects ``%LOCALAPPDATA%`` output directories outright, so a
    default-constructed workspace could never complete an export. The default
    must be ``<home>\\Documents\\QQChatExporter\\exports\\Echo`` instead.
    """
    module = _transient_module()
    home = tmp_path / "home"
    local_app_data = tmp_path / "local-app-data"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    lease = module.QQTransientExportWorkspace().begin_run()

    expected_namespace = (
        home / "Documents" / "QQChatExporter" / "exports" / "Echo"
    )
    assert lease.output_directory.parent == expected_namespace
    assert lease.output_directory.is_relative_to(tmp_path)
    assert not local_app_data.exists()

    lease.cleanup()
    assert expected_namespace.is_dir()


def test_cleanup_removes_only_this_run_below_the_echo_namespace(
    tmp_path: Path,
) -> None:
    """Cleanup owns one run; the namespace and any other QCE file survive.

    ``exports\\Echo`` belongs to the QCE integration, not to one analysis run,
    and everything next to it belongs to QCE or the user.
    """
    other_qce_export = _write_qce_export(
        _exports_root(tmp_path) / "another-qce-export.json"
    )
    workspace = _workspace(tmp_path)
    first = workspace.begin_run()
    second = workspace.begin_run()
    second_file = _write_qce_export(second.output_directory / "second.json")

    first.cleanup()

    assert not first.output_directory.exists()
    assert _echo_namespace(tmp_path).is_dir()
    assert _exports_root(tmp_path).is_dir()
    assert second.output_directory.is_dir()
    assert second_file.is_file()
    assert other_qce_export.is_file()

    second.cleanup()

    assert _echo_namespace(tmp_path).is_dir()
    assert other_qce_export.is_file()


# ---------------------- Stage 1.2 Windows verbatim (\\?\) ownership


def _verbatim(path: Path) -> str:
    """Return ``path`` in the verbatim form QCE reports in ``filePath``."""
    return "\\\\?\\" + str(path)


def test_verbatim_prefixes_are_normalized_without_touching_other_text() -> None:
    """Both Windows verbatim forms are stripped; nothing else is rewritten.

    Platform-independent: the check is on the string form, so it also pins the
    required ``\\\\?\\UNC\\server\\share\\...`` -> ``\\\\server\\share\\...``
    mapping that cannot be reproduced with a real local file.
    """
    normalize = _transient_module()._strip_windows_verbatim_prefix

    assert normalize("\\\\?\\C:\\Users\\fictional\\export.json") == (
        "C:\\Users\\fictional\\export.json"
    )
    assert normalize("\\\\?\\UNC\\server\\share\\export.json") == (
        "\\\\server\\share\\export.json"
    )
    # Not a brute replace: only one leading, well-formed prefix is removed.
    assert normalize("C:\\Users\\fictional\\export.json") == (
        "C:\\Users\\fictional\\export.json"
    )
    assert normalize("\\\\server\\share\\export.json") == (
        "\\\\server\\share\\export.json"
    )
    assert normalize("\\\\?\\Volume{00000000}\\export.json") == (
        "\\\\?\\Volume{00000000}\\export.json"
    )
    assert normalize("\\\\?\\UNC\\server") == "\\\\?\\UNC\\server"


@pytest.mark.skipif(os.name != "nt", reason="Windows verbatim path form")
def test_owned_export_file_accepts_a_verbatim_qce_returned_path(
    tmp_path: Path,
) -> None:
    """RED before the fix: a real owned ``\\\\?\\C:\\...`` file was rejected.

    On Windows ``Path(<verbatim>).resolve()`` keeps the ``\\\\?\\`` prefix, so
    ``is_relative_to`` compared a verbatim anchor against a normal one and
    produced a false negative for a file Echo genuinely owns.
    """
    module = _transient_module()
    lease = _lease(tmp_path)
    export_file = _write_qce_export(lease.output_directory / "qce-export.json")

    resolved = lease.require_owned_export_file(_verbatim(export_file))

    assert resolved == export_file.resolve()
    assert not str(resolved).startswith("\\\\?\\")

    lease.cleanup()


@pytest.mark.skipif(os.name != "nt", reason="Windows verbatim path form")
def test_verbatim_normalization_never_widens_ownership(
    tmp_path: Path,
) -> None:
    """Stripping the prefix must not let an outside file into the run."""
    module = _transient_module()
    outside = _write_qce_export(tmp_path / "elsewhere" / "other.json")
    lease = _lease(tmp_path)

    with pytest.raises(module.QQTransientExportOwnershipError):
        lease.require_owned_export_file(_verbatim(outside))

    lease.cleanup()
    assert outside.is_file()


@pytest.mark.skipif(os.name != "nt", reason="Windows verbatim path form")
def test_verbatim_path_to_the_run_directory_is_still_rejected(
    tmp_path: Path,
) -> None:
    """A verbatim directory is not a payload, exactly like a plain one."""
    module = _transient_module()
    lease = _lease(tmp_path)

    with pytest.raises(module.QQTransientExportOwnershipError):
        lease.require_owned_export_file(_verbatim(lease.output_directory))

    lease.cleanup()
