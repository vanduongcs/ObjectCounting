"""
AI Service: Vòng lặp xử lý chính -- nhận frame -> detect -> vẽ -> đếm -> cache.

Ai gọi module này?
    - VideoThread (views/video_thread.py) gọi detect_and_track() trong background thread.

Module này gọi ai?
    - ObjectDetector (services/detector.py)        -- detect + track đối tượng
    - CounterService (services/counter_service.py) -- đếm nhập/xuất qua vạch
    - QtDisplayAdapter (utils/qt_helpers.py)       -- gửi frame + count về UI thread
    - cache_service (services/cache_service.py)    -- lưu frame annotated ra đĩa
    - db_service (services/db_service.py)           -- lưu kết quả vào SQLite

Luồng xử lý 1 frame:
    Queue.get() -> Detector.track() -> Counter.update()
                -> cache_service.save_frame() -> Adapter.show()
"""

import os
import queue
import time
import threading

import cv2
from datetime import datetime
import re

try:
    import pytesseract
except Exception:
    pytesseract = None

from .detector import ObjectDetector
from .counter_service import CounterService

from . import cache_service
from . import db_service
from src.utils.draw_line import draw_line_with_arrows
import configs.settings as settings



class AIService:
    """
    Điều phối pipeline AI: nhận frame từ Queue, detect, vẽ kết quả, đếm.

    Được tạo bởi: main.py
    Được gọi bởi: VideoThread.run()
    UI toggle:    show_boxes -- được MainWindow thay đổi trực tiếp.
    """

    def __init__(self, model_path, display_handler=None):
        # detector: xử lý YOLO inference (services/detector.py)
        self._model_path = model_path
        self._detector_thread_id = None
        self._pending_conf = None
        self.detector = None

        # display_handler: gửi frame/count về UI qua Qt Signal (utils/qt_helpers.py)
        self.display_handler = display_handler

        # Tùy chọn hiển thị -- MainWindow toggle qua checkbox
        self.show_boxes = True

        # Event log cuối cùng (để export Excel)
        self.last_event_log = []

        # Stop flag -- được set từ UI thread khi user bấm Dừng
        self._stop_requested = False
        self._is_live = False
        self._ocr_ready = False

        if pytesseract is not None:
            tcmd = getattr(settings, "TESSERACT_CMD", "") or ""
            if tcmd:
                try:
                    pytesseract.pytesseract.tesseract_cmd = tcmd
                    self._ocr_ready = True
                except Exception:
                    self._ocr_ready = False
            else:
                # Try common default path, else assume PATH
                default_path = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
                if os.path.exists(default_path):
                    try:
                        pytesseract.pytesseract.tesseract_cmd = default_path
                        self._ocr_ready = True
                    except Exception:
                        self._ocr_ready = False
                else:
                    self._ocr_ready = True

    def set_conf(self, value):
        """Cập nhật confidence cho detector (an toàn khi detector chưa khởi tạo)."""
        self._pending_conf = value
        if self.detector:
            self.detector.conf = value

    def _ensure_detector(self):
        """Khởi tạo detector trong đúng thread chạy inference."""
        current_tid = threading.get_ident()
        if self.detector is None or self._detector_thread_id != current_tid:
            self.detector = ObjectDetector(self._model_path, conf=self._pending_conf)
            self._detector_thread_id = current_tid

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

        # Đảm bảo detector được khởi tạo trong thread hiện tại
        self._ensure_detector()

        # ===== Khởi tạo =====
        start_time = time.time()
        self._frame_index = 0
        self._recording_started = False  # Sẽ khởi tạo khi có frame đầu tiên
        fps_count = 0
        fps_last_time = time.time()

        # Reset tracker state từ lần chạy trước (tránh crash khi restart)
        self.detector.reset_tracker()

        # Lấy FPS thực tế từ extraction thread (chờ tối đa 5 giây)
        fps = settings.DEFAULT_FPS  # fallback
        if extraction_thread and hasattr(extraction_thread, '_fps_ready'):
            if extraction_thread._fps_ready.wait(timeout=5):
                fps = extraction_thread.video_fps
                print(f"[AI] FPS thực tế: {fps}")

        # Xác định nguồn: camera live hay video file
        is_live = isinstance(video_name, str) and video_name.startswith(("http", "rtsp"))
        self._is_live = is_live

        # Cập nhật FPS cho tracker (đặc biệt cho OpenVINO custom tracker)
        if self.detector:
            self.detector.set_fps(fps)

        # Tạo bộ đếm nếu có vạch ảo
        counter = CounterService(
            virtual_line[0], virtual_line[1],
            fps=fps, is_live=is_live,
        ) if virtual_line else None
        self._virtual_line = virtual_line  # Lưu để vẽ lên frame
        self._video_name = video_name or "output"  # Lưu cho start_recording

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

            # Stream: ưu tiên frame mới nhất để giảm độ trễ
            if is_live and getattr(settings, "REALTIME_DROP_FRAMES", False):
                while True:
                    try:
                        nxt = frame_queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt is None:
                        item = None
                        break
                    item = nxt
                if item is None:
                    break

            # Unpack: extractor gửi (frame, frame_pos, timestamp_space?)
            if isinstance(item, tuple) and len(item) >= 3:
                frame, frame_pos, ts_roi = item[0], item[1], item[2]
            elif isinstance(item, tuple) and len(item) == 2:
                frame, frame_pos = item
                ts_roi = None
            else:
                frame, frame_pos, ts_roi = item
            self._frame_index = frame_pos

            self._process_frame(frame, counter, ts_roi=ts_roi)
            fps_count += 1
            now = time.time()
            if now - fps_last_time >= 0.5:
                fps_value = fps_count / (now - fps_last_time)
                fps_count = 0
                fps_last_time = now
                if self.display_handler:
                    self.display_handler.emit_fps(fps_value)

        # ===== Hoàn tất: lưu video + DB =====
        duration = time.time() - start_time

        count_nhap, count_xuat = {}, {}
        if counter:
            count_nhap, count_xuat = counter.get_counts()
            print(f"Kết quả đếm - Nhập: {count_nhap}, Xuất: {count_xuat}")

            # Lưu event log với tên label đã resolve
            names = self.detector.names or {}
            self.last_event_log = []
            for evt in counter.get_event_log():
                self.last_event_log.append({
                    "label": names.get(evt["label"], str(evt["label"])),
                    "action": evt["action"],
                    "timestamp": evt["timestamp"],
                })

            # Nếu là video: OCR timestamp từ ảnh đã crop (sau khi dừng/hết video)
            if not is_live:
                self._finalize_event_log_timestamps()

        # Đóng VideoWriter và lấy đường dẫn file
        output_path, frame_count = cache_service.finish_recording()
        if output_path:
            # Chuyển label ID thành tên khi lưu DB
            names = self.detector.names or {}
            db_nhap = {names.get(k, str(k)): v for k, v in count_nhap.items()}
            db_xuat = {names.get(k, str(k)): v for k, v in count_xuat.items()}
            db_service.save_session(
                video_name=video_name or "unknown",
                output_path=output_path,
                count_nhap=db_nhap,
                count_xuat=db_xuat,
                duration_sec=duration,
                event_log=self.last_event_log,
            )
            print(f"[AI] Lưu xong: {frame_count} frames")

    def _process_frame(self, frame, counter, ts_roi=None):
        """
        Pipeline xử lý 1 frame:
            1. Detector.track()      -> phát hiện + tracking đối tượng
            2. raw_results.plot()    -> vẽ bounding box / mask lên frame
            3. Counter.update()      -> đếm đối tượng qua vạch ảo
            4. cache_service.save()  -> lưu frame ra đĩa
            5. Adapter.show()        -> gửi frame đã vẽ về UI
        """
        # Đồng bộ frame_id cho tracker (đặc biệt OpenVINO custom tracker)
        if self.detector:
            self.detector.advance_tracker_frame(self._frame_index)

        # Bước 1: Detect + track bằng YOLO
        raw_results, detections = self.detector.track(frame)

        # Không phát hiện gì → vẽ line + hiển thị frame gốc
        if not self.detector.has_detections(raw_results):
            if self._virtual_line:
                draw_line_with_arrows(frame, self._virtual_line)
            cache_service.save_frame(frame)
            if self.display_handler:
                self.display_handler.show(frame)
            return

        # Bước 2: Vẽ kết quả lên frame
        annotated_frame = self.detector.render(frame, raw_results, self.show_boxes)

        # Bước 3: Cập nhật bộ đếm + gửi số liệu về UI
        if counter:
            counter.set_frame_index(self._frame_index)
            events = counter.update(detections)
            event_fired = bool(events)
            if event_fired:
                ts_value = None
                if self._is_live:
                    ts_value = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                else:
                    if settings.TIMESTAMP_SPACE_ENABLED and ts_roi is not None:
                        ts_value = self._save_timestamp_crop(ts_roi)
                    if not ts_value:
                        ts_value = counter._get_timestamp()

                if ts_value:
                    for evt in events:
                        evt["timestamp"] = ts_value
            if self.display_handler:
                nhap, xuat = counter.get_counts()
                # Chuyển label ID (0, 1, 2...) thành tên ("person", "car"...)
                names = self.detector.names or {}
                self.display_handler.emit_counts(
                    {names[k]: v for k, v in nhap.items()},
                    {names[k]: v for k, v in xuat.items()},
                )
            # Lưu snapshot frame khi có sự kiện đếm
            if event_fired:
                self._save_count_snapshot(annotated_frame)

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

    def _save_timestamp_crop(self, roi):
        """Lưu ảnh timestamp space và trả về đường dẫn."""
        try:
            if roi is None or roi.size == 0:
                return ""
            settings.TIMESTAMP_SPACE_DIR.mkdir(parents=True, exist_ok=True)
            safe_name = "".join(
                c if c.isalnum() or c in "-_." else "_"
                for c in getattr(self, "_video_name", "video")
            )
            fname = f"{safe_name}_{self._frame_index:08d}.jpg"
            path = settings.TIMESTAMP_SPACE_DIR / fname
            cv2.imwrite(str(path), roi, [cv2.IMWRITE_JPEG_QUALITY, settings.CACHE_IMAGE_QUALITY])
            return str(path)
        except Exception:
            return ""

    def _finalize_event_log_timestamps(self):
        """OCR các ảnh timestamp đã crop và ghi lại vào event_log."""
        if not settings.TIMESTAMP_OCR_ENABLED:
            return
        if pytesseract is None or not self._ocr_ready:
            print("[Timestamp OCR] Tesseract chưa sẵn sàng, bỏ qua OCR.")
            return

        for evt in self.last_event_log:
            ts = evt.get("timestamp", "")
            if not ts or not os.path.exists(ts):
                continue
            text = self._ocr_timestamp_image(ts)
            if text:
                evt["timestamp"] = text
                print(f"[Timestamp OCR] {ts} -> {text}")
            else:
                print(f"[Timestamp OCR] {ts} -> (fail)")

    @staticmethod
    def _ocr_timestamp_image(image_path):
        """OCR ảnh timestamp và trả về chuỗi ngày giờ đã làm sạch."""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return ""
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)
            _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, th2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            config = f"--psm 7 -c tessedit_char_whitelist={settings.TIMESTAMP_OCR_WHITELIST}"

            def _run_ocr(img_in):
                txt = pytesseract.image_to_string(img_in, lang=settings.TIMESTAMP_OCR_LANG, config=config)
                txt = re.sub(r"[^0-9:/\\- ]+", " ", txt)
                txt = re.sub(r"\s+", " ", txt).strip()
                return txt

            texts = [_run_ocr(th1), _run_ocr(th2)]
            pattern = settings.TIMESTAMP_OCR_REGEX
            for t in texts:
                m = re.search(pattern, t)
                if m:
                    # lấy date + time
                    parts = re.findall(r"(\d{2}[-/]\d{2}[-/]\d{4})|(\d{2}:\d{2}:\d{2})", m.group(0))
                    date_part = ""
                    time_part = ""
                    for d, tm in parts:
                        if d:
                            date_part = d
                        if tm:
                            time_part = tm
                    if date_part and time_part:
                        return f"{date_part} {time_part}"
                    return m.group(0)

            # Fallback: tìm date + time riêng
            for t in texts:
                date_m = re.search(r"\d{2}[-/]\d{2}[-/]\d{4}", t)
                time_m = re.search(r"\d{2}:\d{2}:\d{2}", t)
                if date_m and time_m:
                    return f"{date_m.group(0)} {time_m.group(0)}"
            return ""
        except Exception:
            return ""

    def _save_count_snapshot(self, frame):
        """
        Lưu frame snapshot khi có sự kiện đếm vào SNAPSHOT_DIR.

        Filename: {video_name}_{frame_index:08d}_{timestamp}.jpg
        """
        try:
            import datetime
            os.makedirs(str(settings.SNAPSHOT_DIR), exist_ok=True)
            safe_name = "".join(
                c if c.isalnum() or c in "-_." else "_"
                for c in getattr(self, '_video_name', 'video')
            )
            ts = datetime.datetime.now().strftime("%H%M%S_%f")[:9]
            fname = f"{safe_name}_{self._frame_index:08d}_{ts}.jpg"
            path = os.path.join(str(settings.SNAPSHOT_DIR), fname)
            cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, settings.CACHE_IMAGE_QUALITY])
        except Exception as e:
            print(f"[AI] Snapshot lỗi: {e}")
