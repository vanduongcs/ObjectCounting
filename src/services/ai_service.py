import cv2
import os
from pathlib import Path
import configs.settings as settings

from src.services.display_service import DisplayService

from .model_detector import ObjectDetector
from src.utils import input_processor as input_p

class AIService:
    def __init__(self, model_path, video_path, target_fps):
        self.detector = ObjectDetector(model_path)

    def detect_and_track(self):
        ds = DisplayService()
        saved_count = 0
        # Detect and track on all frames in CACHE_DIR
        frames = [f for f in os.listdir(settings.CACHE_DIR) if f.lower().endswith(settings.VALID_EXTENSION)]
        frames.sort()
        frames_detected_info = []
        for frame_name in frames:
            frame_path = os.path.join(settings.CACHE_DIR, frame_name)
            frame = input_p.read_input_image(frame_path)
            frame_detected_result = self.detector.predict(frame)
            frame_detected_image = frame_detected_result[0].plot(boxes=False, masks=True)
            saved_count+=1
            frame_name = settings.OUTPUT_DETECT_DIR / f"frame_{saved_count:05d}.jpg"
            saving = cv2.imwrite(str(frame_name), frame_detected_image)
            ds.show(frame_detected_image)
            detected_info = self.detector.track(frame)
            frames_detected_info.append(detected_info)
        return frames_detected_info