"""Minimal local-only HTTP client for NapCat's `EchoSnapshotApi` RPC.

The Direct DB snapshot helper exposes `runtimeCore.apis.EchoSnapshotApi` over
NapCat's in-process `/rpc` bridge (`napcat_bridge_url`).  This module is a
thin client that may only invoke the three frozen methods `acquire` /
`cleanup` / `recover`:

* `acquire`    -> a fresh opaque `generation_id` for a ready snapshot
* `cleanup`    -> remove one generation by its id
* `recover`    -> remove orphan staging / legacy plaintext artifacts

It never accepts an absolute database path from the runtime.  Callers compute a
generation directory from the returned opaque id under a known snapshot root,
and the id is strictly validated so path traversal can never escape that root.
The only additional NapCat API call exposed here is the fixed
``GroupApi.getGroupMemberAll`` request used to resolve Direct DB group senders.

Privacy contract: error objects may only carry stable codes and privacy-safe
messages.  A runtime error message, the QQ UIN, nicknames, message text, the
passphrase and absolute paths never reach an exception's public message.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable


DEFAULT_RPC_TIMEOUT_SECONDS = 30
DEFAULT_ACQUIRE_RPC_TIMEOUT_SECONDS = 65
RECOVER_READINESS_ATTEMPTS = 51
RECOVER_READINESS_POLL_SECONDS = 0.1
RPC_METHOD_NAMESPACE = "EchoSnapshotApi"
GENERATIONS_DIRECTORY_NAME = "generations"

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_direct_snapshot")

_ACQUIRE = "acquire"
_CLEANUP = "cleanup"
_RECOVER = "recover"
_GROUP_MEMBER_ALL = "getGroupMemberAll"

class QQSnapshotRuntimeError(Exception):
    """Base, privacy-safe error for snapshot runtime client failures."""

    code = "qq_snapshot_runtime_error"
    public_message = "QQ local chat snapshot is unavailable."

    def __init__(self, public_message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class QQSnapshotRuntimeUnavailable(QQSnapshotRuntimeError):
    """The local runtime could not be reached at all."""

    code = "qq_snapshot_runtime_unavailable"
    public_message = (
        "QQ local chat data is unavailable. Please finish QQ login and try again."
    )


class QQSnapshotRuntimeInvalidResponse(QQSnapshotRuntimeError):
    """The runtime answered but the response was not a valid RPC envelope."""

    code = "qq_snapshot_runtime_invalid_response"
    public_message = "QQ local chat data is temporarily unavailable. Please try again."


class QQSnapshotRuntimeNotReady(QQSnapshotRuntimeError):
    """The bridge is ready but `EchoSnapshotApi` is not registered yet."""

    code = "qq_snapshot_runtime_not_ready"
    public_message = "QQ local chat data is still starting. Please try again."


class QQSnapshotRuntimeFailure(QQSnapshotRuntimeError):
    """The runtime reported a failure for the requested snapshot operation."""

    code = "qq_snapshot_runtime_failure"
    public_message = "QQ local chat data is temporarily unavailable. Please try again."


class QQSnapshotInvalidGenerationId(QQSnapshotRuntimeError):
    """A generation id was not a safe opaque path segment."""

    code = "qq_snapshot_invalid_generation_id"
    public_message = "QQ local chat data is temporarily unavailable. Please try again."


class QQSnapshotCleanupFailed(QQSnapshotRuntimeError):
    """The runtime could not remove a generation that may still hold plaintext."""

    code = "qq_snapshot_cleanup_failed"
    public_message = "QQ local chat data cleanup failed. Please try again."


def validate_generation_id(generation_id: Any) -> str:
    """Return a normalized opaque generation id, or raise on any unsafe value.

    Only a single, non-empty path segment is allowed.  Separators, traversal
    segments, NUL bytes and non-string values are rejected before the value can
    ever be joined under the snapshot root.
    """
    if isinstance(generation_id, bool) or not isinstance(generation_id, str):
        raise QQSnapshotInvalidGenerationId()
    value = generation_id.strip()
    if not value or value in (".", ".."):
        raise QQSnapshotInvalidGenerationId()
    if "/" in value or "\\" in value or "\x00" in value:
        raise QQSnapshotInvalidGenerationId()
    return value


class QQDirectSnapshotRuntimeClient:
    """Thin `EchoSnapshotApi` client bound to a known snapshot root."""

    def __init__(
        self,
        base_url: str,
        *,
        snapshot_root: str | Path,
        timeout: float = DEFAULT_RPC_TIMEOUT_SECONDS,
        acquire_timeout: float = DEFAULT_ACQUIRE_RPC_TIMEOUT_SECONDS,
        transport: Callable[[str, bytes, float], tuple[int, str]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._snapshot_root = Path(snapshot_root)
        self._timeout = timeout
        self._acquire_timeout = acquire_timeout
        self._transport = transport or _urllib_transport

    # ------------------------------------------------------------------ lifecycle

    def acquire(self) -> str:
        """Acquire a fresh generation and return its validated opaque id."""
        started_at = time.monotonic()
        _LOGGER.info("QQ snapshot acquire RPC started timeout=%.1fs", self._acquire_timeout)
        try:
            result = self._rpc(_ACQUIRE, [], timeout=self._acquire_timeout)
            if not isinstance(result, Mapping):
                raise QQSnapshotRuntimeInvalidResponse()
            if result.get("ok") is not True:
                raise QQSnapshotRuntimeFailure()
            if result.get("status") != "ready":
                raise QQSnapshotRuntimeFailure()
            generation_id = validate_generation_id(result.get("generation_id"))
        except Exception as error:
            _LOGGER.info(
                "QQ snapshot acquire RPC finished outcome=%s elapsed=%.2fs",
                type(error).__name__,
                time.monotonic() - started_at,
            )
            raise
        _LOGGER.info(
            "QQ snapshot acquire RPC finished outcome=ready elapsed=%.2fs generation_id=%s",
            time.monotonic() - started_at,
            generation_id,
        )
        return generation_id
    def cleanup(self, generation_id: str) -> None:
        """Remove one generation.  A missing generation is already cleaned."""
        normalized = validate_generation_id(generation_id)
        result = self._rpc(_CLEANUP, [normalized])
        if isinstance(result, Mapping) and result.get("ok") is True:
            return
        code = ""
        if isinstance(result, Mapping):
            code = _clean_str(result.get("code"))
        if code == "generation_not_found":
            return
        raise QQSnapshotCleanupFailed()

    def recover(self, *, deadline: float | None = None) -> None:
        """Ask the runtime to remove orphan staging and legacy artifacts."""
        if deadline is not None:
            result = self._rpc(_RECOVER, [], deadline=deadline)
            if isinstance(result, Mapping) and result.get("ok") is True:
                return
            raise QQSnapshotRuntimeFailure()
        for attempt in range(RECOVER_READINESS_ATTEMPTS):
            try:
                result = self._rpc(_RECOVER, [])
            except QQSnapshotRuntimeNotReady:
                if attempt == RECOVER_READINESS_ATTEMPTS - 1:
                    raise
                time.sleep(RECOVER_READINESS_POLL_SECONDS)
                continue
            if isinstance(result, Mapping) and result.get("ok") is True:
                return
            raise QQSnapshotRuntimeFailure()

    # ------------------------------------------------------------------ paths

    def generation_directory(self, generation_id: str) -> Path:
        """Compute the generation directory under the known snapshot root."""
        normalized = validate_generation_id(generation_id)
        return self._snapshot_root / GENERATIONS_DIRECTORY_NAME / normalized

    def get_group_member_all(self, group_code: str) -> Mapping[str, Any]:
        """Fetch one group's member metadata through NapCat's local RPC bridge."""
        result = self._rpc(
            _GROUP_MEMBER_ALL,
            [group_code],
            namespace="GroupApi",
        )
        if not isinstance(result, Mapping):
            raise QQSnapshotRuntimeInvalidResponse()
        return result

    # ------------------------------------------------------------------ internals

    def _rpc(
        self, method: str, params: list[Any], *,
        deadline: float | None = None, timeout: float | None = None,
        namespace: str = RPC_METHOD_NAMESPACE,
    ) -> Any:
        body = json.dumps(
            {"method": f"{namespace}.{method}", "params": params},
            ensure_ascii=False,
        ).encode("utf-8")
        url = f"{self._base_url}/rpc"
        timeout = self._timeout if timeout is None else timeout
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QQSnapshotRuntimeUnavailable()
            timeout = min(remaining, self._timeout)
        try:
            status, text = self._transport(url, body, timeout)
        except QQSnapshotRuntimeError:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise QQSnapshotRuntimeUnavailable() from error
        result = _unwrap_rpc(status, text)
        if deadline is not None and time.monotonic() >= deadline:
            raise QQSnapshotRuntimeUnavailable()
        return result


def _unwrap_rpc(status: int, text: str) -> Any:
    """Validate the bridge `{id, ok, result|error}` envelope."""
    if status < 200 or status >= 300:
        raise QQSnapshotRuntimeInvalidResponse()
    payload: Any = None
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
    if not isinstance(payload, Mapping):
        raise QQSnapshotRuntimeInvalidResponse()
    if payload.get("ok") is not True:
        if _is_recover_api_not_ready(payload.get("error")):
            raise QQSnapshotRuntimeNotReady()
        # The bridge error string may embed runtime details; it is never
        # surfaced, only mapped to a stable, privacy-safe failure.
        raise QQSnapshotRuntimeFailure()
    return payload.get("result")


def _is_recover_api_not_ready(error: Any) -> bool:
    """Match only the bridge's exact privacy-safe missing-method response."""
    return error == (
        f"NapCatCore method not found: {RPC_METHOD_NAMESPACE}.{_RECOVER}"
    )


def _urllib_transport(url: str, body: bytes, timeout: float) -> tuple[int, str]:
    """Perform one POST against the local `/rpc` bridge only."""
    if not url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        raise QQSnapshotRuntimeUnavailable()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        response_text = ""
        try:
            response_text = error.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - best effort on broken streams
            response_text = ""
        return int(error.code), response_text


def _clean_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


__all__ = [
    "DEFAULT_RPC_TIMEOUT_SECONDS",
    "DEFAULT_ACQUIRE_RPC_TIMEOUT_SECONDS",
    "GENERATIONS_DIRECTORY_NAME",
    "QQDirectSnapshotRuntimeClient",
    "QQSnapshotCleanupFailed",
    "QQSnapshotInvalidGenerationId",
    "QQSnapshotRuntimeError",
    "QQSnapshotRuntimeFailure",
    "QQSnapshotRuntimeNotReady",
    "QQSnapshotRuntimeInvalidResponse",
    "QQSnapshotRuntimeUnavailable",
    "validate_generation_id",
]
