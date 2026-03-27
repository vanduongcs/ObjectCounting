"""Video preview widget with line/ROI drawing support."""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen

import configs.settings_interface as ui_settings


class VideoLabel(QLabel):
    line_drawn_signal = pyqtSignal(tuple, tuple)
    roi_drawn_signal = pyqtSignal(tuple, tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drawing_mode = None
        self.start_point = None
        self.current_point = None

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setObjectName("videoCanvas")
        self.setMinimumSize(
            ui_settings.VIDEO_CANVAS_MIN_WIDTH,
            ui_settings.VIDEO_CANVAS_MIN_HEIGHT,
        )
        self.setMouseTracking(True)

    def enable_drawing(self, enable=True, mode="line"):
        self.drawing_mode = mode if enable else None
        self._reset_drawing()
        self.setCursor(
            Qt.CursorShape.CrossCursor if enable else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def _reset_drawing(self):
        self.start_point = None
        self.current_point = None

    def mousePressEvent(self, event):
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.current_point = event.pos()
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_mode and self.start_point:
            self.current_point = event.pos()
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            end_point = event.pos()
            if self.start_point and end_point:
                p1 = (self.start_point.x(), self.start_point.y())
                p2 = (end_point.x(), end_point.y())
                if self.drawing_mode == "roi":
                    self.roi_drawn_signal.emit(p1, p2)
                else:
                    self.line_drawn_signal.emit(p1, p2)

            self.drawing_mode = None
            self._reset_drawing()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            return
        super().mouseReleaseEvent(event)

    def _draw_preview_shape(self, painter):
        pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if self.drawing_mode == "roi":
            x1 = self.start_point.x()
            y1 = self.start_point.y()
            x2 = self.current_point.x()
            y2 = self.current_point.y()
            painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            return
        painter.drawLine(self.start_point, self.current_point)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drawing_mode and self.start_point and self.current_point:
            painter = QPainter(self)
            self._draw_preview_shape(painter)
            painter.end()
