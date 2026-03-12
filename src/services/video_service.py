"""
Video Service: Tiện ích chọn video và khởi tạo trích xuất frame.

Ai gọi module này?
    - MainWindow (views/main_window.py) gọi khi user chọn video hoặc bấm "Bắt đầu".

Module này gọi ai?
    - FrameExtractionThread (services/frame_extractor.py) -- tạo thread trích xuất frame.
    - configs.settings -- lấy BASE_DIR, MAX_QUEUE_SIZE.

Các function:
    select_video_file() -- mở dialog chọn file     -- gọi bởi MainWindow.start_choosing()
    get_first_frame()   -- lấy frame preview       -- gọi bởi MainWindow.setup_video()
    start_extraction()  -- tạo thread + queue      -- gọi bởi MainWindow.start_processing()
"""

import queue
import cv2
from PyQt6.QtWidgets import QFileDialog

import configs.settings as settings
from src.services.frame_extractor import FrameExtractionThread


def select_video_file():
    """Mở hộp thoại chọn file video. Trả về path hoặc None."""
    file_path, _ = QFileDialog.getOpenFileName(
        None, "Chọn Video", str(settings.BASE_DIR),
        "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)"
    )
    return file_path or None


def get_first_frame(video_path):
    """Lấy frame đầu tiên của video để hiển thị preview trên UI."""
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def start_extraction(video_path):
    """
    Khởi tạo Queue + Thread trích xuất frame.

    Tạo mô hình Producer-Consumer:
        FrameExtractionThread (Producer) -> Queue -> AIService (Consumer)

    Returns:
        (thread, queue) -- MainWindow giữ reference để điều khiển (pause/stop/set_fps).
    """
    is_stream = str(video_path).startswith(("http", "rtsp"))
    max_q = settings.MAX_QUEUE_SIZE_STREAM if is_stream else settings.MAX_QUEUE_SIZE
    frame_queue = queue.Queue(maxsize=max_q)
    thread = FrameExtractionThread(video_path, frame_queue=frame_queue)
    thread.start()
    return thread, frame_queue
