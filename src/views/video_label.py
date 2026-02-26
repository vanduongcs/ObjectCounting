"""
Video Label: Widget hiển thị video và hỗ trợ vẽ vạch ảo.

- Kế thừa QLabel để hiển thị ảnh.
- Hỗ trợ các sự kiện chuột (Press, Move, Release) để vẽ đường thẳng.
"""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPen


class VideoLabel(QLabel):
    # Signal bắn ra khi vẽ xong: trả về tọa độ (start_point, end_point)
    line_drawn_signal = pyqtSignal(tuple, tuple)

    def __init__(self, parent=None):
        """Khởi tạo widget hiển thị video."""
        super().__init__(parent)
        
        self.drawing_mode = False   # Trạng thái đang vẽ
        self.start_point = None     # Điểm click ban đầu
        self.current_point = None   # Điểm chuột hiện tại (khi đang kéo)

        # Cấu hình UI: Căn giữa, màu nền tối, kích thước cố định
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #222; color: #EEE; font-size: 20px;")
        self.setFixedSize(800, 600)

    def enable_drawing(self, enable=True):
        """Bật/tắt chế độ vẽ."""
        self.drawing_mode = enable
        if enable:
            self.start_point = None
            self.current_point = None

    # --- XỬ LÝ SỰ KIỆN CHUỘT ---

    def mousePressEvent(self, event):
        """Khi click chuột trái: Bắt đầu vẽ."""
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.current_point = event.pos()
            self.update()  # Trigger vẽ lại

    def mouseMoveEvent(self, event):
        """Khi di chuyển chuột: Cập nhật đường vẽ tạm thời."""
        if self.drawing_mode and self.start_point:
            self.current_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        """Khi thả chuột: Kết thúc vẽ và gửi signal."""
        if self.drawing_mode and event.button() == Qt.MouseButton.LeftButton:
            end_point = event.pos()

            if self.start_point and end_point:
                # Gửi tọa độ 2 điểm về MainWindow
                p1 = (self.start_point.x(), self.start_point.y())
                p2 = (end_point.x(), end_point.y())
                self.line_drawn_signal.emit(p1, p2)

            # Reset trạng thái
            self.drawing_mode = False
            self.start_point = None
            self.current_point = None
            self.update()

    def paintEvent(self, event):
        """Vẽ nội dung lên widget (Video + Đường vẽ tạm)."""
        super().paintEvent(event)  # Vẽ ảnh video trước

        # Vẽ đường nét đứt màu vàng nếu đang kéo chuột
        if self.drawing_mode and self.start_point and self.current_point:
            painter = QPainter(self)
            pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(self.start_point, self.current_point)
            painter.end()
