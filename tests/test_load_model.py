"""
Test Load Model: Kiểm tra khởi tạo ObjectDetector và inference cơ bản.

Cách chạy: python -m tests.test_load_model
"""

import cv2
import numpy as np
import configs.settings as settings
from src.services.detector import ObjectDetector


def load_model_test():
    """Khởi tạo ObjectDetector với model path từ settings."""
    try:
        detector = ObjectDetector(settings.MODEL_PATH, conf=0.25)
        print(f"✅ Model loaded thành công từ: {settings.MODEL_PATH}")
        return detector
    except Exception as e:
        print(f"❌ Lỗi load model: {e}")
        return None


def run_track_test(detector):
    """Test track trên dummy frame."""
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    try:
        raw_results, detections = detector.track(dummy)
        print(f"✅ Track thành công - {len(detections)} detection(s)")
        return True
    except Exception as e:
        print(f"❌ Lỗi track: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("TEST LOAD MODEL")
    print("=" * 50)

    detector = load_model_test()
    if detector:
        run_track_test(detector)
