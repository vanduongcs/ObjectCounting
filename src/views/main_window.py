"""
Main Window: Giao diện chính của ứng dụng Object Counting.

Đây là module trung tâm, kết nối tất cả thành phần:

    MainWindow (file này)
    |-- video_service        -- chọn video, lấy preview, tạo extraction thread
    |-- FrameExtractionThread -- Producer: đọc frame từ video -> Queue
    |-- VideoThread          -- Consumer wrapper: gọi AIService trong background
    |-- AIService            -- xử lý AI (detect, track, đếm)
    |-- QtDisplayAdapter     -- nhận frame/count từ AI thread qua signal
    |-- VideoLabel           -- hiển thị video + vẽ vạch ảo
    |-- draw_line            -- tính toán vạch ảo + vẽ overlay
    |-- export_csv           -- xuất kết quả ra file CSV

Nguyên tắc:
    - UI Layer chỉ chứa layout và event handlers.
    - Logic AI nằm trong services/.
    - Giao tiếp giữa thread qua QtDisplayAdapter (signal).
"""

import os
import cv2
import json
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout,
    QVBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QCheckBox,
    QFileDialog, QMessageBox, QInputDialog,
)
from PyQt6.QtCore import Qt

# --- Services ---
import src.services.video_service as video_service  # Chọn video, tạo extraction thread
from src.services.frame_extractor import ROTATION_MAP  # Bảng xoay frame

# --- Utils ---
from src.utils.draw_line import calculate_virtual_line, draw_line_with_arrows
from src.utils.qt_helpers import convert_cv_to_qt  # Chuyển OpenCV -> QPixmap
from src.utils.export_excel_processor import export_to_excel  # Xuất Excel

# --- Views ---
from src.views.video_label import VideoLabel
from src.views.video_thread import VideoThread
from src.views.history_panel import HistoryPanel




class MainWindow(QMainWindow):
    def __init__(self, ai_service, display_adapter):
        super().__init__()
        self.setWindowTitle("Ứng dụng kiểm đếm")
        self.resize(1280, 720)

        self.ai_service = ai_service
        self.display_adapter = display_adapter

        # Trạng thái
        self.current_video_path = None
        self.original_frame = None
        self.current_frame = None
        self.virtual_line = None
        self.virtual_line_frame_size = None
        self.rotation_angle = 0
        self.timestamp_space_rel = None

        self.extraction_thread = None
        self.frame_queue = None
        self.video_thread = None
        self.is_paused = False

        # Dữ liệu đếm (để export)
        self.latest_counts_nhap = {}
        self.latest_counts_xuat = {}

        # Signal connections
        self.display_adapter.frame_signal.connect(self.update_image)
        self.display_adapter.count_signal.connect(self.update_counter_table)
        self.display_adapter.fps_signal.connect(self.update_fps)

        self._build_ui()
        self._load_timestamp_space_roi()

    # ===== UI BUILDER =====

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QGridLayout(central)

        # Video (trái)
        self.video_label = VideoLabel()
        self.video_label.line_drawn_signal.connect(self.handle_line_drawn)
        self.video_label.roi_drawn_signal.connect(self.handle_timestamp_space_drawn)
        layout.addWidget(self.video_label, 0, 0)

        # Panel điều khiển (phải)
        panel = QWidget()
        panel.setFixedWidth(350)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._build_controls(panel_layout)
        self._build_buttons(panel_layout)
        panel_layout.addStretch()
        self._build_table(panel_layout)
        self._build_export(panel_layout)

        layout.addWidget(panel, 0, 1)

        # History panel (bên phải panel điều khiển)
        self.history_panel = HistoryPanel()
        self.history_panel.setFixedWidth(300)
        layout.addWidget(self.history_panel, 0, 2)

        # Sync UI target size for overlay scaling
        self._update_ui_target_size()

    def _build_controls(self, parent):
        """Nhóm controls: Resolution, Confidence, Checkboxes."""
        group = QGroupBox("Điều khiển")
        grid = QGridLayout()

        # Resolution
        grid.addWidget(QLabel("Độ phân giải (W):"), 0, 0)
        self.res_combo = QComboBox()
        self.res_combo.addItems(["480", "640", "1280"])
        self.res_combo.currentTextChanged.connect(self.change_resolution)
        grid.addWidget(self.res_combo, 0, 1)

        # Confidence
        grid.addWidget(QLabel("Conf tối thiểu:"), 1, 0)
        self.conf_spinbox = QDoubleSpinBox()
        self.conf_spinbox.setRange(0.05, 1.0)
        self.conf_spinbox.setSingleStep(0.05)
        self.conf_spinbox.setValue(0.4)
        self.conf_spinbox.valueChanged.connect(self.change_conf)
        grid.addWidget(self.conf_spinbox, 1, 1)

        # Checkboxes
        self.show_boxes_cb = QCheckBox("Hiển thị Bounding Box")
        self.show_boxes_cb.setChecked(True)
        self.show_boxes_cb.toggled.connect(self.toggle_show_boxes)
        grid.addWidget(self.show_boxes_cb, 2, 0, 1, 2)

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setStyleSheet("color: #66d9ef; font-weight: bold;")
        grid.addWidget(self.fps_label, 3, 0, 1, 2)

        group.setLayout(grid)
        parent.addWidget(group)

    def _build_buttons(self, parent):
        """Các nút hành động."""
        grid = QGridLayout()
        sz = (140, 40)

        self.choose_btn = self._btn("Chọn video", sz, self.start_choosing)
        grid.addWidget(self.choose_btn, 0, 0)

        self.camera_btn = self._btn("Kết nối Camera", sz, self.connect_camera)
        grid.addWidget(self.camera_btn, 0, 1)

        self.draw_btn = self._btn("Vẽ vạch ảo", sz, self.start_drawing_line, False)
        grid.addWidget(self.draw_btn, 1, 0)

        self.rotate_btn = self._btn("Xoay 90°", sz, self.rotate_camera, False)
        grid.addWidget(self.rotate_btn, 1, 1)

        self.timestamp_space_btn = self._btn("Vẽ Timestamp space", sz, self.start_drawing_timestamp_space, False)
        grid.addWidget(self.timestamp_space_btn, 2, 0)

        self.start_btn = self._btn("Bắt đầu", sz, self.start_processing, False)
        grid.addWidget(self.start_btn, 2, 1)

        self.pause_btn = self._btn("Tạm dừng", sz, self.toggle_pause, False)
        grid.addWidget(self.pause_btn, 3, 0)

        self.stop_btn = self._btn("Dừng", (290, 40), self.stop_processing, False)
        self.stop_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        grid.addWidget(self.stop_btn, 4, 0, 1, 2)

        parent.addLayout(grid)


    def _build_table(self, parent):
        """Bảng kết quả đếm."""
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["Loại", "Nhập", "Xuất"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setMinimumHeight(300)
        parent.addWidget(self.result_table)

    def _build_export(self, parent):
        """Nút xuất CSV."""
        self.export_btn = self._btn("Xuất Excel", (330, 40), self.export_data)
        parent.addWidget(self.export_btn)

    @staticmethod
    def _btn(text, size, callback, enabled=True):
        """Tạo QPushButton."""
        btn = QPushButton(text)
        btn.setFixedSize(*size)
        btn.clicked.connect(callback)
        btn.setEnabled(enabled)
        return btn

    # ===== EVENT HANDLERS =====

    def toggle_show_boxes(self, checked):
        """Bật/tắt hiển thị bounding box."""
        self.ai_service.show_boxes = checked

    def export_data(self):
        """Xuất dữ liệu đếm ra file Excel."""
        if not self.latest_counts_nhap and not self.latest_counts_xuat:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có dữ liệu để xuất!")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Lưu file Excel", "", "Excel Files (*.xlsx);;All Files (*)"
        )
        if not filepath:
            return

        event_log = getattr(self.ai_service, 'last_event_log', [])
        ok, msg = export_to_excel(
            filepath, self.latest_counts_nhap, self.latest_counts_xuat, event_log
        )
        if ok:
            QMessageBox.information(self, "Kết quả", msg)
        else:
            QMessageBox.critical(self, "Kết quả", msg)

    def start_choosing(self):
        path = video_service.select_video_file()
        if path:
            self.setup_video(path)

    def connect_camera(self):
        url, ok = QInputDialog.getText(
            self, "Kết nối Camera",
            "Nhập URL Camera (VD: http://192.168.1.10:8080/video):",
        )
        if ok and url:
            self.setup_video(url)

    def setup_video(self, video_path):
        """Thiết lập nguồn video và hiển thị preview."""
        self.current_video_path = video_path
        display = os.path.basename(video_path) if os.path.isfile(video_path) else video_path
        self.video_label.setText(f"Đang tải: {display}...")

        first_frame = video_service.get_first_frame(video_path)
        if first_frame is None:
            self.video_label.setText("Lỗi kết nối/đọc video!")
            return

        self.original_frame = first_frame.copy()
        self.current_frame = first_frame
        self.rotation_angle = 0
        self.video_label.setPixmap(convert_cv_to_qt(first_frame))

        # Mở khóa nút
        self.draw_btn.setEnabled(True)
        self.rotate_btn.setEnabled(True)
        self.timestamp_space_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.choose_btn.setText("Chọn lại video")
        if "http" in video_path or "rtsp" in video_path:
            self.camera_btn.setText("Kết nối lại")

        self.result_table.setRowCount(0)

    def rotate_camera(self):
        self.rotation_angle = (self.rotation_angle + 90) % 360

        if self.extraction_thread:
            self.extraction_thread.set_rotation(self.rotation_angle)

        # Cập nhật preview nếu chưa chạy
        if self.original_frame is not None and not self.extraction_thread:
            frame = _rotate_frame(self.original_frame.copy(), self.rotation_angle)
            self.current_frame = frame
            self.video_label.setPixmap(convert_cv_to_qt(frame))
            self.virtual_line = None
            self.draw_btn.setText("Vẽ vạch ảo")
            self.draw_btn.setEnabled(True)
            self.update_image(frame)

    def start_drawing_line(self):
        self.video_label.enable_drawing(True)
        self.draw_btn.setText("Kéo chuột để vẽ...")
        self.draw_btn.setEnabled(False)

    def start_drawing_timestamp_space(self):
        self.video_label.enable_drawing(True, mode="roi")
        self.timestamp_space_btn.setText("Kéo chuột để chọn Timestamp...")
        self.timestamp_space_btn.setEnabled(False)

    def handle_line_drawn(self, p1, p2):
        if self.current_frame is None:
            return
        h, w = self.current_frame.shape[:2]

        # Lấy kích thước pixmap thực tế (ảnh sau scale, không phải widget)
        # QLabel AlignCenter sẽ căn giữa pixmap trong widget → tạo offset
        pixmap = self.video_label.pixmap()
        if pixmap and not pixmap.isNull():
            pm_w, pm_h = pixmap.width(), pixmap.height()
            label_w = self.video_label.width()
            label_h = self.video_label.height()

            # Offset do pixmap nhỏ hơn widget và được căn giữa
            offset_x = (label_w - pm_w) / 2
            offset_y = (label_h - pm_h) / 2

            # Trừ offset → tọa độ tương đối với pixmap
            p1_adj = (p1[0] - offset_x, p1[1] - offset_y)
            p2_adj = (p2[0] - offset_x, p2[1] - offset_y)

            # Dùng pixmap size (không phải label size) cho scale
            display_size = (pm_w, pm_h)
        else:
            p1_adj, p2_adj = p1, p2
            display_size = (self.video_label.width(), self.video_label.height())

        extended = calculate_virtual_line(
            p1_adj, p2_adj,
            display_size,
            (w, h),
        )
        if extended:
            self.virtual_line = extended
            self.virtual_line_frame_size = (w, h)
            self.draw_btn.setText("Vẽ lại vạch")
            self.draw_btn.setEnabled(True)
            self.update_image(self.current_frame.copy())
        else:
            self.draw_btn.setText("Lỗi! Vẽ lại đi")
            self.draw_btn.setEnabled(True)

    def handle_timestamp_space_drawn(self, p1, p2):
        if self.current_frame is None:
            return
        h, w = self.current_frame.shape[:2]

        pixmap = self.video_label.pixmap()
        if pixmap and not pixmap.isNull():
            pm_w, pm_h = pixmap.width(), pixmap.height()
            label_w = self.video_label.width()
            label_h = self.video_label.height()
            offset_x = (label_w - pm_w) / 2
            offset_y = (label_h - pm_h) / 2
            p1_adj = (p1[0] - offset_x, p1[1] - offset_y)
            p2_adj = (p2[0] - offset_x, p2[1] - offset_y)
            display_size = (pm_w, pm_h)
        else:
            p1_adj, p2_adj = p1, p2
            display_size = (self.video_label.width(), self.video_label.height())

        # Scale UI -> image coords
        img_w, img_h = w, h
        scale = min(display_size[0] / img_w, display_size[1] / img_h)
        if scale <= 0:
            return

        x1 = int(p1_adj[0] / scale)
        y1 = int(p1_adj[1] / scale)
        x2 = int(p2_adj[0] / scale)
        y2 = int(p2_adj[1] / scale)
        x1, x2 = sorted((max(0, x1), min(img_w - 1, x2)))
        y1, y2 = sorted((max(0, y1), min(img_h - 1, y2)))
        if x2 <= x1 or y2 <= y1:
            self.timestamp_space_btn.setText("Lỗi! Vẽ lại")
            self.timestamp_space_btn.setEnabled(True)
            return

        # Lưu Timestamp space theo tỉ lệ ảnh gốc
        self.timestamp_space_rel = (x1 / img_w, y1 / img_h, (x2 - x1) / img_w, (y2 - y1) / img_h)
        try:
            import configs.settings as settings
            settings.TIMESTAMP_SPACE_REL = self.timestamp_space_rel
            settings.TIMESTAMP_SPACE_ROI_PATH.parent.mkdir(parents=True, exist_ok=True)
            settings.TIMESTAMP_SPACE_ROI_PATH.write_text(
                json.dumps({'rel': self.timestamp_space_rel}), encoding='utf-8'
            )
        except Exception:
            pass

        self.timestamp_space_btn.setText("Vẽ Timestamp space")
        self.timestamp_space_btn.setEnabled(True)
        # Refresh preview
        self.update_image(self.current_frame.copy())

    def start_processing(self):
        if not self.current_video_path:
            return
        if not self.virtual_line:
            reply = QMessageBox.question(
                self, "Chưa vẽ vạch",
                "Bạn chưa vẽ vạch ảo.\nVideo sẽ chạy nhưng KHÔNG đếm.\n\nTiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self._cleanup_threads()
        self._update_ui_target_size()
        self._set_ui_running(True)
        self.result_table.setRowCount(0)

        # Khởi tạo extraction
        self.extraction_thread, self.frame_queue = \
            video_service.start_extraction(self.current_video_path)
        self.change_resolution(self.res_combo.currentText())
        self.extraction_thread.set_rotation(self.rotation_angle)

        # Scale vạch ảo theo resolution thực tế
        scaled_line = self._scale_line_to_width(self._get_effective_width())

        # Chạy AI thread
        video_name = os.path.basename(self.current_video_path) \
            if os.path.isfile(self.current_video_path) else self.current_video_path
        self.video_thread = VideoThread(
            self.ai_service, self.extraction_thread,
            frame_queue=self.frame_queue, virtual_line=scaled_line,
            video_name=video_name,
        )
        self.video_thread.finished.connect(self.on_processing_finished)
        self.video_thread.start()

    def stop_processing(self):
        """Dừng xử lý: AI loop thoát nhanh, compile video chạy nền."""
        # 1. Signal AI loop thoát (trong ≤ 0.5s)
        self.ai_service._stop_requested = True

        # 2. Dừng extraction thread (producer)
        if self.extraction_thread:
            self.extraction_thread.is_running = False

        # 2.1. Đẩy sentinel để AI thread thoát ngay (tránh treo/crash)
        if self.frame_queue:
            try:
                self.frame_queue.put(None, timeout=1)
            except Exception:
                pass

        # 3. Reset UI ngay — không đợi compile video
        self._set_ui_running(False)
        self.start_btn.setText("Đang lưu...")
        self.start_btn.setEnabled(False)

        # Video thread sẽ tự hoàn tất (compile video + save DB)
        # Khi xong, signal finished → on_processing_finished → refresh lịch sử

    def on_processing_finished(self):
        """Reset UI sau khi kết thúc (cả dừng sớm và hết video)."""
        self._set_ui_running(False)
        # Dọn dẹp references
        self.video_thread = None
        self.frame_queue = None
        self.extraction_thread = None
        # Làm mới lịch sử
        self.history_panel.refresh()

    def toggle_pause(self):
        if not self.extraction_thread:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.extraction_thread.pause()
            self.pause_btn.setText("Tiếp tục")
        else:
            self.extraction_thread.resume()
            self.pause_btn.setText("Tạm dừng")

    # ===== DISPLAY =====

    def update_image(self, cv_img):
        """Đảnh Hiển thị frame, vẽ vạch ảo nếu có."""
        self._update_ui_target_size()
        if self.virtual_line:
            line = self._scale_line_to_frame(cv_img)
            draw_line_with_arrows(cv_img, line)
        if self.timestamp_space_rel:
            h, w = cv_img.shape[:2]
            x, y, rw, rh = self.timestamp_space_rel
            x1 = int(x * w)
            y1 = int(y * h)
            x2 = int((x + rw) * w)
            y2 = int((y + rh) * h)
            cv2.rectangle(cv_img, (x1, y1), (x2, y2), (0, 255, 255), 2)
        self.video_label.setPixmap(convert_cv_to_qt(cv_img))

    def update_counter_table(self, count_nhap, count_xuat):
        """Cập nhật bảng nhập/xuất."""
        self.latest_counts_nhap = count_nhap
        self.latest_counts_xuat = count_xuat
        labels = sorted(set(count_nhap) | set(count_xuat))
        self.result_table.setRowCount(len(labels))
        for row, label in enumerate(labels):
            self.result_table.setItem(row, 0, QTableWidgetItem(str(label)))
            self.result_table.setItem(row, 1, QTableWidgetItem(str(count_nhap.get(label, 0))))
            self.result_table.setItem(row, 2, QTableWidgetItem(str(count_xuat.get(label, 0))))

    def update_fps(self, fps_value):
        """Cập nhật FPS realtime trên UI."""
        if hasattr(self, "fps_label"):
            self.fps_label.setText(f"FPS: {fps_value:.1f}")

    # ===== SETTINGS =====

    def change_fps(self, value):
        if self.extraction_thread:
            self.extraction_thread.set_fps(value)

    def change_resolution(self, text):
        width = int(text) if text.isdigit() else 0
        if self.extraction_thread:
            self.extraction_thread.set_resolution(width)

    def change_conf(self, value):
        self.ai_service.set_conf(value)

    # ===== PRIVATE =====

    def _set_ui_running(self, running):
        """Toggle trạng thái UI giữa chạy/dừng."""
        self.start_btn.setEnabled(not running)
        self.start_btn.setText("Đang chạy..." if running else "Bắt đầu")
        self.choose_btn.setEnabled(not running)
        self.camera_btn.setEnabled(not running)
        self.draw_btn.setEnabled(not running)
        self.rotate_btn.setEnabled(not running)
        self.timestamp_space_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.pause_btn.setText("Tạm dừng")
        self.stop_btn.setEnabled(running)
        self.is_paused = False

    def _scale_line_to_frame(self, frame):
        """Scale vạch ảo cho khớp kích thước frame hiện tại."""
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line

        h_now, w_now = frame.shape[:2]
        return self._do_scale(w_now, h_now)

    def _scale_line_to_width(self, target_width):
        """Scale vạch ảo theo width mới (khi thay đổi resolution)."""
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line

        w_orig, h_orig = self.virtual_line_frame_size

        # Không cần scale nếu giữ nguyên resolution
        if target_width <= 0 or target_width == w_orig:
            return self.virtual_line

        h_new = int(h_orig * target_width / w_orig)
        return self._do_scale(target_width, h_new)

    def _do_scale(self, w_now, h_now):
        """Tính tọa độ vạch ảo mới theo kích thước (w_now, h_now)."""
        w_orig, h_orig = self.virtual_line_frame_size

        # Kích thước không đổi → không cần scale
        if w_now == w_orig and h_now == h_orig:
            return self.virtual_line

        scale_x = w_now / w_orig
        scale_y = h_now / h_orig
        p1, p2 = self.virtual_line
        return (
            (int(p1[0] * scale_x), int(p1[1] * scale_y)),
            (int(p2[0] * scale_x), int(p2[1] * scale_y)),
        )

    def _get_effective_width(self):
        """Tính width mà FrameExtractor sẽ resize về."""
        text = self.res_combo.currentText()
        width = int(text) if text.isdigit() else 0
        is_stream = self.current_video_path and \
            self.current_video_path.startswith(("http", "rtsp"))
        if width == 0 and is_stream:
            width = 640
        return width

    def _cleanup_threads(self):
        """Dừng và dọn dẹp tất cả thread (dùng khi bắt đầu lại hoặc đóng app)."""
        # Signal AI loop thoát
        self.ai_service._stop_requested = True

        # Dừng extraction thread
        if self.extraction_thread:
            self.extraction_thread.is_running = False
            self.extraction_thread = None

        # Gửi None vào queue để AI thread thoát khỏi vòng lặp
        if self.frame_queue:
            try:
                while not self.frame_queue.empty():
                    self.frame_queue.get_nowait()
            except Exception:
                pass
            try:
                self.frame_queue.put(None, timeout=1)
            except Exception:
                pass

        # Chờ video thread kết thúc
        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.wait(10000)
        self.video_thread = None
        self.frame_queue = None

    def _update_ui_target_size(self):
        """C?p nh?t k?ch th??c hi?n th? m?c ti?u ?? scale overlay ?n ??nh."""
        try:
            import configs.settings as settings
            w = max(1, self.video_label.width())
            h = max(1, self.video_label.height())
            settings.UI_TARGET_WIDTH = w
            settings.UI_TARGET_HEIGHT = h
        except Exception:
            pass

    def _load_timestamp_space_roi(self):
        """Load timestamp space ROI t? file n?u c?."""
        try:
            import configs.settings as settings
            path = settings.TIMESTAMP_SPACE_ROI_PATH
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                rel = data.get("rel")
                if isinstance(rel, (list, tuple)) and len(rel) == 4:
                    self.timestamp_space_rel = tuple(float(x) for x in rel)
                    settings.TIMESTAMP_SPACE_REL = self.timestamp_space_rel
        except Exception:
            pass

    def closeEvent(self, event):
        self._cleanup_threads()
        event.accept()


# --- Module-level helper ---

def _rotate_frame(frame, angle):
    """Xoay frame theo góc (0/90/180/270). Dùng ROTATION_MAP chung."""
    rotation = ROTATION_MAP.get(angle)
    return cv2.rotate(frame, rotation) if rotation is not None else frame
    def change_resolution(self, text):
        width = int(text) if text.isdigit() else 0
        if self.extraction_thread:
            self.extraction_thread.set_resolution(width)
