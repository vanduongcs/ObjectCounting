"""Main AI pipeline: consume frames, detect, count, render, and save output."""

import os
import queue
import time
import threading

import cv2
from datetime import datetime

from .detector import ObjectDetector
from .counter_service import CounterService
from .tracklet_stitcher import TrackletStitcher
from .timestamp_ocr import TimestampOCRService

from . import cache_service
from . import db_service
from src.utils.draw_line import draw_line_with_arrows
from src.utils.source_utils import is_stream_source
import configs.settings as settings

class AIService:
    """Coordinate detection, counting, OCR, and UI updates for one session."""

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
        self.show_box_conf = False

        # Event log cuối cùng (để export Excel)
        self.last_event_log = []

        # Stop flag -- được set từ UI thread khi user bấm Dừng
        self._stop_requested = False
        self._is_live = False
        self._stitcher = None
        self._video_fps = float(settings.DEFAULT_FPS)
        self._timestamp_session_dir = None
        self._run_token = 0
        self._ocr_contexts = {}
        self._last_emitted_counts = None
        self._reuse_preloaded_detector = False
        self.timestamp_ocr = TimestampOCRService()

    def set_conf(self, value):
        """Cập nhật confidence cho detector (an toàn khi detector chưa khởi tạo)."""
        self._pending_conf = value
        if self.detector:
            self.detector.conf = value

    def _ensure_detector(self):
        """Khởi tạo detector khi cần, hoặc tái dùng bản đã preload từ lúc startup."""
        current_tid = threading.get_ident()
        if self.detector is None:
            self.detector = ObjectDetector(self._model_path, conf=self._pending_conf)
            self._detector_thread_id = current_tid
            return

        if self._detector_thread_id != current_tid and not self._reuse_preloaded_detector:
            self.detector = ObjectDetector(self._model_path, conf=self._pending_conf)
            self._detector_thread_id = current_tid

    def preload_detector(self):
        """Warm up detector before showing the main window to avoid first-run lag."""
        self._reuse_preloaded_detector = True
        self._ensure_detector()

    @staticmethod
    def _resolve_video_fps(extraction_thread):
        fps = settings.DEFAULT_FPS
        if extraction_thread and hasattr(extraction_thread, "_fps_ready"):
            if extraction_thread._fps_ready.wait(timeout=5):
                fps = extraction_thread.video_fps
                print(f"[AI] FPS thực tế: {fps}")
        return fps if fps and fps > 0 else float(settings.DEFAULT_FPS)

    @staticmethod
    def _unpack_queue_item(item):
        if isinstance(item, tuple):
            if len(item) >= 3:
                return item[0], item[1], item[2]
            if len(item) == 2:
                return item[0], item[1], None
            if len(item) == 1:
                return item[0], 0, None
        return item, 0, None

    def _consume_latest_live_item(self, frame_queue, item):
        if not getattr(settings, "REALTIME_DROP_FRAMES", False):
            return item

        latest_item = item
        while True:
            try:
                next_item = frame_queue.get_nowait()
            except queue.Empty:
                return latest_item
            if next_item is None:
                return None
            latest_item = next_item

    def _sync_file_item_to_wall_clock(self, frame_queue, item, fps, start_time):
        if not getattr(settings, "VIDEO_REALTIME_SYNC", False) or fps <= 0:
            return item

        max_lag = float(getattr(settings, "VIDEO_REALTIME_MAX_LAG_SEC", 0.5))
        latest_item = item
        while True:
            _, frame_pos, _ = self._unpack_queue_item(latest_item)
            wall_time = time.time() - start_time
            lag = wall_time - (frame_pos / fps)
            if lag <= max_lag:
                return latest_item
            try:
                latest_item = frame_queue.get_nowait()
            except queue.Empty:
                return latest_item
            if latest_item is None:
                return None

    def _capture_timestamp_roi_enabled(self, ts_roi):
        return (
            settings.TIMESTAMP_SPACE_ENABLED
            and settings.TIMESTAMP_OCR_ENABLED
            and self.timestamp_ocr.ready
            and ts_roi is not None
        )

    def _resolve_label_names(self):
        return self.detector.names or {}

    def _build_runtime_events(self, events, counter, ts_roi):
        if not events:
            return [], ""

        fallback_timestamp = (
            datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            if self._is_live
            else counter._get_timestamp()
        )
        if not fallback_timestamp:
            return [], ""

        ocr_path = ""
        if (not self._is_live) and self._capture_timestamp_roi_enabled(ts_roi):
            ocr_path = self._save_timestamp_crop(ts_roi)

        names = self._resolve_label_names()
        runtime_events = []
        for event in events:
            runtime_event = {
                "label": names.get(event.get("label"), str(event.get("label"))),
                "action": event.get("action", ""),
                "timestamp": fallback_timestamp,
            }
            if ocr_path:
                runtime_event["_timestamp_path"] = ocr_path
            runtime_events.append(runtime_event)
        return runtime_events, ocr_path

    def _emit_counter_counts(self, counter):
        if not self.display_handler:
            return
        names = self._resolve_label_names()
        count_nhap, count_xuat = counter.get_counts()
        counts_key = (
            tuple(sorted(count_nhap.items())),
            tuple(sorted(count_xuat.items())),
        )
        if counts_key == self._last_emitted_counts:
            return
        self._last_emitted_counts = counts_key
        self.display_handler.emit_counts(
            {names.get(key, str(key)): value for key, value in count_nhap.items()},
            {names.get(key, str(key)): value for key, value in count_xuat.items()},
        )

    def _wait_while_paused(self, extraction_thread, start_time):
        """Pause the consumer without skewing file-playback wall-clock sync."""
        pause_started_at = None
        while (
            not self._stop_requested
            and extraction_thread is not None
            and getattr(extraction_thread, "is_paused", False)
        ):
            pause_started_at = pause_started_at or time.time()
            time.sleep(0.05)

        if pause_started_at is not None:
            start_time += time.time() - pause_started_at
        return start_time

    def detect_and_track(self, extraction_thread=None, frame_queue=None,
                         virtual_line=None, video_name=""):
        """Run the end-to-end pipeline until the source finishes or is stopped."""
        if frame_queue is None:
            return

        self._stop_requested = False
        self._run_token += 1
        run_token = self._run_token
        self._last_emitted_counts = None

        self._ensure_detector()
        self._runtime_event_log = []

        start_time = time.time()
        self._frame_index = 0
        self._recording_started = False
        fps_count = 0
        fps_last_time = time.time()

        self.detector.reset_tracker()
        self._stitcher = None

        fps = self._resolve_video_fps(extraction_thread)
        self._video_fps = fps
        is_live = is_stream_source(video_name)
        self._is_live = is_live

        if self.detector:
            self.detector.set_fps(fps)

        if getattr(settings, "TRACKLET_ENABLED", False):
            self._stitcher = TrackletStitcher(fps=fps)

        counter = CounterService(
            virtual_line[0], virtual_line[1],
            fps=fps, is_live=is_live,
        ) if virtual_line else None
        self._virtual_line = virtual_line
        self._video_name = video_name or "output"
        self._prepare_timestamp_session_dir()
        self._start_timestamp_ocr_worker(run_token)

        while not self._stop_requested:
            start_time = self._wait_while_paused(extraction_thread, start_time)
            if self._stop_requested:
                break
            try:
                item = frame_queue.get(timeout=0.5)
            except queue.Empty:
                if extraction_thread and not extraction_thread.isRunning():
                    break
                continue

            if item is None:
                break

            start_time = self._wait_while_paused(extraction_thread, start_time)
            if self._stop_requested:
                break
            item = (
                self._consume_latest_live_item(frame_queue, item)
                if is_live
                else self._sync_file_item_to_wall_clock(
                    frame_queue,
                    item,
                    fps,
                    start_time,
                )
            )
            if item is None:
                break

            start_time = self._wait_while_paused(extraction_thread, start_time)
            if self._stop_requested:
                break
            frame, frame_pos, ts_roi = self._unpack_queue_item(item)
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

        duration = time.time() - start_time

        count_nhap, count_xuat = {}, {}
        raw_event_log = []
        if counter:
            count_nhap, count_xuat = counter.get_counts()
            print(f"Kết quả đếm - Nhập: {count_nhap}, Xuất: {count_xuat}")
            raw_event_log = self._runtime_event_log
            self.last_event_log = self._event_log_with_fallback_timestamps(raw_event_log)

        output_path, frame_count = cache_service.finish_recording()
        session_id = None
        if output_path:
            names = self._resolve_label_names()
            db_nhap = {names.get(k, str(k)): v for k, v in count_nhap.items()}
            db_xuat = {names.get(k, str(k)): v for k, v in count_xuat.items()}
            session_id = db_service.save_session(
                video_name=video_name or "unknown",
                output_path=output_path,
                count_nhap=db_nhap,
                count_xuat=db_xuat,
                duration_sec=duration,
                event_log=self.last_event_log,
            )
            print(f"[AI] Lưu xong: {frame_count} frames")
        self._start_timestamp_postprocess(
            session_id=session_id,
            output_path=output_path,
            run_token=run_token,
            is_live=is_live,
            event_log=raw_event_log,
        )
        self._cleanup_timestamp_session_dir()

    def _process_frame(self, frame, counter, ts_roi=None):
        """Process one frame: detect, count, render, save, and emit to UI."""
        if self.detector:
            self.detector.advance_tracker_frame(self._frame_index)

        raw_results, detections = self.detector.track(frame)
        has_det = self.detector.has_detections(raw_results)
        if not has_det:
            detections = []

        if self._stitcher is not None:
            detections = self._stitcher.process(detections, frame_shape=frame.shape)

        if self.show_boxes and has_det:
            annotated_frame = self.detector.render(
                frame,
                raw_results,
                show_boxes=True,
                show_conf=self.show_box_conf,
            )
        else:
            annotated_frame = frame

        if counter:
            counter.set_frame_index(self._frame_index)
            events = counter.update(detections)
            event_fired = bool(events)
            if event_fired:
                runtime_events, ocr_path = self._build_runtime_events(
                    events,
                    counter,
                    ts_roi,
                )
                self._runtime_event_log.extend(runtime_events)
                self.last_event_log = list(self._runtime_event_log)
                if ocr_path and runtime_events:
                    self._enqueue_timestamp_ocr(
                        run_token=getattr(self, "_active_run_token", 0),
                        events=runtime_events,
                        image_path=ocr_path,
                    )
            self._emit_counter_counts(counter)
            if event_fired:
                self._save_count_snapshot(annotated_frame)

        if self._virtual_line:
            draw_line_with_arrows(annotated_frame, self._virtual_line)

        self._ensure_recording_started(annotated_frame)
        cache_service.save_frame(annotated_frame)

        if self.display_handler:
            self.display_handler.show(annotated_frame)

    def _ensure_recording_started(self, frame):
        if self._recording_started:
            return
        h, w = frame.shape[:2]
        output_path = cache_service.start_recording(
            fps=settings.OUTPUT_VIDEO_FPS,
            frame_size=(w, h),
            video_name=getattr(self, '_video_name', 'output'),
        )
        self._recording_started = bool(output_path)

    def _save_timestamp_crop(self, roi):
        return self.timestamp_ocr.save_crop(
            roi,
            session_dir=self._timestamp_session_dir,
            video_name=getattr(self, "_video_name", "video"),
            frame_index=self._frame_index,
        )

    def _finalize_event_log_timestamps(self, event_log):
        return self.timestamp_ocr.finalize_event_log(
            event_log,
            fps=self._video_fps,
        )

    def _prepare_timestamp_session_dir(self):
        self._timestamp_session_dir = self.timestamp_ocr.prepare_session_dir(
            is_live=self._is_live,
            video_name=getattr(self, "_video_name", "video"),
        )

    def _cleanup_timestamp_session_dir(self, session_dir=None):
        if session_dir is None:
            session_dir = self._timestamp_session_dir
            self._timestamp_session_dir = None
        self.timestamp_ocr.cleanup_session_dir(session_dir)

    def _event_log_with_fallback_timestamps(self, event_log):
        return self.timestamp_ocr.normalize_event_log(
            event_log,
            fps=self._video_fps,
        )

    def _rename_output_video_from_events(self, session_id, output_path, event_log):
        if not output_path:
            return output_path
        parsed_dt = self.timestamp_ocr.first_valid_event_timestamp(event_log)
        if parsed_dt is None:
            return output_path

        target_name = self.timestamp_ocr.build_output_video_name(parsed_dt)
        renamed_path = cache_service.rename_output_video(output_path, target_name)
        if session_id is not None and renamed_path and renamed_path != output_path:
            db_service.update_session_output_path(session_id, renamed_path)
        return renamed_path

    def _start_timestamp_postprocess(self, session_id, output_path, run_token, is_live, event_log):
        self._finish_timestamp_ocr_worker(
            run_token=run_token,
            session_id=session_id,
            output_path=output_path,
            is_live=is_live,
            event_log=event_log,
        )

    def _start_timestamp_ocr_worker(self, run_token):
        if not self.timestamp_ocr.can_process_video(is_live=self._is_live):
            return
        session_dir = self._timestamp_session_dir
        if session_dir is None:
            return
        context = {
            "run_token": run_token,
            "queue": queue.Queue(),
            "session_id": None,
            "output_path": "",
            "event_log": None,
            "session_dir": session_dir,
        }
        worker = threading.Thread(
            target=self._timestamp_ocr_worker_loop,
            args=(context,),
            daemon=True,
        )
        context["worker"] = worker
        self._ocr_contexts[run_token] = context
        self._active_run_token = run_token
        worker.start()

    def _enqueue_timestamp_ocr(self, run_token, events, image_path):
        context = self._ocr_contexts.get(run_token)
        if context is None or not image_path:
            return
        context["queue"].put((list(events), image_path))

    def _finish_timestamp_ocr_worker(self, run_token, session_id, output_path, is_live, event_log):
        context = self._ocr_contexts.get(run_token)
        if context is None:
            finalized = self._finalize_event_log_timestamps(event_log)
            if session_id is not None:
                db_service.update_session_event_log(session_id, finalized)
            self._rename_output_video_from_events(session_id, output_path, finalized)
            if run_token == self._run_token:
                self.last_event_log = finalized
            if self.display_handler and hasattr(self.display_handler, "emit_session_refresh"):
                self.display_handler.emit_session_refresh()
            if not is_live:
                self._cleanup_timestamp_session_dir()
            return
        context["session_id"] = session_id
        context["output_path"] = output_path
        context["event_log"] = event_log
        context["queue"].put(None)
        if self._timestamp_session_dir == context.get("session_dir"):
            self._timestamp_session_dir = None

    def _timestamp_ocr_worker_loop(self, context):
        run_token = context["run_token"]
        try:
            while True:
                task = context["queue"].get()
                if task is None:
                    break
                events, image_path = task
                text = self.timestamp_ocr.ocr_image(image_path)
                if text:
                    for evt in events:
                        evt["timestamp"] = text
                        evt.pop("_timestamp_path", None)
                    print(f"[Timestamp OCR] {image_path} -> {text}")
                else:
                    print(f"[Timestamp OCR] {image_path} -> (fail)")
                self.timestamp_ocr.safe_delete_file(image_path)

            finalized = self._finalize_event_log_timestamps(context.get("event_log"))
            session_id = context.get("session_id")
            if session_id is not None:
                db_service.update_session_event_log(session_id, finalized)
            self._rename_output_video_from_events(
                session_id,
                context.get("output_path"),
                finalized,
            )
            if run_token == self._run_token:
                self.last_event_log = finalized
            if self.display_handler and hasattr(self.display_handler, "emit_session_refresh"):
                self.display_handler.emit_session_refresh()
            print("[Timestamp OCR] Background postprocess finished.")
        finally:
            self._ocr_contexts.pop(run_token, None)
            self._cleanup_timestamp_session_dir(context.get("session_dir"))

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
