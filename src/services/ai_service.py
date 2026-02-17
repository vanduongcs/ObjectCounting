import cv2
import os
from pathlib import Path
import configs.settings as settings

from .model_detector import ObjectDetector
from .video_reader import VideoReader
from src.utils import input_processor as input_p

class AIService:
    def __init__(self, model_path, video_path, target_fps):
        self.detector = ObjectDetector(model_path)
        self.reader = VideoReader(video_path, target_fps)

    def detect_and_track(self):
        # Detect and track on all frames in CACHE_DIR
        frames = [f for f in os.listdir(settings.CACHE_DIR) if f.lower().endswith(settings.VALID_EXTENSION)]
        frames.sort()
        frames_detected_info = []
        for frame_name in frames:
            frame_path = os.path.join(settings.CACHE_DIR, frame_name)
            frame = input_p.read_input_image(frame_path)
            frame_detected = self.detector.predict(frame)
            detected_info = self.detector.track(frame)
            frames_detected_info.append(detected_info)
        return frames_detected_info