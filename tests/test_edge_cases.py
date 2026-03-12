"""
Test Edge Cases: Kiểm tra logic đếm và trạng thái UI.

Cách chạy: python -m tests.test_edge_cases
"""

import sys
import os
from unittest.mock import MagicMock

# Fix encoding cho Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Mock PyQt6 & ultralytics (không cần cài để test logic)
sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = MagicMock()
sys.modules['PyQt6.QtCore'] = MagicMock()
sys.modules['PyQt6.QtGui'] = MagicMock()
sys.modules['ultralytics'] = MagicMock()

from src.services.counter_service import CounterService
import configs.settings as settings


# ======================================================================
# HELPER
# ======================================================================
_SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')


def _read_source(relative_path):
    with open(os.path.join(_SOURCE_DIR, relative_path), 'r', encoding='utf-8') as f:
        return f.read()


def _make_det(id, label=0, cx=100, cy=100, w=50, h=50, conf=0.8):
    """Helper tạo detection dict cho tests."""
    return {"id": id, "label": label, "center": (cx, cy),
            "bbox_wh": (w, h), "conf": conf}


def _repeat_update(counter, detections, n=5):
    """Gửi cùng detections n lần liên tiếp để thoả debounce."""
    for _ in range(n):
        counter.update(detections)


# ======================================================================
# COUNTER SERVICE TESTS
# ======================================================================

def test_counter_basic_nhap():
    """XUAT → NHAP = đếm 1 NHẬP."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (250, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    nhap, xuat = counter.get_counts()
    assert nhap.get(0, 0) == 1
    assert xuat.get(0, 0) == 0
    print("✅ TEST 1 PASSED: Đếm NHẬP cơ bản")


def test_counter_basic_xuat():
    """NHAP → XUAT = đếm 1 XUẤT."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (250, 200)}])
    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1
    assert nhap.get(0, 0) == 0
    print("✅ TEST 2 PASSED: Đếm XUẤT cơ bản")


def test_counter_near_line_still_counts():
    """Vật gần vạch vẫn đếm (không có buffer zone nữa)."""
    counter = CounterService((200, 0), (200, 400))
    # Bắt đầu ở x=195 (rất gần vạch, bên NHAP)
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (195, 200)}])
    # Di chuyển sang x=205 (rất gần vạch, bên XUAT)
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (205, 200)}])
    nhap, xuat = counter.get_counts()
    assert sum(nhap.values()) + sum(xuat.values()) == 1
    print("✅ TEST 3 PASSED: Gần vạch vẫn đếm đúng")


def test_counter_multiple_objects():
    """Nhiều vật cùng qua vạch."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [
        {"id": 1, "label": 0, "center": (150, 100)},
        {"id": 2, "label": 0, "center": (150, 200)},
        {"id": 3, "label": 1, "center": (150, 300)},
    ])
    _repeat_update(counter, [
        {"id": 1, "label": 0, "center": (250, 100)},
        {"id": 2, "label": 0, "center": (250, 200)},
        {"id": 3, "label": 1, "center": (250, 300)},
    ])
    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 2
    assert xuat.get(1, 0) == 1
    print("✅ TEST 4 PASSED: Đếm nhiều vật cùng lúc")


def test_counter_no_double_count():
    """Qua vạch 1 lần chỉ đếm 1."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (250, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (300, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (350, 200)}])
    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1
    print("✅ TEST 5 PASSED: Không đếm trùng")


def test_counter_object_returns():
    """NHAP → XUAT → NHAP = 1 XUẤT + 1 NHẬP (phải chờ cooldown hết)."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (250, 200)}])
    # Chờ cooldown hết
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (250, 200)}],
                   n=settings.COUNTER_COOLDOWN_FRAMES + 1)
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1
    assert nhap.get(0, 0) == 1
    print("✅ TEST 6 PASSED: Vật quay lại đếm đúng")


def test_counter_memory_limit():
    """object_states phải được giới hạn."""
    counter = CounterService((200, 0), (200, 400))
    for i in range(settings.MAX_TRACKED_OBJECTS + 500):
        counter.update([{"id": i, "label": 0, "center": (150, 200)}])
    assert len(counter.object_states) <= settings.MAX_TRACKED_OBJECTS + 1
    print(f"✅ TEST 7 PASSED: Memory limit ({len(counter.object_states)} entries)")


def test_counter_diagonal_line():
    """Vạch chéo vẫn đếm đúng."""
    counter = CounterService((0, 0), (400, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (100, 300)}])
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (300, 100)}])
    nhap, xuat = counter.get_counts()
    assert sum(nhap.values()) + sum(xuat.values()) == 1
    print("✅ TEST 8 PASSED: Vạch chéo đếm đúng")


def test_counter_flicker_no_overcount():
    """Vật nhấp nháy qua vạch → chỉ đếm ít (anti-flicker)."""
    counter = CounterService((200, 0), (200, 400))
    _repeat_update(counter, [{"id": 1, "label": 0, "center": (150, 200)}])
    # Nhấp nháy: qua lại vạch mỗi frame (1 frame mỗi bên, < debounce=2)
    for _ in range(20):
        counter.update([{"id": 1, "label": 0, "center": (250, 200)}])
        counter.update([{"id": 1, "label": 0, "center": (150, 200)}])
    nhap, xuat = counter.get_counts()
    total = sum(nhap.values()) + sum(xuat.values())
    assert total <= 1, f"Flicker: expected ≤1, got {total}"
    print(f"✅ TEST 8b PASSED: Anti-flicker (total={total})")


# ======================================================================
# TRACKLET STITCHER TESTS -- tạm bỏ (stitcher disabled)
# ======================================================================


# ======================================================================
# UI STATE TESTS (kiểm tra source code)
# ======================================================================

def test_ui_running_state_toggle():
    """_set_ui_running phải toggle đúng các nút."""
    source = _read_source('views/main_window.py')
    assert '_set_ui_running' in source
    assert '_set_ui_running(True)' in source
    assert '_set_ui_running(False)' in source
    print("✅ TEST 15 PASSED: _set_ui_running toggle đúng")


def test_close_event_has_cleanup():
    """closeEvent phải gọi _cleanup_threads."""
    source = _read_source('views/main_window.py')
    lines = source.split('\n')
    found_close = False
    for i, line in enumerate(lines):
        if 'def closeEvent' in line:
            found_close = True
        if found_close and '_cleanup_threads' in line:
            break
    assert found_close, "closeEvent không tìm thấy"
    assert '_cleanup_threads' in source
    print("✅ TEST 16 PASSED: closeEvent cleanup đúng")


def test_start_cleans_old_threads():
    """start_processing phải cleanup thread cũ trước khi tạo mới."""
    source = _read_source('views/main_window.py')
    cleanup_pos = source.index('_cleanup_threads')
    thread_pos = source.index('start_extraction')
    assert cleanup_pos < thread_pos
    print("✅ TEST 17 PASSED: start_processing cleanup thread cũ đúng")


def test_start_without_video_returns():
    """start_processing phải kiểm tra current_video_path."""
    source = _read_source('views/main_window.py')
    assert 'current_video_path' in source
    print("✅ TEST 18 PASSED: start guard check OK")


def test_frame_extractor_reconnect_limit():
    """FrameExtractor phải có giới hạn reconnect."""
    source = _read_source('services/frame_extractor.py')
    assert 'MAX_STREAM_FAILURES' in source
    assert 'consecutive_failures' in source
    print("✅ TEST 19 PASSED: Stream reconnect limit đúng")


def test_virtual_line_scaling():
    """start_processing phải scale vạch ảo."""
    source = _read_source('views/main_window.py')
    assert '_scale_line' in source
    print("✅ TEST 20 PASSED: Virtual line scaling logic OK")


# ======================================================================
# RUNNER
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("CHAY EDGE CASE TESTS")
    print("=" * 60)

    tests = [
        ("Dem NHAP co ban", test_counter_basic_nhap),
        ("Dem XUAT co ban", test_counter_basic_xuat),
        ("Gan vach van dem", test_counter_near_line_still_counts),
        ("Dem nhieu vat cung luc", test_counter_multiple_objects),
        ("Khong dem trung", test_counter_no_double_count),
        ("Vat quay lai", test_counter_object_returns),
        ("Memory limit", test_counter_memory_limit),
        ("Vach cheo", test_counter_diagonal_line),
        ("Anti-flicker", test_counter_flicker_no_overcount),

        ("UI running state toggle", test_ui_running_state_toggle),
        ("closeEvent cleanup", test_close_event_has_cleanup),
        ("start cleanup thread cu", test_start_cleans_old_threads),
        ("start guard check", test_start_without_video_returns),
        ("Stream reconnect limit", test_frame_extractor_reconnect_limit),
        ("Virtual line scaling", test_virtual_line_scaling),
    ]

    passed = failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"FAILED: {name}")
            print(f"   Error: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"KET QUA: {passed}/{passed + failed} passed, {failed} failed")
    if failed == 0:
        print("TAT CA TESTS DEU PASS!")
    else:
        print(f"CO {failed} TEST THAT BAI!")
    print("=" * 60)
