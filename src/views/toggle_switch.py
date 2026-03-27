"""Compact ON/OFF switch used by the light UI."""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox

import configs.settings_interface as ui_settings
import configs.settings_theme as theme_settings


class ToggleSwitch(QCheckBox):
    """Small painted switch with inline ON/OFF labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setText("")
        self.setFixedSize(
            ui_settings.TOGGLE_SWITCH_WIDTH,
            ui_settings.TOGGLE_SWITCH_HEIGHT,
        )

    def sizeHint(self):
        return QSize(
            ui_settings.TOGGLE_SWITCH_WIDTH,
            ui_settings.TOGGLE_SWITCH_HEIGHT,
        )

    def hitButton(self, pos):
        """Make the whole painted switch clickable, not just the default checkbox hit area."""
        return self.rect().contains(pos)

    def paintEvent(self, event):
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        is_on = self.isChecked()
        track_color = QColor(
            theme_settings.TOGGLE_TRACK_ON_COLOR
            if is_on
            else theme_settings.TOGGLE_TRACK_OFF_COLOR
        )
        border_color = QColor(
            theme_settings.TOGGLE_TRACK_ON_COLOR
            if is_on
            else theme_settings.TOGGLE_TRACK_OFF_COLOR
        )
        label = (
            ui_settings.TOGGLE_SWITCH_ON_LABEL
            if is_on
            else ui_settings.TOGGLE_SWITCH_OFF_LABEL
        )

        painter.setPen(QPen(border_color, ui_settings.TOGGLE_SWITCH_BORDER_WIDTH))
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        thumb_size = rect.height() - 6
        thumb_x = (
            rect.right() - thumb_size - 3
            if is_on
            else rect.left() + 3
        )
        thumb_rect = QRectF(thumb_x, rect.top() + 3, thumb_size, thumb_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme_settings.TOGGLE_THUMB_COLOR))
        painter.drawEllipse(thumb_rect)

        font = painter.font()
        font.setPixelSize(ui_settings.TOGGLE_SWITCH_LABEL_PIXEL_SIZE)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(
            QColor(
                theme_settings.TOGGLE_TEXT_ON_COLOR
                if is_on
                else theme_settings.TOGGLE_TEXT_OFF_COLOR
            )
        )
        text_rect = rect.adjusted(8, 0, -8, 0)
        alignment = (
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            if is_on
            else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        )
        painter.drawText(text_rect, alignment, label)
        painter.end()
