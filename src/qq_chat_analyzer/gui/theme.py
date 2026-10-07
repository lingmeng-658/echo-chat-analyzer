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

# v0 Home OKLCH colors converted to sRGB. Scope these to Home so the
# established workspace/report palette is unaffected by this visual refresh.
HOME_COLOR_PAPER = "#f8f5ed"
HOME_COLOR_LEAF = "#f1ece4"
HOME_COLOR_TEXT = "#1d1a17"
HOME_COLOR_MUTED = "#69625d"
HOME_COLOR_ACCENT = "#a75e41"
HOME_QSS = f"""
QWidget#echoHome, QWidget#echoHome QWidget {{
    font-family: "Noto Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 13px;
    font-weight: 400;
    color: {HOME_COLOR_TEXT};
    background: transparent;
    border: none;
    border-radius: 0;
}}
QWidget#echoHome {{ background: {HOME_COLOR_PAPER}; }}
QWidget#echoHome QFrame#homeBrand {{ background: {HOME_COLOR_LEAF}; }}
QWidget#echoHome QFrame#homeContent {{ border-left: 1px solid #eeebe3; }}
QWidget#echoHome QLabel#homeTitle {{
    font-family: {SERIF_FAMILY};
    font-size: 48px;
    font-weight: 500;
}}
QWidget#echoHome QLabel#homeEnglish,
QWidget#echoHome QLabel#homeSourceDescription {{ color: {HOME_COLOR_MUTED}; }}
QWidget#echoHome QLabel#homeDescription {{ color: #524f4a; }}
QWidget#echoHome QLabel#homePrivacy {{ font-size: 12px; color: {HOME_COLOR_MUTED}; }}
QWidget#echoHome QLabel#homeSourceName {{ font-size: 24px; font-weight: 500; }}
QWidget#echoHome QFrame#homeRule {{ background: #e2dfd8; }}
QWidget#echoHome QPushButton {{
    color: {HOME_COLOR_ACCENT};
    background: transparent;
    border: none;
    border-radius: 0;
    outline: none;
    padding: 6px 4px;
}}
QWidget#echoHome QPushButton:hover,
QWidget#echoHome QPushButton:focus {{
    color: {HOME_COLOR_ACCENT};
    text-decoration: underline;
}}
QWidget#echoHome QPushButton:pressed {{ color: {HOME_COLOR_TEXT}; }}
QWidget#echoHome QPushButton#homeReports {{ font-size: 12px; color: {HOME_COLOR_MUTED}; }}
QWidget#echoHome QPushButton#homeReports:hover {{ color: {HOME_COLOR_TEXT}; text-decoration: none; }}
QWidget#echoHome QPushButton#homeReports:focus {{ color: {HOME_COLOR_ACCENT}; text-decoration: underline; }}
"""

def paint_echo_note(painter) -> None:
    """Draw Home's terracotta note mark inside a 16 x 24 local box.

    Shared so the guided setup's current-stage mark is literally the same
    musical mark Home draws, instead of a second hand-tuned copy.
    """
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QPainterPath, QPen

    color = QColor(HOME_COLOR_ACCENT)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.save()
    painter.translate(4.6, 19.4)
    painter.rotate(-20)
    painter.drawEllipse(QRectF(-3.6, -2.6, 7.2, 5.2))
    painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path = QPainterPath()
    path.moveTo(7.9, 18.4)
    path.lineTo(7.9, 2.5)
    path.cubicTo(8.5, 4.9, 10.3, 6.1, 12.1, 7.3)
    path.cubicTo(13.5, 8.3, 13.7, 10.1, 12.9, 11.7)
    painter.drawPath(path)


# Guided setup shares Home's paper, ink and link colors. Keep these scoped
# so session controls and other workspaces retain their existing presentation.
WECHAT_GUIDE_STYLE = f"""
QLabel {{
    background: transparent; border: none; padding: 0;
    color: {HOME_COLOR_MUTED}; font-size: 13px; font-weight: 400;
}}
QLabel#wechatCurrentAction {{
    color: {HOME_COLOR_TEXT}; font-size: 26px; font-weight: 500;
}}
QLabel#wechatPrivacy {{ font-size: 12px; }}
"""
WECHAT_GUIDE_STYLE_EMPHASIS = WECHAT_GUIDE_STYLE + f"""
QLabel {{ color: {HOME_COLOR_ACCENT}; }}
"""
WECHAT_STATUS_STYLE = f"""
color: {HOME_COLOR_MUTED}; background: transparent;
border: none; border-bottom: 1px solid {COLOR_RULE_SOFT};
border-radius: 0; padding: 0 0 16px 0;
"""

# Guided setup's five-stage trail: a hairline connecting a filled dot per
# finished stage, Home's terracotta note for the current stage, and a soft
# hollow ring for the stages still ahead.
WECHAT_TRACK_DONE = HOME_COLOR_MUTED
WECHAT_TRACK_PENDING = "#c7c0b4"
WECHAT_TRACK_LINE = COLOR_RULE_SOFT
WECHAT_TRACK_LABEL = COLOR_FAINT
WECHAT_TRACK_LABEL_CURRENT = HOME_COLOR_MUTED
WECHAT_TRACK_COUNTER = COLOR_FAINT
WECHAT_SETUP_QSS = f"""
QWidget#wechatWorkspace, QDialog#wechatSetupDialog {{ background: {HOME_COLOR_PAPER}; }}
QWidget#wechatSessionPanel, QFrame#wechatConnectionSurface {{ background: transparent; }}
QFrame#wechatConnectionSurface QWidget, QDialog#wechatSetupDialog QWidget {{
    font-family: "Noto Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    color: {HOME_COLOR_TEXT}; background: transparent;
}}
QFrame#wechatConnectionSurface QPushButton, QDialog#wechatSetupDialog QPushButton {{
    border: 1px solid {COLOR_BORDER}; border-radius: 0;
    background: transparent; padding: 8px 20px;
}}
QFrame#wechatConnectionSurface QPushButton:hover,
QFrame#wechatConnectionSurface QPushButton:focus,
QDialog#wechatSetupDialog QPushButton:hover,
QDialog#wechatSetupDialog QPushButton:focus {{
    border-color: {HOME_COLOR_ACCENT}; color: {HOME_COLOR_ACCENT};
    background: {HOME_COLOR_LEAF};
}}
QFrame#wechatConnectionSurface QPushButton#wechatSettings {{
    color: {HOME_COLOR_MUTED}; border: none; padding: 8px 0;
}}
QFrame#wechatConnectionSurface QPushButton#wechatSettings:hover,
QFrame#wechatConnectionSurface QPushButton#wechatSettings:focus {{
    color: {HOME_COLOR_ACCENT}; background: transparent; text-decoration: underline;
}}
QDialog#wechatSetupDialog QLabel {{ color: {HOME_COLOR_MUTED}; }}
QDialog#wechatSetupDialog QLineEdit, QDialog#wechatSetupDialog QComboBox {{
    background: {HOME_COLOR_LEAF}; border: 1px solid {COLOR_BORDER};
    border-radius: 0; padding: 8px;
}}
QDialog#wechatSetupDialog QLineEdit:focus, QDialog#wechatSetupDialog QComboBox:focus {{
    border-color: {HOME_COLOR_ACCENT};
}}
QDialog#wechatSetupDialog QPushButton#wechatSave {{
    color: {HOME_COLOR_ACCENT}; border-color: {HOME_COLOR_ACCENT};
}}
"""

WINDOW_CLIENT_SEPARATOR_STYLE = (
    f"QFrame#echoClientSeparator {{ background: {COLOR_RULE_SOFT}; border: none; }}"
)
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
    "HOME_COLOR_ACCENT",
    "HOME_COLOR_LEAF",
    "HOME_COLOR_MUTED",
    "HOME_COLOR_PAPER",
    "HOME_COLOR_TEXT",
    "HOME_QSS",
    "METRIC_CARD_STYLE",
    "SERIF_FAMILY",
    "SESSION_LIST_STYLE",
    "STATUS_STYLE_BASE",
    "STATUS_STYLE_ERROR",
    "WINDOW_TITLE_STYLE",
    "WINDOW_CLIENT_SEPARATOR_STYLE",
    "WECHAT_GUIDE_STYLE",
    "WECHAT_GUIDE_STYLE_EMPHASIS",
    "WECHAT_STATUS_STYLE",
    "WECHAT_SETUP_QSS",
    "WECHAT_TRACK_COUNTER",
    "WECHAT_TRACK_DONE",
    "WECHAT_TRACK_LABEL",
    "WECHAT_TRACK_LABEL_CURRENT",
    "WECHAT_TRACK_LINE",
    "WECHAT_TRACK_PENDING",
    "paint_echo_note",
]
