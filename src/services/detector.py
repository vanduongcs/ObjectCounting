"""
Detector Service: Lớp bọc model YOLO với backend OpenVINO.

Hỗ trợ detect và track đối tượng trên từng frame.
Tối ưu cho CPU và iGPU Intel thông qua OpenVINO runtime.

Lưu ý về device:
  - Ultralytics + OpenVINO dùng format: 'cpu', 'intel:gpu', 'intel:npu'
  - KHÔNG dùng 'GPU' hay 'CUDA' (đó là cho PyTorch CUDA)
  - 'AUTO' = OpenVINO tự chọn thiết bị nhanh nhất (iGPU > CPU)
"""

from pathlib import Path

# Đường dẫn tới file cấu hình tracker tùy chỉnh
# Đường dẫn tới file cấu hình tracker tùy chỉnh
_CUSTOM_TRACKER = Path(__file__).resolve().parent.parent.parent / "configs" / "bytetrack_custom.yaml"
# Dùng file custom nếu tồn tại, ngược lại fallback về bytetrack mặc định của ultralytics
TRACKER_CONFIG = str(_CUSTOM_TRACKER) if _CUSTOM_TRACKER.exists() else "bytetrack.yaml"

import numpy as np
from ultralytics import YOLO
from src.utils.result_parser import parse_tracking_results


def _select_best_device() -> str:
    """
    Chọn thiết bị tối ưu cho Ultralytics + OpenVINO.
    Format Ultralytics: 'intel:gpu' (iGPU), 'cpu'
    Fallback: dùng 'AUTO' để OpenVINO tự chọn.
    """
    try:
        from openvino import Core
        core = Core()
        available = core.available_devices
        print(f"[OpenVINO] Thiết bị khả dụng: {available}")

        # Kiểm tra có GPU (iGPU Intel) không
        has_gpu = any(d.startswith("GPU") for d in available)
        if has_gpu:
            print("[OpenVINO] Phát hiện Intel iGPU → sử dụng 'intel:gpu'")
            return "intel:gpu"

        print("[OpenVINO] Sử dụng CPU")
        return "cpu"
    except Exception as e:
        print(f"[OpenVINO] Không thể kiểm tra thiết bị, dùng AUTO: {e}")
        return "AUTO"


class ObjectDetector:
    def __init__(self, model_path, conf=0.15):
        """
        Khởi tạo model YOLO với backend OpenVINO.
        Args:
            model_path: Đường dẫn tới thư mục model OpenVINO (chứa .xml/.bin).
            conf: Ngưỡng tin cậy (0.0 - 1.0).
        """
        self.conf = conf

        # Chọn thiết bị tối ưu (iGPU Intel > CPU)
        self.device = _select_best_device()

        # Tải model OpenVINO (Ultralytics tự nhận diện khi đường dẫn là thư mục .xml)
        self.yolo_model = YOLO(model_path, task="segment")

        # Warmup: chạy 1 lần để OpenVINO biên dịch kernel trước
        # → Giảm độ trễ lần infer đầu tiên trong thực tế
        print(f"[OpenVINO] Warming up model trên {self.device}...")
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        try:
            self.yolo_model.predict(
                dummy,
                device=self.device,
                verbose=False,
                conf=self.conf
            )
            print("[OpenVINO] Warmup hoàn tất.")
        except Exception as e:
            # Nếu iGPU fail (driver cũ, v.v.) → thử lại với CPU
            print(f"[OpenVINO] Warmup với {self.device} thất bại: {e}")
            print("[OpenVINO] Chuyển sang CPU...")
            self.device = "cpu"
            try:
                self.yolo_model.predict(
                    dummy,
                    device=self.device,
                    verbose=False,
                    conf=self.conf
                )
                print("[OpenVINO] Warmup CPU hoàn tất.")
            except Exception as e2:
                print(f"[OpenVINO] Warmup CPU cũng thất bại (bỏ qua): {e2}")

    def predict(self, frame):
        """Nhận diện đối tượng (không track)."""
        return self.yolo_model(frame, conf=self.conf, device=self.device)

    def track(self, frame):
        """Theo dõi đối tượng (tracking). Trả về list thông tin."""
        results = self.yolo_model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf,
            device=self.device,
            tracker=TRACKER_CONFIG
        )
        return parse_tracking_results(results)

    def track_with_result(self, frame):
        """
        Track đối tượng VÀ trả về cả kết quả để vẽ (plot).
        Gộp 2 bước: Detect + Track.
        """
        results = self.yolo_model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf,
            device=self.device,
            tracker=TRACKER_CONFIG
        )
        detections = parse_tracking_results(results)
        return results, detections
