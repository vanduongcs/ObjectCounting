"""
History Panel: Hiển thị lịch sử xử lý video từ SQLite.

Ai gọi module này?
    - MainWindow nhúng HistoryPanel vào layout (sidebar hoặc tab).

Module này gọi ai?
    - db_service.get_all_sessions() -- lấy danh sách sessions
    - db_service.delete_session()   -- xóa session
    - Mở video bằng media player hệ thống (os.startfile / subprocess)
"""

import os
import subprocess
import sys

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import Qt

from src.services import db_service
from src.utils.export_excel_processor import export_to_excel


class HistoryPanel(QWidget):
    """Panel hiển thị danh sách video đã xử lý."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        title = QLabel("Lịch sử")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Đường kẻ phân cách
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        layout.addWidget(sep)

        # Scroll area cho danh sách
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

    def refresh(self):
        """Đọc lại danh sách từ DB và hiển thị (mới nhất trước)."""
        # Xóa items cũ
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sessions = db_service.get_all_sessions()

        if not sessions:
            empty_label = QLabel("Chưa có lịch sử")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #888; padding: 20px;")
            self._list_layout.addWidget(empty_label)
            return

        for session in sessions:
            card = self._create_session_card(session)
            self._list_layout.addWidget(card)

    def _create_session_card(self, session):
        """Tạo 1 card hiển thị thông tin session."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
            }
            QFrame:hover {
                border-color: #666;
                background: #2a2a2a;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 6, 8, 6)

        # Tên video
        name_label = QLabel(session['video_name'])
        name_label.setStyleSheet("font-weight: bold; font-size: 12px; border: none;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # Thời gian
        time_str = session['created_at']
        dur = session.get("duration_sec", 0)
        if dur > 0:
            mins, secs = int(dur // 60), int(dur % 60)
            time_str += f"  —  {mins}m {secs}s"

        time_label = QLabel(time_str)
        time_label.setStyleSheet("color: #999; font-size: 10px; border: none;")
        layout.addWidget(time_label)

        # Kết quả đếm
        nhap = session.get("count_nhap", {})
        xuat = session.get("count_xuat", {})
        if nhap or xuat:
            all_labels = sorted(set(list(nhap.keys()) + list(xuat.keys())))
            parts = []
            for lbl in all_labels:
                n = nhap.get(lbl, 0)
                x = xuat.get(lbl, 0)
                parts.append(f"{lbl}: {n} nhập / {x} xuất")
            count_label = QLabel("\n".join(parts))
            count_label.setStyleSheet(
                "font-size: 11px; color: #ccc; padding-left: 4px; border: none;"
            )
            layout.addWidget(count_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        play_btn = QPushButton("Xem video")
        play_btn.setFixedHeight(26)
        play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        play_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background: #3a3a3a; }
        """)
        play_btn.clicked.connect(lambda _, s=session: self._play_video(s))
        btn_row.addWidget(play_btn)

        export_btn = QPushButton("Xuất Excel")
        export_btn.setFixedHeight(26)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background: #3a3a3a; }
        """)
        export_btn.clicked.connect(lambda _, s=session: self._export_session(s))
        btn_row.addWidget(export_btn)

        btn_row.addStretch()

        del_btn = QPushButton("Xóa")
        del_btn.setFixedHeight(26)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
                color: #c55;
            }
            QPushButton:hover { background: #3a2020; border-color: #c55; }
        """)
        del_btn.clicked.connect(lambda _, s=session: self._delete_session(s))
        btn_row.addWidget(del_btn)

        layout.addLayout(btn_row)
        return card

    def _play_video(self, session):
        """Mở video bằng media player hệ thống."""
        path = session.get("output_path", "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Lỗi", f"Không tìm thấy video:\n{path}")
            return

        # Mở bằng ứng dụng mặc định của OS
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể mở video:\n{e}")

    def _delete_session(self, session):
        """Xóa session sau khi xác nhận."""
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Xóa lịch sử '{session['video_name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            db_service.delete_session(session["id"])

            # Xóa luôn file video output nếu có
            path = session.get("output_path", "")
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

            self.refresh()

    def _export_session(self, session):
        """Xuất Excel cho session đã chọn."""
        nhap = session.get("count_nhap", {})
        xuat = session.get("count_xuat", {})
        event_log = session.get("event_log", [])
        if not nhap and not xuat:
            QMessageBox.warning(self, "Cảnh báo", "Không có dữ liệu để xuất!")
            return

        default_name = f"{session.get('video_name', 'output')}.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Lưu file Excel", default_name, "Excel Files (*.xlsx);;All Files (*)"
        )
        if not filepath:
            return

        ok, msg = export_to_excel(filepath, nhap, xuat, event_log)
        if ok:
            QMessageBox.information(self, "Kết quả", msg)
        else:
            QMessageBox.critical(self, "Kết quả", msg)
