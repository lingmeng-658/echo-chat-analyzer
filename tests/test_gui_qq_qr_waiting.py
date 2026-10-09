"""QQ QR waiting experience: cancel-button release without faking success.

The scan stage deliberately disables "取消连接" while the QR is still loading,
so a stray click during the first moments cannot abort a healthy login. It must
not stay disabled forever: after a bounded wait the user gets the button back,
plus copy that says waiting is still fine.

All data here is fictional; no real QQ client, QR code, or chat data is used.
"""

from __future__ import annotations

import time
from pathlib import Path

from qq_chat_analyzer.gui.qq_workspace import QQWorkspace

from test_gui import (  # noqa: F401  (fixtures are re-exported here for pytest)
    StubFacade,
    _GatedQRFacade,
    _drain,
    _inline_executor,
    _qq_snapshot,
    _write_qrcode_png,
    instant_qq_connect,
    qt_app,
    sources,
)

_LOADING_COPY = "正在加载 QQ 登录二维码，请稍候…"
_READY_COPY = "请使用手机 QQ 扫码登录"
_SLOW_COPY = "二维码加载较慢，你可以继续等待，或取消后重新连接。"


def _enter_waiting_auth(facade) -> QQWorkspace:
    workspace = QQWorkspace(facade, executor=_inline_executor())
    workspace._show_qq_status(_qq_snapshot("waiting_auth"), False)
    return workspace


def _expire_qr_wait(workspace: QQWorkspace) -> None:
    """Move the start stamp back so the bounded wait has already elapsed."""
    workspace._qq_waiting_auth_since = time.monotonic() - 9.0


def test_qr_loading_disables_cancel_and_shows_loading_copy(qt_app, sources) -> None:
    workspace = _enter_waiting_auth(StubFacade(sources=sources))

    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False
    assert workspace._qq_connect_button.isEnabled() is False
    assert workspace._qq_connect_button.text() == "取消连接"
    assert workspace._qq_guide_label.text() == _LOADING_COPY
    assert workspace._qq_qr_wait_timer.isActive() is True


def test_qr_ready_releases_cancel_immediately_with_scan_copy(
    qt_app, sources, tmp_path: Path, instant_qq_connect
) -> None:
    """A QR that arrives early releases the button without waiting out the bound."""
    qr_path = tmp_path / "fictional-qq-qr.png"
    _write_qrcode_png(qr_path)
    facade = _GatedQRFacade(
        _qq_snapshot("waiting_auth"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    facade.qr_ready = True
    facade.qr_path = qr_path
    workspace = QQWorkspace(facade, executor=_inline_executor())

    workspace.connect_qq()
    _drain(workspace)

    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is True
    assert workspace._qq_connect_button.isEnabled() is True
    assert workspace._qq_guide_label.text() == _READY_COPY
    assert workspace._qq_qr_wait_timer.isActive() is False


def test_slow_qr_releases_cancel_without_failing_the_connection(
    qt_app, sources
) -> None:
    """Past the bound the user regains control, but the login is not aborted."""
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    assert workspace._qq_connect_button.isEnabled() is False

    _expire_qr_wait(workspace)
    workspace._on_qq_qr_wait_elapsed()

    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False
    assert workspace._qq_connect_button.isEnabled() is True
    assert workspace._qq_connect_button.text() == "取消连接"
    assert workspace._qq_guide_label.text() == _SLOW_COPY
    assert facade.disconnect_qq_calls == []
    assert workspace._qq_status_timer.isActive() is True


def test_polling_does_not_disable_the_released_cancel_button(
    qt_app, sources
) -> None:
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    _expire_qr_wait(workspace)
    workspace._on_qq_qr_wait_elapsed()
    assert workspace._qq_connect_button.isEnabled() is True

    workspace._show_qq_status(_qq_snapshot("waiting_auth"), False)

    assert workspace._qq_connect_button.isEnabled() is True
    assert workspace._qq_guide_label.text() == _SLOW_COPY


def test_cancel_after_slow_qr_really_disconnects_through_the_facade(
    qt_app, sources
) -> None:
    """The released button must act, not only look enabled."""
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    _expire_qr_wait(workspace)
    workspace._on_qq_qr_wait_elapsed()

    workspace._qq_connect_button.click()

    assert facade.disconnect_qq_calls == [1]
    assert facade.start_qq_auth_flow_calls == []
    assert workspace._qq_status_timer.isActive() is False
    assert workspace._qq_qr_wait_timer.isActive() is False
    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False


def test_qr_wait_timer_stops_when_the_scan_stage_is_left(qt_app, sources) -> None:
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    assert workspace._qq_qr_wait_timer.isActive() is True

    workspace._show_qq_status(_qq_snapshot("connected"), False)

    assert workspace._qq_qr_wait_timer.isActive() is False
    assert workspace._qq_guide_label.isVisibleTo(workspace) is False
    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False


def test_late_qr_wait_callback_does_not_touch_a_new_connection_state(
    qt_app, sources
) -> None:
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    assert workspace._qq_connect_button.isEnabled() is False
    _expire_qr_wait(workspace)

    workspace._show_qq_status(_qq_snapshot("connected"), False)
    connected_enabled = workspace._qq_connect_button.isEnabled()

    workspace._on_qq_qr_wait_elapsed()  # a stale release callback

    assert workspace._qq_connect_button.isEnabled() == connected_enabled
    assert workspace._qq_guide_label.isVisibleTo(workspace) is False
    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False


def test_scan_timeout_still_wins_and_stops_the_release_timer(
    qt_app, sources
) -> None:
    """The existing 120s scan timeout keeps its behaviour and its precedence."""
    facade = StubFacade(sources=sources)
    workspace = _enter_waiting_auth(facade)
    workspace._qq_waiting_auth_since = time.monotonic() - 121.0

    workspace._poll_qq_status()

    assert facade.disconnect_qq_calls == [1]
    assert workspace._qq_connect_button.text() == "重新开始"
    assert workspace._qq_connect_button.isEnabled() is True
    assert workspace._qq_status_timer.isActive() is False
    assert workspace._qq_qr_wait_timer.isActive() is False
    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False
