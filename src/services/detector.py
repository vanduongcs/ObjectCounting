"""
Detector Service: Wrapper cho model YOLO + OpenVINO.

Ai gọi module này?
    - AIService._process_frame() (services/ai_service.py) gọi detector.track()

Module này gọi ai?
    - YOLO (ultralytics) -- chạy inference (detect + track)
    - OpenVINO (openvino) -- chọn device tối ưu (iGPU / CPU)
    - result_parser (utils/result_parser.py) -- parse kết quả YOLO thành dict

Luồng dữ liệu:
    frame (numpy) -> YOLO.track() -> raw_results (YOLO objects)
                                  -> parse_tracking_results() -> detections (list[dict])
"""

import tempfile
from pathlib import Path

import numpy as np
import yaml
from ultralytics import YOLO

from src.utils.result_parser import parse_tracking_results
import configs.settings as settings

# Tracker config gốc: dùng file custom nếu có, fallback về mặc định
_CUSTOM_TRACKER = Path(__file__).resolve().parent.parent.parent / "configs" / "bytetrack_custom.yaml"


def _load_base_tracker_config():
    """Đọc tracker config gốc từ file YAML."""
    if _CUSTOM_TRACKER.exists():
        with open(_CUSTOM_TRACKER, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    # Fallback: config mặc định
    return {
        "tracker_type": "bytetrack",
        "track_high_thresh": 0.3,
        "track_low_thresh": 0.05,
        "new_track_thresh": 0.4,
        "track_buffer": 60,
        "match_thresh": 0.6,
        "fuse_score": True,
        "aspect_ratio_thresh": 10.0,
        "min_box_area": 10,
        "with_reid": True,
    }


def _generate_tracker_config(fps):
    """
    Tạo tracker config với track_buffer tính động từ FPS.

    track_buffer = FPS × TRACK_BUFFER_SECONDS
    Ví dụ: 30 FPS × 5s = 150 frames

    Returns: đường dẫn tới file YAML tạm.
    """
    config = _load_base_tracker_config()

    # Tính track_buffer động
    buffer_frames = int(fps * settings.TRACK_BUFFER_SECONDS)
    config["track_buffer"] = max(buffer_frames, settings.TRACK_BUFFER_MIN_FRAMES)

    print(f"[Tracker] track_buffer = {config['track_buffer']} frames "
          f"({fps} FPS × {settings.TRACK_BUFFER_SECONDS}s)")

    # Ghi ra file tạm (ultralytics yêu cầu path tới YAML)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', prefix='tracker_',
        delete=False, encoding='utf-8'
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return tmp.name


def _select_best_device() -> str:
    """
    Chọn thiết bị tối ưu cho OpenVINO inference.
    Ưu tiên: Intel iGPU > CPU > AUTO.
    """
    try:
        from openvino import Core
        available = Core().available_devices
        print(f"[OpenVINO] Thiết bị khả dụng: {available}")

        if any(d.startswith("GPU") for d in available):
            print("[OpenVINO] Sử dụng Intel iGPU")
            return "intel:gpu"

        print("[OpenVINO] Sử dụng CPU")
        return "cpu"
    except Exception as e:
        print(f"[OpenVINO] Không thể kiểm tra thiết bị, dùng AUTO: {e}")
        return "AUTO"


class ObjectDetector:
    def __init__(self, model_path, conf=None):
        self.conf = conf if conf is not None else settings.DETECTION_CONFIDENCE
        self.device = _select_best_device()
        self.yolo_model = YOLO(model_path, task="detect")
        self._tracker_config = None  # Sẽ generate khi biết FPS
        self._warmup()

    def configure_tracker(self, fps):
        """
        Tạo tracker config với track_buffer tính từ FPS.
        Gọi trước khi bắt đầu tracking.

        Args:
            fps: FPS thực tế của video/camera.
        """
        self._tracker_config = _generate_tracker_config(fps)

    def _warmup(self):
        """
        Chạy 1 lần predict với ảnh trắng để OpenVINO biên dịch kernel.

        Tại sao cần warmup?
            OpenVINO cần biên dịch mô hình cho device cụ thể (CPU/GPU) lần đầu tiên.
            Quá trình này mất 3-10 giây. Nếu không warmup, frame đầu tiên sẽ bị lag.
        """
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        print(f"[OpenVINO] Warming up trên {self.device}...")

        try:
            self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
            print("[OpenVINO] Warmup hoàn tất.")
        except Exception as e:
            # GPU lỗi -> thử lại với CPU
            print(f"[OpenVINO] Warmup {self.device} thất bại: {e}, chuyển sang CPU...")
            self.device = "cpu"
            try:
                self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
                print("[OpenVINO] Warmup CPU hoàn tất.")
            except Exception as e2:
                # CPU cũng lỗi -> bỏ qua, sẽ warmup tự động khi chạy thật
                print(f"[OpenVINO] Warmup CPU cũng thất bại (bỏ qua): {e2}")

    def track(self, frame):
        """
        Detect + Track đối tượng.
        Returns: (raw_results, parsed_detections)
            - raw_results: Kết quả gốc từ YOLO (để vẽ plot)
            - parsed_detections: List[dict] đã parse (để đếm)
        """
        # Fallback: nếu chưa configure → dùng file config gốc
        tracker = self._tracker_config
        if tracker is None:
            tracker = str(_CUSTOM_TRACKER) if _CUSTOM_TRACKER.exists() else "bytetrack.yaml"

        try:
            results = self.yolo_model.track(
                frame,
                persist=True,
                verbose=False,
                conf=self.conf,
                device=self.device,
                tracker=tracker,
            )
        except (np.linalg.LinAlgError, ValueError) as e:
            # ByteTrack Kalman filter bị NaN do bbox degenerate (height≈0)
            # → reset tracker hoàn toàn và retry track với state sạch
            print(f"[Tracker] Kalman filter lỗi ({e}), reset tracker...")
            self._reset_tracker()
            try:
                # Retry track() — tracker mới sẽ được ultralytics tạo lại
                results = self.yolo_model.track(
                    frame,
                    persist=True,
                    verbose=False,
                    conf=self.conf,
                    device=self.device,
                    tracker=tracker,
                )
            except Exception:
                # Vẫn lỗi → bỏ qua tracking, chỉ detect
                print("[Tracker] Retry thất bại, fallback detect-only...")
                self._strip_tracker_callbacks()
                results = self.yolo_model.predict(
                    frame,
                    verbose=False,
                    conf=self.conf,
                    device=self.device,
                )

        return results, parse_tracking_results(results)

    def _reset_tracker(self):
        """Reset tracker bên trong YOLO để xóa sạch state bị NaN.
        Dùng delattr để ultralytics tự khởi tạo lại từ đầu."""
        if hasattr(self.yolo_model, 'predictor') and self.yolo_model.predictor:
            if hasattr(self.yolo_model.predictor, 'trackers'):
                delattr(self.yolo_model.predictor, 'trackers')

    def _strip_tracker_callbacks(self):
        """Gỡ bỏ tracking callback khỏi predictor để predict() không trigger tracker."""
        if hasattr(self.yolo_model, 'predictor') and self.yolo_model.predictor:
            predictor = self.yolo_model.predictor
            cb_key = "on_predict_postprocess_end"
            if cb_key in predictor.callbacks:
                predictor.callbacks[cb_key] = [
                    cb for cb in predictor.callbacks[cb_key]
                    if "track" not in getattr(cb, '__module__', '')
                ]
