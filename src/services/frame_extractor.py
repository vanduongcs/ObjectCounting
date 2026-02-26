"""
Frame Extractor: Thread trích xuất frame từ video/camera.

- Producer: Đẩy frame vào Queue.
- Sync Real-time: Điều chỉnh tốc độ đọc khớp FPS video gốc.
- Drop-oldest: Nếu Queue đầy (AI chậm), bỏ frame cũ nhất để luôn xử lý frame mới.
"""

import queue
import time
import cv2
from PyQt6.QtCore import QThread, pyqtSignal


class FrameExtractionThread(QThread):
    finished_signal = pyqtSignal()

    def __init__(self, video_path, frame_queue=None):
        """
        Args:
            video_path: Đường dẫn video/camera.
            frame_queue: Hàng đợi chứa frame (để AI xử lý).
        """
        super().__init__()
        self.video_path = str(video_path)
        self.frame_queue = frame_queue
        self.is_running = True
        self.is_paused = False
        
        # Cấu hình mặc định
        self.target_fps = 0    # 0 = dùng FPS gốc của video
        self.target_width = 0  # 0 = giữ nguyên kích thước gốc
        self.rotation_angle = 0 # 0, 90, 180, 270

    def set_fps(self, fps):
        """Đặt FPS trích xuất (0 = FPS gốc)."""
        self.target_fps = fps

    def set_resolution(self, width):
        """Đặt chiều rộng frame (0 = kích thước gốc)."""
        self.target_width = width

    def set_rotation(self, angle):
        """Đặt góc xoay (0, 90, 180, 270)."""
        self.rotation_angle = angle

    def pause(self):
        """Tạm dừng."""
        self.is_paused = True

    def resume(self):
        """Tiếp tục."""
        self.is_paused = False

    def run(self):
        """Đọc frame theo tốc độ thực -> Đẩy vào Queue."""
        # Detect stream
        is_stream = self.video_path.startswith("http") or self.video_path.startswith("rtsp")
        
        cap = cv2.VideoCapture(self.video_path)
        
        if is_stream:
            # Giảm buffer để giảm độ trễ (Buffer bloat)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print(f"Cannot open video: {self.video_path}")
            self.finished_signal.emit()
            return

        # Lấy FPS gốc
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps < 1:
            video_fps = 30 if is_stream else 25
        elif is_stream and video_fps < 10:
            video_fps = 30
        
        # Biến đếm lỗi liên tiếp (dùng cho reconnect stream)
        consecutive_failures = 0
        
        while self.is_running:
            # Xử lý tạm dừng
            if self.is_paused:
                time.sleep(0.1)
                continue

            start_time = time.time()

            # === ĐỌC FRAME ===
            frame = None
            
            if is_stream:
                # Đọc frame từ stream
                ret, frame = cap.read()
                if not ret:
                    # Mất kết nối? Thử reconnect
                    consecutive_failures += 1
                    if consecutive_failures > 30:
                        print("Stream mất kết nối quá lâu, dừng.")
                        break
                    time.sleep(0.1)
                    cap.release()
                    cap = cv2.VideoCapture(self.video_path)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    continue
            else:
                # Với Video File: Đọc bình thường
                ret, frame = cap.read()
                if not ret:
                    break
            
            if frame is None:
                continue
            
            # Reset bộ đếm lỗi khi đọc thành công
            consecutive_failures = 0

            # Xoay frame nếu cần (Trước khi resize để giữ chất lượng)
            if self.rotation_angle == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation_angle == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation_angle == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # Resize nếu cần
            # Với stream: Nếu user chưa set resolution, tự động resize xuống 640
            effective_width = self.target_width
            if effective_width == 0 and is_stream:
                effective_width = 640  # Auto-downscale stream cho mượt

            if effective_width > 0 and frame is not None:
                h, w = frame.shape[:2]
                if w != effective_width:
                    scale = effective_width / w
                    new_h = int(h * scale)
                    frame = cv2.resize(frame, (effective_width, new_h))

            if self.frame_queue is not None:
                # Nếu Queue đầy -> Drop frame cũ nhất
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass

                # Đẩy frame mới vào Queue
                try:
                    self.frame_queue.put(frame, block=False)
                except queue.Full:
                    pass

            # === SLEEP LOGIC ===
            if is_stream:
                # Stream: Không sleep (đã drain buffer, cap.grab() tự giới hạn tốc độ)
                pass
            else:
                # Video File: Sleep để giữ đúng tốc độ FPS
                current_fps = self.target_fps if self.target_fps > 0 else video_fps
                frame_delay = 1.0 / current_fps if current_fps > 0 else 0.04
                sleep_time = frame_delay - (time.time() - start_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        cap.release()
        self.is_running = False

        # Gửi tín hiệu kết thúc (None) vào Queue
        if self.frame_queue is not None:
            try:
                self.frame_queue.put(None, timeout=1)
            except Exception:
                pass

        self.finished_signal.emit()

    def stop(self):
        """Dừng thread thủ công."""
        self.is_running = False
        self.wait()

