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
WINDOW_STATE_PATH = BASE_DIR / "data" / "window_state.json"
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

# UI and drawing tuning were moved to configs/settings_interface.py

# Timestamp space (crop góc trái)
TIMESTAMP_SPACE_ENABLED = True
# ROI theo tỉ lệ ảnh gốc: (x, y, w, h)
DEFAULT_TIMESTAMP_SPACE_REL = (0.0, 0.0, 0.35, 0.08)
TIMESTAMP_SPACE_REL = DEFAULT_TIMESTAMP_SPACE_REL
TIMESTAMP_SPACE_DIR = BASE_DIR / "data" / "timestamp_space"
TIMESTAMP_SPACE_ROI_PATH = TIMESTAMP_SPACE_DIR / "roi.json"
TIMESTAMP_SPACE_SESSION_ROOT = TIMESTAMP_SPACE_DIR / "sessions"
VIRTUAL_LINE_PATH = BASE_DIR / "data" / "virtual_line.json"

# OCR after stop (video only)
TIMESTAMP_OCR_ENABLED = True
TIMESTAMP_OCR_LANG = "eng"
TIMESTAMP_OCR_WHITELIST = "0123456789:-/ "
TIMESTAMP_OCR_REGEX = r"\d{2}[-/]\d{2}[-/]\d{4}.*?\d{2}:\d{2}:\d{2}"
TESSERACT_CMD = ""

# Tracklet stitching (ByteTrack bridge)
TRACKLET_ENABLED = True
TRACKLET_MAX_LOST_FRAMES = 18
TRACKLET_MIN_OBSERVE_FRAMES = 3
TRACKLET_MAX_LOST_TRACKS = 200
TRACKLET_IOU_THRESHOLD = 0.30
TRACKLET_MAX_DISTANCE_PIXELS = 90
TRACKLET_MAX_DISTANCE_RATIO = 0.05
TRACKLET_SIZE_RATIO_MIN = 0.5
TRACKLET_SIZE_RATIO_MAX = 2.0
TRACKLET_REMAP_TTL = 60
TRACKLET_MISSING_TO_LOST = 2
TRACKLET_REMAP_COOLDOWN = 10
TRACKLET_DIRECTION_MIN_COS = 0.15
TRACKLET_MIN_SPEED_FOR_DIRECTION = 6.0
TRACKLET_MIN_CONFIDENCE = 0.20

# Video playback sync (file): drop frames to keep 1s display ~= 1s video
VIDEO_REALTIME_SYNC = True
VIDEO_REALTIME_MAX_LAG_SEC = 0.5
