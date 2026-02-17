import cv2
from pathlib import Path
import configs.settings as settings

class VideoReader:
    def __init__(self, video_path, target_fps=settings.MAX_FPS, output_dir=None):
        self.video_path = str(video_path)
        self.target_fps = target_fps

        self.output_dir = Path(output_dir) if output_dir else settings.CACHE_DIR

    # Extract one video to many frames
    def extract_frames(self):
        cap = cv2.VideoCapture(self.video_path)

        if not cap.isOpened():
            return False
        
        # Get the fps of video
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        # number of jump frames during extract
        # Ex: original fps = 30, we want to handle video with the fps is 15
        # -> frame_interval = 30/15 = 2 -> get one frame and skip one frame
        frame_interval = max(int(video_fps / self.target_fps), 1)

        # number of frames we read now
        frame_count = 0
        # number of frames we actually save
        saved_count = 0

        # This loop will do until the ret is False
        # The ret is False when: end of video (0 frame remainning) or meet unkown error
        # In this loop:
        #   if the frame is the target frame (based on the frame_interval and frame_count)
        #   save the picture (frame) meet the condition
        #   increase the counter variable (save_count) to know how many frame we save now
        #   if not meet the condition: skip this frame and go to the next frame
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                frame_name = self.output_dir / f"frame_{saved_count:05d}.jpg"
                cv2.imwrite(str(frame_name), frame)
                saved_count += 1

            frame_count += 1

        cap.release()

        return True

        # print(f"Saved {saved_count} frames to {self.output_dir}")