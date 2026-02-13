from ultralytics import YOLO
import cv2

class ObjectDetector:
    # Hàm khởi tạo
    def __init__(self, model_path):
        # Instantiate the YOLO model
        self.yolo_model = YOLO(model_path)
        # print(f"Load model succesful")

    # Predict function
    def predict(self, frame):
        # Call yolo model to handle the frame
        result = self.yolo_model(frame)
        return result