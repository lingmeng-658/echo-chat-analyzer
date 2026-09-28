"""Acquire one QQ session from NapCat's local plaintext DB snapshot.

NapCat's in-process `DatabaseApi.decryptDatabase` helper owns decryption and
the passphrase.  This service deliberately starts after that boundary: it
acquires one local snapshot generation through the snapshot runtime, asks the
existing provider to materialize one source-specific payload, releases the
generation, and yields that payload to the existing import path.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from ..providers.qq_database_provider import QQDatabaseProvider, QQSession
from ..providers.qq_direct_snapshot_runtime import (
    QQDirectSnapshotRuntimeClient,
    QQSnapshotRuntimeError,
)
from ..qq_db_identity import QQ_DB_SELF_NAMESPACE, canonical_qq_uin
from .errors import ApplicationServiceError
from .qq_environment_config import QQEnvironmentConfigLoader


_SNAPSHOT_ROOT_RELATIVE_PATH = Path("output", "qq_direct_db_phase35")
_GENERATION_MANIFEST_NAME = "manifest.json"
_MANIFEST_SCHEMA_VERSION = 1

#: Bounded window `shutdown` waits for in-flight acquisitions to drain before
#: it recovers orphan plaintext and reports completion.  This is deliberately
#: finite: a stuck runtime call is never killed and never waited on forever.
DEFAULT_SHUTDOWN_DRAIN_SECONDS = 5.0


class QQDirectDatabaseState(str, Enum):
    """Application-side lifecycle state owned by the Direct DB service."""

    CLOSED = "closed"
    ACTIVE = "active"
    SHUTTING_DOWN = "shutting_down"


class QQDirectDatabaseUnavailable(ApplicationServiceError):
    """Raised when NapCat has not produced a readable plaintext snapshot."""

    code = "qq_direct_database_unavailable"
    public_message = "QQ local chat data is unavailable. Please finish QQ login and try again."


class QQDirectSessionNotFound(ApplicationServiceError):
    """Raised when a selected direct DB session is no longer present."""

    code = "qq_direct_session_not_found"
    public_message = "The selected QQ session is unavailable. Refresh the session list and try again."


class QQDirectSnapshotAcquireFailed(ApplicationServiceError):
    """Raised when the snapshot runtime cannot produce a fresh generation."""

    code = "qq_direct_snapshot_acquire_failed"
    public_message = "QQ local chat data is temporarily unavailable. Please confirm QQ is logged in and try again."


class QQDirectSnapshotInvalid(ApplicationServiceError):
    """Raised when a generation fails manifest or database validation."""

    code = "qq_direct_snapshot_invalid"
    public_message = "QQ local chat data is temporarily unavailable. Please try again."


class QQDirectSnapshotCleanupFailed(ApplicationServiceError):
    """Raised when a generation cannot be removed after reading."""

    code = "qq_direct_snapshot_cleanup_failed"
    public_message = "QQ local chat data cleanup failed. Please try again."


class QQDirectDatabaseRecoveryFailed(ApplicationServiceError):
    """Raised when the runtime cannot recover orphan snapshot plaintext."""

    code = "qq_direct_database_recovery_failed"
    public_message = "QQ local chat data recovery failed. Please restart Echo and try again."


class QQDirectDatabaseShuttingDown(ApplicationServiceError):
    """Raised when a new acquisition arrives after shutdown has begun."""

    code = "qq_direct_database_shutting_down"
    public_message = "QQ local chat data is shutting down. Please try again."


@dataclass(frozen=True, slots=True)
class QQDirectDatabaseAcquisition:
    """The local source-specific payload consumed by `ImportService`."""

    payload_path: Path
    self_uin: str | None = None
    session: QQSession | None = None


class QQDirectDatabaseImportService:
    """Small Direct DB acquisition orchestrator for the QQ product path.

    It intentionally delegates DB reads to `QQDatabaseProvider` and leaves
    parsing, importing, analysis, and reporting to their existing services.
    Each acquisition owns exactly one runtime generation: it is validated,
    read, materialized into a `qq-db-json` payload, and released in
    `finally` before the payload is handed to the consumer, so the plaintext
    DB never outlives payload materialization.

    It also owns the application-side lifecycle: before the first generation is
    read, `recover` removes any plaintext left behind by a previous run (a
    crash, a shutdown, or a kill), and `shutdown` drains in-flight
    acquisitions before recovering one last time, so the plaintext snapshot is
    always cleaned up before the QQ runtime is allowed to stop.
    """

    def __init__(
        self,
        *,
        runtime_client: Any | None = None,
        config_loader: QQEnvironmentConfigLoader | None = None,
        shutdown_drain_seconds: float = DEFAULT_SHUTDOWN_DRAIN_SECONDS,
    ) -> None:
        self._runtime_client = runtime_client
        self._config_loader = config_loader or QQEnvironmentConfigLoader()
        self._shutdown_drain_seconds = shutdown_drain_seconds
        self._state = QQDirectDatabaseState.CLOSED
        self._startup_attempted = False
        self._shutdown_started = False
        self._active_acquisitions = 0
        self._condition = threading.Condition()

    @property
    def state(self) -> QQDirectDatabaseState:
        return self._state

    def start(self) -> None:
        """Recover orphan plaintext and transition to ACTIVE.

        If startup fails the service becomes terminal and refuses further work.
        """
        with self._condition:
            if self._state is QQDirectDatabaseState.ACTIVE:
                return
            if self._shutdown_started:
                raise QQDirectDatabaseShuttingDown()
            if self._startup_attempted:
                raise QQDirectDatabaseUnavailable()
            self._startup_attempted = True
            try:
                self._recover_on_startup()
            except QQDirectDatabaseRecoveryFailed:
                self._state = QQDirectDatabaseState.CLOSED
                raise
            self._state = QQDirectDatabaseState.ACTIVE
    def shutdown(self) -> None:
        """Transition to SHUTTING_DOWN, drain in-flight acquisitions, then recover."""
        with self._condition:
            if self._shutdown_started:
                return
            self._shutdown_started = True
            if self._state is QQDirectDatabaseState.CLOSED:
                return
            self._state = QQDirectDatabaseState.SHUTTING_DOWN
        self._drain_acquisitions()
        try:
            self._recover_on_shutdown()
        finally:
            with self._condition:
                self._state = QQDirectDatabaseState.CLOSED
    def list_sessions(self) -> list[QQSession]:
        """Discover sessions from one fresh generation, then release it.

        The generation is cleaned up in `finally` so the plaintext DB never
        outlives this call.
        """
        self._begin_acquisition()
        try:
            client = self._require_runtime_client()
            generation_id: str | None = None
            try:
                try:
                    generation_id = client.acquire()
                    database_path, _self_uin = _validated_generation(
                        client.generation_directory(generation_id),
                        generation_id,
                    )
                    provider = QQDatabaseProvider(database_path)
                    return provider.list_sessions()
                except QQSnapshotRuntimeError as error:
                    raise QQDirectSnapshotAcquireFailed() from error
                finally:
                    if generation_id is not None:
                        try:
                            client.cleanup(generation_id)
                        except QQSnapshotRuntimeError as error:
                            raise QQDirectSnapshotCleanupFailed() from error
            finally:
                pass
        finally:
            self._end_acquisition()

    @contextmanager
    def acquired_session(
        self,
        session_id: str,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> Iterator[QQDirectDatabaseAcquisition]:
        """Materialize one selected session from one fresh generation.

        One runtime generation is acquired exactly once.  Its manifest and
        database are validated with the same helper used by
        :meth:list_sessions; the target session is located by typed identity
        and materialized from that same generation DB.  The generation is
        removed in `finally` before the payload is yielded, so the plaintext
        DB is released as soon as the `qq-db-json` payload is fully written
        and no tokenizer/analyzer/report ever holds the plaintext DB.
        """
        self._begin_acquisition()
        try:
            client = self._require_runtime_client()
            generation_id: str | None = None
            scratch_context: TemporaryDirectory | None = None
            try:
                try:
                    generation_id = client.acquire()
                    database_path, self_uin = _validated_generation(
                        client.generation_directory(generation_id),
                        generation_id,
                    )
                    provider = QQDatabaseProvider(database_path)
                    session = next(
                        (
                            candidate
                            for candidate in provider.list_sessions()
                            if candidate.session_id == session_id
                        ),
                        None,
                    )
                    if session is None:
                        raise QQDirectSessionNotFound()
                    scratch_context = TemporaryDirectory(prefix="chat-analyzer-qq-db-")
                    payload_path = provider.materialize_session_payload(
                        session,
                        Path(scratch_context.name) / "qq-db-session.json",
                        start_time=start_time,
                        end_time=end_time,
                        self_uin=self_uin,
                    )
                    acquisition = QQDirectDatabaseAcquisition(
                        payload_path=payload_path,
                        self_uin=self_uin,
                        session=session,
                    )
                except QQSnapshotRuntimeError as error:
                    raise QQDirectSnapshotAcquireFailed() from error
                finally:
                    if generation_id is not None:
                        try:
                            client.cleanup(generation_id)
                        except QQSnapshotRuntimeError as error:
                            raise QQDirectSnapshotCleanupFailed() from error
                yield acquisition
            finally:
                if scratch_context is not None:
                    scratch_context.cleanup()
        finally:
            self._end_acquisition()

    # -------------------------------------------------------------- lifecycle

    def _ensure_usable(self) -> None:
        """Ensure startup recover has run, or refuse a non-active service.

        The first call auto-starts the service (recover -> ACTIVE).  After a
        failed startup or a completed shutdown the service is terminal and
        raises without ever reading a generation.
        """
        with self._condition:
            if self._state is QQDirectDatabaseState.ACTIVE:
                return
            if self._shutdown_started:
                raise QQDirectDatabaseShuttingDown()
            if not self._startup_attempted:
                self.start()
                return
            raise QQDirectDatabaseUnavailable()
    def _recover_on_startup(self) -> None:
        """Recover orphan plaintext during startup."""
        client = self._require_runtime_client()
        try:
            client.recover()
        except QQSnapshotRuntimeError as error:
            raise QQDirectDatabaseRecoveryFailed() from error

    def _begin_acquisition(self) -> None:
        """Register one in-flight acquisition, refusing new work after shutdown."""
        self._ensure_usable()
        with self._condition:
            if self._state is not QQDirectDatabaseState.ACTIVE:
                raise QQDirectDatabaseShuttingDown()
            self._active_acquisitions += 1

    def _end_acquisition(self) -> None:
        """Release one in-flight acquisition and wake any shutdown drain."""
        with self._condition:
            self._active_acquisitions -= 1
            if self._active_acquisitions == 0:
                self._condition.notify_all()

    def _drain_acquisitions(self) -> None:
        """Wait, up to a bounded window, for in-flight acquisitions to finish."""
        deadline = time.monotonic() + self._shutdown_drain_seconds
        with self._condition:
            while self._active_acquisitions > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=remaining)

    def _recover_on_shutdown(self) -> None:
        """Recover orphan plaintext one last time before the runtime stops."""
        client = self._require_runtime_client()
        try:
            client.recover()
        except QQSnapshotRuntimeError as error:
            raise QQDirectDatabaseRecoveryFailed() from error

    def _require_runtime_client(self) -> Any:
        """Return the injected runtime client, or build one from config."""
        if self._runtime_client is not None:
            return self._runtime_client
        config = self._environment_config()
        runtime_directory = config.runtime_directory
        if runtime_directory is None:
            raise QQDirectDatabaseUnavailable()
        base_url = config.napcat_bridge_url or "http://127.0.0.1:40654"
        return QQDirectSnapshotRuntimeClient(
            base_url=base_url,
            snapshot_root=Path(runtime_directory).parent / _SNAPSHOT_ROOT_RELATIVE_PATH,
        )

    def _environment_config(self) -> Any:
        try:
            return self._config_loader.load_or_default()
        except Exception:
            raise QQDirectDatabaseUnavailable() from None


def _validated_generation(
    generation_directory: Path,
    generation_id: str,
) -> tuple[Path, str]:
    """Validate one generation's manifest and return its database and self UIN.

    Fail closed on any mismatch: the manifest must declare the exact
    `schema_version`, the exact `generation_id` returned by the runtime, a
    `ready` state, a strictly safe same-directory database name, and a
    canonicalizable `qq_uin` identity.  The database file must then exist.
    This is the single manifest-validation helper shared by `list_sessions`
    and `acquired_session`; no second validation path exists.
    """
    manifest_path = generation_directory / _GENERATION_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise QQDirectSnapshotInvalid() from None
    if not isinstance(payload, dict):
        raise QQDirectSnapshotInvalid()
    if payload.get("schema_version") != _MANIFEST_SCHEMA_VERSION:
        raise QQDirectSnapshotInvalid()
    if payload.get("generation_id") != generation_id:
        raise QQDirectSnapshotInvalid()
    if payload.get("state") != "ready":
        raise QQDirectSnapshotInvalid()

    database_name = _safe_relative_name(payload.get("database"))
    if database_name is None:
        raise QQDirectSnapshotInvalid()

    identity = payload.get("identity")
    if not isinstance(identity, dict):
        raise QQDirectSnapshotInvalid()
    if identity.get("namespace") != QQ_DB_SELF_NAMESPACE:
        raise QQDirectSnapshotInvalid()
    self_uin = canonical_qq_uin(identity.get("value"))
    if self_uin is None:
        raise QQDirectSnapshotInvalid()

    database_path = generation_directory / database_name
    if not database_path.is_file():
        raise QQDirectSnapshotInvalid()
    return database_path, self_uin


def _safe_relative_name(value: Any) -> str | None:
    """Return a single safe same-directory name, or None when unsafe."""
    if isinstance(value, bool) or not isinstance(value, str):
        return None
    name = value.strip()
    if not name or name in (".", ".."):
        return None
    if "/" in name or "\\" in name or "\x00" in name:
        return None
    return name


__all__ = [
    "DEFAULT_SHUTDOWN_DRAIN_SECONDS",
    "QQDirectDatabaseAcquisition",
    "QQDirectDatabaseImportService",
    "QQDirectDatabaseRecoveryFailed",
    "QQDirectDatabaseShuttingDown",
    "QQDirectDatabaseState",
    "QQDirectDatabaseUnavailable",
    "QQDirectSessionNotFound",
    "QQDirectSnapshotAcquireFailed",
    "QQDirectSnapshotCleanupFailed",
    "QQDirectSnapshotInvalid",
]
