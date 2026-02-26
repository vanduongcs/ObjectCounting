"""
Result Parser: Xử lý kết quả trả về từ YOLO.

Chuyển đổi các object phức tạp của Ultralytics thành mảng dictionary đơn giản để dễ xử lý.
"""

def parse_tracking_results(results):
    """
    Rút trích các thông tin cần thiết từ kết quả YOLO track.
    Trả về list[dict]:
        - id: ID tracking (số nguyên, duy nhất cho mỗi đối tượng)
        - label: Class ID (số nguyên, loại đối tượng)
        - conf: Confidence score (0.0 → 1.0, độ tin cậy)
        - center: Tọa độ tâm (cx, cy)
    """
    detections = []

    for result in results:
        boxes = result.boxes
        if boxes.id is None:
            continue

        for box in boxes:
            track_id = int(box.id.item())       # ID theo dõi
            cls_id = int(box.cls.item())         # Loại đối tượng
            conf = float(box.conf.item())        # Độ tin cậy
            cx, cy, w, h = box.xywh[0]           # Tâm + kích thước (YOLO tính sẵn)

            detections.append({
                "id": track_id,
                "label": cls_id,
                "conf": conf,
                "center": (float(cx), float(cy)),
            })

    return detections
