"""
Qt Helpers: Cầu nối thread-safe giữa AI thread và UI thread.

Ai gọi module này?
    - AIService._process_frame() gọi adapter.show() và adapter.emit_counts()
    - MainWindow.update_image() gọi convert_cv_to_qt()

Vấn đề cần giải quyết:
    PyQt6 KHÔNG cho phép cập nhật UI từ thread khác (sẽ crash).
    AIService chạy trên VideoThread (background), nhưng cần gửi frame về MainWindow (UI thread).

Giải pháp:
    QtDisplayAdapter dùng pyqtSignal -- Qt tự động chuyển data sang UI thread.

Luồng dữ liệu:
    AIService (background thread)
        | gọi adapter.show(frame)
        | gọi adapter.emit_counts(nhap, xuat)
    QtDisplayAdapter
        | emit frame_signal / count_signal
    MainWindow (UI thread)
        | nhận signal -> update_image() / update_counter_table()
"""

import cv2
import numpy as np
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

import configs.settings_interface as ui_settings


class QtDisplayAdapter(QObject):
    """
    Adapter chuyển dữ liệu từ AI thread sang UI thread qua Qt Signal.

    Được tạo bởi: main.py
    Được gọi bởi: AIService._process_frame()
    Signal nhận bởi: MainWindow.update_image(), MainWindow.update_counter_table()
    """

    # Signal gửi frame (numpy array) về UI
    frame_signal = pyqtSignal(np.ndarray)

    # Signal gửi kết quả đếm (2 dict: nhập, xuất) về UI
    count_signal = pyqtSignal(dict, dict)

    # Signal gửi FPS realtime về UI
    fps_signal = pyqtSignal(float)

    # Signal báo session/history cần refresh
    session_signal = pyqtSignal()

    def show(self, frame):
        """Gửi frame đã annotate về UI để hiển thị."""
        if frame is not None:
            self.frame_signal.emit(frame)
        return True

    def emit_counts(self, count_nhap, count_xuat):
        """Gửi số liệu đếm về UI để cập nhật bảng."""
        self.count_signal.emit(count_nhap, count_xuat)

    def emit_fps(self, fps_value):
        """Gửi FPS realtime về UI."""
        try:
            self.fps_signal.emit(float(fps_value))
        except Exception:
            pass

    def emit_session_refresh(self):
        """Báo UI refresh lại lịch sử/session."""
        try:
            self.session_signal.emit()
        except Exception:
            pass

    def close(self):
        """Dọn dẹp (hiện tại không cần làm gì)."""
        pass


def convert_cv_to_qt(cv_img, target_width=None, target_height=None):
    """
    Chuyển ảnh OpenCV (BGR numpy) -> QPixmap (RGB) để hiển thị trên QLabel.

    Được gọi bởi: MainWindow.update_image()

    Quy trình:
        1. BGR -> RGB (OpenCV dùng BGR, Qt dùng RGB)
        2. numpy array -> QImage (.copy() để tránh memory bug)
        3. Scale giữ tỷ lệ -> QPixmap
    """
    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape

    # .copy() quan trọng: QImage chỉ tham chiếu rgb.data, không copy.
    # Nếu rgb bị garbage collect trước khi QPixmap tạo xong -> crash.
    qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

    if target_width is None or target_height is None:
        target_width = getattr(ui_settings, "UI_TARGET_WIDTH", 800)
        target_height = getattr(ui_settings, "UI_TARGET_HEIGHT", 600)

    if target_width and target_height:
        scaled = qt_img.scaled(
            target_width, target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        return QPixmap.fromImage(scaled)

    return QPixmap.fromImage(qt_img)
