"""
AI Service: Vòng lặp xử lý chính -- nhận frame -> detect -> vẽ -> đếm -> cache.

Ai gọi module này?
    - VideoThread (views/video_thread.py) gọi detect_and_track() trong background thread.

Module này gọi ai?
    - ObjectDetector (services/detector.py)        -- detect + track đối tượng
    - CounterService (services/counter_service.py) -- đếm nhập/xuất qua vạch
    - TrackletStitcher (services/tracklet_stitcher.py) -- ghép nối ID bị mất
    - QtDisplayAdapter (utils/qt_helpers.py)       -- gửi frame + count về UI thread
    - cache_service (services/cache_service.py)    -- lưu frame annotated ra đĩa
    - db_service (services/db_service.py)           -- lưu kết quả vào SQLite

Luồng xử lý 1 frame:
    Queue.get() -> Detector.track() -> Stitcher.process() -> Counter.update()
                -> cache_service.save_frame() -> Adapter.show()
"""

import os
import queue
import time

import numpy as np
import torch

from .detector import ObjectDetector
from .counter_service import CounterService
from .tracklet_stitcher import TrackletStitcher
from . import cache_service
from . import db_service
from src.utils.draw_line import draw_line_with_arrows
import configs.settings as settings


class AIService:
    """
    Điều phối pipeline AI: nhận frame từ Queue, detect, vẽ kết quả, đếm.

    Được tạo bởi: main.py
    Được gọi bởi: VideoThread.run()
    UI toggle:    show_boxes, show_masks -- được MainWindow thay đổi trực tiếp.
    """

    def __init__(self, model_path, display_handler=None):
        # detector: xử lý YOLO inference (services/detector.py)
        self.detector = ObjectDetector(model_path)

        # display_handler: gửi frame/count về UI qua Qt Signal (utils/qt_helpers.py)
        self.display_handler = display_handler

        # Tùy chọn hiển thị -- MainWindow toggle qua checkbox
        self.show_boxes = True
        self.show_masks = False

        # Event log cuối cùng (để export Excel)
        self.last_event_log = []

        # Stop flag -- được set từ UI thread khi user bấm Dừng
        self._stop_requested = False

    def detect_and_track(self, extraction_thread=None, frame_queue=None,
                         virtual_line=None, video_name=""):
        """
        Vòng lặp xử lý chính. Chạy liên tục cho đến khi hết video.

        Args:
            extraction_thread: FrameExtractionThread -- để kiểm tra còn chạy không.
            frame_queue: Queue chứa frame từ FrameExtractionThread.
            virtual_line: Tuple (p1, p2) -- vạch ảo để đếm. None = không đếm.
            video_name: Tên video gốc (để lưu vào DB).
        """
        if frame_queue is None:
            return

        # Reset stop flag
        self._stop_requested = False

        # ===== Khởi tạo =====
        start_time = time.time()
        self._frame_index = 0
        self._recording_started = False  # Sẽ khởi tạo khi có frame đầu tiên

        # Reset tracker state từ lần chạy trước (tránh crash khi restart)
        self.detector._reset_tracker()

        # Lấy FPS thực tế từ extraction thread (chờ tối đa 5 giây)
        fps = settings.DEFAULT_FPS  # fallback
        if extraction_thread and hasattr(extraction_thread, '_fps_ready'):
            if extraction_thread._fps_ready.wait(timeout=5):
                fps = extraction_thread.video_fps
                print(f"[AI] FPS thực tế: {fps}")

        # Cấu hình tracker với FPS động
        self.detector.configure_tracker(fps)

        # Xác định nguồn: camera live hay video file
        is_live = isinstance(video_name, str) and video_name.startswith(("http", "rtsp"))

        # Tạo bộ đếm nếu có vạch ảo
        counter = CounterService(
            virtual_line[0], virtual_line[1],
            fps=fps, is_live=is_live,
        ) if virtual_line else None
        self._virtual_line = virtual_line  # Lưu để vẽ lên frame
        self._video_name = video_name or "output"  # Lưu cho start_recording

        # Tạo stitcher ghép nối quỹ đạo bị đứt
        self.stitcher = TrackletStitcher(
            fps=fps,
            max_lost_seconds=settings.TRACK_BUFFER_SECONDS,
        )

        # ===== Vòng lặp chính =====
        while not self._stop_requested:
            try:
                item = frame_queue.get(timeout=0.5)
            except queue.Empty:
                if extraction_thread and not extraction_thread.isRunning():
                    break
                continue

            if item is None:
                break

            # Unpack: extractor gửi (frame, frame_pos) với frame_pos là vị trí thực trong video
            frame, frame_pos = item
            self._frame_index = frame_pos

            self._process_frame(frame, counter)

        # ===== Hoàn tất: lưu video + DB =====
        duration = time.time() - start_time

        count_nhap, count_xuat = {}, {}
        if counter:
            count_nhap, count_xuat = counter.get_counts()
            print(f"Kết quả đếm - Nhập: {count_nhap}, Xuất: {count_xuat}")

            # Lưu event log với tên label đã resolve
            names = self.detector.yolo_model.names
            self.last_event_log = []
            for evt in counter.get_event_log():
                self.last_event_log.append({
                    "label": names.get(evt["label"], str(evt["label"])),
                    "action": evt["action"],
                    "timestamp": evt["timestamp"],
                })

        # Đóng VideoWriter và lấy đường dẫn file
        output_path, frame_count = cache_service.finish_recording()
        if output_path:
            # Chuyển label ID thành tên khi lưu DB
            names = self.detector.yolo_model.names
            db_nhap = {names.get(k, str(k)): v for k, v in count_nhap.items()}
            db_xuat = {names.get(k, str(k)): v for k, v in count_xuat.items()}
            db_service.save_session(
                video_name=video_name or "unknown",
                output_path=output_path,
                count_nhap=db_nhap,
                count_xuat=db_xuat,
                duration_sec=duration,
            )
            print(f"[AI] Lưu xong: {frame_count} frames")

    def _process_frame(self, frame, counter):
        """
        Pipeline xử lý 1 frame:
            1. Detector.track()      -> phát hiện + tracking đối tượng
            1.5 Stitcher.process()   -> ghép nối ID bị mất
            2. raw_results.plot()    -> vẽ bounding box / mask lên frame
            3. Counter.update()      -> đếm đối tượng qua vạch ảo
            4. cache_service.save()  -> lưu frame ra đĩa
            5. Adapter.show()        -> gửi frame đã vẽ về UI
        """
        # Bước 1: Detect + track bằng YOLO
        raw_results, detections = self.detector.track(frame)

        # Bước 1.5: Ghép nối ID bị mất (tracklet stitching)
        if hasattr(self, 'stitcher'):
            # Cập nhật frame size cho stitcher (lần đầu hoặc khi resolution thay đổi)
            h, w = frame.shape[:2]
            self.stitcher.set_frame_size(w, h)
            detections = self.stitcher.process(detections)

        # Không phát hiện gì → vẽ line + hiển thị frame gốc
        if not raw_results:
            if self._virtual_line:
                draw_line_with_arrows(frame, self._virtual_line)
            self._frame_index += 1
            cache_service.save_frame(frame, self._frame_index)
            if self.display_handler:
                self.display_handler.show(frame)
            return

        # Bước 2: Lọc NaN/Inf từ tracker rồi vẽ kết quả lên frame
        # ByteTrack có thể tạo bbox degenerate (height≈0) → chia 0 → NaN
        result = raw_results[0]
        if result.boxes is not None and len(result.boxes):
            boxes_data = result.boxes.data
            valid_mask = torch.isfinite(boxes_data).all(dim=1)
            if not valid_mask.all():
                result.boxes = result.boxes[valid_mask]

        annotated_frame = result.plot(
            boxes=self.show_boxes, masks=False  # YOLO26s là model detect, không có mask
        )

        # Bước 3: Cập nhật bộ đếm + gửi số liệu về UI
        if counter:
            counter.set_frame_index(self._frame_index)
            counter.update(detections)
            if self.display_handler:
                nhap, xuat = counter.get_counts()
                # Chuyển label ID (0, 1, 2...) thành tên ("person", "car"...)
                names = self.detector.yolo_model.names
                self.display_handler.emit_counts(
                    {names[k]: v for k, v in nhap.items()},
                    {names[k]: v for k, v in xuat.items()},
                )

        # Bước 4: Vẽ vạch ảo + lưu frame vào video
        if self._virtual_line:
            draw_line_with_arrows(annotated_frame, self._virtual_line)

        # Khởi tạo VideoWriter khi có frame đầu tiên (để biết kích thước)
        if not self._recording_started:
            h, w = annotated_frame.shape[:2]
            cache_service.start_recording(
                fps=settings.OUTPUT_VIDEO_FPS,
                frame_size=(w, h),
                video_name=getattr(self, '_video_name', 'output'),
            )
            self._recording_started = True

        cache_service.save_frame(annotated_frame)

        # Bước 5: Gửi frame đã annotate về UI
        if self.display_handler:
            self.display_handler.show(annotated_frame)
