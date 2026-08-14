"""Read-only rendering of a :class:`DashboardView`.

This page displays values that the presentation layer already formatted. It
never counts, averages, sorts, or re-derives anything: every string it shows
comes straight off the view model.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import DASHBOARD_TITLE_STYLE, METRIC_CARD_STYLE


_EMPTY_TITLE = "\u6682\u65e0\u5206\u6790\u7ed3\u679c"
_DEFAULT_EMPTY_HINT = (
    "\u8fd8\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u6570\u636e\uff0c"
    "\u8bf7\u5148\u8fd0\u884c\u4e00\u6b21\u5206\u6790\u3002"
)
_USER_HEADERS = (
    "#",
    "\u53d1\u8a00\u4eba",
    "\u6d88\u606f\u6570",
    "\u5360\u6bd4",
    "\u5e73\u5747\u957f\u5ea6",
    "\u6d3b\u8dc3\u65f6\u6bb5",
)
_CONVERSATION_HEADERS = (
    "\u4f1a\u8bdd",
    "\u6d88\u606f\u6570",
    "\u53c2\u4e0e\u4eba\u6570",
    "\u65f6\u95f4\u8de8\u5ea6",
)
_TOP_WORDS_CHART_KEY = "top_words"


class DashboardPage(QWidget):
    """Render one dashboard view using plain Qt widgets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.show_empty()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        self._title_label = QLabel("")
        self._title_label.setStyleSheet(DASHBOARD_TITLE_STYLE)
        outer.addWidget(self._title_label)

        self._empty_label = QLabel("")
        self._empty_label.setWordWrap(True)
        outer.addWidget(self._empty_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        self._metrics_box = QGroupBox("\u6982\u89c8")
        self._metrics_layout = QHBoxLayout(self._metrics_box)
        self._content_layout.addWidget(self._metrics_box)

        self._users_box = QGroupBox("\u7528\u6237\u753b\u50cf")
        users_layout = QVBoxLayout(self._users_box)
        self._user_table = QTableWidget(0, len(_USER_HEADERS))
        self._user_table.setHorizontalHeaderLabels(_USER_HEADERS)
        self._user_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._user_table.verticalHeader().setVisible(False)
        self._user_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        users_layout.addWidget(self._user_table)
        self._content_layout.addWidget(self._users_box)

        self._words_box = QGroupBox("\u9ad8\u9891\u8bcd")
        words_layout = QVBoxLayout(self._words_box)
        self._word_list = QListWidget()
        self._word_list.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        words_layout.addWidget(self._word_list)
        self._content_layout.addWidget(self._words_box)

        self._conversations_box = QGroupBox("\u4f1a\u8bdd\u6982\u89c8")
        conversations_layout = QVBoxLayout(self._conversations_box)
        self._conversation_table = QTableWidget(
            0,
            len(_CONVERSATION_HEADERS),
        )
        self._conversation_table.setHorizontalHeaderLabels(
            _CONVERSATION_HEADERS
        )
        self._conversation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._conversation_table.verticalHeader().setVisible(False)
        self._conversation_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        conversations_layout.addWidget(self._conversation_table)
        self._content_layout.addWidget(self._conversations_box)

    # ------------------------------------------------------------- rendering

    def show_empty(self, message: str = _DEFAULT_EMPTY_HINT) -> None:
        """Reset every section and explain that there is nothing to show."""
        self._title_label.setText(_EMPTY_TITLE)
        self._empty_label.setText(message)
        self._empty_label.setVisible(True)
        self._clear_metrics()
        self._user_table.setRowCount(0)
        self._word_list.clear()
        self._conversation_table.setRowCount(0)
        self._set_sections_visible(False)

    def render_view(self, view: Any) -> None:
        """Display one dashboard view exactly as the builder produced it."""
        if view is None:
            self.show_empty()
            return

        self._title_label.setText(view.title)

        if not view.has_data:
            self.show_empty(view.empty_description or _DEFAULT_EMPTY_HINT)
            self._title_label.setText(view.title)
            return

        self._empty_label.setVisible(False)
        self._set_sections_visible(True)
        self._render_metrics(view.summary_metrics)
        self._render_users(view.user_cards)
        self._render_top_words(view.charts)
        self._render_conversations(view.conversation_cards)

    def _render_metrics(self, metrics: Any) -> None:
        self._clear_metrics()
        for metric in metrics or ():
            card = QLabel(f"{metric.title}\n{metric.value}")
            card.setToolTip(metric.description)
            card.setStyleSheet(METRIC_CARD_STYLE)
            self._metrics_layout.addWidget(card)
        self._metrics_box.setVisible(bool(metrics))

    def _render_users(self, user_cards: Any) -> None:
        cards = tuple(user_cards or ())
        self._user_table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            values = (
                str(card.rank),
                card.sender,
                str(card.message_count),
                card.percentage_display,
                card.average_length_display,
                card.active_period,
            )
            for column, value in enumerate(values):
                self._user_table.setItem(row, column, QTableWidgetItem(value))
        self._users_box.setVisible(bool(cards))

    def _render_top_words(self, charts: Any) -> None:
        self._word_list.clear()
        chart = next(
            (
                candidate
                for candidate in charts or ()
                if candidate.key == _TOP_WORDS_CHART_KEY
            ),
            None,
        )
        if chart is not None:
            for series in chart.series:
                for point in series.points:
                    self._word_list.addItem(
                        f"{point.label}\t{int(point.value)}"
                    )
        self._words_box.setVisible(self._word_list.count() > 0)

    def _render_conversations(self, conversation_cards: Any) -> None:
        cards = tuple(conversation_cards or ())
        self._conversation_table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            values = (
                card.conversation_id,
                str(card.message_count),
                str(card.participant_count),
                card.time_span,
            )
            for column, value in enumerate(values):
                self._conversation_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(value),
                )
        self._conversations_box.setVisible(bool(cards))

    # --------------------------------------------------------------- helpers

    def _clear_metrics(self) -> None:
        while self._metrics_layout.count():
            item = self._metrics_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _set_sections_visible(self, visible: bool) -> None:
        self._metrics_box.setVisible(visible)
        self._users_box.setVisible(visible)
        self._words_box.setVisible(visible)
        self._conversations_box.setVisible(visible)