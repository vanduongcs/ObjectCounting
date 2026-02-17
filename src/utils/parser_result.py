from src.utils import cal_support as cal

# Handle the results transmit from services/model_detector.py
def parse_tracking_results(results):
    # List of objects detected
    detections = []

    # In spite of you transmit into this function only one frame
    # It must use the loop for safe, in the future if I want to expand it, it will easier
    for result in results:
        # Get boxes detected by model
        boxes = result.boxes

        # If doesn't see any object -> skip to the next result
        if boxes.id is None:
            continue

        # If not meet the condition above, do it:
        # With each box in boxes:
        # Get the id, class, calculate the center of box, append it into list of object
        for box in boxes:
            track_id = int(box.id.item())
            cls_id = int(box.cls.item())
            x1, y1, x2, y2 = box.xyxy[0]

            cx = cal.center(x1, x2)
            cy = cal.center(y1, y2)

            detections.append({
                "id": track_id,
                "label": cls_id,
                "center": (cx, cy),
                "bbox": (float(x1), float(y1), float(x2), float(y2))
            })

    return detections