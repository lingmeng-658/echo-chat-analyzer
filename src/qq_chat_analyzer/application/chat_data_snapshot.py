"""Application-layer management of raw chat data snapshots."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from ..resources import user_data_dir


_SNAPSHOTS_RELATIVE_ROOT = Path("data") / "snapshots"
_MANIFEST_FILENAME = "manifest.json"
_CAPTURE_SCOPE_ALL = "all_available"
_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.chat_data_snapshot")
_MANIFEST_ERRORS = (
    OSError,
    UnicodeError,
    json.JSONDecodeError,
    KeyError,
    TypeError,
    ValueError,
)


class ChatDataSource(str, Enum):
    """Source labels supported by the snapshot metadata contract."""

    QQ = "qq"
    WECHAT = "wechat"


class SnapshotPayloadState(str, Enum):
    """Persisted lifecycle state of one raw snapshot payload."""

    AVAILABLE = "available"
    REMOVED = "removed"


class SnapshotStatus(str, Enum):
    """Derived availability state for one snapshot on disk."""

    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    MANIFEST_MISSING = "manifest_missing"
    MANIFEST_CORRUPTED = "manifest_corrupted"
    PAYLOAD_MISSING = "payload_missing"
    PAYLOAD_SIZE_MISMATCH = "payload_size_mismatch"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class ChatDataSnapshot:
    """Metadata describing one byte-for-byte chat export snapshot."""

    id: str
    source: ChatDataSource
    session_id: str = field(repr=False)
    session_name: str | None = field(default=None, repr=False)
    session_type: str = "other"
    acquired_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    capture_scope: str = _CAPTURE_SCOPE_ALL
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    message_count: int = 0
    data_size_bytes: int = 0
    storage_format: str = "qce_json"
    storage_path: str = field(default="", repr=False)
    payload_state: SnapshotPayloadState = SnapshotPayloadState.AVAILABLE


@dataclass(frozen=True, slots=True)
class SnapshotValidation:
    """Result of validating one snapshot manifest and raw payload."""

    snapshot_id: str
    status: SnapshotStatus
    snapshot: ChatDataSnapshot | None = None
    payload_path: Path | None = field(default=None, repr=False)

    @property
    def available(self) -> bool:
        return self.status is SnapshotStatus.AVAILABLE


class SnapshotSaveError(RuntimeError):
    """Raised when a snapshot cannot be committed safely."""


class SnapshotCleanupError(RuntimeError):
    """Raised when a snapshot payload cannot be removed safely."""


class ChatDataSnapshotManager:
    """Store and read raw chat payloads below the Echo user data directory."""

    def __init__(self, user_data_directory: str | Path | None = None) -> None:
        self._configured_user_data_directory = (
            Path(user_data_directory)
            if user_data_directory is not None
            else None
        )

    def save_snapshot(
        self,
        payload_path: str | Path,
        *,
        source: ChatDataSource | str,
        session_id: str,
        session_name: str | None,
        session_type: str,
        coverage_start: datetime | None,
        coverage_end: datetime | None,
        message_count: int,
        storage_format: str = "qce_json",
    ) -> ChatDataSnapshot:
        """Copy one raw payload and atomically commit its manifest."""
        source_path = Path(payload_path)
        stage_directory: Path | None = None
        try:
            if not source_path.is_file():
                raise SnapshotSaveError("Snapshot source payload is missing.")
            resolved_source = ChatDataSource(source)
            _validate_metadata(
                session_id=session_id,
                session_name=session_name,
                session_type=session_type,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                message_count=message_count,
                storage_format=storage_format,
            )

            snapshot_id = str(uuid4())
            user_root = self._user_data_root()
            snapshots_root = user_root / _SNAPSHOTS_RELATIVE_ROOT
            staging_root = snapshots_root / ".staging"
            final_directory = snapshots_root / resolved_source.value / snapshot_id
            staging_root.mkdir(parents=True, exist_ok=True)
            stage_directory = staging_root / snapshot_id
            stage_directory.mkdir()

            payload_filename = _payload_filename(source_path)
            staged_payload = stage_directory / payload_filename
            shutil.copyfile(source_path, staged_payload)

            relative_storage_path = (
                _SNAPSHOTS_RELATIVE_ROOT
                / resolved_source.value
                / snapshot_id
                / payload_filename
            ).as_posix()
            snapshot = ChatDataSnapshot(
                id=snapshot_id,
                source=resolved_source,
                session_id=session_id,
                session_name=session_name,
                session_type=session_type,
                acquired_at=datetime.now(timezone.utc),
                coverage_start=_as_utc(coverage_start),
                coverage_end=_as_utc(coverage_end),
                message_count=message_count,
                data_size_bytes=staged_payload.stat().st_size,
                storage_format=storage_format,
                storage_path=relative_storage_path,
            )
            (stage_directory / _MANIFEST_FILENAME).write_text(
                json.dumps(
                    _snapshot_to_payload(snapshot),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            final_directory.parent.mkdir(parents=True, exist_ok=True)
            stage_directory.replace(final_directory)
            stage_directory = None
            return snapshot
        except SnapshotSaveError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise SnapshotSaveError("Chat data snapshot could not be saved.") from exc
        finally:
            if stage_directory is not None:
                shutil.rmtree(stage_directory, ignore_errors=True)

    def get_snapshot(self, snapshot_id: str) -> ChatDataSnapshot | None:
        """Read one snapshot manifest, if the snapshot exists."""
        snapshot_directory = self._find_snapshot_directory(snapshot_id)
        if snapshot_directory is None:
            return None
        manifest_path = snapshot_directory / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            return None
        try:
            return self._read_snapshot(snapshot_directory)
        except _MANIFEST_ERRORS as exc:
            _LOGGER.warning(
                "Chat data snapshot manifest is corrupted; "
                "ignoring snapshot (%s).",
                type(exc).__name__,
            )
            return None

    def list_snapshots(
        self,
        *,
        source: ChatDataSource | str | None = None,
        session_id: str | None = None,
    ) -> tuple[ChatDataSnapshot, ...]:
        """Return readable snapshot manifests newest first."""
        sources = (
            (ChatDataSource(source),)
            if source is not None
            else tuple(ChatDataSource)
        )
        snapshots: list[ChatDataSnapshot] = []
        snapshots_root = self._user_data_root() / _SNAPSHOTS_RELATIVE_ROOT
        try:
            for candidate_source in sources:
                source_root = snapshots_root / candidate_source.value
                if not source_root.is_dir():
                    continue
                for snapshot_directory in source_root.iterdir():
                    if not snapshot_directory.is_dir():
                        continue
                    snapshot = self.get_snapshot(snapshot_directory.name)
                    if snapshot is None:
                        continue
                    if session_id is not None and snapshot.session_id != session_id:
                        continue
                    snapshots.append(snapshot)
        except OSError as exc:
            _LOGGER.warning(
                "Chat data snapshots could not be listed (%s).",
                type(exc).__name__,
            )
            return ()
        return tuple(
            sorted(
                snapshots,
                key=lambda snapshot: snapshot.acquired_at,
                reverse=True,
            )
        )

    def validate_snapshot(self, snapshot_id: str) -> SnapshotValidation:
        """Return the current manifest/payload status for one snapshot."""
        snapshot_directory = self._find_snapshot_directory(snapshot_id)
        if snapshot_directory is None:
            return SnapshotValidation(snapshot_id, SnapshotStatus.NOT_FOUND)

        manifest_path = snapshot_directory / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.MANIFEST_MISSING,
            )
        try:
            snapshot = self._read_snapshot(snapshot_directory)
            payload_path = self._declared_payload_path(
                snapshot,
                snapshot_directory,
            )
        except _MANIFEST_ERRORS:
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.MANIFEST_CORRUPTED,
            )

        if snapshot.payload_state is SnapshotPayloadState.REMOVED:
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.REMOVED,
                snapshot=snapshot,
            )
        if not payload_path.is_file():
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.PAYLOAD_MISSING,
                snapshot=snapshot,
            )
        try:
            payload_size = payload_path.stat().st_size
        except OSError:
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.PAYLOAD_MISSING,
                snapshot=snapshot,
            )
        if payload_size != snapshot.data_size_bytes:
            return SnapshotValidation(
                snapshot_id,
                SnapshotStatus.PAYLOAD_SIZE_MISMATCH,
                snapshot=snapshot,
            )
        return SnapshotValidation(
            snapshot_id,
            SnapshotStatus.AVAILABLE,
            snapshot=snapshot,
            payload_path=payload_path,
        )

    def find_latest_available(
        self,
        *,
        source: ChatDataSource | str,
        session_id: str,
        session_type: str,
    ) -> SnapshotValidation | None:
        """Return the newest valid payload matching one session identity."""
        for snapshot in self.list_snapshots(
            source=source,
            session_id=session_id,
        ):
            if snapshot.session_type != session_type:
                continue
            validation = self.validate_snapshot(snapshot.id)
            if validation.available:
                return validation
        return None

    def resolve_payload_path(self, snapshot_id: str) -> Path | None:
        """Resolve one persisted relative payload path for Application use."""
        validation = self.validate_snapshot(snapshot_id)
        return validation.payload_path if validation.available else None

    def remove_payload(self, snapshot_id: str) -> SnapshotValidation:
        """Remove one raw payload while preserving its queryable manifest."""
        validation = self.validate_snapshot(snapshot_id)
        snapshot = validation.snapshot
        if snapshot is None:
            return validation

        snapshot_directory = self._find_snapshot_directory(snapshot_id)
        if snapshot_directory is None:
            return SnapshotValidation(snapshot_id, SnapshotStatus.NOT_FOUND)
        try:
            payload_path = self._declared_payload_path(
                snapshot,
                snapshot_directory,
            )
            if payload_path.is_file():
                payload_path.unlink()
            removed_snapshot = replace(
                snapshot,
                payload_state=SnapshotPayloadState.REMOVED,
            )
            _write_manifest_atomically(snapshot_directory, removed_snapshot)
        except (OSError, ValueError) as exc:
            raise SnapshotCleanupError(
                "Chat data snapshot payload could not be removed."
            ) from exc
        return SnapshotValidation(
            snapshot_id,
            SnapshotStatus.REMOVED,
            snapshot=removed_snapshot,
        )

    def _user_data_root(self) -> Path:
        if self._configured_user_data_directory is not None:
            return self._configured_user_data_directory.resolve()
        return user_data_dir().resolve()

    def _find_snapshot_directory(self, snapshot_id: str) -> Path | None:
        if not _is_snapshot_id(snapshot_id):
            return None
        snapshots_root = self._user_data_root() / _SNAPSHOTS_RELATIVE_ROOT
        for source in ChatDataSource:
            snapshot_directory = snapshots_root / source.value / snapshot_id
            if snapshot_directory.is_dir():
                return snapshot_directory
        return None

    def _read_snapshot(self, snapshot_directory: Path) -> ChatDataSnapshot:
        manifest_path = snapshot_directory / _MANIFEST_FILENAME
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        snapshot = _snapshot_from_payload(payload)
        if snapshot.id != snapshot_directory.name:
            raise ValueError("Snapshot ID does not match its directory.")
        if snapshot.source.value != snapshot_directory.parent.name:
            raise ValueError("Snapshot source does not match its directory.")
        self._declared_payload_path(snapshot, snapshot_directory)
        return snapshot

    def _declared_payload_path(
        self,
        snapshot: ChatDataSnapshot,
        snapshot_directory: Path,
    ) -> Path:
        storage_path = snapshot.storage_path
        if "\\" in storage_path:
            raise ValueError("Snapshot storage path must use portable separators.")
        relative_path = PurePosixPath(storage_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Snapshot storage path must be relative.")
        payload_path = (
            self._user_data_root().joinpath(*relative_path.parts).resolve()
        )
        if payload_path.parent != snapshot_directory.resolve():
            raise ValueError("Snapshot payload must stay inside its directory.")
        return payload_path


def _snapshot_to_payload(snapshot: ChatDataSnapshot) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "source": snapshot.source.value,
        "session_id": snapshot.session_id,
        "session_name": snapshot.session_name,
        "session_type": snapshot.session_type,
        "acquired_at": snapshot.acquired_at.isoformat(),
        "capture_scope": snapshot.capture_scope,
        "coverage_start": _datetime_payload(snapshot.coverage_start),
        "coverage_end": _datetime_payload(snapshot.coverage_end),
        "message_count": snapshot.message_count,
        "data_size_bytes": snapshot.data_size_bytes,
        "storage_format": snapshot.storage_format,
        "storage_path": snapshot.storage_path,
        "payload_state": snapshot.payload_state.value,
    }


def _write_manifest_atomically(
    snapshot_directory: Path,
    snapshot: ChatDataSnapshot,
) -> None:
    manifest_path = snapshot_directory / _MANIFEST_FILENAME
    temporary_path = snapshot_directory / f"{_MANIFEST_FILENAME}.tmp"
    try:
        temporary_path.write_text(
            json.dumps(
                _snapshot_to_payload(snapshot),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(manifest_path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _snapshot_from_payload(payload: object) -> ChatDataSnapshot:
    if not isinstance(payload, dict):
        raise ValueError("Snapshot manifest must contain an object.")
    coverage_start = _parse_optional_datetime(payload["coverage_start"])
    coverage_end = _parse_optional_datetime(payload["coverage_end"])
    snapshot = ChatDataSnapshot(
        id=_required_string(payload["id"]),
        source=ChatDataSource(payload["source"]),
        session_id=_required_string(payload["session_id"]),
        session_name=_optional_string(payload["session_name"]),
        session_type=_required_string(payload["session_type"]),
        acquired_at=_parse_datetime(payload["acquired_at"]),
        capture_scope=_required_string(payload["capture_scope"]),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        message_count=_non_negative_integer(payload["message_count"]),
        data_size_bytes=_non_negative_integer(payload["data_size_bytes"]),
        storage_format=_required_string(payload["storage_format"]),
        storage_path=_required_string(payload["storage_path"]),
        payload_state=SnapshotPayloadState(payload["payload_state"]),
    )
    if snapshot.capture_scope != _CAPTURE_SCOPE_ALL:
        raise ValueError("Unsupported snapshot capture scope.")
    _validate_metadata(
        session_id=snapshot.session_id,
        session_name=snapshot.session_name,
        session_type=snapshot.session_type,
        coverage_start=snapshot.coverage_start,
        coverage_end=snapshot.coverage_end,
        message_count=snapshot.message_count,
        storage_format=snapshot.storage_format,
    )
    return snapshot


def _validate_metadata(
    *,
    session_id: object,
    session_name: object,
    session_type: object,
    coverage_start: datetime | None,
    coverage_end: datetime | None,
    message_count: object,
    storage_format: object,
) -> None:
    _required_string(session_id)
    _optional_string(session_name)
    _required_string(session_type)
    _required_string(storage_format)
    _non_negative_integer(message_count)
    if (coverage_start is None) != (coverage_end is None):
        raise ValueError("Snapshot coverage must contain both bounds or neither.")
    if coverage_start is not None:
        start = _as_utc(coverage_start)
        end = _as_utc(coverage_end)
        if start > end:
            raise ValueError("Snapshot coverage start exceeds its end.")


def _payload_filename(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    return f"export{suffix if suffix in {'.json', '.jsonl'} else '.data'}"


def _datetime_payload(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def _parse_optional_datetime(value: object) -> datetime | None:
    return None if value is None else _parse_datetime(value)


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Snapshot datetime must be an ISO string.")
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Snapshot datetime must include a timezone.")
    return value.astimezone(timezone.utc)


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Snapshot field must be a non-empty string.")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Snapshot field must be a string or null.")
    return value


def _non_negative_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Snapshot count and size fields must be non-negative.")
    return value


def _is_snapshot_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


__all__ = [
    "ChatDataSnapshot",
    "ChatDataSnapshotManager",
    "ChatDataSource",
    "SnapshotPayloadState",
    "SnapshotCleanupError",
    "SnapshotSaveError",
    "SnapshotStatus",
    "SnapshotValidation",
]
