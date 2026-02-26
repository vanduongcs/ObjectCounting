"""
Settings: Chứa các hằng số và đường dẫn cấu hình toàn cục.
"""

from pathlib import Path

# Thư mục gốc của project (ObjectCounting/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Các định dạng file ảnh được hỗ trợ
VALID_EXTENSION = ('.jpg', '.jpeg', '.png')

# --- ĐƯỜNG DẪN THƯ MỤC ---
CACHE_DIR = BASE_DIR / "data" / "cache"                 # Frame tạm thời (nếu có dùng)
MODELS_DIR = BASE_DIR / "models"                        # Thư mục chứa model AI
OUTPUT_DETECT_DIR = BASE_DIR / "data" / "output_cache"  # Output kết quả detect

# --- ĐƯỜNG DẪN FILE ---
MODEL_PATH = MODELS_DIR / "best_openvino_model"  # Model YOLO OpenVINO (tối ưu CPU/iGPU Intel)
IMAGE_TEST_PATH = BASE_DIR / "assets" / "images" / "test.jpg"
VIDEO_TEST_PATH = BASE_DIR / "assets" / "videos" / "test.mp4"
IMAGE_TEST_RESULT_PATH = BASE_DIR / "tests" / "result" / "result_image.jpg"

# --- CẤU HÌNH ---
MAX_QUEUE_SIZE = 5  # Số frame tối đa trong hàng đợi xử lý