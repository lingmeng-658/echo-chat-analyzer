"""Echo-only local readiness/metadata. No QCE auth, export or GUI dependency."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

from .qq_direct_snapshot_runtime import QQDirectSnapshotRuntimeClient, QQSnapshotRuntimeUnavailable

DEFAULT_BRIDGE_URL = "http://127.0.0.1:40655"


class NapCatQQError(Exception):
    code = "napcat_qq_unavailable"
    public_message = "QQ local runtime is unavailable. Please finish QQ login and retry."

    def __init__(self):
        super().__init__(self.public_message)


@dataclass(frozen=True)
class NapCatStatus:
    bridge_ready: bool
    qq_online: bool
    self_info: dict[str, str]
    database_api_ready: bool
    passphrase_ready: bool
    snapshot_api_ready: bool
    runtime_id: str | None = None

    @property
    def ready(self) -> bool:
        return all((self.bridge_ready, self.qq_online, self.self_info.get("uin"),
                    self.database_api_ready, self.passphrase_ready, self.snapshot_api_ready))


@dataclass(frozen=True)
class NapCatFriend:
    uid: str
    uin: str
    nickname: str
    remark: str

    @property
    def display_name(self) -> str:
        return self.remark or self.nickname or self.uin or self.uid


@dataclass(frozen=True)
class NapCatGroup:
    group_code: str
    group_name: str
    member_count: int | None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise NapCatQQError()


class NapCatQQProvider:
    def __init__(self, base_url: str = DEFAULT_BRIDGE_URL, *, timeout: float = 30,
                 transport: Callable[[str, bytes, float], tuple[int, str]] | None = None):
        try:
            parsed = urllib.parse.urlsplit(base_url)
            valid = (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
                     and not parsed.username and not parsed.password and parsed.path in {"", "/"}
                     and not parsed.query and not parsed.fragment and parsed.port is not None)
            if not valid or timeout <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            raise NapCatQQError() from None
        self._base_url = f"http://{parsed.hostname}:{parsed.port}"
        self._timeout = timeout
        self._transport = transport

    def _request(self, url: str, body: bytes, timeout: float) -> tuple[int, str]:
        if url != self._base_url + "/rpc":
            raise NapCatQQError()
        if self._transport is not None:
            return self._transport(url, body, timeout)
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            try:
                response = opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise NapCatQQError()
                return response.status, data.decode("utf-8")
        except (OSError, ValueError):
            raise NapCatQQError() from None

    def _rpc(self, method: str, params: list[Any] | None = None) -> Any:
        try:
            status, text = self._request(self._base_url + "/rpc", json.dumps({"method": method, "params": params or []}).encode(), self._timeout)
            value = json.loads(text)
            if status != 200 or not isinstance(value, dict) or value.get("ok") is not True:
                raise NapCatQQError()
            return value["result"]
        except (OSError, ValueError, KeyError, TypeError, NapCatQQError):
            raise NapCatQQError() from None

    def status(self) -> NapCatStatus:
        value = self._rpc("Core.status")
        fields = ("bridge_ready", "qq_online", "database_api_ready", "passphrase_ready", "snapshot_api_ready")
        if not isinstance(value, dict) or any(not isinstance(value.get(f), bool) for f in fields) or not isinstance(value.get("self_info"), dict):
            raise NapCatQQError()
        identity = {key: _text(value["self_info"].get(key)) for key in ("uin", "uid", "nickname")}
        return NapCatStatus(value["bridge_ready"], value["qq_online"], identity,
                            value["database_api_ready"], value["passphrase_ready"], value["snapshot_api_ready"],
                            _text(value.get("runtime_id")) or None)

    def list_friends(self) -> list[NapCatFriend]:
        rows = self._rpc("EchoMetadata.listFriends")
        if not isinstance(rows, list):
            raise NapCatQQError()
        return [NapCatFriend(*(_text(row.get(k)) for k in ("uid", "uin", "nickname", "remark"))) for row in rows if isinstance(row, dict)]

    def list_groups(self) -> list[NapCatGroup]:
        rows = self._rpc("EchoMetadata.listGroups")
        if not isinstance(rows, list):
            raise NapCatQQError()
        return [NapCatGroup(_text(row.get("group_code")), _text(row.get("group_name")),
                            row.get("member_count") if type(row.get("member_count")) is int else None)
                for row in rows if isinstance(row, dict)]

    def get_group_member_all(self, group_code: str) -> dict[str, Any]:
        result = self._rpc("GroupApi.getGroupMemberAll", [group_code])
        if not isinstance(result, dict):
            raise NapCatQQError()
        return result

    def snapshot_client(self, snapshot_root: str | Path) -> QQDirectSnapshotRuntimeClient:
        def transport(url: str, body: bytes, timeout: float) -> tuple[int, str]:
            try:
                return self._request(url, body, timeout)
            except NapCatQQError:
                raise QQSnapshotRuntimeUnavailable() from None
        return QQDirectSnapshotRuntimeClient(self._base_url, snapshot_root=snapshot_root, timeout=self._timeout, transport=transport)
