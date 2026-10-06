"""Native Qt translation of the Echo v0 landing page."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import HOME_COLOR_ACCENT, HOME_QSS


class _EchoNote(QWidget):
    """The reference's small musical mark, drawn in device-independent units."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 24)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(HOME_COLOR_ACCENT)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.save()
        painter.translate(4.6, 19.4)
        painter.rotate(-20)
        painter.drawEllipse(QRectF(-3.6, -2.6, 7.2, 5.2))
        painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        path.moveTo(7.9, 18.4)
        path.lineTo(7.9, 2.5)
        path.cubicTo(8.5, 4.9, 10.3, 6.1, 12.1, 7.3)
        path.cubicTo(13.5, 8.3, 13.7, 10.1, 12.9, 11.7)
        painter.drawPath(path)


class HomePage(QWidget):
    """Brand panel, two source links, and the existing local-report entry."""

    navigate_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("echoHome")
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._brand = QFrame()
        self._brand.setObjectName("homeBrand")
        self._brand_layout = QVBoxLayout(self._brand)
        self._brand_layout.setSpacing(0)
        layout.addWidget(self._brand)

        self._brand_layout.addWidget(_EchoNote(self._brand))
        self._brand_layout.addSpacing(24)
        title = QLabel("余音")
        title.setObjectName("homeTitle")
        title_font = title.font()
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.92)
        title.setFont(title_font)
        title.setFixedHeight(58)  # Allow the serif's ascenders within Qt's line box.
        self._brand_layout.addWidget(title)
        self._brand_layout.addSpacing(6)

        english = QLabel("Echo")
        english.setObjectName("homeEnglish")
        english_font = english.font()
        english_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.04)
        english.setFont(english_font)
        english.setFixedHeight(20)
        self._brand_layout.addWidget(english)
        self._brand_layout.addSpacing(64)

        description = QLabel(
            '<p style="line-height:26px">'
            '把 QQ 与微信的聊天记录，整理成一份可以慢慢回看的报告。</p>'
        )
        description.setObjectName("homeDescription")
        description.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        description.setMaximumWidth(200)
        description.setWordWrap(True)
        self._description = description
        self._brand_layout.addWidget(description)
        self._brand_layout.addStretch(1)

        privacy = QLabel("本地读取 · 不上传")
        privacy.setObjectName("homePrivacy")
        privacy.setFixedHeight(23)
        self._brand_layout.addWidget(privacy)

        self._content = QFrame()
        self._content.setObjectName("homeContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content, 1)

        self._sources = QWidget()
        self._sources.setAccessibleName("选择聊天来源")
        self._sources.setMaximumWidth(480)
        source_layout = QVBoxLayout(self._sources)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(0)
        self._add_rule(source_layout)
        self._qq_btn = self._add_source(source_layout, "QQ", "qq")
        self._add_rule(source_layout)
        self._wechat_btn = self._add_source(source_layout, "微信", "wechat")
        self._add_rule(source_layout)
        self._content_layout.addWidget(self._sources)
        self._content_layout.addStretch(1)

        self._local_data_btn = self._link("查看本地报告  →", "查看本地报告", "local_data")
        self._local_data_btn.setObjectName("homeReports")
        self._content_layout.addWidget(self._local_data_btn, alignment=Qt.AlignRight)
        QWidget.setTabOrder(self._qq_btn, self._wechat_btn)
        QWidget.setTabOrder(self._wechat_btn, self._local_data_btn)
        self.setStyleSheet(HOME_QSS)
        self._update_spacing()

    @staticmethod
    def _add_rule(layout: QVBoxLayout) -> None:
        rule = QFrame()
        rule.setObjectName("homeRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)

    def _add_source(self, layout: QVBoxLayout, name: str, intent: str) -> QPushButton:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 24, 0, 24)
        row_layout.setSpacing(24)
        title = QLabel(name)
        title.setObjectName("homeSourceName")
        title.setFixedWidth(56)
        row_layout.addWidget(title, alignment=Qt.AlignBaseline)
        description = QLabel(
            "读取本机 QQ 的聊天记录" if intent == "qq" else "读取本机微信的聊天记录"
        )
        description.setObjectName("homeSourceDescription")
        row_layout.addWidget(description, stretch=1, alignment=Qt.AlignBaseline)
        button = self._link("开始  →", f"从{name}开始", intent)
        row_layout.addWidget(button, alignment=Qt.AlignBaseline)
        layout.addWidget(row)
        return button

    def _link(self, text: str, accessible_name: str, intent: str) -> QPushButton:
        button = QPushButton(text)
        button.setAccessibleName(accessible_name)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.clicked.connect(lambda: self.navigate_requested.emit(intent))
        return button

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_spacing()

    def _update_spacing(self) -> None:
        # v0 uses a 1200 x 728 content area below its title bar. Keep its
        # proportions at that size; contract gutters (not type) on small windows.
        horizontal = min(1.0, self.width() / 1200)
        vertical = min(1.0, self.height() / 728)
        self._brand.setFixedWidth(round(self.width() * 0.37))
        self._brand_layout.setContentsMargins(
            round(104 * horizontal), round(150 * vertical),
            round(64 * horizontal), round(56 * vertical),
        )
        margins = self._brand_layout.contentsMargins()
        description_width = min(
            200, max(1, self._brand.width() - margins.left() - margins.right())
        )
        # QLabel's rich-text size hint can retain the wider, two-line height.
        # Measure the actual column so a third line survives at minimum width.
        self._description.setFixedHeight(
            self._description.heightForWidth(description_width)
        )
        # The source list has -28px top margin inside the reference's 176px inset.
        self._content_layout.setContentsMargins(
            round(128 * horizontal), round(148 * vertical),
            round(96 * horizontal), round(56 * vertical),
        )
