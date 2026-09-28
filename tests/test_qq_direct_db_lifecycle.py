"""RED-GREEN coverage for the Direct DB snapshot lifecycle (Phase 2C).

The Direct DB service owns application-side lifecycle state so the plaintext
snapshot can be recovered at startup and cleaned up before the QQ runtime is
stopped.  These tests drive the service and facade through the fake runtime
client; every database, identity and message here is fictional.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from qq_chat_analyzer.application.facade import ChatAnalyzerFacade, ChatSource
from qq_chat_analyzer.application.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
    QQDirectDatabaseRecoveryFailed,
    QQDirectDatabaseShuttingDown,
    QQDirectDatabaseState,
    QQDirectDatabaseUnavailable,
)
from qq_chat_analyzer.providers.qq_direct_snapshot_runtime import (
    QQSnapshotRuntimeFailure,
)

from qq_direct_db_testing import FICTIONAL_UIN, FakeSnapshotRuntime


GROUP_SESSION_ID = "group:group-partition"


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _field(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _text_blob(text: str) -> bytes:
    segment = _varint((45002 << 3) | 0) + _varint(1) + _field(45101, text.encode("utf-8"))
    return _field(40800, segment)


def _create_snapshot(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        for table_name in ("group_msg_table", "c2c_msg_table"):
            connection.execute(
                f'''CREATE TABLE {table_name} (
                    "40001" INTEGER PRIMARY KEY,
                    "40027" TEXT NOT NULL,
                    "40030" TEXT NOT NULL,
                    "40033" TEXT NOT NULL,
                    "40050" INTEGER NOT NULL,
                    "40800" BLOB NOT NULL
                )'''
            )
        connection.execute(
            '''INSERT INTO group_msg_table
                ("40001", "40027", "40030", "40033", "40050", "40800")
                VALUES (?, ?, ?, ?, ?, ?)''',
            (101, "group-partition", "fictional-group", "fictional-sender", 1760000001, _text_blob("fictional group message")),
        )


def _service(
    runtime: FakeSnapshotRuntime,
    *,
    shutdown_drain_seconds: float = 5.0,
) -> QQDirectDatabaseImportService:
    return QQDirectDatabaseImportService(
        runtime_client=runtime,
        shutdown_drain_seconds=shutdown_drain_seconds,
    )


# ------------------------------------------------------------------ startup


def test_startup_calls_recover_once(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)

    service.start()

    assert runtime.recover_calls == 1


def test_startup_recover_success_marks_active(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)

    service.start()

    assert service.state is QQDirectDatabaseState.ACTIVE
    # Idempotent: a second start does not recover again.
    service.start()
    assert runtime.recover_calls == 1


def test_startup_recover_failure_fails_closed(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    runtime.recover_error = QQSnapshotRuntimeFailure()
    service = _service(runtime)

    with pytest.raises(QQDirectDatabaseRecoveryFailed):
        service.start()

    assert service.state is QQDirectDatabaseState.CLOSED
    # Fail-closed: no generation is ever read after a failed recover.
    with pytest.raises(QQDirectDatabaseUnavailable):
        service.list_sessions()


def test_recover_failure_never_reads_old_generation(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    runtime.write_generation("stale-gen")
    runtime.recover_error = QQSnapshotRuntimeFailure()
    service = _service(runtime)

    with pytest.raises(QQDirectDatabaseRecoveryFailed):
        service.list_sessions()

    assert runtime.acquired == []
    assert runtime.cleaned == []


# ------------------------------------------------------------------ shutdown


def test_shutdown_rejects_new_list_sessions(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)
    service.start()

    service.shutdown()

    with pytest.raises(QQDirectDatabaseShuttingDown):
        service.list_sessions()


def test_shutdown_rejects_new_acquired_session(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)
    service.start()

    service.shutdown()

    with pytest.raises(QQDirectDatabaseShuttingDown):
        with service.acquired_session(GROUP_SESSION_ID):
            pass


def test_shutdown_transitions_to_closed(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)
    service.start()

    service.shutdown()

    assert service.state is QQDirectDatabaseState.CLOSED


def test_shutdown_recover_failure_is_stable_privacy_safe(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)
    service.start()

    runtime.recover_error = QQSnapshotRuntimeFailure()

    with pytest.raises(QQDirectDatabaseRecoveryFailed) as captured:
        service.shutdown()

    assert FICTIONAL_UIN not in str(captured.value)
    assert FICTIONAL_UIN not in captured.value.public_message
    assert service.state is QQDirectDatabaseState.CLOSED


def test_shutdown_drains_inflight_acquisition_without_second_acquire(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime, shutdown_drain_seconds=5.0)
    service.start()

    entered = threading.Event()
    release = threading.Event()
    original_acquire = runtime.acquire

    def _blocking_acquire() -> str:
        entered.set()
        release.wait(timeout=5.0)
        return original_acquire()

    runtime.acquire = _blocking_acquire

    outcome: dict[str, bool] = {}

    def _run() -> None:
        with service.acquired_session(GROUP_SESSION_ID) as acquisition:
            outcome["materialized"] = acquisition.payload_path.is_file()

    worker = threading.Thread(target=_run)
    worker.start()
    assert entered.wait(timeout=2.0)

    shutdown_thread = threading.Thread(target=service.shutdown)
    shutdown_thread.start()

    # Shutdown is now draining; release the in-flight acquire to let it finish.
    time.sleep(0.05)
    release.set()

    worker.join(timeout=5.0)
    shutdown_thread.join(timeout=5.0)

    assert not worker.is_alive()
    assert not shutdown_thread.is_alive()
    assert outcome.get("materialized") is True
    # Exactly one generation: shutdown never started a second acquire.
    assert runtime.acquired == ["gen-0001"]
    assert runtime.cleaned == ["gen-0001"]
    assert service.state is QQDirectDatabaseState.CLOSED


def test_shutdown_cleanup_runs_after_inflight_finishes(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)
    service.start()

    # Startup recover happened; reset the counter so the shutdown recover is
    # observable independently.
    assert runtime.recover_calls == 1
    runtime.recover_calls = 0

    service.shutdown()

    assert runtime.recover_calls == 1


# ------------------------------------------------------------------ orphans


def test_startup_recover_cleans_orphan_leftovers(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot, recover_clean=True)

    # Simulate a previous hard crash: orphan generation, staging and legacy
    # plaintext directories left behind under the snapshot root.
    orphan = tmp_path / "generations" / "gen-orphan"
    orphan.mkdir(parents=True)
    (orphan / "snapshot.db").write_bytes(b"fictional-orphan-plaintext")
    staging = tmp_path / "staging"
    staging.mkdir(parents=True)
    (staging / "nt_msg.db").write_bytes(b"fictional-staging-plaintext")
    legacy = tmp_path / "decrypted"
    legacy.mkdir(parents=True)
    (legacy / "nt_msg.db").write_bytes(b"fictional-legacy-plaintext")

    service = _service(runtime)
    service.start()

    assert runtime.recover_calls == 1
    assert not orphan.exists()
    assert not staging.exists()
    assert not legacy.exists()


def test_hard_crash_leftover_reclaimed_on_next_startup(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot, recover_clean=True)

    leftover = tmp_path / "generations" / "gen-crashed"
    leftover.mkdir(parents=True)
    (leftover / "snapshot.db").write_bytes(b"fictional-crash-plaintext")

    # First use (auto-start on list_sessions) recovers the crash leftover.
    service = _service(runtime)
    service.list_sessions()

    assert not leftover.exists()
    assert runtime.recover_calls == 1


# ------------------------------------------------------------------ success


def test_normal_success_path_leaves_no_residual_plaintext(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _service(runtime)

    service.list_sessions()
    with service.acquired_session(GROUP_SESSION_ID):
        pass

    generations = tmp_path / "generations"
    assert not generations.exists() or not any(generations.iterdir())


# ------------------------------------------------------------------ facade


def test_facade_shutdown_calls_direct_db_service_shutdown(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = QQDirectDatabaseImportService(runtime_client=runtime)
    service.start()
    runtime.recover_calls = 0

    class _Registry:
        def terminate_all(self) -> int:
            return 0

    facade = ChatAnalyzerFacade(qq_service=service, qq_process_registry=_Registry())

    facade.shutdown()

    # facade.shutdown must have delegated to the Direct DB service shutdown,
    # which recovers orphan plaintext one final time.
    assert runtime.recover_calls == 1
    assert service.state is QQDirectDatabaseState.CLOSED


def test_facade_shutdown_cleans_direct_db_before_terminating_runtime() -> None:
    events: list[str] = []

    class _OrderedQQService:
        def shutdown(self) -> None:
            events.append("direct_db_cleanup")

    class _OrderedRegistry:
        def terminate_all(self) -> int:
            events.append("qq_terminate")
            return 0

    facade = ChatAnalyzerFacade(
        qq_service=_OrderedQQService(),
        qq_process_registry=_OrderedRegistry(),
    )

    facade.shutdown()

    assert events == ["direct_db_cleanup", "qq_terminate"]


def test_facade_shutdown_survives_direct_db_cleanup_failure() -> None:
    events: list[str] = []

    class _FailingQQService:
        def shutdown(self) -> None:
            events.append("direct_db_cleanup")
            raise QQDirectDatabaseRecoveryFailed()

    class _OrderedRegistry:
        def terminate_all(self) -> int:
            events.append("qq_terminate")
            return 0

    facade = ChatAnalyzerFacade(
        qq_service=_FailingQQService(),
        qq_process_registry=_OrderedRegistry(),
    )

    # A Direct DB cleanup failure must not skip QQ runtime termination.
    facade.shutdown()

    assert events == ["direct_db_cleanup", "qq_terminate"]
