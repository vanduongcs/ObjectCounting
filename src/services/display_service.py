import cv2

class DisplayService:
    def __init__(self, window_name="Output", delay=1):
        self.window_name = window_name
        self.delay = delay

    def show(self, frame):
        cv2.imshow(self.window_name, frame)
        key = cv2.waitKey(self.delay) & 0xFF

        if key == ord('q'):
            return False
        return True
    
    def close(self):
        cv2.destroyAllWindows()