"""Helpers for choosing a source and starting frame extraction."""

import queue

import cv2
from PyQt6.QtWidgets import QFileDialog

import configs.settings as settings
from src.services.frame_extractor import FrameExtractionThread
from src.utils.source_utils import is_stream_source


def select_video_file():
    """Open the file picker and return a selected local video path."""
    file_path, _ = QFileDialog.getOpenFileName(
        None,
        "Chọn Video",
        str(settings.BASE_DIR),
        "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*)",
    )
    return file_path or None


def _open_capture(video_path):
    capture = cv2.VideoCapture(str(video_path))
    if is_stream_source(str(video_path)):
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def get_first_frame(video_path):
    """Read the first frame of a video or stream for preview."""
    capture = _open_capture(video_path)
    try:
        ok, frame = capture.read()
        return frame if ok else None
    finally:
        capture.release()


def start_extraction(video_path):
    """Create the producer thread and queue used by the AI pipeline."""
    is_stream = is_stream_source(str(video_path))
    max_queue_size = (
        settings.MAX_QUEUE_SIZE_STREAM if is_stream else settings.MAX_QUEUE_SIZE
    )
    frame_queue = queue.Queue(maxsize=max_queue_size)
    thread = FrameExtractionThread(video_path, frame_queue=frame_queue)
    thread.start()
    return thread, frame_queue
