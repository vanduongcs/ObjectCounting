"""
Entry point: Khởi tạo và kết nối các thành phần chính của ứng dụng.

Luồng khởi tạo:
    1. Tạo QtDisplayAdapter -- cầu nối thread-safe giữa AI thread và UI thread
    2. Tạo AIService -- nạp model YOLO, dùng adapter để gửi kết quả về UI
    3. Tạo MainWindow -- nhận AIService + adapter, hiển thị giao diện

Sơ đồ kết nối:
    main.py
    |-- QtDisplayAdapter (utils/qt_helpers.py) --- cầu nối thread-safe
    |-- AIService (services/ai_service.py) ------- xử lý AI
    |-- MainWindow (views/main_window.py) -------- giao diện người dùng
"""

import sys
from PyQt6.QtWidgets import QApplication

import configs.settings as settings
from src.services.ai_service import AIService
from src.services import db_service
from src.utils.qt_helpers import QtDisplayAdapter
from src.views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Bước 0: Khởi tạo database SQLite
    db_service.init_db()

    # Bước 1: Tạo adapter -- AIService sẽ gửi frame/count qua đây
    adapter = QtDisplayAdapter()

    # Bước 2: Tạo AI Service -- nạp model YOLO + OpenVINO
    ai_service = AIService(settings.MODEL_PATH, display_handler=adapter)

    # Bước 3: Tạo UI -- nhận AIService để điều khiển, adapter để nhận kết quả
    window = MainWindow(ai_service, adapter)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Hiện lỗi nếu QApplication còn sống
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app:
                QMessageBox.critical(None, "Lỗi nghiêm trọng", str(e))
        except Exception:
            pass
        input("Nhấn Enter để đóng...")
