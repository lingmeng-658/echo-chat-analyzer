"""Shared visual tokens and the base stylesheet for the desktop GUI.

The palette follows the Echo Report paper language: warm near-white surfaces,
ink text, muted gray-brown secondary text, and restrained brown accent.
"""

from __future__ import annotations


# ---- color tokens -----------------------------------------------------------

COLOR_CANVAS = "#e5e0d6"
COLOR_PAPER = "#fbf9f4"
COLOR_PAPER_ALT = "#f2ede3"
COLOR_BORDER = "#d8d2c8"
COLOR_RULE_SOFT = "#e4dfd5"
COLOR_TEXT = "#292720"
COLOR_MUTED = "#716b61"
COLOR_FAINT = "#aaa398"
COLOR_ACCENT = "#9b5b45"
COLOR_ACCENT_DARK = "#7c4c3a"
COLOR_ACCENT_SOFT = "#e8d6ca"
COLOR_VIEWER = "#527066"
COLOR_VIEWER_SOFT = "#e2ebe5"
COLOR_ERROR = "#c2410c"


# ---- font tokens ------------------------------------------------------------

FONT_FAMILY = '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif'
SERIF_FAMILY = '"Noto Serif SC", "Songti SC", SimSun, serif'

FONT_SIZE_BODY = "13px"
FONT_SIZE_SMALL = "12px"
FONT_SIZE_TITLE = "18px"
FONT_SIZE_HOME_TITLE = "24px"
FONT_SIZE_DASHBOARD_TITLE = "16px"


# ---- shared widget styles ---------------------------------------------------

STATUS_STYLE_BASE = (
    "padding: 8px 10px; border-radius: 6px; "
    "background: palette(alternate-base);"
)
STATUS_STYLE_ERROR = (
    "padding: 8px 10px; border-radius: 6px; "
    "background: palette(alternate-base); "
    f"color: {COLOR_ERROR}; font-weight: 600;"
)
GUIDE_STYLE = (
    "padding: 10px; border-radius: 6px; "
    "background: palette(alternate-base);"
)
GUIDE_STYLE_EMPHASIS = (
    "padding: 10px; border-radius: 6px; "
    "background: palette(alternate-base); "
    f"color: {COLOR_ERROR}; font-weight: 600;"
)

HOME_TITLE_STYLE = f"font-size: {FONT_SIZE_HOME_TITLE}; font-weight: 600;"
HOME_SUBTITLE_STYLE = f"font-size: 14px; color: {COLOR_MUTED};"
WINDOW_TITLE_STYLE = f"font-size: {FONT_SIZE_TITLE}; font-weight: 600;"
DASHBOARD_TITLE_STYLE = (
    f"font-size: {FONT_SIZE_DASHBOARD_TITLE}; font-weight: 600;"
)
EMPTY_TEXT_STYLE = f"color: {COLOR_MUTED};"
METRIC_CARD_STYLE = f"border: 1px solid {COLOR_RULE_SOFT}; padding: 8px;"

SESSION_LIST_STYLE = (
    "QListWidget { border: none; border-radius: 4px; background: transparent; } "
    "QListWidget::item { border-radius: 3px; padding: 4px 6px; } "
    f"QListWidget::item:hover {{ background: {COLOR_PAPER_ALT}; }} "
    f"QListWidget::item:selected {{ background: {COLOR_ACCENT_SOFT}; "
    f"color: {COLOR_TEXT}; }}"
)


# ---- application-wide stylesheet --------------------------------------------

BASE_QSS = f"""
QMainWindow, QDialog {{
    background: {COLOR_CANVAS};
}}

QWidget {{
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BODY};
    color: {COLOR_TEXT};
    background: {COLOR_CANVAS};
}}

QGroupBox {{
    background: {COLOR_PAPER};
    border: 1px solid {COLOR_RULE_SOFT};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {COLOR_TEXT};
}}

QPushButton {{
    background: {COLOR_PAPER};
    border: 1px solid {COLOR_RULE_SOFT};
    border-radius: 4px;
    padding: 6px 14px;
    color: {COLOR_TEXT};
}}

QPushButton:hover {{
    background: {COLOR_PAPER_ALT};
    border-color: {COLOR_BORDER};
}}

QPushButton:pressed {{
    background: {COLOR_PAPER_ALT};
    border-color: {COLOR_BORDER};
}}

QPushButton:checked {{
    background: {COLOR_ACCENT_SOFT};
    border-color: {COLOR_ACCENT};
    color: {COLOR_ACCENT_DARK};
}}

QPushButton:disabled {{
    background: transparent;
    border-color: {COLOR_RULE_SOFT};
    color: {COLOR_FAINT};
}}

QLineEdit, QComboBox, QDateEdit {{
    background: {COLOR_PAPER};
    border: 1px solid {COLOR_RULE_SOFT};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {COLOR_ACCENT_SOFT};
    selection-color: {COLOR_TEXT};
}}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
    border-color: {COLOR_ACCENT};
}}

QComboBox QAbstractItemView {{
    background: {COLOR_PAPER};
    border: 1px solid {COLOR_RULE_SOFT};
    selection-background-color: {COLOR_ACCENT_SOFT};
    selection-color: {COLOR_TEXT};
    outline: 0;
}}

QTableWidget, QListWidget {{
    background: {COLOR_PAPER};
    alternate-background-color: {COLOR_PAPER_ALT};
    border: 1px solid {COLOR_RULE_SOFT};
    border-radius: 4px;
    gridline-color: {COLOR_RULE_SOFT};
}}

QTableWidget::item:selected, QListWidget::item:selected {{
    background: {COLOR_ACCENT_SOFT};
    color: {COLOR_TEXT};
}}

QTableWidget::item:hover, QListWidget::item:hover {{
    background: {COLOR_PAPER_ALT};
}}

QHeaderView::section {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {COLOR_RULE_SOFT};
    padding: 6px;
    color: {COLOR_MUTED};
    font-weight: 600;
}}

QRadioButton::indicator, QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLOR_BORDER};
    background: {COLOR_PAPER};
}}

QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background: {COLOR_ACCENT};
    border-color: {COLOR_ACCENT};
}}

QCalendarWidget QAbstractItemView {{
    background: {COLOR_PAPER};
    selection-background-color: {COLOR_ACCENT_SOFT};
    selection-color: {COLOR_TEXT};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QToolTip {{
    background: {COLOR_PAPER};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_RULE_SOFT};
    padding: 4px 6px;
}}
"""


__all__ = [
    "BASE_QSS",
    "COLOR_ACCENT",
    "COLOR_ACCENT_DARK",
    "COLOR_ACCENT_SOFT",
    "COLOR_BORDER",
    "COLOR_CANVAS",
    "COLOR_ERROR",
    "COLOR_FAINT",
    "COLOR_MUTED",
    "COLOR_PAPER",
    "COLOR_PAPER_ALT",
    "COLOR_RULE_SOFT",
    "COLOR_TEXT",
    "COLOR_VIEWER",
    "COLOR_VIEWER_SOFT",
    "DASHBOARD_TITLE_STYLE",
    "EMPTY_TEXT_STYLE",
    "FONT_FAMILY",
    "FONT_SIZE_BODY",
    "FONT_SIZE_DASHBOARD_TITLE",
    "FONT_SIZE_HOME_TITLE",
    "FONT_SIZE_SMALL",
    "FONT_SIZE_TITLE",
    "GUIDE_STYLE",
    "GUIDE_STYLE_EMPHASIS",
    "HOME_SUBTITLE_STYLE",
    "HOME_TITLE_STYLE",
    "METRIC_CARD_STYLE",
    "SERIF_FAMILY",
    "SESSION_LIST_STYLE",
    "STATUS_STYLE_BASE",
    "STATUS_STYLE_ERROR",
    "WINDOW_TITLE_STYLE",
]
