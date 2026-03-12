"""
Settings: Hằng số và đường dẫn cấu hình toàn cục.

Tất cả tham số có thể tinh chỉnh được dồn về đây để dễ quản lý.
Khi cần thay đổi hành vi hệ thống, chỉ cần sửa file này.

Ai dùng module này?
    - main.py             -- MODEL_PATH
    - video_service.py    -- BASE_DIR, MAX_QUEUE_SIZE
    - detector.py         -- DETECTION_CONFIDENCE, DETECTION_IMGSZ
    - counter_service.py  -- COUNTER_BUFFER_PIXELS, MAX_TRACKED_OBJECTS
    - frame_extractor.py  -- DEFAULT_FPS, MAX_STREAM_FAILURES, DEFAULT_STREAM_WIDTH
    - ai_service.py       -- DEFAULT_FPS
    - draw_line.py        -- LINE_*
"""

from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# ĐƯỜNG DẪN
# ═══════════════════════════════════════════════════════════════════════

# Thư mục gốc của project (ObjectCounting/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Đường dẫn model YOLO (OpenVINO format) -- dùng bởi main.py -> AIService
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "best_openvino_model"

# Đường dẫn video test -- dùng cho testing
VIDEO_TEST_PATH = BASE_DIR / "assets" / "videos" / "test.mp4"

# Cache và output
CACHE_DIR = BASE_DIR / "data" / "cache"            # Frame annotated tạm
OUTPUT_DIR = BASE_DIR / "data" / "output"           # Video output đã xử lý
SNAPSHOT_DIR = BASE_DIR / "data" / "cache_processed"  # Ảnh lưu khi có sự kiện đếm
DB_PATH = BASE_DIR / "data" / "history.db"          # SQLite database
CACHE_IMAGE_QUALITY = 85                            # JPEG quality (0-100)
OUTPUT_VIDEO_FPS = 30                               # FPS cho video output

# ═══════════════════════════════════════════════════════════════════════
# DETECTION (YOLO)
# ═══════════════════════════════════════════════════════════════════════

# Ngưỡng confidence cho YOLO detection
DETECTION_CONFIDENCE = 0.4

# Kích thước ảnh đầu vào cho YOLO
# OpenVINO model export với shape cố định → phải khớp với lúc export
# Muốn dùng 1280: cần re-export model với imgsz=1280
DETECTION_IMGSZ = 640

# ═══════════════════════════════════════════════════════════════════════
# TRACKING (ByteTrack) -- đang dùng default ultralytics
# ═══════════════════════════════════════════════════════════════════════
# Hiện tại dùng bytetrack.yaml mặc định, không custom gì.

# ═══════════════════════════════════════════════════════════════════════
# COUNTER (đếm nhập/xuất)
# ═══════════════════════════════════════════════════════════════════════

# Chỉ đếm các class này (label ID). None = đếm tất cả.
# Lấy từ metadata.yaml: 0=can_nho, 1=can_to, 2=xo_nuoc
COUNTING_CLASSES = {0, 1}  # Không đếm xo_nuoc (class 2)

# Cooldown sau mỗi lần đếm (frames) -- khóa object không cho đếm lại
# 15 frames ≈ 0.5s @30FPS -- đủ ngăn flicker, không bỏ sót vật qua nhanh
COUNTER_COOLDOWN_FRAMES = 15

# Giới hạn số track tối đa trong bộ nhớ counter
MAX_TRACKED_OBJECTS = 10000

# ═══════════════════════════════════════════════════════════════════════
# STREAM / VIDEO
# ═══════════════════════════════════════════════════════════════════════

# FPS mặc định khi không đọc được từ video (dùng cho stream và fallback)
DEFAULT_FPS = 30

# FPS mặc định cho video file khi OpenCV trả về giá trị bất thường (< 1)
DEFAULT_VIDEO_FPS = 25

# Width mặc định cho stream (khi user chưa chọn resolution)
DEFAULT_STREAM_WIDTH = 640

# Số lần reconnect tối đa khi stream mất kết nối
MAX_STREAM_FAILURES = 30

# Kích thước tối đa của Queue frame
# Giá trị nhỏ = ít RAM nhưng AI có thể phải chờ; lớn = tốn RAM nhưng mượt hơn
MAX_QUEUE_SIZE = 30
# Queue nhỏ cho stream để ưu tiên realtime (giảm độ trễ)
MAX_QUEUE_SIZE_STREAM = 2
# Luôn ưu tiên frame mới nhất khi xử lý stream (giảm lag)
REALTIME_DROP_FRAMES = True

# ═══════════════════════════════════════════════════════════════════════
# UI / DRAWING (vẽ overlay)
# ═══════════════════════════════════════════════════════════════════════

# Độ trong suốt overlay vùng Nhập/Xuất (0.0 = hoàn toàn trong suốt)
LINE_OVERLAY_ALPHA = 0.1

# Màu và độ dày vạch ảo trên ảnh (BGR format)
LINE_COLOR = (0, 0, 255)     # Đỏ
LINE_THICKNESS = 2

# Kích thước hiển thị mục tiêu (dùng để scale overlay khi resize UI)
UI_TARGET_WIDTH = 800
UI_TARGET_HEIGHT = 600
UI_BASE_FONT_SCALE = 0.7
UI_BASE_TEXT_THICKNESS = 2
UI_BASE_BOX_THICKNESS = 2
UI_BASE_ARROW_LEN = 50

# Timestamp space (crop góc trái)
TIMESTAMP_SPACE_ENABLED = True
# ROI theo tỉ lệ ảnh gốc: (x, y, w, h)
TIMESTAMP_SPACE_REL = (0.0, 0.0, 0.35, 0.08)
TIMESTAMP_SPACE_DIR = BASE_DIR / "data" / "timestamp_space"
TIMESTAMP_SPACE_ROI_PATH = TIMESTAMP_SPACE_DIR / "roi.json"

# OCR after stop (video only)
TIMESTAMP_OCR_ENABLED = True
TIMESTAMP_OCR_LANG = "eng"
TIMESTAMP_OCR_WHITELIST = "0123456789:-/ "
TIMESTAMP_OCR_REGEX = r"\d{2}[-/]\d{2}[-/]\d{4}.*?\d{2}:\d{2}:\d{2}"
TESSERACT_CMD = ""
