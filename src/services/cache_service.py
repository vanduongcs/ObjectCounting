"""
Cache Service: Ghi frame annotated trực tiếp vào video MP4.

Ai gọi module này?
    - AIService._process_frame() gọi save_frame() mỗi frame
    - AIService.detect_and_track() gọi start_recording() trước vòng lặp,
      và finish_recording() sau khi kết thúc.

Luồng:
    start_recording(fps, size, name) → [save_frame() × N] → finish_recording() → path
"""

import os
import threading
import queue as queue_module
from datetime import datetime

import cv2

import configs.settings as settings

# Background writer thread — tránh I/O block AI loop
_write_queue = None
_writer_thread = None
_video_writer = None
_output_path = None
_frame_count = 0


def _writer_loop():
    """Thread ghi frame trực tiếp vào VideoWriter (chạy nền)."""
    global _frame_count
    while True:
        item = _write_queue.get()
        if item is None:  # Sentinel → dừng thread
            break
        try:
            _video_writer.write(item)
            _frame_count += 1
        except Exception as e:
            print(f"[Cache] Write error: {e}")


def start_recording(fps, frame_size, video_name="output"):
    """
    Mở VideoWriter và khởi tạo writer thread.

    Args:
        fps: FPS cho video output.
        frame_size: (width, height) của frame.
        video_name: Tên cơ sở cho file output.

    Returns:
        str — đường dẫn file MP4 sẽ được ghi.
    """
    global _write_queue, _writer_thread, _video_writer, _output_path, _frame_count

    # Dọn dẹp nếu còn session cũ
    finish_recording()

    _frame_count = 0

    # Tạo thư mục output
    os.makedirs(str(settings.OUTPUT_DIR), exist_ok=True)

    # Tạo tên file unique theo timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in video_name)
    _output_path = os.path.join(str(settings.OUTPUT_DIR), f"{safe_name}_{timestamp}.mp4")

    # Mở VideoWriter
    w, h = frame_size
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    _video_writer = cv2.VideoWriter(_output_path, fourcc, fps, (w, h))

    if not _video_writer.isOpened():
        print(f"[Cache] Cannot open VideoWriter: {_output_path}")
        _video_writer = None
        _output_path = None
        return None

    # Khởi tạo writer thread
    _write_queue = queue_module.Queue(maxsize=200)
    _writer_thread = threading.Thread(target=_writer_loop, daemon=True)
    _writer_thread.start()

    print(f"[Cache] Recording started: {_output_path}")
    return _output_path


def save_frame(frame):
    """
    Ghi 1 frame vào video (non-blocking).

    Frame được đẩy vào queue, thread nền sẽ ghi vào VideoWriter.
    """
    if _write_queue is None or _video_writer is None:
        return
    try:
        _write_queue.put_nowait(frame.copy())
    except queue_module.Full:
        pass  # Bỏ frame nếu queue đầy (ưu tiên không block AI)


def finish_recording():
    """
    Dừng writer thread và đóng VideoWriter.

    Returns:
        (output_path, frame_count) hoặc (None, 0) nếu không có recording.
    """
    global _writer_thread, _write_queue, _video_writer, _output_path, _frame_count

    path = _output_path
    count = _frame_count

    if _write_queue is not None and _writer_thread is not None:
        _write_queue.put(None)  # Sentinel dừng thread
        _writer_thread.join(timeout=30)
        _writer_thread = None
        _write_queue = None

    if _video_writer is not None:
        _video_writer.release()
        _video_writer = None
        print(f"[Cache] Recording finished: {path} ({count} frames)")

    _output_path = None
    _frame_count = 0

    if path and count == 0:
        # Xóa file rỗng
        try:
            os.remove(path)
        except OSError:
            pass
        return None, 0

    return path, count
