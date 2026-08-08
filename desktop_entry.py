"""Standalone entry point used by the PyInstaller desktop build.

PyInstaller executes this file as the top-level ``__main__`` script, so it
must not use relative imports. It only re-exports the real GUI entry
function; ``python -m qq_chat_analyzer.gui`` keeps using the package module.
"""

from __future__ import annotations

import sys

from qq_chat_analyzer.gui.app import main


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]

