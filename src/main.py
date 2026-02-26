"""
Entry point của ứng dụng.
Khởi tạo QApplication, các service (AI, Adapter) và cửa sổ chính (MainWindow).
"""

import sys
from PyQt6.QtWidgets import QApplication

import configs.settings as settings
from src.services.ai_service import AIService
from src.utils.qt_helpers import QtDisplayAdapter
from src.views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Adapter: Cầu nối gửi ảnh từ AI thread sang UI thread
    adapter = QtDisplayAdapter()

    # AIService: Quản lý logic AI (detect, track, count)
    ai_service = AIService(
        settings.MODEL_PATH,
        display_handler=adapter
    )

    # MainWindow: Giao diện chính
    window = MainWindow(ai_service, adapter)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()