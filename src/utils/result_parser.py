"""
Result Parser: Chuyển kết quả YOLO track thành list[dict] đơn giản.

Ai gọi module này?
    - ObjectDetector.track() (services/detector.py) gọi parse_tracking_results()

Ai dùng kết quả?
    - CounterService.update() (services/counter_service.py) dùng để đếm.

Tại sao cần parse?
    Kết quả gốc của YOLO là object phức tạp (tensors, nhiều thuộc tính).
    Module này rút trích chỉ 4 thông tin cần thiết cho việc đếm:
        - id: Track ID (để theo dõi vật thể qua các frame)
        - label: Loại đối tượng (0=person, 1=car, ...)
        - conf: Độ tin cậy (0.0 -> 1.0)
        - center: Tâm bounding box (cx, cy)
"""

import math


def parse_tracking_results(results):
    """
    Rút trích thông tin cần thiết từ kết quả YOLO track.

    Args:
        results: Kết quả gốc từ YOLO model.track() -- list các Result object.

    Returns:
        list[dict] -- mỗi dict chứa: id, label, conf, center.
        Ví dụ: [{"id": 5, "label": 0, "conf": 0.85, "center": (320.5, 240.1)}]
    """
    detections = []
    for result in results:
        boxes = result.boxes

        # Nếu chưa có track ID (frame đầu hoặc tracking lỗi) -> bỏ qua
        if boxes.id is None:
            continue

        for box in boxes:
            # xywh = [center_x, center_y, width, height]
            cx, cy, w, h = box.xywh[0]
            cx, cy, w, h = float(cx), float(cy), float(w), float(h)

            # Pre-filter: skip bbox degenerate (w/h quá nhỏ hoặc NaN/Inf)
            # Ngăn Kalman filter crash từ gốc thay vì bắt lỗi sau
            if w <= 1 or h <= 1:
                continue
            if not (math.isfinite(cx) and math.isfinite(cy)
                    and math.isfinite(w) and math.isfinite(h)):
                continue

            detections.append({
                "id": int(box.id.item()),       # Track ID (ByteTrack gán)
                "label": int(box.cls.item()),   # Class ID (0, 1, 2, ...)
                "conf": float(box.conf.item()), # Confidence score
                "center": (cx, cy),             # Tâm bbox
                "bbox_wh": (w, h),              # Kích thước bbox
            })
    return detections
