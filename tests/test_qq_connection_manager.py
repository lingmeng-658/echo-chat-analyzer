"""Tests for the QQ connection lifecycle manager.

All data here is fictional. The manager must never raise and never start a
runtime just to answer a status question.
"""

from __future__ import annotations

import importlib

import pytest


def _connection_module():
    return importlib.import_module("qq_chat_analyzer.application.connection")


def _status(
    *,
    available=False,
    qce_running=False,
    authenticated=False,
    version=None,
    message="",
    action_hint="",
):
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_connection_service"
    )
    return module.QQConnectionStatus(
        available=available,
        qce_running=qce_running,
        authenticated=authenticated,
        version=version,
        message=message,
        action_hint=action_hint,
    )


class _StubConnectionService:
    def __init__(self, status=None, error=None):
        self._status = status
        self._error = error
        self.check_calls = 0

    def check_status(self):
        self.check_calls += 1
        if self._error is not None:
            raise self._error
        return self._status


class _StubSetupService:
    def __init__(self, connect_status=None, error=None, runtime_status=None):
        self._connect_status = connect_status
        self._error = error
        self._runtime_status = runtime_status
        self.connect_calls = 0
        self.start_runtime_calls = 0
        self.get_runtime_status_calls = 0

    def connect(self):
        self.connect_calls += 1
        if self._error is not None:
            raise self._error
        return self._connect_status

    def start_runtime(self):
        self.start_runtime_calls += 1
        raise AssertionError("status checks must not start the runtime")

    def get_runtime_status(self):
        self.get_runtime_status_calls += 1
        return self._runtime_status


def _manager(setup_service=None, connection_service=None):
    return _connection_module().QQConnectionManager(
        setup_service=setup_service,
        connection_service=connection_service,
    )


def test_available_service_maps_to_connected() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(
            available=True,
            qce_running=True,
            authenticated=True,
            version="9.9.9",
            message="QQ \u5df2\u8fde\u63a5\u3002",
        )
    )

    snapshot = _manager(connection_service=service).get_snapshot()

    assert snapshot.state is module.ConnectionState.CONNECTED
    assert snapshot.connected is True
    assert snapshot.source == "qq"
    assert snapshot.version == "9.9.9"


def test_running_without_qq_data_maps_to_waiting_auth() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=True, authenticated=True)
    )

    snapshot = _manager(connection_service=service).get_snapshot()

    assert snapshot.state is module.ConnectionState.WAITING_AUTH
    assert snapshot.connected is False
    assert snapshot.message
    assert snapshot.action_hint


def test_stopped_service_maps_to_disconnected() -> None:
    module = _connection_module()
    service = _StubConnectionService(
        _status(available=False, qce_running=False, authenticated=False)
    )

    snapshot = _manager(connection_service=service).get_snapshot()

    assert snapshot.state is module.ConnectionState.DISCONNECTED
    assert snapshot.action_hint


def test_status_probe_failure_becomes_disconnected_not_an_exception() -> None:
    module = _connection_module()
    service = _StubConnectionService(error=RuntimeError("fictional probe"))

    snapshot = _manager(connection_service=service).get_snapshot()

    assert snapshot.state is module.ConnectionState.DISCONNECTED
    assert snapshot.message


def test_get_snapshot_never_starts_the_runtime() -> None:
    setup = _StubSetupService()
    service = _StubConnectionService(_status(available=True))

    _manager(setup_service=setup, connection_service=service).get_snapshot()

    assert setup.connect_calls == 0
    assert setup.start_runtime_calls == 0


def test_runtime_started_without_qq_login_maps_to_waiting_auth() -> None:
    module = _connection_module()
    runtime = importlib.import_module(
        "qq_chat_analyzer.application.runtime"
    )
    setup = _StubSetupService(
        runtime_status=runtime.QQRuntimeStatus(
            state=runtime.QQRuntimeState.RUNNING,
            available=True,
        )
    )
    service = _StubConnectionService(
        _status(available=False, qce_running=False, authenticated=False)
    )

    snapshot = _manager(
        setup_service=setup,
        connection_service=service,
    ).get_snapshot()

    assert setup.get_runtime_status_calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_missing_services_report_an_error_snapshot() -> None:
    module = _connection_module()

    snapshot = _manager().get_snapshot()

    assert snapshot.state is module.ConnectionState.ERROR
    assert snapshot.message


def test_connect_delegates_to_the_setup_service_once() -> None:
    module = _connection_module()
    setup = _StubSetupService(
        connect_status=_status(
            available=True,
            qce_running=True,
            authenticated=True,
        )
    )

    snapshot = _manager(setup_service=setup).connect()

    assert setup.connect_calls == 1
    assert snapshot.state is module.ConnectionState.CONNECTED


def test_connect_returns_waiting_auth_without_waiting_for_login() -> None:
    module = _connection_module()
    setup = _StubSetupService(
        connect_status=_status(
            available=True,
            qce_running=True,
            authenticated=True,
        )
    )
    service = _StubConnectionService(
        _status(
            available=False,
            qce_running=True,
            authenticated=False,
        )
    )

    snapshot = _manager(
        setup_service=setup,
        connection_service=service,
    ).connect()

    assert setup.connect_calls == 0
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_connect_starts_an_idle_runtime_and_reports_its_state() -> None:
    module = _connection_module()
    setup = _StubSetupService(
        connect_status=_status(
            available=False,
            qce_running=True,
            authenticated=False,
        )
    )
    service = _StubConnectionService(
        _status(
            available=False,
            qce_running=False,
            authenticated=False,
        )
    )

    snapshot = _manager(
        setup_service=setup,
        connection_service=service,
    ).connect()

    assert setup.connect_calls == 1
    assert snapshot.state is module.ConnectionState.WAITING_AUTH


def test_connect_failure_is_reported_as_an_error_snapshot() -> None:
    module = _connection_module()
    setup = _StubSetupService(error=RuntimeError("fictional failure"))

    snapshot = _manager(setup_service=setup).connect()

    assert snapshot.state is module.ConnectionState.ERROR
    assert snapshot.action_hint


def test_connect_failure_prefers_the_public_message() -> None:
    class _PublicError(RuntimeError):
        public_message = "\u8fde\u63a5\u5931\u8d25\u3002"

    setup = _StubSetupService(error=_PublicError("internal detail"))

    snapshot = _manager(setup_service=setup).connect()

    assert snapshot.message == "\u8fde\u63a5\u5931\u8d25\u3002"
    assert "internal detail" not in snapshot.message


def test_connect_without_a_setup_service_reports_error() -> None:
    module = _connection_module()

    snapshot = _manager().connect()

    assert snapshot.state is module.ConnectionState.ERROR


def test_snapshot_is_immutable() -> None:
    module = _connection_module()
    snapshot = module.ConnectionSnapshot(
        state=module.ConnectionState.CONNECTED,
        source="qq",
        message="ok",
    )

    with pytest.raises(Exception):
        snapshot.state = module.ConnectionState.ERROR


def test_in_progress_covers_startup_states() -> None:
    module = _connection_module()

    def snap(state):
        return module.ConnectionSnapshot(
            state=state, source="qq", message="m"
        )

    assert snap(module.ConnectionState.INITIALIZING).in_progress is True
    assert snap(module.ConnectionState.STARTING).in_progress is True
    assert snap(module.ConnectionState.CONNECTED).in_progress is False
    assert snap(module.ConnectionState.ERROR).in_progress is False
