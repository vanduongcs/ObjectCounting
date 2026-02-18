import os
import cv2

import configs.settings as settings
import src.utils.video_reader as vr

from src.services.display_service import DisplayService
from src.services.ai_service import AIService

# from src.utils.draw_line import LineDrawer
# from src.utils import input_processor as input_p

# from src.services.ai_service import AIService
# from src.services.counter_service import CounterService

def main():
    for f in os.listdir(settings.CACHE_DIR):
        if f.lower().endswith(settings.VALID_EXTENSION):
            os.remove(os.path.join(settings.CACHE_DIR, f))

    first_frame = vr.extract_frames(settings.VIDEO_TEST_PATH, settings.MAX_FPS)
    if first_frame is None:
        print("Không đọc được video.")
        return
    
    ai_ser = AIService(settings.MODEL_PATH, settings.VIDEO_TEST_PATH, 15)
    ai_ser.detect_and_track()

    
if __name__ == "__main__":
    main()