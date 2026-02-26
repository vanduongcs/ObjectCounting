"""
Main Window: Giao diện chính của ứng dụng object counting.

Mô hình hoạt động:
- UI Layer: Chỉ chứa Layout, Nút bấm, và hiển thị hình ảnh (VideoLabel).
- Logic Layer: Gọi xuống services (video_service, ai_service) để xử lý.
"""

import os
import cv2
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, 
    QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QGroupBox, QCheckBox,
    QFileDialog, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt

import src.services.video_service as video_service
from src.utils.draw_line import calculate_virtual_line, draw_region_overlay
from src.utils.qt_helpers import convert_cv_to_qt
from src.utils.export_excel_processor import export_to_csv
from src.views.video_label import VideoLabel
from src.views.video_thread import VideoThread


class MainWindow(QMainWindow):
    def __init__(self, ai_service, display_adapter):
        """
        Khởi tạo cửa sổ chính.
        Args:
            ai_service: Service xử lý AI.
            display_adapter: Cầu nối nhận ảnh từ AI thread để hiển thị.
        """
        super().__init__()
        self.setWindowTitle("Ứng dụng kiểm đếm")
        self.resize(1280, 720)

        self.ai_service = ai_service
        self.display_adapter = display_adapter
        
        # Trạng thái ứng dụng
        self.current_video_path = None
        self.original_frame = None
        self.current_frame = None
        self.virtual_line = None
        self.virtual_line_frame_size = None  # (w, h) khi vẽ vạch
        self.rotation_angle = 0
        
        self.extraction_thread = None
        self.frame_queue = None
        self.video_thread = None
        self.is_paused = False
        
        # Dữ liệu đếm mới nhất (để export)
        self.latest_counts_nhap = {}
        self.latest_counts_xuat = {}

        # Đăng ký nhận ảnh từ AI service
        self.display_adapter.frame_signal.connect(self.update_image)
        # Đăng ký nhận kết quả đếm
        self.display_adapter.count_signal.connect(self.update_counter_table)

        self._build_ui()

    def _build_ui(self):
        """Xây dựng layout giao diện (Nút bấm, Màn hình video)."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QGridLayout(central_widget)

        # 1. Màn hình video (Trái)
        self.video_label = VideoLabel()
        self.video_label.line_drawn_signal.connect(self.handle_line_drawn)
        layout.addWidget(self.video_label, 0, 0)

        # 2. Panel điều khiển (Phải)
        right_panel = QWidget()
        right_panel.setFixedWidth(350)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- GROUP CONTROL (Các nút điều khiển) ---
        control_group = QGroupBox("Điều khiển")
        control_layout = QGridLayout()
        
        # Cột 1: Label
        control_layout.addWidget(QLabel("FPS xử lý:"), 0, 0)
        control_layout.addWidget(QLabel("Độ phân giải (W):"), 1, 0)
        control_layout.addWidget(QLabel("Conf tối thiểu:"), 2, 0)
        
        # Cột 2: Input Controls
        # FPS Input
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setRange(1, 120)
        self.fps_spinbox.setValue(30)
        self.fps_spinbox.valueChanged.connect(self.change_fps)
        control_layout.addWidget(self.fps_spinbox, 0, 1)

        # Resolution Combo
        self.res_combo = QComboBox()
        self.res_combo.addItems(["Gốc", "480", "640", "1280"])
        self.res_combo.currentTextChanged.connect(self.change_resolution)
        control_layout.addWidget(self.res_combo, 1, 1)

        # Confidence Threshold
        self.conf_spinbox = QDoubleSpinBox()
        self.conf_spinbox.setRange(0.05, 1.0)
        self.conf_spinbox.setSingleStep(0.05)
        self.conf_spinbox.setValue(0.15)
        self.conf_spinbox.valueChanged.connect(self.change_conf)
        control_layout.addWidget(self.conf_spinbox, 2, 1)

        # Hiển thị Bounding Box
        self.show_boxes_checkbox = QCheckBox("Hiển thị Bounding Box")
        self.show_boxes_checkbox.setChecked(True)
        self.show_boxes_checkbox.stateChanged.connect(self.toggle_show_boxes)
        control_layout.addWidget(self.show_boxes_checkbox, 3, 0, 1, 2)

        # Hiển thị Mask
        self.show_masks_checkbox = QCheckBox("Hiển thị Mask")
        self.show_masks_checkbox.setChecked(False)
        self.show_masks_checkbox.stateChanged.connect(self.toggle_show_masks)
        control_layout.addWidget(self.show_masks_checkbox, 4, 0, 1, 2)

        control_group.setLayout(control_layout)
        right_layout.addWidget(control_group)

        # --- GROUP ACTIONS (Các nút hành động) ---
        # Dùng GridLayout cho 2 cột nút
        action_layout = QGridLayout()

        # Nút Chọn Video (Hàng 0, Cột 0)
        self.choose_button = QPushButton("Chọn video")
        self.choose_button.setFixedSize(140, 40)
        self.choose_button.clicked.connect(self.start_choosing)
        action_layout.addWidget(self.choose_button, 0, 0)

        # Nút Kết nối Camera (Hàng 0, Cột 1)
        self.camera_button = QPushButton("Kết nối Camera")
        self.camera_button.setFixedSize(140, 40)
        self.camera_button.clicked.connect(self.connect_camera)
        action_layout.addWidget(self.camera_button, 0, 1)

        # Nút Vẽ Vạch (Hàng 1, Cột 0)
        self.draw_button = QPushButton("Vẽ vạch ảo")
        self.draw_button.setFixedSize(140, 40)
        self.draw_button.clicked.connect(self.start_drawing_line)
        self.draw_button.setEnabled(False)
        action_layout.addWidget(self.draw_button, 1, 0)

        # Nút Xoay 90 (Hàng 1, Cột 1)
        self.rotate_button = QPushButton("Xoay 90°")
        self.rotate_button.setFixedSize(140, 40)
        self.rotate_button.clicked.connect(self.rotate_camera)
        self.rotate_button.setEnabled(False)
        action_layout.addWidget(self.rotate_button, 1, 1)

        # Nút Bắt đầu (Hàng 2, Cột 0)
        self.start_button = QPushButton("Bắt đầu")
        self.start_button.setFixedSize(140, 40)
        self.start_button.clicked.connect(self.start_processing)
        self.start_button.setEnabled(False)
        action_layout.addWidget(self.start_button, 2, 0)

        # Nút Tạm dừng (Hàng 2, Cột 1)
        self.pause_button = QPushButton("Tạm dừng")
        self.pause_button.setFixedSize(140, 40)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)
        action_layout.addWidget(self.pause_button, 2, 1)

        # Nút Dừng (Hàng 3, chiếm 2 cột)
        self.stop_button = QPushButton("Dừng")
        self.stop_button.setFixedSize(290, 40)
        self.stop_button.clicked.connect(self.stop_processing)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        action_layout.addWidget(self.stop_button, 3, 0, 1, 2)  # Hàng 3, Cột 0, span 1 hàng x 2 cột

        right_layout.addLayout(action_layout)

        # Spacer để đẩy bảng xuống dưới (nếu cần)
        right_layout.addStretch()

        # --- BẢNG SỐ LIỆU ---
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["Loại", "Nhập", "Xuất"])
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # Giới hạn chiều cao bảng tối thiểu để dễ nhìn
        self.result_table.setMinimumHeight(300)
        right_layout.addWidget(self.result_table)

        # --- NÚT XUẤT EXCEL ---
        self.export_button = QPushButton("Xuất file Excel")
        self.export_button.setFixedSize(330, 40)  # Cố định kích thước cho đẹp
        self.export_button.clicked.connect(self.export_data)
        right_layout.addWidget(self.export_button)

        layout.addWidget(right_panel, 0, 1)

    # --- SỰ KIỆN (HANDLERS) ---
    
    def export_data(self):
        """Xuất dữ liệu ra file Excel (CSV)."""
        if not self.latest_counts_nhap and not self.latest_counts_xuat:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có dữ liệu để xuất!")
            return

        # Mở hộp thoại chọn nơi lưu
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Lưu file Excel", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if filepath:
            success, message = export_to_csv(filepath, self.latest_counts_nhap, self.latest_counts_xuat)
            if success:
                QMessageBox.information(self, "Thành công", message)
            else:
                QMessageBox.critical(self, "Lỗi", message)

    def start_choosing(self):
        """Mở hộp thoại chọn video & hiển thị preview."""
        video_path = video_service.select_video_file()
        if video_path:
            self.setup_video(video_path)

    def connect_camera(self):
        """Kết nối tới Camera IP qua URL."""
        url, ok = QInputDialog.getText(
            self, "Kết nối Camera", 
            "Nhập URL Camera (VD: http://192.168.1.10:8080/video):"
        )
        if ok and url:
            # Gợi ý: Nếu user nhập IP dạng 192.168.x.x:port mà thiếu http, có thể tự thêm?
            # Hiện tại ta cứ tin tưởng user nhập đúng.
            self.setup_video(url)

    def setup_video(self, video_path):
        """Thiết lập nguồn video (File hoặc URL)."""
        self.current_video_path = video_path
        
        # Hiển thị tên file hoặc URL
        display_name = os.path.basename(video_path) if os.path.isfile(video_path) else video_path
        self.video_label.setText(f"Đang tải: {display_name}...")

        # Lấy frame đầu tiên để xem trước
        first_frame = video_service.get_first_frame(video_path)
        if first_frame is not None:
            self.original_frame = first_frame.copy()
            self.current_frame = first_frame
            self.rotation_angle = 0
            
            self.video_label.setPixmap(convert_cv_to_qt(first_frame))
            
            # Mở khóa các nút tiếp theo
            self.draw_button.setEnabled(True)
            self.rotate_button.setEnabled(True)
            
            self.camera_button.setText("Kết nối lại") if "http" in video_path else None
            self.start_button.setEnabled(True)
            self.choose_button.setText("Chọn lại video")
            
            # Reset bảng khi chọn video mới
            self.result_table.setRowCount(0)
        else:
            self.video_label.setText("Lỗi kết nối/đọc video!")

    def rotate_camera(self):
        """Xoay frame 90 độ."""
        self.rotation_angle = (self.rotation_angle + 90) % 360
        
        # Cập nhật thread đang chạy
        if self.extraction_thread:
            self.extraction_thread.set_rotation(self.rotation_angle)

        # Cập nhật preview nếu chưa chạy
        if self.original_frame is not None and not self.extraction_thread:
            frame = self.original_frame.copy()
            if self.rotation_angle == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation_angle == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation_angle == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
            self.current_frame = frame
            self.video_label.setPixmap(convert_cv_to_qt(frame))
            
            # Reset vạch vẽ vì kích thước thay đổi
            self.virtual_line = None
            self.draw_button.setText("Vẽ vạch ảo")
            self.draw_button.setEnabled(True)
            # Update image to clear overlay
            self.update_image(frame)

    def start_drawing_line(self):
        """Bật chế độ vẽ vạch trên VideoLabel."""
        self.video_label.enable_drawing(True)
        self.draw_button.setText("Kéo chuột để vẽ...")
        self.draw_button.setEnabled(False)

    def handle_line_drawn(self, p1, p2):
        """Xử lý khi người dùng vẽ xong (thả chuột)."""
        if self.current_frame is None:
            return

        h_img, w_img = self.current_frame.shape[:2]
        
        # Tính toán tọa độ thực tế trên ảnh gốc
        lbl_w = self.video_label.width()
        lbl_h = self.video_label.height()
        extended = calculate_virtual_line(
            p1, p2, 
            (lbl_w, lbl_h),  # Kích thước thực tế của VideoLabel
            (w_img, h_img)   # Kích thước ảnh gốc
        )

        if extended:
            self.virtual_line = extended
            self.virtual_line_frame_size = (w_img, h_img)
            self.draw_button.setText("Vẽ lại vạch")
            self.draw_button.setEnabled(True)
            
            # Vẽ overlay lên frame preview
            self.update_image(self.current_frame.copy())
        else:
            self.draw_button.setText("Lỗi! Vẽ lại đi")
            self.draw_button.setEnabled(True)

    def start_processing(self):
        """Bắt đầu chạy thread xử lý video."""
        if not self.current_video_path:
            return

        # Cảnh báo nếu chưa vẽ vạch ảo (sẽ không đếm được)
        if not self.virtual_line:
            reply = QMessageBox.question(
                self, "Chưa vẽ vạch",
                "Bạn chưa vẽ vạch ảo.\nVideo sẽ chạy nhưng KHÔNG đếm.\n\nBạn có muốn tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Dọn dẹp thread cũ nếu có (tránh race condition)
        self._cleanup_threads()

        # Khóa UI
        self.start_button.setEnabled(False)
        self.start_button.setText("Đang chạy...")
        self.choose_button.setEnabled(False)
        self.camera_button.setEnabled(False)
        self.draw_button.setEnabled(False)
        self.rotate_button.setEnabled(False)
        
        # Reset bảng
        self.result_table.setRowCount(0)

        # Khởi tạo Queue & Thread trích xuất
        self.extraction_thread, self.frame_queue = \
            video_service.start_extraction(self.current_video_path)

        # Áp dụng cấu hình ngay lập tức
        self.change_fps(self.fps_spinbox.value())
        self.change_resolution(self.res_combo.currentText())
        self.extraction_thread.set_rotation(self.rotation_angle)

        # Mở khóa nút Tạm dừng + Dừng
        self.pause_button.setEnabled(True)
        self.pause_button.setText("Tạm dừng")
        self.stop_button.setEnabled(True)
        self.is_paused = False

        # Scale virtual line theo resolution thực tế sẽ dùng
        # (frame có thể bị resize bởi FrameExtractor)
        scaled_line = self._get_scaled_virtual_line()

        # Tạo & Chạy AI Thread
        self.video_thread = VideoThread(
            self.ai_service,
            self.extraction_thread,
            frame_queue=self.frame_queue,
            virtual_line=scaled_line
        )
        self.video_thread.finished.connect(self.on_processing_finished)
        self.video_thread.start()

    def _get_scaled_virtual_line(self):
        """
        Tính tọa độ vạch ảo theo resolution thực tế mà FrameExtractor sẽ dùng.
        Cần thiết vì CounterService nhận frame đã resize, không phải frame gốc.
        """
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line

        w_orig, h_orig = self.virtual_line_frame_size

        # Xác định width thực tế mà FrameExtractor sẽ resize về
        effective_width = 0
        res_text = self.res_combo.currentText()
        if res_text.isdigit():
            effective_width = int(res_text)
        
        is_stream = self.current_video_path and (
            self.current_video_path.startswith("http") or 
            self.current_video_path.startswith("rtsp")
        )
        if effective_width == 0 and is_stream:
            effective_width = 640  # Auto-downscale stream (giống logic trong FrameExtractor)

        if effective_width == 0 or effective_width == w_orig:
            return self.virtual_line  # Không resize → giữ nguyên

        # Scale tọa độ
        sx = effective_width / w_orig
        # Tính height mới theo tỉ lệ
        sy = sx  # Giữ tỷ lệ khung hình
        p1, p2 = self.virtual_line
        return (
            (int(p1[0] * sx), int(p1[1] * sy)),
            (int(p2[0] * sx), int(p2[1] * sy))
        )

    def stop_processing(self):
        """Dừng hoàn toàn quá trình xử lý video."""
        self._cleanup_threads()
        self.on_processing_finished()

    def on_processing_finished(self):
        """Được gọi khi video kết thúc hoặc user nhấn Dừng → Reset UI."""
        # Mở khóa lại các nút
        self.start_button.setEnabled(True)
        self.start_button.setText("Bắt đầu")
        self.choose_button.setEnabled(True)
        self.camera_button.setEnabled(True)
        self.draw_button.setEnabled(True)
        self.rotate_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Tạm dừng")
        self.stop_button.setEnabled(False)
        self.is_paused = False

    def _cleanup_threads(self):
        """Dừng và dọn dẹp tất cả thread đang chạy."""
        if self.extraction_thread and self.extraction_thread.isRunning():
            self.extraction_thread.stop()
            self.extraction_thread = None

        if self.video_thread and self.video_thread.isRunning():
            # Gửi sentinel None vào queue để AI thread thoát vòng lặp
            if self.frame_queue:
                try:
                    self.frame_queue.put(None, timeout=1)
                except Exception:
                    pass
            self.video_thread.wait(3000)  # Chờ tối đa 3 giây
            self.video_thread = None

        self.frame_queue = None

    def closeEvent(self, event):
        """Xử lý khi user đóng cửa sổ (nhấn X) → Cleanup tài nguyên."""
        self._cleanup_threads()
        event.accept()

    def update_image(self, cv_img):
        """Được gọi khi có frame mới từ AI -> Hiển thị lên UI."""
        if self.virtual_line:
            # Scale tọa độ vạch theo kích thước frame thực tế
            line = self._scale_line_to_frame(cv_img)
            draw_region_overlay(cv_img, line, alpha=0.25)
        
        self.video_label.setPixmap(convert_cv_to_qt(cv_img))

    def _scale_line_to_frame(self, frame):
        """
        Scale tọa độ vạch ảo theo kích thước frame hiện tại.
        Vì frame có thể bị resize (VD: 1080p -> 640p) nên tọa độ cần scale theo.
        """
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line
        
        h_now, w_now = frame.shape[:2]
        w_orig, h_orig = self.virtual_line_frame_size
        
        # Nếu cùng kích thước -> không cần scale
        if w_now == w_orig and h_now == h_orig:
            return self.virtual_line
        
        # Scale tọa độ tỉ lệ
        sx = w_now / w_orig
        sy = h_now / h_orig
        p1, p2 = self.virtual_line
        return (
            (int(p1[0] * sx), int(p1[1] * sy)),
            (int(p2[0] * sx), int(p2[1] * sy))
        )

    def update_counter_table(self, count_nhap, count_xuat):
        """
        Cập nhật bảng số liệu nhập/xuất.
        Được gọi từ signal của Adapter.
        """
        # Lưu lại để export
        self.latest_counts_nhap = count_nhap
        self.latest_counts_xuat = count_xuat

        # Gộp tất cả loại hàng từ cả 2 danh sách nhập/xuất để không bỏ sót
        all_labels = set(count_nhap.keys()) | set(count_xuat.keys())
        
        self.result_table.setRowCount(len(all_labels))
        
        for row, label in enumerate(sorted(all_labels)):
            sl_nhap = count_nhap.get(label, 0)
            sl_xuat = count_xuat.get(label, 0)
            
            # Cột 0: Loại hàng
            self.result_table.setItem(row, 0, QTableWidgetItem(str(label)))
            # Cột 1: Nhập
            self.result_table.setItem(row, 1, QTableWidgetItem(str(sl_nhap)))
            # Cột 2: Xuất
            self.result_table.setItem(row, 2, QTableWidgetItem(str(sl_xuat)))

    def change_fps(self, value):
        """Thay đổi FPS trích xuất."""
        if self.extraction_thread:
            self.extraction_thread.set_fps(value)

    def change_resolution(self, text):
        """Thay đổi độ phân giải trích xuất."""
        width = 0
        if text.isdigit():
            width = int(text)
        
        if self.extraction_thread:
            self.extraction_thread.set_resolution(width)

    def toggle_show_boxes(self, state):
        """Bật/tắt hiển thị bounding box."""
        self.ai_service.show_boxes = (state == 2)  # 2 = Qt.Checked

    def toggle_show_masks(self, state):
        """Bật/tắt hiển thị mask."""
        self.ai_service.show_masks = (state == 2)

    def change_conf(self, value):
        """Thay đổi ngưỡng confidence tối thiểu."""
        self.ai_service.detector.conf = value

    def toggle_pause(self):
        """Bật/tắt tạm dừng."""
        if not self.extraction_thread:
            return
            
        self.is_paused = not self.is_paused
        
        # Cập nhật thread trích xuất
        if self.is_paused:
            self.extraction_thread.pause()
            self.pause_button.setText("Tiếp tục")
        else:
            self.extraction_thread.resume()
            self.pause_button.setText("Tạm dừng")