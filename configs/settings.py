from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

VALID_EXTENSION = ('.jpg', '.jpeg', '.png')

# Cache extract frames from video
CACHE_DIR = BASE_DIR / "data" / "cache"

# Model
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "bestyolo11n.pt"

# Testing input-output
IMAGE_TEST_PATH = BASE_DIR / "assets" / "images" / "test.jpg"
VIDEO_TEST_PATH = BASE_DIR / "assets" / "videos" / "test.mp4"

OUTPUT_TEST_DIR = BASE_DIR / "tests" / "result"
IMAGE_TEST_RESULT_PATH = OUTPUT_TEST_DIR / "result_image.jpg"

# Detecting processor
OUTPUT_DETECT_DIR = BASE_DIR / "data" / "output_cache"


# UX
MAX_FPS = 15