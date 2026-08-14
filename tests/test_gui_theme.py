"""Theme token consistency tests for the desktop GUI."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.gui import theme


def test_error_status_style_uses_shared_error_color() -> None:
    assert theme.COLOR_ERROR in theme.STATUS_STYLE_ERROR
    assert theme.COLOR_ERROR in theme.GUIDE_STYLE_EMPHASIS


def test_normal_status_style_keeps_palette_background() -> None:
    assert "palette(alternate-base)" in theme.STATUS_STYLE_BASE
    assert "palette(alternate-base)" in theme.GUIDE_STYLE


def test_base_qss_covers_core_widget_selectors() -> None:
    for selector in (
        "QPushButton",
        "QGroupBox",
        "QLineEdit",
        "QComboBox",
        "QDateEdit",
        "QTableWidget",
        "QListWidget",
        "QHeaderView::section",
        "QDialog",
    ):
        assert selector in theme.BASE_QSS


def test_gui_pages_use_shared_theme_styles() -> None:
    gui_dir = SRC_ROOT / "qq_chat_analyzer" / "gui"
    names = (
        "analysis_page.py",
        "qq_workspace.py",
        "wechat_workspace.py",
        "local_data_page.py",
        "home_page.py",
        "main_window.py",
        "dashboard_page.py",
    )
    for name in names:
        source = (gui_dir / name).read_text(encoding="utf-8")
        assert "from .theme import" in source, f"{name} still inlines theme styles"
