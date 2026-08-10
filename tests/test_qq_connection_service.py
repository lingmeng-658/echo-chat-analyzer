"""Behavior tests for the QQ connection layer.

The service under test never talks to a real QCE instance. Provider behaviour
is simulated with stubs so the tests cover running, stopped, unauthenticated
and failing states without touching real chat data or tokens.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_connection_service"
    )


class _FakeProvider:
    """Stand in for QQChatExporterProvider with a configurable health/token."""

    def __init__(
        self,
        *,
        running: bool = True,
        version: str | None = "4.1.0",
        token: str | None = "fictional-token",
        unexpected_error: Exception | None = None,
    ) -> None:
        self._running = running
        self._version = version
        self._token = token
        self._unexpected_error = unexpected_error
        self.health_calls = 0
        self.token_calls = 0

    def health_check(self):
        self.health_calls += 1
        if self._unexpected_error is not None:
            raise self._unexpected_error
        provider = importlib.import_module(
            "qq_chat_analyzer.providers.qq_chat_exporter_provider"
        )
        if not self._running:
            return provider.ServiceHealth(available=False)
        return provider.ServiceHealth(
            available=True,
            status="healthy",
            version=self._version or "",
        )

    def resolve_token(self) -> str:
        self.token_calls += 1
        if self._token is None:
            provider = importlib.import_module(
                "qq_chat_analyzer.providers.qq_chat_exporter_provider"
            )
            raise provider.TokenUnavailable()
        return self._token


def _status(**provider_kwargs):
    service = _module().QQConnectionService(_FakeProvider(**provider_kwargs))
    return service.check_status()


# ------------------------------------------------------------ running service


def test_qce_running_and_authenticated_marks_source_available() -> None:
    status = _status(running=True, token="fictional-token", version="4.2.0")

    assert status.available is True
    assert status.qce_running is True
    assert status.authenticated is True
    assert status.version == "4.2.0"
    assert status.message != ""
    assert status.action_hint != ""


# -------------------------------------------------------------- stopped service


def test_qce_not_running_returns_user_facing_message() -> None:
    status = _status(running=False, token="fictional-token")

    assert status.available is False
    assert status.qce_running is False
    assert status.authenticated is True
    assert status.version is None
    assert "QQChatExporter" not in status.message
    assert status.message != ""
    assert status.action_hint != ""


# ------------------------------------------------------------ missing token


def test_missing_token_requests_initialization() -> None:
    status = _status(running=True, token=None)

    assert status.available is False
    assert status.qce_running is True
    assert status.authenticated is False
    assert "QQChatExporter" not in status.message
    assert status.message != ""
    assert status.action_hint != ""


def test_missing_token_works_even_when_service_is_stopped() -> None:
    status = _status(running=False, token=None)

    assert status.available is False
    assert status.qce_running is False
    assert status.authenticated is False
    assert status.message != ""


# ------------------------------------------------------------ error isolation


def test_unexpected_provider_exception_never_leaks() -> None:
    status = _status(
        unexpected_error=RuntimeError("internal token endpoint exploded")
    )

    assert status.available is False
    assert status.qce_running is False
    assert status.authenticated is False
    assert "internal token endpoint exploded" not in status.message
    assert "Traceback" not in status.message
    assert "Exception" not in status.message
    assert status.action_hint != ""


def test_status_is_a_frozen_dataclass() -> None:
    module = _module()
    status = module.QQConnectionStatus(
        available=True,
        qce_running=True,
        authenticated=True,
        version="4.1.0",
        message="\u53ef\u7528",
        action_hint="\u5f00\u59cb\u5206\u6790",
    )

    try:
        status.message = "changed"
    except Exception as error:
        assert type(error).__name__ == "FrozenInstanceError"
    else:  # pragma: no cover - guards the immutability contract
        raise AssertionError("QQConnectionStatus should be immutable")


def test_service_calls_health_check_and_token_resolution() -> None:
    provider = _FakeProvider(running=True, token="fictional-token")
    service = _module().QQConnectionService(provider)

    service.check_status()

    assert provider.health_calls == 1
    assert provider.token_calls == 1
