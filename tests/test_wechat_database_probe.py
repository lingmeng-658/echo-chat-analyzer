"""Focused diagnostics for probing known WeChat session databases.

Every path, key, account, and message fragment in this file is fictional.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qq_chat_analyzer.application.wechat_setup_service import WeChatSetupService
from qq_chat_analyzer.application.wechat_environment_config import (
    WeChatEnvironmentConfig,
)
from qq_chat_analyzer.providers.wechat_database_provider import (
    DatabaseUnreadable,
    WeChatDatabaseProvider,
)


FICTIONAL_KEY = "b" * 64
FICTIONAL_ACCOUNT = "wxid_probe_owner"
FICTIONAL_CHAT_TEXT = "fictional private chat text"
VERIFY_SQL = "SELECT count(*) FROM sqlite_master"


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _success_result() -> str:
    return json.dumps(
        {
            "ok": True,
            "columns": ["count(*)"],
            "rows": [{"count(*)": 1}],
            "row_count": 1,
            "truncated": False,
        }
    )


def _code_26_result(message: str = "file is not a database") -> str:
    return json.dumps(
        {
            "ok": False,
            "stage": "prepare",
            "error": "prepare failed",
            "wcdb_error_code": 26,
            "wcdb_error_ext_code": 1032,
            "wcdb_error_message": message,
        }
    )


def _make_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    message_dir = root / FICTIONAL_ACCOUNT / "db_storage" / "message"
    message_dir.mkdir(parents=True, exist_ok=True)
    (message_dir / "session.db").write_bytes(f"fake-{name}".encode())
    (message_dir / "message_0.db").write_bytes(b"fake")
    return root


def _session_db(root: Path) -> Path:
    return root / FICTIONAL_ACCOUNT / "db_storage" / "message" / "session.db"


def _provider(
    tmp_path: Path,
    root: Path,
    runner,
) -> WeChatDatabaseProvider:
    helper = tmp_path / "wcdb_cli.exe"
    library = tmp_path / "WCDB.dll"
    helper.write_bytes(b"fake")
    library.write_bytes(b"fake")
    return WeChatDatabaseProvider(
        data_root=root,
        db_key=FICTIONAL_KEY,
        wcdb_cli_path=helper,
        wcdb_dll_path=library,
        timeout=10,
        runner=runner,
    )


class _Factory:
    def __init__(self, provider: object) -> None:
        self.provider = provider
        self.creates = 0

    def create(self) -> object:
        self.creates += 1
        return self.provider

    def invalidate(self) -> None:
        pass


class _ConfigLoader:
    def __init__(self, config: WeChatEnvironmentConfig) -> None:
        self._config = config

    def load(self) -> WeChatEnvironmentConfig:
        return self._config


def _command_database(command: list[str]) -> Path:
    return Path(command[command.index("--db") + 1])


def _command_sql(command: list[str]) -> str:
    return command[command.index("--sql") + 1]


def test_probe_logs_one_unique_candidate_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = _make_root(tmp_path, "saved_root")
    calls: list[list[str]] = []

    def runner(command, timeout, environment):
        calls.append(list(command))
        return _FakeCompleted(stdout=_code_26_result(), returncode=1)

    provider = _provider(tmp_path, root, runner)

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.providers.wechat_database_provider",
    ):
        provider.probe_session_databases(additional_roots=(root, root))

    assert len(calls) == 1
    assert "wechat.database.probe candidate_count=1" in caplog.text
    assert "wechat.database.probe candidate=1 success=false" in caplog.text
    assert "wcdb_error_code=26" in caplog.text


def test_probe_uses_the_same_key_for_all_unique_candidates(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    saved = _make_root(tmp_path, "saved_root")
    detected = _make_root(tmp_path, "detected_root")
    seen: list[tuple[Path, str]] = []

    def runner(command, timeout, environment):
        seen.append((_command_database(command), environment["WX_DB_KEY"]))
        return _FakeCompleted(stdout=_success_result())

    provider = _provider(tmp_path, saved, runner)

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.providers.wechat_database_provider",
    ):
        provider.probe_session_databases(
            additional_roots=(detected, saved, detected)
        )

    assert [path for path, _key in seen] == [
        _session_db(saved),
        _session_db(detected),
    ]
    assert {key for _path, key in seen} == {FICTIONAL_KEY}
    assert "wechat.database.probe candidate_count=2" in caplog.text
    assert "wechat.database.probe candidate=1 success=true" in caplog.text
    assert "wechat.database.probe candidate=2 success=true" in caplog.text


def test_verify_failure_probes_all_candidates_when_none_are_readable(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    saved = _make_root(tmp_path, "saved_root")
    detected = _make_root(tmp_path, "detected_root")
    calls: list[Path] = []

    def runner(command, timeout, environment):
        database = _command_database(command)
        calls.append(database)
        return _FakeCompleted(stdout=_code_26_result(), returncode=1)

    provider = _provider(tmp_path, saved, runner)
    service = WeChatSetupService(
        provider_factory=_Factory(provider),
        data_roots_detector=lambda: [detected],
    )

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.providers.wechat_database_provider",
    ):
        with pytest.raises(DatabaseUnreadable):
            service.verify_connection()

    assert calls == [_session_db(saved), _session_db(saved), _session_db(detected)]
    assert provider._data_root == saved
    assert "wechat.database.probe candidate=1 success=false" in caplog.text
    assert "wcdb_error_code=26" in caplog.text
    assert "wechat.database.probe candidate=2 success=false" in caplog.text


def test_probe_bypasses_saved_root_shortcut_before_fallback(
    tmp_path: Path,
) -> None:
    saved = _make_root(tmp_path, "saved_root")
    detected = _make_root(tmp_path, "detected_root")
    detector_calls: list[object] = []
    probe_calls: list[Path] = []

    def detect_roots() -> list[Path]:
        detector_calls.append(1)
        return [saved, detected]

    def runner(command, timeout, environment):
        database = _command_database(command)
        probe_calls.append(database)
        return _FakeCompleted(stdout=_code_26_result(), returncode=1)

    provider = _provider(tmp_path, saved, runner)
    service = WeChatSetupService(
        config_loader=_ConfigLoader(
            WeChatEnvironmentConfig(data_root=saved)
        ),
        provider_factory=_Factory(provider),
        data_roots_detector=detect_roots,
    )

    assert service.detect_wechat_data_roots() == [saved]
    assert detector_calls == []

    with pytest.raises(DatabaseUnreadable):
        service.verify_connection()

    assert detector_calls == [1]
    assert probe_calls == [
        _session_db(saved),
        _session_db(saved),
        _session_db(detected),
    ]


def test_all_code_26_candidates_are_logged_without_cipher_retry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    saved = _make_root(tmp_path, "saved_root")
    detected = _make_root(tmp_path, "detected_root")
    commands: list[list[str]] = []

    def runner(command, timeout, environment):
        commands.append(list(command))
        return _FakeCompleted(stdout=_code_26_result(), returncode=1)

    provider = _provider(tmp_path, saved, runner)
    service = WeChatSetupService(
        provider_factory=_Factory(provider),
        data_roots_detector=lambda: [detected],
    )

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.providers.wechat_database_provider",
    ):
        with pytest.raises(DatabaseUnreadable):
            service.verify_connection()

    assert "wechat.database.probe candidate_count=2" in caplog.text
    assert "wechat.database.probe candidate=1 success=false" in caplog.text
    assert "wechat.database.probe candidate=2 success=false" in caplog.text
    assert caplog.text.count("wcdb_error_code=26") >= 2
    assert all(_command_sql(command) == VERIFY_SQL for command in commands)
    assert all("--cipher-version" not in command for command in commands)
    assert all("--page-size" not in command for command in commands)


def test_probe_logs_are_anonymous(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    saved = _make_root(tmp_path, "saved_secret_root")
    detected = _make_root(tmp_path, "detected_secret_root")
    sensitive_message = (
        f"{_session_db(saved)} {_session_db(detected)} "
        f"{FICTIONAL_KEY} {VERIFY_SQL} {FICTIONAL_CHAT_TEXT}"
    )

    def runner(command, timeout, environment):
        return _FakeCompleted(
            stdout=_code_26_result(sensitive_message),
            returncode=1,
        )

    provider = _provider(tmp_path, saved, runner)
    service = WeChatSetupService(
        provider_factory=_Factory(provider),
        data_roots_detector=lambda: [detected],
    )

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.providers.wechat_database_provider",
    ):
        with pytest.raises(DatabaseUnreadable):
            service.verify_connection()

    logs = caplog.text
    assert str(saved) not in logs
    assert str(detected) not in logs
    assert FICTIONAL_ACCOUNT not in logs
    assert FICTIONAL_KEY not in logs
    assert VERIFY_SQL not in logs
    assert FICTIONAL_CHAT_TEXT not in logs


def test_probe_exception_does_not_replace_the_gui_recovery_error(
    tmp_path: Path,
) -> None:
    original_error = DatabaseUnreadable()

    class _CrashingProbeProvider:
        def __init__(self) -> None:
            self.probe_calls = 0

        def verify_readable(self) -> None:
            raise original_error

        def probe_session_databases(self, additional_roots) -> None:
            self.probe_calls += 1
            raise RuntimeError("probe failed")

    provider = _CrashingProbeProvider()
    service = WeChatSetupService(
        provider_factory=_Factory(provider),
        data_roots_detector=lambda: [tmp_path],
    )

    with pytest.raises(DatabaseUnreadable) as failure:
        service.verify_connection()

    assert failure.value is original_error
    assert provider.probe_calls == 1
