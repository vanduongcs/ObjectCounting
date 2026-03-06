"""
Video Thread: Background thread để chạy logic AI mà không treo UI.

Ai gọi module này?
    - MainWindow.start_processing() tạo VideoThread và gọi .start()

Module này gọi ai?
    - AIService.detect_and_track() -- vòng lặp xử lý chính.

Tại sao cần thread riêng?
    YOLO inference mất ~30-100ms/frame. Nếu chạy trên UI thread,
    giao diện sẽ đơ. QThread cho phép chạy song song.

Luồng dữ liệu:
    MainWindow --tạo--> VideoThread --gọi--> AIService.detect_and_track()
                                              |
                                         Queue.get() -> Detect -> Draw -> Count
                                              |
                                         QtDisplayAdapter --signal--> MainWindow (hiển thị)
"""

from PyQt6.QtCore import QThread


class VideoThread(QThread):
    """
    Wrapper QThread cho AIService -- chỉ forward tham số và gọi detect_and_track.

    Khi thread kết thúc (video hết hoặc user bấm Dừng),
    signal 'finished' được emit -> MainWindow.on_processing_finished() reset UI.
    """

    def __init__(self, ai_service, extraction_thread, frame_queue=None,
                 virtual_line=None, video_name=""):
        super().__init__()
        self.ai_service = ai_service
        self.extraction_thread = extraction_thread
        self.frame_queue = frame_queue
        self.virtual_line = virtual_line
        self.video_name = video_name

    def run(self):
        """Chạy vòng lặp AI (blocking cho đến hết video)."""
        self.ai_service.detect_and_track(
            self.extraction_thread,
            frame_queue=self.frame_queue,
            virtual_line=self.virtual_line,
            video_name=self.video_name,
        )
