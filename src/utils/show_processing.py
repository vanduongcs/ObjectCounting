import cv2
import os
import time
import configs.settings as settings


def get_processed_image_files():
    result_dir = settings.OUTPUT_DETECT_DIR
    frame_files = [f for f in os.listdir(result_dir) if f.lower().endswith(settings.VALID_EXTENSION)]
    frame_files.sort()
    return [os.path.join(result_dir, f) for f in frame_files]

def show_images(image_paths, fps):
    delay = 1.0 / fps
    if not image_paths:
        print("No processed images found!")
        return
    for frame_path in image_paths:
        img = cv2.imread(str(frame_path))
        if img is None:
            continue
        cv2.imshow("Processed Frame", img)
        key = cv2.waitKey(int(delay * 1000)) & 0xFF
        if key == 27:  # ESC để thoát
            break
    cv2.destroyAllWindows()

def show_processed_images():
    fps = settings.MAX_FPS
    image_paths = get_processed_image_files()
    show_images(image_paths, fps)

if __name__ == "__main__":
    show_processed_images()
