import cv2
import configs.settings as settings
from src.utils.draw_line import LineDrawer
from src.services.ai_service import AIService
from src.services.counter_service import CounterService
from src.utils import input_processor as input_p
import os


def extract_frames_and_get_first_frame():
    from src.services.video_reader import VideoReader
    video_reader = VideoReader(
        video_path=settings.VIDEO_TEST_PATH,
        target_fps=settings.MAX_FPS
    )
    extract_result = video_reader.extract_frames()
    if extract_result:
        print("Extract complete")
    else:
        print("Error when extract video")
        return None
    frame_files = [f for f in os.listdir(settings.CACHE_DIR) if f.lower().endswith(settings.VALID_EXTENSION)]
    if not frame_files:
        print("No frames found!")
        return None
    frame_files.sort()
    first_frame_path = os.path.join(settings.CACHE_DIR, frame_files[0])
    first_frame = input_p.read_input_image(first_frame_path)
    return first_frame

def draw_virtual_line(frame):
    line_drawer = LineDrawer()
    line = line_drawer.draw_line_interactive(frame)
    if not line:
        print("No line drawn!")
        return None
    x1, y1, x2, y2 = line
    region_split_y = int((y1 + y2) / 2)
    return region_split_y

def detect_count_and_show(region_split_y):
    service = AIService(
        model_path=settings.MODEL_PATH,
        video_path=settings.VIDEO_TEST_PATH,
        target_fps=settings.MAX_FPS
    )
    frames = [f for f in os.listdir(settings.CACHE_DIR) if f.lower().endswith(settings.VALID_EXTENSION)]
    frames.sort()
    counter = CounterService(region_split_y=region_split_y)
    fps = settings.MAX_FPS
    delay = 1.0 / fps
    for idx, frame_name in enumerate(frames):
        frame_path = os.path.join(settings.CACHE_DIR, frame_name)
        frame = input_p.read_input_image(frame_path)
        frame_detected = service.detector.predict(frame)
        predicted_image = frame_detected[0].plot(boxes=False, masks=True)
        detected_info = service.detector.track(frame)
        counter.update(detected_info)
        cv2.imshow("Processing", predicted_image)
        key = cv2.waitKey(int(delay * 1000)) & 0xFF
        if key == 27:
            break
    cv2.destroyAllWindows()
    count_nhap, count_xuat = counter.get_counts()
    print("Đếm nhập:", count_nhap)
    print("Đếm xuất:", count_xuat)

def main():
    first_frame = extract_frames_and_get_first_frame()
    if first_frame is None:
        return
    region_split_y = draw_virtual_line(first_frame)
    if region_split_y is None:
        return
    detect_count_and_show(region_split_y)

if __name__ == "__main__":
    main()