"""
AI Service: Quản lý vòng lặp chính của ứng dụng.
Nhận frame từ Queue -> Detect (YOLO) -> Draw/Display -> Count.
"""

import queue

from .detector import ObjectDetector
from .counter_service import CounterService


class AIService:
    def __init__(self, model_path, display_handler=None):
        """
        Khởi tạo AI Service.
        Args:
            model_path: Đường dẫn model YOLO.
            display_handler: Adapter để gửi ảnh render về UI.
        """
        self.detector = ObjectDetector(model_path)
        self.display_handler = display_handler

        # Tùy chọn hiển thị (UI toggle)
        self.show_boxes = True
        self.show_masks = False

    def detect_and_track(self, extraction_thread=None, frame_queue=None, virtual_line=None):
        """
        Vòng lặp xử lý chính:
        1. Lấy frame từ Queue.
        2. Chạy YOLO track (detect + tracking).
        3. Vẽ bounding box & gửi về UI.
        4. Cập nhật bộ đếm (CounterService).
        """
        # Khởi tạo bộ đếm nếu có vạch ảo
        counter = None
        if virtual_line:
            counter = CounterService(virtual_line[0], virtual_line[1])

        while True:
            # Lấy frame từ hàng đợi (có timeout để không treo vĩnh viễn)
            if frame_queue is None:
                break

            try:
                frame = frame_queue.get(timeout=1)
            except Exception:
                # Nếu thread trích xuất đã dừng mà queue rỗng -> Dừng hẳn
                if extraction_thread and not extraction_thread.isRunning():
                    break
                continue

            # Sentinel Check: None báo hiệu hết video
            if frame is None:
                break

            # === DRAIN QUEUE: Giới hạn số frame bỏ qua ===
            # max_skip = 0: KHÔNG bỏ frame nào.
            # Tracker (ByteTrack/Kalman Filter) cần frame liên tiếp để duy trình
            # track ID ổn định khi vật đang di chuyển. Bỏ frame → vật "nhảy" vị trí
            # → IoU thấp → mất ID.
            # Đánh đổi: nếu GPU chậm hơn FPS trích xuất, video sẽ có độ trễ nhẹ.
            max_skip = 0
            skipped = 0
            while skipped < max_skip and not frame_queue.empty():
                try:
                    newer_frame = frame_queue.get_nowait()
                    if newer_frame is None:
                        # Sentinel -> dừng
                        frame = None
                        break
                    frame = newer_frame  # Cập nhật frame mới hơn
                    skipped += 1
                except queue.Empty:
                    break
            
            if frame is None:
                break

            # Gọi YOLO detect & track (1 lần gọi duy nhất)
            result = self.detector.track_with_result(frame)
            if result is not None:
                track_result, detected_info = result

                # Kiểm tra kết quả hợp lệ trước khi vẽ
                if not track_result:
                    if self.display_handler:
                        self.display_handler.show(frame)
                    continue

                # Vẽ bounding box lên frame
                frame_detected_image = track_result[0].plot(
                    boxes=self.show_boxes, masks=self.show_masks
                )

                if counter:
                    # Luôn update (kể cả frame không có detection)
                    counter.update(detected_info)

                    # Luôn gửi số liệu về UI sau mỗi frame
                    if self.display_handler:
                        c_nhap, c_xuat = counter.get_counts()
                        names = self.detector.yolo_model.names
                        final_nhap = {names[k]: v for k, v in c_nhap.items()}
                        final_xuat = {names[k]: v for k, v in c_xuat.items()}
                        self.display_handler.emit_counts(final_nhap, final_xuat)

                # Gửi ảnh đã vẽ về giao diện
                if self.display_handler:
                    self.display_handler.show(frame_detected_image)

        # In tổng kết ra console (debug)
        if counter:
            count_nhap, count_xuat = counter.get_counts()
            print(f"Kết quả đếm - Nhập: {count_nhap}, Xuất: {count_xuat}")
