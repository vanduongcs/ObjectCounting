import cv2
import numpy as np

class LineDrawer:
    def __init__(self):
        self.line = None  # (x1, y1, x2, y2)
        self.drawing = False
        self.start_point = None
        self.end_point = None
        self.done = False

    def draw_line_interactive(self, frame):
        clone = frame.copy()
        window_name = "Draw Virtual Line"
        cv2.namedWindow(window_name)
        cv2.setMouseCallback(window_name, self.mouse_events, param=clone)

        h, w = frame.shape[:2]

        while not self.done:
            temp = clone.copy()
            if self.start_point and self.end_point:
                # Tính toán phương trình đường thẳng
                x1, y1 = self.start_point
                x2, y2 = self.end_point
                if x1 == x2:
                    # Đường thẳng đứng
                    pt1 = (x1, 0)
                    pt2 = (x2, h)
                else:
                    slope = (y2 - y1) / (x2 - x1)
                    intercept = y1 - slope * x1
                    # Giao với mép trái (x=0)
                    y_left = int(intercept)
                    # Giao với mép phải (x=w-1)
                    y_right = int(slope * (w-1) + intercept)
                    pt1 = (0, y_left)
                    pt2 = (w-1, y_right)
                # Vẽ đường thẳng kéo dài
                cv2.line(temp, pt1, pt2, (0, 0, 255), 2)
                # Vẽ vùng
                mask = np.zeros_like(frame, dtype=np.uint8)
                # Tạo đa giác cho 2 vùng
                pts1 = np.array([[0,0],[w-1,0],pt2,pt1], np.int32)
                pts2 = np.array([[0,h-1],[w-1,h-1],pt2,pt1], np.int32)
                cv2.fillPoly(mask, [pts1], (0,255,0))
                cv2.fillPoly(mask, [pts2], (255,0,0))
                temp = cv2.addWeighted(mask, 0.1, temp, 0.9, 0)
            cv2.imshow(window_name, temp)
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter to finish
                self.done = True
            elif key == 27:  # ESC to cancel
                self.line = None
                self.done = True
        cv2.destroyWindow(window_name)
        if self.start_point and self.end_point:
            # Trả về 2 điểm mép ảnh
            x1, y1 = self.start_point
            x2, y2 = self.end_point
            if x1 == x2:
                pt1 = (x1, 0)
                pt2 = (x2, h)
            else:
                slope = (y2 - y1) / (x2 - x1)
                intercept = y1 - slope * x1
                y_left = int(intercept)
                y_right = int(slope * (w-1) + intercept)
                pt1 = (0, y_left)
                pt2 = (w-1, y_right)
            self.line = (*pt1, *pt2)
        return self.line

    def mouse_events(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            self.end_point = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.end_point = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.end_point = (x, y)
