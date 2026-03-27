"""Headless OpenCV smoke test."""

import sys

import cv2
import numpy as np


def main():
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    img[:, :, 1] = 180

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (320, 240))
    ok, encoded = cv2.imencode(".png", resized)

    assert ok is True
    assert encoded is not None
    assert encoded.size > 0

    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[:2] == (240, 320)

    print("OpenCV smoke test passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OpenCV smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
