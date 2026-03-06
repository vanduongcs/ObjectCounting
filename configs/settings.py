"""
Settings: Hằng số và đường dẫn cấu hình toàn cục.

Tất cả tham số có thể tinh chỉnh được dồn về đây để dễ quản lý.
Khi cần thay đổi hành vi hệ thống, chỉ cần sửa file này.

Ai dùng module này?
    - main.py             -- MODEL_PATH
    - video_service.py    -- BASE_DIR, MAX_QUEUE_SIZE
    - detector.py         -- DETECTION_CONFIDENCE, TRACK_BUFFER_*
    - counter_service.py  -- COUNTER_BUFFER_PIXELS, MAX_TRACKED_OBJECTS
    - tracklet_stitcher.py-- STITCH_*
    - frame_extractor.py  -- DEFAULT_FPS, MAX_STREAM_FAILURES, DEFAULT_STREAM_WIDTH
    - ai_service.py       -- TRACK_BUFFER_SECONDS, DEFAULT_FPS
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
MODEL_PATH = MODELS_DIR / "best.pt"

# Đường dẫn video test -- dùng cho testing
VIDEO_TEST_PATH = BASE_DIR / "assets" / "videos" / "test.mp4"

# Cache và output
CACHE_DIR = BASE_DIR / "data" / "cache"            # Frame annotated tạm
OUTPUT_DIR = BASE_DIR / "data" / "output"           # Video output đã xử lý
DB_PATH = BASE_DIR / "data" / "history.db"          # SQLite database
CACHE_IMAGE_QUALITY = 85                            # JPEG quality (0-100)
OUTPUT_VIDEO_FPS = 30                               # FPS cho video output

# ═══════════════════════════════════════════════════════════════════════
# DETECTION (YOLO)
# ═══════════════════════════════════════════════════════════════════════

# Ngưỡng confidence cho YOLO detection
DETECTION_CONFIDENCE = 0.15

# ═══════════════════════════════════════════════════════════════════════
# TRACKING (ByteTrack)
# ═══════════════════════════════════════════════════════════════════════

# Thời gian giữ track khi vật bị mất (giây)
# track_buffer = FPS × TRACK_BUFFER_SECONDS (ví dụ: 30 FPS × 5s = 150 frames)
TRACK_BUFFER_SECONDS = 5

# Track buffer tối thiểu (frames) -- tránh buffer quá ngắn khi FPS thấp
TRACK_BUFFER_MIN_FRAMES = 30

# ═══════════════════════════════════════════════════════════════════════
# TRACKLET STITCHER (ghép nối quỹ đạo)
# ═══════════════════════════════════════════════════════════════════════

STITCH_MAX_DISTANCE = 200        # Pixel tối đa giữa predicted pos và actual pos
STITCH_SIZE_RATIO_THRESH = 0.5   # Bbox chênh lệch kích thước tối đa (50%)
STITCH_MIN_OBSERVE_FRAMES = 5    # Track phải quan sát ≥ N frames mới vào pool
STITCH_CONFIDENCE_GATE = 0.2     # Conf tối thiểu của detection mới
STITCH_REMAP_COOLDOWN = 10       # Cooldown sau mỗi lần ghép (frames)
STITCH_MAX_LOST_TRACKS = 200     # Giới hạn lost pool
STITCH_COST_THRESHOLD = 0.6      # Cost tối đa để chấp nhận ghép

# Trọng số cost function (tổng = 1.0)
STITCH_W_DISTANCE = 0.40
STITCH_W_SIZE = 0.25
STITCH_W_TIME = 0.20
STITCH_W_DIRECTION = 0.15

# Guard 7: Collision với active track — nếu new detection overlap ≥ N%
# với active track khác → reject stitch (tránh cướp ID khi chồng lấn)
STITCH_COLLISION_IOU_THRESH = 0.3

# ═══════════════════════════════════════════════════════════════════════
# COUNTER (đếm nhập/xuất)
# ═══════════════════════════════════════════════════════════════════════

# Chỉ đếm các class này (label ID). None = đếm tất cả.
# Lấy từ metadata.yaml: 0=can_nho, 1=can_to, 2=xo_nuoc
COUNTING_CLASSES = {0, 1}  # Không đếm xo_nuoc (class 2)

# Vùng đệm quanh vạch ảo (pixel) -- tránh đếm rung khi vật đứng gần vạch
COUNTER_BUFFER_PIXELS = 15

# Số frames liên tiếp vật phải ở vùng mới để xác nhận chuyển vùng (debounce)
# 2 = chặn flicker 1-frame, không bỏ sót vật thực
COUNTER_CONFIRM_FRAMES = 2

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

# ═══════════════════════════════════════════════════════════════════════
# UI / DRAWING (vẽ overlay)
# ═══════════════════════════════════════════════════════════════════════

# Độ trong suốt overlay vùng Nhập/Xuất (0.0 = hoàn toàn trong suốt)
LINE_OVERLAY_ALPHA = 0.1

# Màu và độ dày vạch ảo trên ảnh (BGR format)
LINE_COLOR = (0, 0, 255)     # Đỏ
LINE_THICKNESS = 2