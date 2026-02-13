import sys
import os
from pathlib import Path
import cv2

# Get root dir
BASE_DIR = Path(__file__).resolve().parent.parent
# print("Dir: ", BASE_DIR)

# Add root dir into system dir
sys.path.append(str(BASE_DIR))

from src.services.ai_service import ObjectDetector

def load_model_test():
    model_path = os.path.join(BASE_DIR, "models", "bestyolo11n.pt")
    # print("Load model at: ", model_path)

    try:
        testing = ObjectDetector(model_path)
        return testing
    except Exception as e:
        print("Error", e)

def run_model_test(detector):
    # Input image path
    img_path = os.path.join(BASE_DIR, "assets", "images", "test.jpg")

    # Output dir
    output_dir = os.path.join(BASE_DIR, "tests", "result")
    
    # Output image path
    img_result_path = os.path.join(output_dir, "result_image.jpg")

    frame = cv2.imread(img_path)

    # Use model to detect objects
    result = detector.predict(frame)
    
    # Get the image with mask and bounding box
    predicted_image = result[0].plot()

    saving = cv2.imwrite(img_result_path, predicted_image)




if __name__ == "__main__":
    model_detector = load_model_test()
    run_model_test(model_detector)


