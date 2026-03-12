"""
Frame Extractor: Thread trích xuất frame từ video/camera (Producer).

Ai gọi module này?
    - video_service.start_extraction() tạo thread và start.
    - MainWindow điều khiển: set_fps(), set_resolution(), set_rotation(), pause(), stop().

Module này gọi ai?
    - OpenCV (cv2.VideoCapture) -- đọc frame từ video file hoặc camera stream.

Mô hình Producer-Consumer:
    FrameExtractionThread (Producer)
        | đọc frame từ video
        | transform (xoay + resize)
        | đẩy vào Queue (drop frame cũ nếu queue đầy)
    Queue
        |
    AIService (Consumer) -- lấy frame từ queue để detect
"""

import queue
import time
import cv2
from PyQt6.QtCore import QThread, pyqtSignal
import threading

import configs.settings as settings


# Lookup table cho rotation (export để main_window dùng chung)
ROTATION_MAP = {
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}



class FrameExtractionThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, video_path, frame_queue=None):
        super().__init__()
        self.video_path = str(video_path)
        self.frame_queue = frame_queue
        self.is_running = True
        self.is_paused = False

        self.target_width = 0
        self.rotation_angle = 0

        # FPS thực tế của video (được set khi video mở xong)
        self.video_fps = settings.DEFAULT_FPS  # mặc định
        self._fps_ready = threading.Event()  # Signal cho AIService biết FPS đã sẵn sàng

    # --- Setters ---

    def set_resolution(self, width):
        self.target_width = width

    def set_rotation(self, angle):
        self.rotation_angle = angle

    def pause(self):
        self.is_paused = True

    def resume(self):
        self.is_paused = False

    # --- Core ---

    def run(self):
        """Đọc frame -> transform -> đẩy vào Queue.
        Video file: blocking put (đảm bảo mọi frame được xử lý).
        Stream: drop frame cũ nếu queue đầy (real-time).
        """
        self._is_stream = self.video_path.startswith(("http", "rtsp"))

        cap = cv2.VideoCapture(self.video_path)
        if self._is_stream:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print(f"Cannot open video: {self.video_path}")
            self.finished_signal.emit()
            return

        video_fps = self._get_video_fps(cap, self._is_stream)
        self.video_fps = video_fps
        self._fps_ready.set()  # Báo cho AIService biết FPS đã sẵn sàng
        consecutive_failures = 0
        frame_pos = 0  # Vị trí frame thực tế trong video

        while self.is_running:
            if self.is_paused:
                time.sleep(0.1)
                continue

            ret, frame = cap.read()
            if not ret:
                if self._is_stream:
                    consecutive_failures += 1
                    if consecutive_failures > settings.MAX_STREAM_FAILURES:
                        print("Stream mất kết nối quá lâu, dừng.")
                        break
                    time.sleep(0.1)
                    cap.release()
                    cap = cv2.VideoCapture(self.video_path)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    continue
                else:
                    break

            consecutive_failures = 0
            frame_pos += 1

            # Transform: xoay trước (để ROI trùng với ảnh user thấy)
            frame = self._apply_rotation(frame)

            # Timestamp space trước khi resize (dùng frame đã xoay)
            ts_roi = self._crop_timestamp_space(frame) if settings.TIMESTAMP_SPACE_ENABLED else None

            # Resize sau cùng
            frame = self._apply_resize(frame, self._is_stream)

            # Đẩy vào queue kèm vị trí frame
            self._enqueue_frame((frame, frame_pos, ts_roi))

        cap.release()
        self.is_running = False
        self._enqueue_frame(None)
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False
        self.wait()

    # --- Private helpers ---

    @staticmethod
    def _get_video_fps(cap, is_stream):
        """Lấy FPS gốc, fallback nếu bất thường."""
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps < 1:
            return settings.DEFAULT_FPS if is_stream else settings.DEFAULT_VIDEO_FPS
        if is_stream and fps < 10:
            return settings.DEFAULT_FPS
        return fps

    def _apply_rotation(self, frame):
        """Xoay frame theo góc hiện tại."""
        rotation = ROTATION_MAP.get(self.rotation_angle)
        if rotation is not None:
            frame = cv2.rotate(frame, rotation)
        return frame

    def _apply_resize(self, frame, is_stream):
        """Resize frame."""
        width = self.target_width
        if width == 0 and is_stream:
            width = settings.DEFAULT_STREAM_WIDTH

        if width > 0:
            h, w = frame.shape[:2]
            if w != width:
                scale = width / w
                frame = cv2.resize(frame, (width, int(h * scale)))

        return frame

    @staticmethod
    def _crop_timestamp_space(frame):
        """Crop vùng timestamp space theo tỉ lệ settings.TIMESTAMP_SPACE_REL."""
        try:
            x, y, w, h = settings.TIMESTAMP_SPACE_REL
            ih, iw = frame.shape[:2]
            x1 = max(0, int(x * iw))
            y1 = max(0, int(y * ih))
            x2 = min(iw, int((x + w) * iw))
            y2 = min(ih, int((y + h) * ih))
            if x2 <= x1 or y2 <= y1:
                return None
            return frame[y1:y2, x1:x2].copy()
        except Exception:
            return None

    def _enqueue_frame(self, item):
        """
        Đẩy frame vào queue.
        Video file: chờ (block) nếu queue đầy → không mất frame nào.
        Stream: drop frame cũ để giữ real-time.
        None sentinel: luôn đẩy vào (force).
        """
        if self.frame_queue is None:
            return

        # None sentinel → luôn đẩy vào để AI thread biết dừng
        if item is None:
            try:
                self.frame_queue.put(None, timeout=2)
            except queue.Full:
                pass
            return

        if self._is_stream:
            # Stream: drop frame cũ nếu queue đầy (giữ real-time)
            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self.frame_queue.put(item, block=False)
            except queue.Full:
                pass
        else:
            # Video file: blocking put → mọi frame đều được xử lý
            while self.is_running:
                try:
                    self.frame_queue.put(item, timeout=0.5)
                    break
                except queue.Full:
                    continue

    @staticmethod
    def _sleep_for_fps(fps, start_time):
        """Sleep vừa đủ để giữ đúng tốc độ FPS (dùng cho stream)."""
        delay = 1.0 / fps if fps > 0 else 0.04
        remaining = delay - (time.time() - start_time)
        if remaining > 0:
            time.sleep(remaining)
