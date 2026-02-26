"""
Qt Helpers: Các tiện ích chuyển đổi dữ liệu giữa OpenCV và PyQt.
"""

import cv2
import numpy as np
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap


class QtDisplayAdapter(QObject):
    """
    Adapter giúp gửi frame từ Background Thread (AI) sang Main Thread (UI).
    Sử dụng Qt Signal để đảm bảo thread-safe.
    """
    frame_signal = pyqtSignal(np.ndarray)
    count_signal = pyqtSignal(dict, dict)  # Signal gửi (count_nhap, count_xuat)

    def show(self, frame):
        """Bắn signal chứa frame ảnh về UI."""
        if frame is not None:
            self.frame_signal.emit(frame)
        return True

    def emit_counts(self, count_nhap, count_xuat):
        """Bắn signal chứa thông tin đếm về UI."""
        self.count_signal.emit(count_nhap, count_xuat)

    def close(self):
        pass


def convert_cv_to_qt(cv_img, target_width=800, target_height=600):
    """
    Chuyển đổi ảnh OpenCV (BGR) sang QPixmap (RGB) để hiển thị lên QLabel.
    Tự động scale ảnh về kích thước mong muốn.
    """
    # Chuyển BGR -> RGB
    rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_img.shape
    bytes_per_line = ch * w

    # Tạo QImage từ dữ liệu numpy
    qt_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

    # Scale ảnh nếu cần
    if target_width and target_height:
        scaled = qt_img.scaled(
            target_width, target_height,
            Qt.AspectRatioMode.KeepAspectRatio
        )
        return QPixmap.fromImage(scaled)

    return QPixmap.fromImage(qt_img)
