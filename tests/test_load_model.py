"""Smoke test for model loading and one tracking call."""

import sys

import numpy as np

import configs.settings as settings
from src.services.detector import ObjectDetector


def load_model():
    detector = ObjectDetector(settings.MODEL_PATH, conf=0.25)
    assert detector is not None
    return detector


def run_track(detector):
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    raw_results, detections = detector.track(dummy)
    assert raw_results is not None
    assert isinstance(detections, list)
    return len(detections)


def main():
    print("=" * 50)
    print("TEST LOAD MODEL")
    print("=" * 50)
    detector = load_model()
    detection_count = run_track(detector)
    print(f"Model OK: {settings.MODEL_PATH}")
    print(f"Track OK: {detection_count} detection(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
