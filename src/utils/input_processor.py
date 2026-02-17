import cv2
import os
from pathlib import Path
import configs.settings as settings

def read_input_image(frame_path):
    image_input = cv2.imread(frame_path)
    return image_input
