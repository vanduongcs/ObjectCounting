"""Main application window for the object counting workflow."""

import json
import os

import cv2
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedLayout,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import configs.settings as settings
import configs.settings_interface as ui_settings
import configs.settings_theme as theme_settings
import src.services.video_service as video_service
from src.services.frame_extractor import ROTATION_MAP
from src.utils.draw_line import calculate_virtual_line, draw_line_with_arrows
from src.utils.export_excel_processor import export_to_excel
from src.utils.qt_helpers import convert_cv_to_qt
from src.utils.source_utils import (
    get_source_region,
    is_stream_source,
    load_source_region_store,
    save_source_region,
)
from src.utils.ui_state import compute_main_window_button_states
from src.services.timestamp_ocr import TimestampOCRService
from src.views.history_panel import HistoryDrawer
from src.views.toggle_switch import ToggleSwitch
from src.views.video_label import VideoLabel
from src.views.video_thread import VideoThread


class MainWindow(QMainWindow):
    BUTTON_HEIGHT = ui_settings.CONTROL_BUTTON_HEIGHT
    PANEL_WIDTH = ui_settings.SIDE_PANEL_WIDTH
    HISTORY_EXPANDED_WIDTH = HistoryDrawer.EXPANDED_WIDTH
    HISTORY_COLLAPSED_WIDTH = HistoryDrawer.COLLAPSED_WIDTH

    def __init__(self, ai_service, display_adapter):
        super().__init__()
        self.setWindowTitle("Ứng dụng kiểm đếm")
        self.resize(ui_settings.APP_WINDOW_WIDTH, ui_settings.APP_WINDOW_HEIGHT)
        self.setMinimumSize(
            ui_settings.APP_WINDOW_MIN_WIDTH,
            ui_settings.APP_WINDOW_MIN_HEIGHT,
        )

        self.ai_service = ai_service
        self.display_adapter = display_adapter

        self.current_video_path = None
        self.original_frame = None
        self.current_frame = None
        self.virtual_line = None
        self.virtual_line_frame_size = None
        self.virtual_line_rel = None
        self.rotation_angle = 0
        self.timestamp_space_rel = None
        self._virtual_line_store = {}
        self._timestamp_space_store = {}

        self.extraction_thread = None
        self.frame_queue = None
        self.video_thread = None
        self.is_paused = False

        self.latest_counts_nhap = {}
        self.latest_counts_xuat = {}

        self.display_adapter.frame_signal.connect(self.update_image)
        self.display_adapter.count_signal.connect(self.update_counter_table)
        self.display_adapter.fps_signal.connect(self.update_fps)

        self._build_ui()
        self._refresh_result_table()
        self._apply_styles()

        self.display_adapter.session_signal.connect(self.history_panel_refresh_safe)
        self._load_virtual_line()
        self._load_timestamp_space_roi()
        self._refresh_action_buttons(running=False)
        self._restore_window_state()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(
            ui_settings.APP_ROOT_MARGIN,
            ui_settings.APP_ROOT_MARGIN,
            ui_settings.APP_ROOT_MARGIN,
            ui_settings.APP_ROOT_MARGIN,
        )
        root_layout.setSpacing(ui_settings.APP_ROOT_SPACING)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(ui_settings.SPLITTER_HANDLE_WIDTH)

        self.video_label = VideoLabel()
        self.video_label.setText("Chọn video hoặc kết nối camera để bắt đầu.")
        self.video_label.line_drawn_signal.connect(self.handle_line_drawn)
        self.video_label.roi_drawn_signal.connect(self.handle_timestamp_space_drawn)
        self.main_splitter.addWidget(self._build_video_stage())

        self.main_splitter.addWidget(self._build_side_panel())

        self.history_drawer = HistoryDrawer(collapsed=False)
        self.history_drawer.toggled.connect(self._handle_history_drawer_toggled)
        self.history_panel = self.history_drawer.panel
        self.main_splitter.addWidget(self.history_drawer)

        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)
        self.main_splitter.setStretchFactor(2, 0)

        root_layout.addWidget(self.main_splitter, 1)
        self._sync_main_splitter_sizes()
        self._update_ui_target_size()

    def _build_header(self):
        header = QFrame()
        header.setObjectName("appHeader")

        layout = QVBoxLayout(header)
        layout.setContentsMargins(
            ui_settings.HEADER_MARGIN,
            ui_settings.HEADER_MARGIN,
            ui_settings.HEADER_MARGIN,
            ui_settings.HEADER_MARGIN,
        )
        layout.setSpacing(ui_settings.HEADER_SPACING)

        eyebrow = QLabel("BẢNG ĐIỀU KHIỂN")
        eyebrow.setObjectName("appEyebrow")
        layout.addWidget(eyebrow)

        title = QLabel("Object Counting Studio")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Chọn nguồn, vẽ vạch ảo, rồi theo dõi đếm đối tượng và lịch sử phiên xử lý."
        )
        subtitle.setObjectName("appSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return header

    def _build_video_stage(self):
        card = QFrame()
        card.setObjectName("videoStageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setSpacing(ui_settings.VIDEO_STAGE_SPACING)

        title = QLabel("Preview")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        layout.addWidget(self.video_label, 1)

        hint = QLabel("Vẽ vạch hoặc vùng timestamp trực tiếp trên khung hình preview.")
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_side_panel(self):
        scroll = QScrollArea()
        scroll.setObjectName("sidePanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(self.PANEL_WIDTH)
        scroll.setMaximumWidth(self.PANEL_WIDTH)
        scroll.setViewportMargins(0, 0, ui_settings.SCROLLBAR_VIEWPORT_MARGIN, 0)
        scroll.viewport().setObjectName("sidePanelViewport")
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        panel = QWidget()
        panel.setObjectName("sidePanelContent")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, ui_settings.SIDE_PANEL_CONTENT_RIGHT_MARGIN, 0)
        layout.setSpacing(ui_settings.SIDE_PANEL_SECTION_SPACING)

        self._build_controls(layout)
        self._build_buttons(layout)
        self._build_table(layout)
        self._build_overview_card(layout)
        layout.addStretch(1)

        scroll.setWidget(panel)
        return scroll

    def _build_overview_card(self, parent):
        group = QGroupBox()
        layout = QGridLayout(group)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setHorizontalSpacing(ui_settings.OVERVIEW_HORIZONTAL_SPACING)
        layout.setVerticalSpacing(ui_settings.OVERVIEW_VERTICAL_SPACING)

        self.source_value_label = self._build_overview_value(layout, 0, "Nguồn")
        self.line_value_label = self._build_overview_value(layout, 1, "Vạch")
        self.timestamp_value_label = self._build_overview_value(layout, 2, "Timestamp")
        self.mode_value_label = self._build_overview_value(layout, 3, "Trạng thái")

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setObjectName("fpsValue")
        layout.addWidget(self.fps_label, 4, 0, 1, 2)

        group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        parent.addWidget(group)

    @staticmethod
    def _build_overview_value(layout, row, label_text):
        label = QLabel(label_text)
        label.setObjectName("overviewItem")
        layout.addWidget(label, row, 0)

        value = QLabel("--")
        value.setObjectName("overviewValue")
        value.setWordWrap(True)
        layout.addWidget(value, row, 1)
        return value

    def _build_controls(self, parent):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setSpacing(ui_settings.CARD_SPACING)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        grid.addWidget(self._build_field_label("Độ phân giải (W)"), 0, 0)
        self.res_combo = QComboBox()
        self.res_combo.addItems(["480", "640", "1280"])
        self.res_combo.currentTextChanged.connect(self.change_resolution)
        grid.addWidget(self.res_combo, 0, 1)

        grid.addWidget(self._build_field_label("Conf tối thiểu"), 1, 0)
        self.conf_spinbox = QDoubleSpinBox()
        self.conf_spinbox.setRange(0.05, 1.0)
        self.conf_spinbox.setSingleStep(0.05)
        self.conf_spinbox.setDecimals(2)
        self.conf_spinbox.setValue(float(settings.DETECTION_CONFIDENCE))
        self.conf_spinbox.valueChanged.connect(self.change_conf)
        grid.addWidget(self.conf_spinbox, 1, 1)

        layout.addLayout(grid)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(ui_settings.CARD_SPACING)

        toggle_label = QLabel("Hiển thị bounding box")
        toggle_label.setObjectName("fieldLabel")
        toggle_row.addWidget(toggle_label)
        toggle_row.addStretch(1)

        self.show_boxes_switch = ToggleSwitch()
        self.show_boxes_switch.setChecked(bool(self.ai_service.show_boxes))
        self.show_boxes_switch.toggled.connect(self.toggle_show_boxes)
        toggle_row.addWidget(self.show_boxes_switch)

        layout.addLayout(toggle_row)

        conf_toggle_row = QHBoxLayout()
        conf_toggle_row.setContentsMargins(0, 0, 0, 0)
        conf_toggle_row.setSpacing(ui_settings.CARD_SPACING)

        conf_toggle_label = QLabel("Hiển thị conf")
        conf_toggle_label.setObjectName("fieldLabel")
        conf_toggle_row.addWidget(conf_toggle_label)
        conf_toggle_row.addStretch(1)

        self.show_conf_switch = ToggleSwitch()
        self.show_conf_switch.setChecked(bool(self.ai_service.show_box_conf))
        self.show_conf_switch.setEnabled(bool(self.ai_service.show_boxes))
        self.show_conf_switch.toggled.connect(self.toggle_show_box_conf)
        conf_toggle_row.addWidget(self.show_conf_switch)

        layout.addLayout(conf_toggle_row)

        group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        parent.addWidget(group)

    def _build_buttons(self, parent):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setSpacing(ui_settings.CARD_SPACING)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.choose_btn = self._btn("Chọn video", self.start_choosing)
        self.camera_btn = self._btn(
            "Kết nối camera",
            self.connect_camera,
        )
        self.draw_btn = self._btn(
            "Vẽ vạch ảo",
            self.start_drawing_line,
            enabled=False,
        )
        self.rotate_btn = self._btn(
            "Xoay 90°",
            self.rotate_camera,
            enabled=False,
        )
        self.timestamp_space_btn = self._btn(
            "Vẽ vùng timestamp",
            self.start_drawing_timestamp_space,
            enabled=False,
        )
        self.start_btn = self._btn(
            "Bắt đầu",
            self.start_processing,
            enabled=False,
            variant="primary",
        )
        self.pause_btn = self._btn(
            "Tạm dừng",
            self.toggle_pause,
            enabled=False,
        )
        self.stop_btn = self._btn(
            "Dừng",
            self.stop_processing,
            enabled=False,
            variant="danger",
        )

        grid.addWidget(self.choose_btn, 0, 0)
        grid.addWidget(self.camera_btn, 0, 1)
        grid.addWidget(self.draw_btn, 1, 0)
        grid.addWidget(self.timestamp_space_btn, 1, 1)
        grid.addWidget(self.rotate_btn, 2, 0)
        grid.addWidget(self.start_btn, 2, 1)
        grid.addWidget(self.pause_btn, 3, 0)
        grid.addWidget(self.stop_btn, 4, 0, 1, 2)

        layout.addLayout(grid)

        group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        parent.addWidget(group)

    def _build_table(self, parent):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setSpacing(ui_settings.CARD_SPACING)

        table_card = QFrame()
        table_card.setObjectName("resultTableCard")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(0, 0, 0, 0)
        table_card_layout.setSpacing(0)

        table_stack_host = QWidget()
        table_stack_host.setObjectName("resultTableStackHost")
        self.result_table_stack = QStackedLayout(table_stack_host)
        self.result_table_stack.setContentsMargins(0, 0, 0, 0)
        self.result_table_stack.setStackingMode(QStackedLayout.StackingMode.StackOne)

        self.result_table = QTableWidget()
        self.result_table.setObjectName("resultTable")
        self.result_table.setFrameShape(QFrame.Shape.NoFrame)
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["Loại", "Nhập", "Xuất"])
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )
        self.result_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.result_table.setMinimumHeight(ui_settings.RESULT_TABLE_MIN_HEIGHT)
        self.result_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.viewport().setObjectName("resultTableViewport")
        self.result_table_stack.addWidget(self.result_table)

        self.result_table_empty = QLabel(
            "Chưa có dữ liệu ghi nhận.\nKhi có vật thể được đếm, bảng sẽ cập nhật tại đây."
        )
        self.result_table_empty.setObjectName("emptyStateLabel")
        self.result_table_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_table_empty.setMinimumHeight(ui_settings.RESULT_TABLE_MIN_HEIGHT)
        self.result_table_empty.setWordWrap(True)
        self.result_table_stack.addWidget(self.result_table_empty)
        table_card_layout.addWidget(table_stack_host)
        layout.addWidget(table_card)

        self.export_btn = self._btn(
            "Xuất Excel",
            self.export_data,
            enabled=False,
        )
        layout.addWidget(self.export_btn)

        group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        parent.addWidget(group)

    @staticmethod
    def _build_field_label(text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _btn(self, text, callback, enabled=True, variant="secondary", height=None):
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(height or self.BUTTON_HEIGHT)
        button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        button.setEnabled(enabled)
        button.setProperty("variant", variant)
        button.clicked.connect(callback)
        return button

    def _sync_main_splitter_sizes(self):
        if not hasattr(self, "main_splitter"):
            return

        history_width = (
            self.HISTORY_COLLAPSED_WIDTH
            if self.history_drawer.is_collapsed()
            else self.HISTORY_EXPANDED_WIDTH
        )
        total_width = max(1, self.width() - 56)
        video_width = max(
            ui_settings.MIN_VIDEO_PANEL_WIDTH,
            total_width - self.PANEL_WIDTH - history_width,
        )
        self.main_splitter.setSizes([video_width, self.PANEL_WIDTH, history_width])

    def _handle_history_drawer_toggled(self, collapsed):
        del collapsed
        self._sync_main_splitter_sizes()

    def _apply_styles(self):
        self.setStyleSheet(theme_settings.MAIN_WINDOW_STYLESHEET)

    @staticmethod
    def _serialize_rect(rect):
        if rect is None or not rect.isValid():
            return None
        return {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "width": int(rect.width()),
            "height": int(rect.height()),
        }

    @staticmethod
    def _deserialize_rect(payload):
        if not isinstance(payload, dict):
            return None
        try:
            rect = QRect(
                int(payload["x"]),
                int(payload["y"]),
                int(payload["width"]),
                int(payload["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return rect if rect.isValid() else None

    def _load_window_state(self):
        path = settings.WINDOW_STATE_PATH
        try:
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _save_window_state(self):
        path = settings.WINDOW_STATE_PATH
        normal_rect = self.normalGeometry()
        if not normal_rect.isValid():
            normal_rect = self.geometry()
        window_state = (
            "maximized"
            if self.isMaximized() or self.isFullScreen()
            else "normal"
        )

        payload = {
            "window_state": window_state,
            "geometry": self._serialize_rect(self.geometry()),
            "normal_geometry": self._serialize_rect(normal_rect),
        }

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _restore_window_state(self):
        payload = self._load_window_state()
        if not payload:
            if ui_settings.WINDOW_START_MAXIMIZED:
                self.setWindowState(
                    self.windowState() | Qt.WindowState.WindowMaximized
                )
            return

        normal_rect = self._deserialize_rect(payload.get("normal_geometry"))
        current_rect = self._deserialize_rect(payload.get("geometry"))
        state = str(payload.get("window_state", "normal")).strip().lower()

        if normal_rect is not None:
            self.setGeometry(normal_rect)
        elif current_rect is not None:
            self.setGeometry(current_rect)

        if state in {"fullscreen", "maximized"}:
            self.setWindowState(
                self.windowState() | Qt.WindowState.WindowMaximized
            )
        elif current_rect is not None:
            self.setGeometry(current_rect)

        self._sync_main_splitter_sizes()
        self._update_ui_target_size()

    @staticmethod
    def _compute_button_states(source_loaded, running, has_line, is_stream):
        return compute_main_window_button_states(
            source_loaded=source_loaded,
            running=running,
            has_line=has_line,
            is_stream=is_stream,
        )

    def _is_stream_source(self):
        return is_stream_source(self.current_video_path)

    def _is_processing_active(self):
        return self.video_thread is not None and self.video_thread.isRunning()

    def _has_loaded_source(self):
        return self.current_frame is not None and bool(self.current_video_path)

    def _current_persistence_variant(self):
        return f"rot={self.rotation_angle}"

    def _has_export_data(self):
        event_log = getattr(self.ai_service, "last_event_log", [])
        return bool(self.latest_counts_nhap or self.latest_counts_xuat or event_log)

    def _refresh_export_button(self):
        self.export_btn.setEnabled(self._has_export_data())

    def _display_source_name(self):
        source = self.current_video_path
        if not source:
            return "Chưa chọn"
        display = os.path.basename(source) if os.path.isfile(source) else str(source)
        if len(display) <= 40:
            return display
        return f"{display[:18]}...{display[-18:]}"

    def _current_mode_text(self):
        if self.video_label.drawing_mode == "line":
            return "Đang vẽ vạch"
        if self.video_label.drawing_mode == "roi":
            return "Đang chọn vùng timestamp"
        if self.video_thread is not None:
            if self.start_btn.text() == "Đang lưu...":
                return "Đang lưu kết quả"
            if self.is_paused:
                return "Đang tạm dừng"
            return "Đang xử lý"
        if self._has_loaded_source():
            return "Sẵn sàng"
        return "Chờ thao tác"

    def _refresh_overview(self):
        self.source_value_label.setText(self._display_source_name())
        self.line_value_label.setText("Đã có" if self.virtual_line else "Chưa có")
        self.timestamp_value_label.setText(
            "Đã chọn" if self.timestamp_space_rel else "Mặc định"
        )
        self.mode_value_label.setText(
            f"{self._current_mode_text()} | xoay {self.rotation_angle}°"
        )

    def _refresh_action_buttons(self, running=False):
        states = self._compute_button_states(
            source_loaded=self._has_loaded_source(),
            running=running,
            has_line=bool(self.virtual_line),
            is_stream=self._is_stream_source(),
        )
        self.choose_btn.setEnabled(states["choose"])
        self.camera_btn.setEnabled(states["camera"])
        self.draw_btn.setEnabled(states["draw"])
        self.rotate_btn.setEnabled(states["rotate"])
        self.timestamp_space_btn.setEnabled(states["timestamp"])
        self.start_btn.setEnabled(states["start"])
        self.pause_btn.setEnabled(states["pause"])
        self.stop_btn.setEnabled(states["stop"])
        self._refresh_export_button()
        self._refresh_overview()

    def toggle_show_boxes(self, checked):
        self.ai_service.show_boxes = checked
        if hasattr(self, "show_conf_switch"):
            self.show_conf_switch.setEnabled(bool(checked))

    def toggle_show_box_conf(self, checked):
        self.ai_service.show_box_conf = checked

    def export_data(self):
        event_log = getattr(self.ai_service, "last_event_log", [])
        if not self.latest_counts_nhap and not self.latest_counts_xuat and not event_log:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có dữ liệu để xuất!")
            return

        default_name = (
            TimestampOCRService.build_output_file_name_from_events(event_log, "xlsx")
            or "output.xlsx"
        )
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu file Excel",
            default_name,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not filepath:
            return

        try:
            ok, message = export_to_excel(
                filepath,
                self.latest_counts_nhap,
                self.latest_counts_xuat,
                event_log,
            )
        except Exception as exc:
            ok, message = False, f"Lỗi xuất file: {exc}"

        if ok:
            QMessageBox.information(self, "Kết quả", message)
        else:
            QMessageBox.critical(self, "Kết quả", message)

    def start_choosing(self):
        path = video_service.select_video_file()
        if path:
            self.setup_video(path)

    def connect_camera(self):
        url, ok = QInputDialog.getText(
            self,
            "Kết nối Camera",
            "Nhập URL camera (VD: http://192.168.1.10:8080/video):",
        )
        if ok and url:
            self.setup_video(url.strip())

    def setup_video(self, video_path):
        display_name = (
            os.path.basename(video_path) if os.path.isfile(video_path) else video_path
        )
        self.video_label.setText(f"Đang tải: {display_name}...")
        previous_line_rel = self.virtual_line_rel
        previous_timestamp_rel = self.timestamp_space_rel

        first_frame = video_service.get_first_frame(video_path)
        if first_frame is None:
            QMessageBox.warning(
                self,
                "Lỗi nguồn video",
                "Không thể đọc frame đầu tiên từ nguồn đã chọn.",
            )
            if self.current_frame is not None:
                self.update_image(self.current_frame.copy())
            else:
                self.video_label.setText("Lỗi kết nối hoặc không đọc được video.")
            self._refresh_action_buttons(running=False)
            return

        self.current_video_path = video_path
        self.original_frame = first_frame.copy()
        self.current_frame = first_frame
        self.rotation_angle = 0
        self._restore_timestamp_space_for_current_source(
            fallback_rel=previous_timestamp_rel
        )
        self._restore_virtual_line_for_current_frame(fallback_rel=previous_line_rel)
        self.draw_btn.setText("Vẽ lại vạch" if self.virtual_line else "Vẽ vạch ảo")
        self.timestamp_space_btn.setText(
            "Vẽ lại vùng timestamp"
            if self.timestamp_space_rel
            else "Vẽ vùng timestamp"
        )
        self.update_image(first_frame.copy())

        self.choose_btn.setText("Chọn lại video")
        self.camera_btn.setText(
            "Kết nối lại" if self._is_stream_source() else "Kết nối camera"
        )
        self.latest_counts_nhap = {}
        self.latest_counts_xuat = {}
        self.ai_service.last_event_log = []
        self._refresh_result_table()
        self._refresh_action_buttons(running=False)

    def rotate_camera(self):
        previous_rotation = self.rotation_angle
        previous_line_rel = self.virtual_line_rel
        previous_timestamp_rel = self.timestamp_space_rel
        self.rotation_angle = (self.rotation_angle + 90) % 360

        if self.extraction_thread:
            self.extraction_thread.set_rotation(self.rotation_angle)

        if self.original_frame is not None and not self.extraction_thread:
            rotation_delta = (self.rotation_angle - previous_rotation) % 360
            frame = _rotate_frame(self.original_frame.copy(), self.rotation_angle)
            self.current_frame = frame
            self._restore_timestamp_space_for_current_source(
                fallback_rel=_rotate_relative_rect(
                    previous_timestamp_rel,
                    rotation_delta,
                )
            )
            self._restore_virtual_line_for_current_frame(
                fallback_rel=_rotate_relative_line(
                    previous_line_rel,
                    rotation_delta,
                )
            )
            self.draw_btn.setText("Vẽ lại vạch" if self.virtual_line else "Vẽ vạch ảo")
            self.timestamp_space_btn.setText(
                "Vẽ lại vùng timestamp"
                if self.timestamp_space_rel
                else "Vẽ vùng timestamp"
            )
            self.update_image(frame.copy())
            self._refresh_action_buttons(running=False)
            return

        self._refresh_overview()

    def start_drawing_line(self):
        self.video_label.enable_drawing(True)
        self.draw_btn.setText("Kéo chuột để vẽ...")
        self.draw_btn.setEnabled(False)
        self._refresh_overview()

    def start_drawing_timestamp_space(self):
        self.video_label.enable_drawing(True, mode="roi")
        self.timestamp_space_btn.setText("Kéo chuột để chọn...")
        self.timestamp_space_btn.setEnabled(False)
        self._refresh_overview()

    def handle_line_drawn(self, p1, p2):
        if self.current_frame is None:
            return

        frame_h, frame_w = self.current_frame.shape[:2]
        p1_adj, p2_adj, display_size = self._adjust_drawn_points(p1, p2)
        extended = calculate_virtual_line(
            p1_adj,
            p2_adj,
            display_size,
            (frame_w, frame_h),
        )
        if not extended:
            self.draw_btn.setText("Lỗi! Vẽ lại đi")
            self._refresh_action_buttons(running=False)
            return

        self.virtual_line = extended
        self.virtual_line_frame_size = (frame_w, frame_h)
        (x1, y1), (x2, y2) = extended
        self.virtual_line_rel = (
            x1 / frame_w,
            y1 / frame_h,
            x2 / frame_w,
            y2 / frame_h,
        )
        self._save_virtual_line()
        self.draw_btn.setText("Vẽ lại vạch")
        self.update_image(self.current_frame.copy())
        self._refresh_action_buttons(running=False)

    def handle_timestamp_space_drawn(self, p1, p2):
        rect = self._map_drawn_rect_to_image(p1, p2)
        if rect is None:
            self.timestamp_space_btn.setText("Lỗi! Vẽ lại")
            self.timestamp_space_btn.setEnabled(True)
            self._refresh_overview()
            return

        x1, y1, x2, y2 = rect
        frame_h, frame_w = self.current_frame.shape[:2]
        self.timestamp_space_rel = (
            x1 / frame_w,
            y1 / frame_h,
            (x2 - x1) / frame_w,
            (y2 - y1) / frame_h,
        )

        settings.TIMESTAMP_SPACE_REL = self.timestamp_space_rel
        save_source_region(
            settings.TIMESTAMP_SPACE_ROI_PATH,
            self._timestamp_space_store,
            self.current_video_path,
            self.timestamp_space_rel,
            variant=self._current_persistence_variant(),
        )

        self.timestamp_space_btn.setText("Vẽ lại vùng timestamp")
        self.update_image(self.current_frame.copy())
        self._refresh_action_buttons(running=False)

    def start_processing(self):
        if not self.current_video_path:
            return
        if not self.virtual_line:
            QMessageBox.warning(
                self,
                "Thiếu vạch",
                "Cần có vạch ảo trước khi bắt đầu đếm.",
            )
            return

        self._cleanup_threads()
        self._update_ui_target_size()
        self._set_ui_running(True)
        self.latest_counts_nhap = {}
        self.latest_counts_xuat = {}
        self.ai_service.last_event_log = []
        self._refresh_result_table()
        self._refresh_export_button()

        self.extraction_thread, self.frame_queue = video_service.start_extraction(
            self.current_video_path
        )
        self.change_resolution(self.res_combo.currentText())
        self.extraction_thread.set_rotation(self.rotation_angle)

        scaled_line = self._scale_line_to_width(self._get_effective_width())
        video_name = (
            os.path.basename(self.current_video_path)
            if os.path.isfile(self.current_video_path)
            else self.current_video_path
        )
        self.video_thread = VideoThread(
            self.ai_service,
            self.extraction_thread,
            frame_queue=self.frame_queue,
            virtual_line=scaled_line,
            video_name=video_name,
        )
        self.video_thread.finished.connect(self.on_processing_finished)
        self.video_thread.start()
        self._refresh_overview()

    def stop_processing(self):
        self.ai_service._stop_requested = True

        if self.extraction_thread:
            self.extraction_thread.is_running = False

        if self.frame_queue:
            try:
                self.frame_queue.put(None, timeout=1)
            except Exception:
                pass

        self._set_ui_running(False)
        self.start_btn.setText("Đang lưu...")
        self.start_btn.setEnabled(False)
        self._refresh_overview()

    def on_processing_finished(self):
        self._set_ui_running(False)
        self.video_thread = None
        self.frame_queue = None
        self.extraction_thread = None
        self.history_panel.refresh()
        self._refresh_result_table()
        self._refresh_export_button()
        self._refresh_overview()

    def history_panel_refresh_safe(self):
        try:
            self.history_panel.refresh()
            self._refresh_result_table()
            self._refresh_export_button()
        except Exception:
            pass

    def toggle_pause(self):
        if not self.extraction_thread or self._is_stream_source():
            return

        self.is_paused = not self.is_paused
        if self.is_paused:
            self.extraction_thread.pause()
            self.pause_btn.setText("Tiếp tục")
        else:
            self.extraction_thread.resume()
            self.pause_btn.setText("Tạm dừng")
        self._refresh_overview()

    def update_image(self, cv_img):
        """Render preview frame with the saved overlays."""
        render_preview_overlays = not self._is_processing_active()
        frame_to_display = cv_img.copy() if render_preview_overlays else cv_img

        if render_preview_overlays and self.virtual_line:
            draw_line_with_arrows(
                frame_to_display,
                self._scale_line_to_frame(frame_to_display),
            )

        if render_preview_overlays and self.timestamp_space_rel:
            h, w = frame_to_display.shape[:2]
            x, y, rw, rh = self.timestamp_space_rel
            x1 = int(x * w)
            y1 = int(y * h)
            x2 = int((x + rw) * w)
            y2 = int((y + rh) * h)
            cv2.rectangle(
                frame_to_display,
                (x1, y1),
                (x2, y2),
                theme_settings.TIMESTAMP_ROI_COLOR,
                2,
            )

        canvas_rect = self._get_video_canvas_rect()
        self.video_label.setPixmap(
            convert_cv_to_qt(
                frame_to_display,
                canvas_rect.width(),
                canvas_rect.height(),
            )
        )

    def update_counter_table(self, count_nhap, count_xuat):
        self.latest_counts_nhap = dict(count_nhap or {})
        self.latest_counts_xuat = dict(count_xuat or {})
        self._refresh_result_table()
        self._refresh_export_button()

    @staticmethod
    def _summarize_event_log_counts(event_log):
        count_nhap = {}
        count_xuat = {}
        for event in event_log or []:
            if not isinstance(event, dict):
                continue
            label = str(
                event.get("label")
                or event.get("class_name")
                or event.get("class")
                or event.get("loai")
                or ""
            ).strip()
            action = str(event.get("action", "")).strip().lower()
            if not action:
                direction = str(event.get("direction", "")).strip().lower()
                if any(token in direction for token in ("vao", "vào", "nhap", "nhập", "in", "enter")):
                    action = "nhap"
                elif any(token in direction for token in ("ra", "rời", "roi", "xuat", "xuất", "out", "exit")):
                    action = "xuat"
            if not label:
                continue
            if "nh" in action:
                count_nhap[label] = count_nhap.get(label, 0) + 1
            elif "xu" in action:
                count_xuat[label] = count_xuat.get(label, 0) + 1
        return count_nhap, count_xuat

    def _refresh_result_table(self):
        display_nhap = dict(self.latest_counts_nhap or {})
        display_xuat = dict(self.latest_counts_xuat or {})

        if not display_nhap and not display_xuat:
            fallback_nhap, fallback_xuat = self._summarize_event_log_counts(
                getattr(self.ai_service, "last_event_log", [])
            )
            if fallback_nhap or fallback_xuat:
                display_nhap, display_xuat = fallback_nhap, fallback_xuat

        labels = sorted(set(display_nhap) | set(display_xuat))
        self.result_table.clearContents()
        if not labels:
            self.result_table.setRowCount(0)
            if hasattr(self, "result_table_stack") and hasattr(self, "result_table_empty"):
                self.result_table_stack.setCurrentWidget(self.result_table_empty)
            return

        if hasattr(self, "result_table_stack"):
            self.result_table_stack.setCurrentWidget(self.result_table)
        self.result_table.setRowCount(len(labels))
        for row, label in enumerate(labels):
            self.result_table.setItem(row, 0, self._make_result_table_item(str(label)))
            self.result_table.setItem(
                row,
                1,
                self._make_result_table_item(str(display_nhap.get(label, 0))),
            )
            self.result_table.setItem(
                row,
                2,
                self._make_result_table_item(str(display_xuat.get(label, 0))),
            )

    @staticmethod
    def _make_result_table_item(text, muted=False):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        )
        item.setForeground(
            QBrush(
                QColor(
                    theme_settings.TABLE_MUTED_TEXT
                    if muted
                    else theme_settings.TABLE_TEXT
                )
            )
        )
        item.setToolTip("")
        return item

    def update_fps(self, fps_value):
        self.fps_label.setText(f"FPS: {fps_value:.1f}")

    def change_resolution(self, text):
        width = int(text) if text.isdigit() else 0
        if self.extraction_thread:
            self.extraction_thread.set_resolution(width)

    def change_conf(self, value):
        self.ai_service.set_conf(value)

    def _save_virtual_line(self):
        if not self.virtual_line_rel or not self.current_video_path:
            return
        save_source_region(
            settings.VIRTUAL_LINE_PATH,
            self._virtual_line_store,
            self.current_video_path,
            self.virtual_line_rel,
            variant=self._current_persistence_variant(),
        )

    def _load_virtual_line(self):
        self._virtual_line_store = load_source_region_store(settings.VIRTUAL_LINE_PATH)
        self.virtual_line_rel = None

    def _restore_virtual_line_for_current_frame(self, fallback_rel=None):
        saved_rel = get_source_region(
            self._virtual_line_store,
            self.current_video_path,
            variant=self._current_persistence_variant(),
            fallback_to_last_used=True,
        )
        self.virtual_line_rel = saved_rel or self._coerce_rel_region(fallback_rel)
        if self.current_frame is None:
            self.virtual_line = None
            self.virtual_line_frame_size = None
            return
        if not self.virtual_line_rel:
            self.virtual_line = None
            self.virtual_line_frame_size = None
            return

        frame_h, frame_w = self.current_frame.shape[:2]
        x1, y1, x2, y2 = self.virtual_line_rel
        self.virtual_line = (
            (int(x1 * frame_w), int(y1 * frame_h)),
            (int(x2 * frame_w), int(y2 * frame_h)),
        )
        self.virtual_line_frame_size = (frame_w, frame_h)
        if saved_rel is None and self.current_video_path:
            self._save_virtual_line()

    def _set_ui_running(self, running):
        self.start_btn.setText("Đang chạy..." if running else "Bắt đầu")
        self.pause_btn.setText("Tạm dừng")
        self.is_paused = False
        self._refresh_action_buttons(running=running)

    def _scale_line_to_frame(self, frame):
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line
        frame_h, frame_w = frame.shape[:2]
        return self._do_scale(frame_w, frame_h)

    def _scale_line_to_width(self, target_width):
        if not self.virtual_line or not self.virtual_line_frame_size:
            return self.virtual_line

        orig_w, orig_h = self.virtual_line_frame_size
        if target_width <= 0 or target_width == orig_w:
            return self.virtual_line

        target_h = int(orig_h * target_width / orig_w)
        return self._do_scale(target_width, target_h)

    def _do_scale(self, width_now, height_now):
        orig_w, orig_h = self.virtual_line_frame_size
        if width_now == orig_w and height_now == orig_h:
            return self.virtual_line

        scale_x = width_now / orig_w
        scale_y = height_now / orig_h
        p1, p2 = self.virtual_line
        return (
            (int(p1[0] * scale_x), int(p1[1] * scale_y)),
            (int(p2[0] * scale_x), int(p2[1] * scale_y)),
        )

    def _get_effective_width(self):
        width_text = self.res_combo.currentText()
        width = int(width_text) if width_text.isdigit() else 0
        if width == 0 and self._is_stream_source():
            return settings.DEFAULT_STREAM_WIDTH
        return width

    def _cleanup_threads(self):
        self.ai_service._stop_requested = True

        if self.extraction_thread:
            self.extraction_thread.is_running = False
            self.extraction_thread.wait(5000)
            self.extraction_thread = None

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

        if self.video_thread and self.video_thread.isRunning():
            self.video_thread.wait(10000)
        self.video_thread = None
        self.frame_queue = None
        self._refresh_overview()

    def _get_display_geometry(self):
        canvas_rect = self._get_video_canvas_rect()
        pixmap = self.video_label.pixmap()
        if pixmap and not pixmap.isNull():
            display_size = (pixmap.width(), pixmap.height())
            offset = (
                canvas_rect.x() + (canvas_rect.width() - display_size[0]) / 2,
                canvas_rect.y() + (canvas_rect.height() - display_size[1]) / 2,
            )
            return display_size, offset
        return (
            (canvas_rect.width(), canvas_rect.height()),
            (float(canvas_rect.x()), float(canvas_rect.y())),
        )

    def _adjust_drawn_points(self, p1, p2):
        display_size, (offset_x, offset_y) = self._get_display_geometry()
        adjusted_p1 = (p1[0] - offset_x, p1[1] - offset_y)
        adjusted_p2 = (p2[0] - offset_x, p2[1] - offset_y)
        return adjusted_p1, adjusted_p2, display_size

    def _map_drawn_rect_to_image(self, p1, p2):
        if self.current_frame is None:
            return None

        frame_h, frame_w = self.current_frame.shape[:2]
        p1_adj, p2_adj, display_size = self._adjust_drawn_points(p1, p2)
        scale = min(display_size[0] / frame_w, display_size[1] / frame_h)
        if scale <= 0:
            return None

        x1 = int(p1_adj[0] / scale)
        y1 = int(p1_adj[1] / scale)
        x2 = int(p2_adj[0] / scale)
        y2 = int(p2_adj[1] / scale)

        x1, x2 = sorted((max(0, x1), min(frame_w - 1, x2)))
        y1, y2 = sorted((max(0, y1), min(frame_h - 1, y2)))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def _update_ui_target_size(self):
        try:
            canvas_rect = self._get_video_canvas_rect()
            ui_settings.UI_TARGET_WIDTH = max(1, canvas_rect.width())
            ui_settings.UI_TARGET_HEIGHT = max(1, canvas_rect.height())
        except Exception:
            pass

    def _get_video_canvas_rect(self):
        rect = self.video_label.contentsRect()
        if rect.width() > 0 and rect.height() > 0:
            return rect
        return self.video_label.rect()

    def _load_timestamp_space_roi(self):
        self._timestamp_space_store = load_source_region_store(
            settings.TIMESTAMP_SPACE_ROI_PATH
        )
        self._restore_timestamp_space_for_current_source()

    def _restore_timestamp_space_for_current_source(self, fallback_rel=None):
        saved_rel = get_source_region(
            self._timestamp_space_store,
            self.current_video_path,
            variant=self._current_persistence_variant(),
            fallback_to_last_used=True,
        )
        self.timestamp_space_rel = (
            saved_rel
            or self._coerce_rel_region(fallback_rel)
            or settings.DEFAULT_TIMESTAMP_SPACE_REL
        )
        settings.TIMESTAMP_SPACE_REL = self.timestamp_space_rel
        if saved_rel is None and self.current_video_path:
            save_source_region(
                settings.TIMESTAMP_SPACE_ROI_PATH,
                self._timestamp_space_store,
                self.current_video_path,
                self.timestamp_space_rel,
                variant=self._current_persistence_variant(),
            )

    @staticmethod
    def _coerce_rel_region(rel):
        if not isinstance(rel, (list, tuple)) or len(rel) != 4:
            return None
        try:
            return tuple(float(value) for value in rel)
        except (TypeError, ValueError):
            return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_ui_target_size()
        self._sync_main_splitter_sizes()
        if self.current_frame is not None and self.video_thread is None:
            self.update_image(self.current_frame.copy())

    def closeEvent(self, event):
        self._save_window_state()
        self._cleanup_threads()
        event.accept()


def _rotate_frame(frame, angle):
    """Rotate preview frame using the shared rotation lookup."""
    rotation = ROTATION_MAP.get(angle)
    return cv2.rotate(frame, rotation) if rotation is not None else frame


def _rotate_relative_line(line_rel, angle_delta):
    rel = _coerce_relative_region(line_rel)
    if rel is None:
        return None

    x1, y1, x2, y2 = rel
    rx1, ry1 = _rotate_relative_point(x1, y1, angle_delta)
    rx2, ry2 = _rotate_relative_point(x2, y2, angle_delta)
    return rx1, ry1, rx2, ry2


def _rotate_relative_rect(rect_rel, angle_delta):
    rel = _coerce_relative_region(rect_rel)
    if rel is None:
        return None

    x, y, w, h = rel
    corners = (
        _rotate_relative_point(x, y, angle_delta),
        _rotate_relative_point(x + w, y, angle_delta),
        _rotate_relative_point(x, y + h, angle_delta),
        _rotate_relative_point(x + w, y + h, angle_delta),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return (
        min(xs),
        min(ys),
        max(xs) - min(xs),
        max(ys) - min(ys),
    )


def _rotate_relative_point(x, y, angle_delta):
    angle_delta %= 360
    if angle_delta == 90:
        return _clamp_relative_point(1.0 - y, x)
    if angle_delta == 180:
        return _clamp_relative_point(1.0 - x, 1.0 - y)
    if angle_delta == 270:
        return _clamp_relative_point(y, 1.0 - x)
    return _clamp_relative_point(x, y)


def _clamp_relative_point(x, y):
    return max(0.0, min(1.0, float(x))), max(0.0, min(1.0, float(y)))


def _coerce_relative_region(rel):
    if not isinstance(rel, (list, tuple)) or len(rel) != 4:
        return None
    try:
        return tuple(float(value) for value in rel)
    except (TypeError, ValueError):
        return None
