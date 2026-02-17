
from ultralytics import YOLO

# local
from src.utils import parser_result as pr


class ObjectDetector:
    # Constructor
    def __init__(self, model_path, conf=0.25):
        # Load model
        self.yolo_model = YOLO(model_path)
        self.conf = conf

    # Predict function
    def predict(self, frame):
        # Call yolo model to handle the frame with confidence threshold
        result = self.yolo_model(frame, conf=self.conf)
        return result
    
    # Track objects in the image
    def track(self, frame):
        results = self.yolo_model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf
        )
        return pr.parse_tracking_results(results)