"""Development-only verification of the GUI WeChat connect closed loop.

Usage:
    python scripts/verify_wechat_connect_flow.py
    python scripts/verify_wechat_connect_flow.py --data-root "D:\\xwechat_files"
    python scripts/verify_wechat_connect_flow.py --dry-run

This drives the *real* facade through exactly the path the GUI button uses:

    detect_wechat_data_root -> setup_wechat_environment -> get_connection_status
    -> list_sessions

It never opens a window, never prints chat content, never prints the database
key, and never prints raw account identifiers. Only counts and states are
shown, so the output is safe to paste into an issue.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
os.environ.setdefault(
    "MPLCONFIGDIR",
    str(PROJECT_ROOT / "build" / "matplotlib-config"),
)
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application.facade import (  # noqa: E402
    ChatSource,
    FacadeError,
    WeChatEnvironmentConfig,
)


OK = "[ OK ]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def _print_step(marker: str, text: str) -> None:
    print(f"{marker} {text}", flush=True)


def _build_facade():
    """Build the same facade the desktop app composes at startup."""
    from qq_chat_analyzer.gui.app import build_facade

    return build_facade()


def verify(
    *,
    data_root: Path | None,
    dry_run: bool,
    limit: int,
) -> int:
    """Run the connect closed loop and report each stage."""
    print("=" * 62)
    print("WeChat connect closed-loop verification")
    print("=" * 62)

    try:
        facade = _build_facade()
    except Exception as error:
        _print_step(FAIL, f"build facade: {type(error).__name__}")
        return 1
    _print_step(OK, "facade composed")

    # --- Step 1: the same detection the button performs -----------------
    detected = data_root
    if detected is None:
        try:
            detected = facade.detect_wechat_data_root()
        except Exception as error:
            _print_step(FAIL, f"detect data root: {type(error).__name__}")
            return 1

    if detected is None:
        _print_step(
            FAIL,
            "no WeChat data directory detected; "
            "rerun with --data-root <path> (GUI would open the dialog here)",
        )
        return 1

    detected = Path(detected)
    _print_step(OK, f"data root detected (exists={detected.is_dir()})")
    print(f"       name: {detected.name}")

    if dry_run:
        _print_step(SKIP, "--dry-run set: stopping before key acquisition")
        return 0

    # --- Step 2: setup + key acquisition (blocks until login) ----------
    print()
    print("Keep WeChat running and logged in. Acquiring key may take a while...")
    config = WeChatEnvironmentConfig(data_root=detected)
    try:
        facade.setup_wechat_environment(config)
    except FacadeError as error:
        _print_step(FAIL, f"setup_wechat_environment: {error.code}")
        print(f"       message: {error.public_message}")
        return 1
    except Exception as error:
        _print_step(FAIL, f"setup_wechat_environment: {type(error).__name__}")
        return 1
    _print_step(OK, "environment saved and key acquired")

    # --- Step 3: connection status the GUI renders ---------------------
    try:
        status = facade.get_connection_status(ChatSource.WECHAT)
    except FacadeError as error:
        _print_step(FAIL, f"get_connection_status: {error.code}")
        print(f"       message: {error.public_message}")
        return 1
    _print_step(
        OK if status.available else FAIL,
        f"connection available={status.available} "
        f"data={status.data_found} key={status.db_key_available} "
        f"runtime={status.runtime_available}",
    )
    print(f"       message: {status.message}")
    if not status.available:
        print(f"       hint: {status.action_hint}")
        return 1

    # --- Step 4: sessions load, same as the GUI list -------------------
    try:
        sessions = facade.list_sessions(ChatSource.WECHAT)
    except FacadeError as error:
        _print_step(FAIL, f"list_sessions: {error.code}")
        print(f"       message: {error.public_message}")
        return 1
    _print_step(OK, f"sessions loaded: {len(sessions)}")

    if not sessions:
        _print_step(FAIL, "no sessions returned; nothing to analyze")
        return 1

    # Privacy: show only counts and a masked ordinal, never names or ids.
    shown = min(limit, len(sessions))
    for index in range(shown):
        session = sessions[index]
        count = session.message_count
        count_text = "unknown" if count is None else str(count)
        print(f"       session #{index + 1}: messages={count_text}")

    print()
    print("=" * 62)
    print("RESULT: closed loop OK - GUI can connect and list sessions.")
    print("=" * 62)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_wechat_connect_flow",
        description="Verify the GUI WeChat connect closed loop on real data.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Override the detected WeChat data directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only test detection; do not acquire the key or read data.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="How many sessions to summarize (counts only).",
    )
    args = parser.parse_args(argv)
    return verify(
        data_root=args.data_root,
        dry_run=args.dry_run,
        limit=max(0, args.limit),
    )


if __name__ == "__main__":
    raise SystemExit(main())
