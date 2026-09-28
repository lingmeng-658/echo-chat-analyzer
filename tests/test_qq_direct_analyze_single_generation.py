"""RED-GREEN coverage for the single-generation analyze path (Phase 2B).

One ``analyze_session`` for the Direct DB QQ source must acquire exactly one
runtime snapshot generation, validate it once, locate the target session and
materialize its payload from that same generation, then release the generation
before tokenizer/analyzer/report run.  These tests drive the service and the
facade through the fake runtime client, so no real NapCat bridge, passphrase or
QQ data is involved.  Every database, identity and message here is fictional.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from qq_chat_analyzer.application.analysis_service import AnalysisApplicationService
from qq_chat_analyzer.application.facade import (
    AnalysisConfig,
    ChatAnalyzerFacade,
    ChatSource,
)
from qq_chat_analyzer.application.import_request import ImportRequest
from qq_chat_analyzer.application.import_service import ImportService
from qq_chat_analyzer.application.qq_direct_database_import_service import (
    QQDirectDatabaseImportService,
    QQDirectSessionNotFound,
    QQDirectSnapshotAcquireFailed,
    QQDirectSnapshotCleanupFailed,
    QQDirectSnapshotInvalid,
)
from qq_chat_analyzer.providers.qq_database_provider import QQDatabaseProvider
from qq_chat_analyzer.providers.qq_direct_snapshot_runtime import (
    QQSnapshotCleanupFailed,
    QQSnapshotRuntimeUnavailable,
)

from qq_direct_db_testing import FICTIONAL_UIN, FakeSnapshotRuntime


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
            (101, "group-partition", "fictional-group", "fictional-group-sender", 1760000001, _text_blob("fictional group message")),
        )
        connection.execute(
            '''INSERT INTO c2c_msg_table
                ("40001", "40027", "40030", "40033", "40050", "40800")
                VALUES (?, ?, ?, ?, ?, ?)''',
            (201, "private-partition", "fictional-peer", "fictional-private-sender", 1760000002, _text_blob("fictional private message")),
        )


GROUP_SESSION_ID = "group:group-partition"
PRIVATE_SESSION_ID = "private:private-partition"


class _SpyDirectService(QQDirectDatabaseImportService):
    """Direct DB service that records public ``list_sessions`` usage."""

    def __init__(self, *args, **kwargs) -> None:
        self.list_sessions_calls = 0
        super().__init__(*args, **kwargs)

    def list_sessions(self):
        self.list_sessions_calls += 1
        return super().list_sessions()


def _service(tmp_path: Path, **kwargs) -> QQDirectDatabaseImportService:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    return QQDirectDatabaseImportService(runtime_client=runtime, **kwargs), runtime, snapshot


# ------------------------------------------------------------------ service


def test_acquired_session_acquires_exactly_one_generation(tmp_path: Path) -> None:
    service, runtime, _ = _service(tmp_path)

    with service.acquired_session(GROUP_SESSION_ID) as acquisition:
        assert acquisition.payload_path.is_file()

    assert runtime.acquired == ["gen-0001"]


def test_lookup_and_materialization_share_one_generation(tmp_path: Path) -> None:
    service, runtime, _ = _service(tmp_path)

    with service.acquired_session(GROUP_SESSION_ID) as acquisition:
        outcome = ImportService().execute(ImportRequest(input_path=acquisition.payload_path))
        assert outcome.messages[0].text == "fictional group message"

    # Exactly one generation was both acquired and cleaned.
    assert runtime.acquired == ["gen-0001"]
    assert runtime.cleaned == ["gen-0001"]


def test_success_cleans_up_generation(tmp_path: Path) -> None:
    service, runtime, _ = _service(tmp_path)

    with service.acquired_session(PRIVATE_SESSION_ID):
        pass

    assert runtime.cleaned == ["gen-0001"]
    assert not runtime.generation_directory("gen-0001").exists()


def test_payload_materialized_before_generation_release(tmp_path: Path) -> None:
    """The plaintext generation is gone before the analysis consumer runs."""
    service, runtime, _ = _service(tmp_path)

    with service.acquired_session(GROUP_SESSION_ID) as acquisition:
        # The generation lease was released before yield, so tokenizer/analyzer
        # never hold the plaintext DB.
        assert runtime.cleaned == ["gen-0001"]
        assert not runtime.generation_directory("gen-0001").exists()
        # The transient payload is still fully readable.
        assert acquisition.payload_path.is_file()
        outcome = ImportService().execute(ImportRequest(input_path=acquisition.payload_path))
        assert outcome.messages[0].text == "fictional group message"


def test_session_missing_still_cleans_up(tmp_path: Path) -> None:
    service, runtime, _ = _service(tmp_path)

    with pytest.raises(QQDirectSessionNotFound):
        with service.acquired_session("group:does-not-exist"):
            pass

    assert runtime.cleaned == ["gen-0001"]
    assert not runtime.generation_directory("gen-0001").exists()


def test_materialize_exception_still_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, runtime, _ = _service(tmp_path)

    def _raise(*_args, **_kwargs) -> None:
        raise RuntimeError("materialization exploded")

    monkeypatch.setattr(QQDatabaseProvider, "materialize_session_payload", _raise)

    with pytest.raises(RuntimeError, match="materialization exploded"):
        with service.acquired_session(GROUP_SESSION_ID):
            pass

    assert runtime.cleaned == ["gen-0001"]
    assert not runtime.generation_directory("gen-0001").exists()


def test_invalid_manifest_still_cleans_up(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    runtime.manifest_overrides = {"state": "building"}
    service = QQDirectDatabaseImportService(runtime_client=runtime)

    with pytest.raises(QQDirectSnapshotInvalid):
        with service.acquired_session(GROUP_SESSION_ID):
            pass

    assert runtime.cleaned == ["gen-0001"]


def test_cleanup_failure_returns_stable_privacy_safe_error(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    runtime.cleanup_error = QQSnapshotCleanupFailed()
    service = QQDirectDatabaseImportService(runtime_client=runtime)

    with pytest.raises(QQDirectSnapshotCleanupFailed) as captured:
        with service.acquired_session(GROUP_SESSION_ID):
            pass

    assert FICTIONAL_UIN not in str(captured.value)
    assert FICTIONAL_UIN not in captured.value.public_message


def test_second_acquire_failure_does_not_reuse_previous(tmp_path: Path) -> None:
    service, runtime, _ = _service(tmp_path)

    with service.acquired_session(GROUP_SESSION_ID):
        pass

    runtime.acquire_error = QQSnapshotRuntimeUnavailable()

    with pytest.raises(QQDirectSnapshotAcquireFailed):
        with service.acquired_session(GROUP_SESSION_ID):
            pass

    # The failed second acquire never appended a generation, and the first
    # generation was already cleaned.
    assert runtime.acquired == ["gen-0001"]
    assert runtime.cleaned == ["gen-0001"]


# ------------------------------------------------------------------ facade


def _facade(service: QQDirectDatabaseImportService) -> ChatAnalyzerFacade:
    return ChatAnalyzerFacade(
        qq_service=service,
        analysis_service=AnalysisApplicationService(),
        stopwords_directory=Path(__file__).resolve().parents[1],
    )


def test_analyze_acquires_exactly_one_generation(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = QQDirectDatabaseImportService(runtime_client=runtime)
    facade = _facade(service)

    outcome = facade.analyze_session(
        ChatSource.QQ,
        GROUP_SESSION_ID,
        AnalysisConfig(output_directory=tmp_path / "report"),
    )

    assert outcome.session is not None
    assert outcome.session.session_id == GROUP_SESSION_ID
    assert runtime.acquired == ["gen-0001"]
    assert runtime.cleaned == ["gen-0001"]


def test_analyze_does_not_call_public_list_sessions(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = _SpyDirectService(runtime_client=runtime)
    facade = _facade(service)

    facade.analyze_session(
        ChatSource.QQ,
        GROUP_SESSION_ID,
        AnalysisConfig(output_directory=tmp_path / "report"),
    )

    assert service.list_sessions_calls == 0


def test_two_analyzes_produce_distinct_generations(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = QQDirectDatabaseImportService(runtime_client=runtime)
    facade = _facade(service)

    facade.analyze_session(
        ChatSource.QQ, GROUP_SESSION_ID,
        AnalysisConfig(output_directory=tmp_path / "report-1"),
    )
    facade.analyze_session(
        ChatSource.QQ, GROUP_SESSION_ID,
        AnalysisConfig(output_directory=tmp_path / "report-2"),
    )

    assert runtime.acquired == ["gen-0001", "gen-0002"]
    assert runtime.acquired[0] != runtime.acquired[1]
    assert runtime.cleaned == ["gen-0001", "gen-0002"]


def test_second_analyze_acquire_failure_does_not_fallback(tmp_path: Path) -> None:
    snapshot = tmp_path / "source.db"
    _create_snapshot(snapshot)
    runtime = FakeSnapshotRuntime(tmp_path, snapshot_path=snapshot)
    service = QQDirectDatabaseImportService(runtime_client=runtime)
    facade = _facade(service)

    facade.analyze_session(
        ChatSource.QQ, GROUP_SESSION_ID,
        AnalysisConfig(output_directory=tmp_path / "report-1"),
    )

    runtime.acquire_error = QQSnapshotRuntimeUnavailable()

    with pytest.raises(Exception) as captured:
        facade.analyze_session(
            ChatSource.QQ, GROUP_SESSION_ID,
            AnalysisConfig(output_directory=tmp_path / "report-2"),
        )

    assert getattr(captured.value, "code", None) == "qq_direct_snapshot_acquire_failed"
    assert runtime.acquired == ["gen-0001"]


# ------------------------------------------------------------------ wiring


def test_production_service_builds_runtime_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The GUI composition's default service really gets a runtime client."""
    from qq_chat_analyzer.application.qq_environment_config import (
        QQEnvironmentConfig,
        QQEnvironmentConfigLoader,
    )
    from qq_chat_analyzer.gui.app import _optional_qq_service
    from qq_chat_analyzer.providers.qq_direct_snapshot_runtime import (
        QQDirectSnapshotRuntimeClient,
    )

    service = _optional_qq_service(provider_factory=object())
    assert isinstance(service, QQDirectDatabaseImportService)

    config = QQEnvironmentConfig(
        runtime_directory=tmp_path / "runtime" / "qq",
        napcat_bridge_url="http://127.0.0.1:40654",
    )
    monkeypatch.setattr(
        QQEnvironmentConfigLoader,
        "load_or_default",
        lambda self: config,
    )

    client = service._require_runtime_client()
    assert isinstance(client, QQDirectSnapshotRuntimeClient)
