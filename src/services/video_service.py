"""
Video Service: Các hàm tiện ích xử lý video.

- Chọn file video.
- Lấy frame đầu tiên (preview).
- Khởi tạo luồng trích xuất frame.
"""

import os
import queue
import cv2
from PyQt6.QtWidgets import QFileDialog

import configs.settings as settings
from src.services.frame_extractor import FrameExtractionThread


def select_video_file():
    """Mở hộp thoại chọn file video."""
    file_path, _ = QFileDialog.getOpenFileName(
        None,
        "Chọn Video",
        str(settings.BASE_DIR),
        "Video Files (*.mp4)"
    )
    return file_path or None


def get_first_frame(video_path):
    """Lấy frame đầu tiên của video để hiển thị preview."""
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def start_extraction(video_path):
    """
    Khởi tạo Queue và Thread trích xuất frame.
    Trả về (thread, queue).
    """
    # Dọn dẹp cache cũ nếu có
    try:
        if os.path.exists(settings.CACHE_DIR):
            for f in os.listdir(settings.CACHE_DIR):
                if f.lower().endswith(settings.VALID_EXTENSION):
                    os.remove(os.path.join(settings.CACHE_DIR, f))
    except Exception as e:
        print(f"Lỗi dọn cache: {e}")

    # Tạo Queue mới
    frame_queue = queue.Queue(maxsize=settings.MAX_QUEUE_SIZE)
    # Khởi tạo Thread
    extraction_thread = FrameExtractionThread(video_path, frame_queue=frame_queue)
    extraction_thread.start()

    return extraction_thread, frame_queue
