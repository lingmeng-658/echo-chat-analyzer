"""Shared Echo trail for the connection journeys of every source.

WeChat's guided setup and QQ's connection flow walk the user through the same
kind of staged journey, so they draw the same trail: one hairline threads the
stages together, finished stages carry a small filled dot, the current stage
carries Home's terracotta note, and the stages still ahead stay soft hollow
rings. A restrained ``x / n`` counter sits on the right, and the stage names
stay small so the current action keeps the hierarchy.

A subclass only declares its ``STAGES``; the visual language itself lives here
so no source can drift into its own hand-tuned copy of the trail.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .theme import (
    CONNECTION_TRACK_COUNTER,
    CONNECTION_TRACK_DONE,
    CONNECTION_TRACK_LABEL,
    CONNECTION_TRACK_LABEL_CURRENT,
    CONNECTION_TRACK_LINE,
    CONNECTION_TRACK_PENDING,
    paint_echo_note,
)


CONNECTION_TRACK_HEIGHT = 40


class ConnectionProgressTrack(QWidget):
    """One connection journey drawn in device-independent units."""

    STAGES: tuple[str, ...] = ()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stage = 0
        self.setFixedHeight(CONNECTION_TRACK_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("连接进度")

    @property
    def stage(self) -> int:
        return self._stage

    def set_stage(self, stage: int) -> None:
        self._stage = max(0, min(len(self.STAGES) - 1, int(stage)))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        count = len(self.STAGES)
        counter = f"{self._stage + 1} / {count}"
        counter_width = metrics.horizontalAdvance(counter) + 12
        left = 6.0
        track_width = max(1.0, self.width() - left * 2 - counter_width)
        slot = track_width / count
        dot_y = 15.0
        centers = [left + slot * (index + 0.5) for index in range(count)]

        painter.setPen(QPen(QColor(CONNECTION_TRACK_LINE), 1))
        painter.drawLine(QPointF(centers[0], dot_y), QPointF(centers[-1], dot_y))

        for index, center in enumerate(centers):
            if index < self._stage:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(CONNECTION_TRACK_DONE))
                painter.drawEllipse(QPointF(center, dot_y), 3.0, 3.0)
            elif index == self._stage:
                painter.save()
                painter.translate(center, dot_y)
                painter.scale(0.72, 0.72)
                painter.translate(-4.6, -19.4)
                paint_echo_note(painter)
                painter.restore()
            else:
                painter.setPen(QPen(QColor(CONNECTION_TRACK_PENDING), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(center, dot_y), 3.0, 3.0)

        for index, center in enumerate(centers):
            reached = index <= self._stage
            painter.setPen(
                QColor(
                    CONNECTION_TRACK_LABEL_CURRENT if reached
                    else CONNECTION_TRACK_LABEL
                )
            )
            painter.drawText(
                QRectF(center - slot / 2, 27.0, slot, 13.0),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                self.STAGES[index],
            )

        painter.setPen(QColor(CONNECTION_TRACK_COUNTER))
        painter.drawText(
            QRectF(
                self.width() - counter_width,
                dot_y - 9.0,
                counter_width - 6.0,
                18.0,
            ),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            counter,
        )
