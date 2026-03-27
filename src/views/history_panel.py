"""History sidebar widgets for processed sessions."""

import os
import subprocess
import sys

import configs.settings as settings
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

import configs.settings_interface as ui_settings
from src.services import db_service
from src.services.timestamp_ocr import TimestampOCRService
from src.utils.export_excel_processor import export_to_excel


class HistoryDrawer(QWidget):
    """Collapsible right drawer that hosts the session history."""

    toggled = pyqtSignal(bool)

    COLLAPSED_WIDTH = ui_settings.HISTORY_DRAWER_COLLAPSED_WIDTH
    EXPANDED_WIDTH = ui_settings.HISTORY_DRAWER_EXPANDED_WIDTH

    def __init__(self, parent=None, collapsed=True):
        super().__init__(parent)
        self.setObjectName("historyDrawer")
        self._collapsed = collapsed
        self.panel = HistoryPanel()
        self._build_ui()
        self.set_collapsed(collapsed, emit_signal=False)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_settings.HISTORY_LAYOUT_SPACING)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("historyDrawerToggle")
        self.toggle_btn.setProperty("variant", "drawer")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Expanding,
        )
        self.toggle_btn.setFixedWidth(self.COLLAPSED_WIDTH)
        self.toggle_btn.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self.toggle_btn)

        self.body = QFrame()
        self.body.setObjectName("historyDrawerBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(
            ui_settings.HISTORY_BODY_MARGIN,
            ui_settings.HISTORY_BODY_MARGIN,
            ui_settings.HISTORY_BODY_MARGIN,
            ui_settings.HISTORY_BODY_MARGIN,
        )
        body_layout.addWidget(self.panel)
        layout.addWidget(self.body, 1)

    def refresh(self):
        self.panel.refresh()

    def is_collapsed(self):
        return self._collapsed

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed, emit_signal=True):
        self._collapsed = collapsed
        self.body.setVisible(not collapsed)
        width = self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)
        self.toggle_btn.setText("<" if collapsed else ">")
        self.toggle_btn.setToolTip(
            "Mở lịch sử phiên" if collapsed else "Ẩn lịch sử phiên"
        )
        if emit_signal:
            self.toggled.emit(collapsed)


class HistoryPanel(QWidget):
    """Show saved processing sessions and quick actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historySidebar")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_settings.HISTORY_LAYOUT_SPACING)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(
            ui_settings.HISTORY_HEADER_MARGIN,
            ui_settings.HISTORY_HEADER_MARGIN,
            ui_settings.HISTORY_HEADER_MARGIN,
            ui_settings.HISTORY_HEADER_MARGIN,
        )
        header_layout.setSpacing(0)

        title = QLabel("Lịch sử")
        title.setObjectName("historyHeaderTitle")
        header_layout.addWidget(title)

        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setObjectName("historyScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setViewportMargins(0, 0, 8, 0)
        scroll.viewport().setObjectName("historyViewport")
        scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._list_widget = QWidget()
        self._list_widget.setObjectName("historyListWidget")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(
            0,
            0,
            ui_settings.HISTORY_LIST_RIGHT_MARGIN,
            0,
        )
        self._list_layout.setSpacing(ui_settings.HISTORY_LAYOUT_SPACING)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

    def refresh(self):
        """Reload sessions from SQLite and rebuild the list."""
        self._clear_cards()
        sessions = db_service.get_all_sessions()
        if not sessions:
            self._list_layout.addWidget(self._create_empty_state())
            return

        for session in sessions:
            self._list_layout.addWidget(self._create_session_card(session))
        self._list_layout.addStretch(1)

    def _clear_cards(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_empty_state(self):
        card = QFrame()
        card.setObjectName("emptyHistoryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.HISTORY_EMPTY_VERTICAL_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.HISTORY_EMPTY_VERTICAL_MARGIN,
        )
        layout.setSpacing(ui_settings.HEADER_SPACING)

        title = QLabel("Chưa có lịch sử")
        title.setObjectName("historyCardTitle")
        layout.addWidget(title)

        subtitle = QLabel("Sau khi xử lý video, lịch sử sẽ xuất hiện ở đây.")
        subtitle.setObjectName("historyCardMeta")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return card

    def _create_session_card(self, session):
        card = QFrame()
        card.setObjectName("sessionCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
            ui_settings.CARD_MARGIN,
        )
        layout.setSpacing(ui_settings.HISTORY_CARD_SPACING)

        title = QLabel(session.get("video_name", "Unknown"))
        title.setObjectName("historyCardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(self._format_session_meta(session))
        meta.setObjectName("historyCardMeta")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        counts_text = self._format_counts(session)
        if counts_text:
            counts = QLabel(counts_text)
            counts.setObjectName("historyCardCounts")
            counts.setWordWrap(True)
            layout.addWidget(counts)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(ui_settings.HISTORY_CARD_SPACING)

        play_btn = self._make_action_button("Xem video")
        play_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        play_btn.setEnabled(os.path.exists(session.get("output_path", "")))
        play_btn.clicked.connect(lambda _, s=session: self._play_video(s))
        actions.addWidget(play_btn)
        open_folder_btn = self._make_action_button(
            "",
            variant="icon",
            icon=self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
            tooltip="Mo thu muc chua video output",
            square=True,
        )
        open_folder_btn.setEnabled(bool(self._resolve_output_directory(session)))
        open_folder_btn.clicked.connect(lambda _, s=session: self._open_output_folder(s))
        actions.addWidget(open_folder_btn)

        export_btn = self._make_action_button("Xuất Excel")
        export_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        export_btn.clicked.connect(lambda _, s=session: self._export_session(s))
        actions.addWidget(export_btn)

        actions.addStretch(1)

        delete_btn = self._make_action_button("Xóa", variant="danger")
        delete_btn.clicked.connect(lambda _, s=session: self._delete_session(s))
        actions.addWidget(delete_btn)

        layout.addLayout(actions)
        return card

    @staticmethod
    def _make_action_button(
        text,
        variant="ghost",
        icon=None,
        tooltip="",
        square=False,
    ):
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("variant", variant)
        button.setFixedHeight(ui_settings.HISTORY_ACTION_BUTTON_HEIGHT)
        if icon is not None:
            button.setIcon(icon)
            button.setIconSize(QSize(16, 16))
        if tooltip:
            button.setToolTip(tooltip)
        if square:
            size = ui_settings.HISTORY_ACTION_BUTTON_HEIGHT
            button.setFixedSize(size, size)
        return button

    @staticmethod
    def _format_duration(duration_sec):
        if not duration_sec:
            return "0s"
        total_seconds = max(0, int(duration_sec))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def _format_session_meta(self, session):
        parts = [session.get("created_at", "")]
        duration = self._format_duration(session.get("duration_sec", 0))
        if duration:
            parts.append(duration)
        event_count = len(session.get("event_log") or [])
        if event_count:
            parts.append(f"{event_count} sự kiện")
        output_path = session.get("output_path", "")
        parts.append(
            "Có video output" if os.path.exists(output_path) else "Thiếu video output"
        )
        return " | ".join(part for part in parts if part)

    @staticmethod
    def _format_counts(session):
        nhap = session.get("count_nhap", {})
        xuat = session.get("count_xuat", {})
        all_labels = sorted(set(nhap) | set(xuat))
        if not all_labels:
            return ""
        return "\n".join(
            f"{label}: {nhap.get(label, 0)} nhập / {xuat.get(label, 0)} xuất"
            for label in all_labels
        )

    def _play_video(self, session):
        path = session.get("output_path", "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Lỗi", f"Không tìm thấy video:\n{path}")
            return

        try:
            self._open_with_system(path)
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi", f"Không thể mở video:\n{exc}")

    def _open_output_folder(self, session):
        output_path = session.get("output_path", "")
        folder_path = self._resolve_output_directory(session)
        if output_path and os.path.exists(output_path):
            target_path = output_path
        elif folder_path:
            target_path = folder_path
        else:
            QMessageBox.warning(
                self,
                "Loi",
                f"Khong tim thay thu muc luu video:\n{output_path}",
            )
            return
            QMessageBox.warning(
                self,
                "Lá»—i",
                f"KhÃ´ng tÃ¬m tháº¥y thÆ° má»¥c lÆ°u video:\n{output_path}",
            )
            return

        try:
            self._reveal_in_file_manager(target_path)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Loi",
                f"Khong the mo thu muc video:\n{exc}",
            )
            return
            QMessageBox.warning(
                self,
                "Lá»—i",
                f"KhÃ´ng thá»ƒ má»Ÿ thÆ° má»¥c video:\n{exc}",
            )

    @staticmethod
    def _resolve_output_directory(session):
        output_path = session.get("output_path", "")
        if output_path:
            normalized_path = os.path.abspath(output_path)
            if os.path.isdir(normalized_path):
                return normalized_path
            parent_dir = os.path.dirname(normalized_path)
            if parent_dir and os.path.isdir(parent_dir):
                return parent_dir

        default_dir = os.path.abspath(str(settings.OUTPUT_DIR))
        if os.path.isdir(default_dir):
            return default_dir
        return ""

    @staticmethod
    def _open_with_system(path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    @classmethod
    def _reveal_in_file_manager(cls, target_path):
        normalized_path = os.path.abspath(target_path)
        if sys.platform == "win32" and os.path.isfile(normalized_path):
            subprocess.run(
                ["explorer", "/select,", os.path.normpath(normalized_path)],
                check=False,
            )
            return
        if os.path.isfile(normalized_path):
            normalized_path = os.path.dirname(normalized_path)
        cls._open_with_system(normalized_path)

    def _delete_session(self, session):
        reply = QMessageBox.question(
            self,
            "Xác nhận",
            f"Xóa lịch sử '{session.get('video_name', 'Unknown')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db_service.delete_session(session["id"])
        output_path = session.get("output_path", "")
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        self.refresh()

    def _export_session(self, session):
        nhap = session.get("count_nhap", {})
        xuat = session.get("count_xuat", {})
        event_log = session.get("event_log", [])
        if not nhap and not xuat and not event_log:
            QMessageBox.warning(self, "Cảnh báo", "Không có dữ liệu để xuất!")
            return

        default_name = (
            TimestampOCRService.build_output_file_name_from_events(event_log, "xlsx")
            or f"{session.get('video_name', 'output')}.xlsx"
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
            ok, message = export_to_excel(filepath, nhap, xuat, event_log)
        except Exception as exc:
            ok, message = False, f"Lỗi xuất file: {exc}"

        if ok:
            QMessageBox.information(self, "Kết quả", message)
        else:
            QMessageBox.critical(self, "Kết quả", message)
