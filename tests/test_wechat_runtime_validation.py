"""Behavior tests for the development-only WeChat runtime validator.

All fixtures are fictional. The validator is tested with a fake provider that
never touches a real database, so the tests cover environment checks, session
reads, message conversion, analysis, and error normalisation without reading
real chat data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.providers.wechat_database_provider import (  # noqa: E402
    DatabaseNotFound,
    KeyUnavailable,
    WcdbHelperNotFound,
    WcdbLibraryNotFound,
    WeChatSession,
)
from qq_chat_analyzer.validation.wechat_runtime_validator import (  # noqa: E402
    VC_RUNTIME_ERROR_MESSAGE,
    check_vc_runtime,
    validate_wechat_runtime,
)


FICTIONAL_SESSION = "wxid_fictional"
FICTIONAL_KEY = "a" * 64


def _row(text: str = "fictional validation deck trade coffee") -> dict:
    return {
        "local_id": 11,
        "server_id": 900001,
        "local_type": 1,
        "create_time": 1753412807,
        "message_content": text,
        "user_name": "wxid_fictional_sender",
    }


class _FakeProvider:
    """Stand in for WeChatDatabaseProvider without touching a database."""

    def __init__(
        self,
        *,
        data_ok: bool = True,
        key: str | None = FICTIONAL_KEY,
        helper_ok: bool = True,
        library_ok: bool = True,
        sessions: list[WeChatSession] | None = None,
        rows: list[dict] | None = None,
        session_error: Exception | None = None,
        export_error: Exception | None = None,
        probe_error: str | None = None,
    ) -> None:
        self._data_ok = data_ok
        self._key = key
        self._helper_ok = helper_ok
        self._library_ok = library_ok
        self._sessions = list(sessions or [])
        self._rows = list(rows or [])
        self._session_error = session_error
        self._export_error = export_error
        self._probe_error = probe_error
        self.export_limits: list[int | None] = []

    def _session_db_path(self) -> Path:
        if self._probe_error == "data":
            raise RuntimeError("raw data probe failure")
        if not self._data_ok:
            raise DatabaseNotFound()
        return Path("fictional/session.db")

    def _resolve_key(self) -> str:
        if self._probe_error == "key":
            raise RuntimeError("raw key probe failure")
        if self._key is None:
            raise KeyUnavailable()
        return self._key

    def _resolve_helper(self) -> Path:
        if self._probe_error == "helper":
            raise RuntimeError("raw helper probe failure")
        if not self._helper_ok:
            raise WcdbHelperNotFound()
        return Path("fictional/wcdb_cli.exe")

    def _resolve_library(self) -> Path:
        if self._probe_error == "library":
            raise RuntimeError("raw library probe failure")
        if not self._library_ok:
            raise WcdbLibraryNotFound()
        return Path("fictional/WCDB.dll")

    def list_sessions(self) -> list[WeChatSession]:
        if self._session_error is not None:
            raise self._session_error
        return list(self._sessions)

    def export_session_json(
        self,
        session_id: str,
        output_path: Path,
        start_time=None,
        end_time=None,
        limit: int | None = None,
    ) -> Path:
        self.export_limits.append(limit)
        if self._export_error is not None:
            raise self._export_error
        rows = self._rows
        if limit is not None:
            rows = rows[:limit]
        document = {
            "source": "wechat-db",
            "conversation": {"username": session_id},
            "messages": rows,
        }
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(document, ensure_ascii=False),
            encoding="utf-8",
        )
        return destination


def _provider(**overrides) -> _FakeProvider:
    defaults = {
        "sessions": [
            WeChatSession(
                session_id=FICTIONAL_SESSION,
                display_name="Fictional Session",
            )
        ],
        "rows": [_row()],
    }
    defaults.update(overrides)
    return _FakeProvider(**defaults)


# ------------------------------------------------------------- full success


def test_validation_success_reads_messages_and_runs_analysis() -> None:
    provider = _provider(rows=[_row(), _row(text="second fictional deck")])

    report = validate_wechat_runtime(provider, message_limit=10)

    assert report.ok is True
    assert report.environment_ok is True
    assert report.session_read is True
    assert report.message_read is True
    assert report.raw_message_count == 2
    assert report.chat_message_count == 2
    assert report.analysis_ok is True
    assert report.analysis_status is not None
    assert report.errors == ()
    assert provider.export_limits == [10]


def test_validation_accepts_an_explicit_session_id() -> None:
    provider = _provider()

    report = validate_wechat_runtime(
        provider,
        session_id=FICTIONAL_SESSION,
        message_limit=5,
    )

    assert report.ok is True
    assert provider.export_limits == [5]


# --------------------------------------------------------------- environment


def test_missing_db_key_fails_environment_validation() -> None:
    report = validate_wechat_runtime(_provider(key=None))

    assert report.ok is False
    assert report.environment_ok is False
    assert report.session_read is False
    assert report.message_read is False
    assert report.analysis_ok is False
    assert any("\u8bfb\u53d6\u6388\u6743" in error for error in report.errors)


@pytest.mark.parametrize("missing", ["helper", "library"])
def test_missing_wcdb_runtime_fails_environment_validation(
    missing: str,
) -> None:
    provider = _provider(**{f"{missing}_ok": False})

    report = validate_wechat_runtime(provider)

    assert report.ok is False
    assert report.environment_ok is False
    assert any("\u8fde\u63a5\u7ec4\u4ef6" in error for error in report.errors)


def test_missing_data_directory_fails_environment_validation() -> None:
    report = validate_wechat_runtime(_provider(data_ok=False))

    assert report.ok is False
    assert report.environment_ok is False
    assert any("\u6570\u636e\u4f4d\u7f6e" in error for error in report.errors)


# ------------------------------------------------------------- error handling


def test_session_read_error_is_normalized() -> None:
    report = validate_wechat_runtime(
        _provider(session_error=RuntimeError("raw session boom"))
    )

    assert report.ok is False
    assert report.environment_ok is True
    assert report.session_read is False
    assert report.message_read is False
    assert report.analysis_ok is False
    assert report.errors
    assert "raw session boom" not in " ".join(report.errors)
    assert "\u672a\u9884\u671f\u7684\u9519\u8bef" in report.errors[0]


def test_export_error_is_normalized() -> None:
    report = validate_wechat_runtime(
        _provider(export_error=RuntimeError("raw export boom"))
    )

    assert report.ok is False
    assert report.environment_ok is True
    assert report.session_read is True
    assert report.message_read is False
    assert report.analysis_ok is False
    assert "raw export boom" not in " ".join(report.errors)


@pytest.mark.parametrize("stage", ["data", "key", "helper", "library"])
def test_unexpected_probe_error_is_normalized(stage: str) -> None:
    report = validate_wechat_runtime(_provider(probe_error=stage))

    assert report.ok is False
    assert report.environment_ok is False
    assert report.errors
    assert "raw" not in " ".join(report.errors)
    assert any(
        "\u65e0\u6cd5\u786e\u8ba4\u5fae\u4fe1\u6570\u636e\u6e90\u72b6\u6001"
        in error
        for error in report.errors
    )


def test_empty_session_list_fails_validation() -> None:
    report = validate_wechat_runtime(_provider(sessions=[]))

    assert report.ok is False
    assert report.environment_ok is True
    assert report.session_read is False
    assert any("\u4f1a\u8bdd" in error for error in report.errors)

# ------------------------------------------------------------ VC++ runtime


def test_vc_runtime_sufficient_version_passes() -> None:
    ok, message = check_vc_runtime(
        platform="win32",
        version_reader=lambda _path: (14, 51, 36247, 0),
    )

    assert ok is True
    assert message is None


def test_vc_runtime_exact_minimum_passes() -> None:
    ok, message = check_vc_runtime(
        platform="win32",
        version_reader=lambda _path: (14, 43, 0, 0),
    )

    assert ok is True
    assert message is None


def test_vc_runtime_missing_dll_fails() -> None:
    ok, message = check_vc_runtime(
        platform="win32",
        version_reader=lambda _path: None,
    )

    assert ok is False
    assert message == VC_RUNTIME_ERROR_MESSAGE


def test_vc_runtime_too_old_fails() -> None:
    ok, message = check_vc_runtime(
        platform="win32",
        version_reader=lambda _path: (14, 16, 27033, 0),
    )

    assert ok is False
    assert message == VC_RUNTIME_ERROR_MESSAGE


def test_vc_runtime_non_windows_is_not_flagged() -> None:
    ok, message = check_vc_runtime(
        platform="linux",
        version_reader=lambda _path: None,
    )

    assert ok is True
    assert message is None


def test_validation_fails_when_vc_runtime_missing() -> None:
    def missing_runtime() -> tuple[bool, str | None]:
        return False, VC_RUNTIME_ERROR_MESSAGE

    report = validate_wechat_runtime(_provider(), vc_runtime_check=missing_runtime)

    assert report.ok is False
    assert report.environment_ok is False
    assert report.session_read is False
    assert report.message_read is False
    assert report.analysis_ok is False
    assert VC_RUNTIME_ERROR_MESSAGE in report.errors


def test_validation_passes_when_vc_runtime_ok() -> None:
    def ok_runtime() -> tuple[bool, str | None]:
        return True, None

    report = validate_wechat_runtime(
        _provider(),
        vc_runtime_check=ok_runtime,
        message_limit=10,
    )

    assert report.ok is True
    assert report.environment_ok is True
