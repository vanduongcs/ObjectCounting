import cv2
import configs.settings as settings

from src.services.detector import ObjectDetector

def load_model_test():
    try:
        model_loaded = ObjectDetector(settings.MODEL_PATH, conf=0.25)
        return model_loaded
    except Exception as e:
        print("Error", e)

def run_model_test(detector, frame):
    
    # Use model to detect objects
    result = detector.predict(frame)

    # Get the image with mask and bounding box
    predicted_image = result[0].plot(boxes=False, masks=True)

    # Save the predicted image
    saving = cv2.imwrite(str(settings.IMAGE_TEST_RESULT_PATH), predicted_image)

    # Optionally track detections
    processor = ObjectDetector(settings.MODEL_PATH)
    detections = processor.track(frame)
    print(detections)



if __name__ == "__main__":
    model_detector = load_model_test()
    # Example: read frame from file or camera
    frame = cv2.imread(str(settings.IMAGE_TEST_PATH))
    run_model_test(model_detector, frame)


