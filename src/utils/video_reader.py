import cv2
from pathlib import Path
import configs.settings as settings
from src.services.display_service import DisplayService

def extract_frames(video_path, target_fps=settings.MAX_FPS, output_dir=None):
    video_path = str(video_path)
    output_dir = Path(output_dir or settings.CACHE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    if target_fps is None or target_fps <= 0:
        target_fps = settings.MAX_FPS if settings.MAX_FPS > 0 else 10

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if not video_fps or video_fps <= 0:
        video_fps = target_fps

    frame_interval = max(int(video_fps / target_fps), 1)

    frame_count = 0
    saved_count = 0
    first_frame = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frame_name = output_dir / f"frame_{saved_count:05d}.jpg"
            ok = cv2.imwrite(str(frame_name), frame)
            if ok:
                if first_frame is None:
                    first_frame = frame.copy()
                saved_count += 1

        frame_count += 1

    cap.release()
    return first_frame

def extract_and_display_frames(video_path, max_fps):
    """
    Extract frames from a video file and display them in real-time using DisplayService.

    Args:
        video_path (str): Path to the video file.
        max_fps (int): Maximum frames per second to process.
    """
    ds = DisplayService()
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"Cannot open video file: {video_path}")
        return None

    frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
    frame_interval = max(1, frame_rate // max_fps)

    while cap.isOpened():
        for _ in range(frame_interval):
            ret, frame = cap.read()
            if not ret:
                print("End of video or cannot read the frame.")
                cap.release()
                return None

        # Display the frame using DisplayService
        if ds.show(frame) == False:  # Exit if user presses the exit key
            break

    cap.release()
    cv2.destroyAllWindows()