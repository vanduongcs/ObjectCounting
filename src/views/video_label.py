"""
Video Label: Widget hiển thị video, hỗ trợ vẽ vạch ảo bằng chuột.

Ai gọi module này?
    - MainWindow._build_ui() tạo VideoLabel và đặt vào layout.
    - MainWindow.update_image() gọi setPixmap() để hiển thị frame.
    - MainWindow.start_drawing_line() gọi enable_drawing(True).

Module này gọi ai?
    - Emit line_drawn_signal(p1, p2) -> MainWindow.handle_line_drawn() xử lý.

Luồng vẽ vạch ảo:
    User bấm "Vẽ vạch ảo" -> enable_drawing(True)
    User kéo chuột        -> paintEvent vẽ đường dash vàng
    User thả chuột        -> emit line_drawn_signal(p1, p2)
    MainWindow             -> calculate_virtual_line() -> lưu vạch ảo
"""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen


class VideoLabel(QLabel):
    line_drawn_signal = pyqtSignal(tuple, tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drawing_mode = False
        self.start_point = None
        self.current_point = None

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #222; color: #EEE; font-size: 20px;")
        self.setMinimumSize(800, 600)

    def enable_drawing(self, enable=True):
        self.drawing_mode = enable
        if enable:
            self.start_point = None
            self.current_point = None

    # --- Mouse Events ---

    def mousePressEvent(self, event):
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.current_point = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self.drawing_mode and self.start_point:
            self.current_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            end_point = event.pos()
            if self.start_point and end_point:
                p1 = (self.start_point.x(), self.start_point.y())
                p2 = (end_point.x(), end_point.y())
                self.line_drawn_signal.emit(p1, p2)

            self.drawing_mode = False
            self.start_point = None
            self.current_point = None
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.drawing_mode and self.start_point and self.current_point:
            painter = QPainter(self)
            painter.setPen(QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine))
            painter.drawLine(self.start_point, self.current_point)
            painter.end()
