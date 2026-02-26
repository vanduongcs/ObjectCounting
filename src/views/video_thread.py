"""
Video Thread: Nơi chạy logic AI (Background Thread).

Qt yêu cầu xử lý nặng phải tách khỏi Main Thread để không làm treo giao diện.
Thread này sẽ gọi AIService.detect_and_track() chạy liên tục.
"""

from PyQt6.QtCore import QThread


class VideoThread(QThread):
    def __init__(self, ai_service, extraction_thread, frame_queue=None, virtual_line=None):
        """
        Khởi tạo worker thread.
        Args:
            ai_service: Service chứa logic AI.
            extraction_thread: Thread lấy frame (để check trạng thái).
            frame_queue: Hàng đợi frame.
            virtual_line: Tọa độ vạch đếm.
        """
        super().__init__()
        self.ai_service = ai_service
        self.extraction_thread = extraction_thread
        self.frame_queue = frame_queue
        self.virtual_line = virtual_line

    def run(self):
        """Logic chính chạy trên thread riêng."""
        self.ai_service.detect_and_track(
            self.extraction_thread,
            frame_queue=self.frame_queue,
            virtual_line=self.virtual_line
        )
