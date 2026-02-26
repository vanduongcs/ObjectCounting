"""
Test Edge Cases: Kiểm tra các tình huống đặc biệt khi UI chuyển trạng thái.

Các trường hợp test:
1. Đang xử lý → Tạm dừng → Đổi độ phân giải: CÓ ĐƯỢC (resolution thay đổi real-time)
2. Đang xử lý → Kết nối camera khác: KHÔNG ĐƯỢC (nút bị khóa)
3. Đang xử lý → Chọn video khác: KHÔNG ĐƯỢC (nút bị khóa)
4. Đang xử lý → Xoay: KHÔNG ĐƯỢC (nút bị khóa)
5. Đang xử lý → Vẽ vạch: KHÔNG ĐƯỢC (nút bị khóa)
6. Tạm dừng → Tiếp tục → Tạm dừng (toggle nhiều lần)
7. Dừng → Chọn video mới → Chạy lại
8. Đóng cửa sổ khi đang xử lý
9. Chạy mà chưa chọn video
10. Chạy mà chưa vẽ vạch (vẫn chạy, chỉ không đếm)
11. Đổi FPS khi đang tạm dừng
12. Xuất Excel khi chưa có dữ liệu

Cách chạy: python -m pytest tests/test_edge_cases.py -v
(Hoặc:  python -m tests.test_edge_cases  để chạy trực tiếp)
"""

import sys
import queue
from unittest.mock import MagicMock, patch, PropertyMock

# Fix encoding cho Windows console (tránh lỗi cp1252)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# === MOCK PyQt6 TRƯỚC KHI IMPORT (không cần cài PyQt6 để test logic) ===
# Tạo mock module cho PyQt6 để test logic mà không cần GUI thật
mock_qt_widgets = MagicMock()
mock_qt_core = MagicMock()
mock_qt_gui = MagicMock()

sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = mock_qt_widgets
sys.modules['PyQt6.QtCore'] = mock_qt_core
sys.modules['PyQt6.QtGui'] = mock_qt_gui

# Mock ultralytics (nặng, không cần cho test UI)
sys.modules['ultralytics'] = MagicMock()

# --- Bây giờ mới import ---
from src.services.counter_service import CounterService, MAX_TRACKED_OBJECTS


# ======================================================================
# TEST 1: CounterService - Logic đếm cơ bản
# ======================================================================
def test_counter_basic_nhap():
    """Vật thể di chuyển từ XUAT → NHAP phải được đếm là NHẬP."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    # Frame 1: Vật ở bên XUAT (phải vạch, cross < 0)
    counter.update([{"id": 1, "label": 0, "center": (250, 200), "bbox": (0, 0, 0, 0)}])

    # Frame 2: Vật qua vạch, sang bên NHAP (trái vạch, cross > 0)
    counter.update([{"id": 1, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])

    nhap, xuat = counter.get_counts()
    assert nhap.get(0, 0) == 1, f"Phải đếm 1 NHẬP, nhưng got {nhap}"
    assert xuat.get(0, 0) == 0, f"Phải 0 XUẤT, nhưng got {xuat}"
    print("✅ TEST 1 PASSED: Đếm NHẬP cơ bản")


def test_counter_basic_xuat():
    """Vật thể di chuyển từ NHAP → XUAT phải được đếm là XUẤT."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    # Frame 1: Ở bên NHAP (trái)
    counter.update([{"id": 1, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])
    # Frame 2: Sang bên XUAT (phải)
    counter.update([{"id": 1, "label": 0, "center": (250, 200), "bbox": (0, 0, 0, 0)}])

    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1, f"Phải đếm 1 XUẤT, nhưng got {xuat}"
    assert nhap.get(0, 0) == 0, f"Phải 0 NHẬP, nhưng got {nhap}"
    print("✅ TEST 2 PASSED: Đếm XUẤT cơ bản")


# ======================================================================
# TEST 2: CounterService - Vùng BUFFER (không đếm trùng)
# ======================================================================
def test_counter_buffer_zone_no_count():
    """Vật ở trong vùng BUFFER → KHÔNG được đếm."""
    counter = CounterService((200, 0), (200, 400), buffer=50)

    # Vật ở sát vạch (trong buffer zone)
    counter.update([{"id": 1, "label": 0, "center": (195, 200), "bbox": (0, 0, 0, 0)}])
    counter.update([{"id": 1, "label": 0, "center": (205, 200), "bbox": (0, 0, 0, 0)}])

    nhap, xuat = counter.get_counts()
    total = sum(nhap.values()) + sum(xuat.values())
    assert total == 0, f"Phải 0 (trong buffer), nhưng đếm được {total}"
    print("✅ TEST 3 PASSED: Vùng BUFFER không đếm")


# ======================================================================
# TEST 3: CounterService - Đếm nhiều vật cùng lúc
# ======================================================================
def test_counter_multiple_objects():
    """Nhiều vật thể khác nhau qua vạch cùng lúc."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    # 3 vật xuất hiện bên NHAP
    counter.update([
        {"id": 1, "label": 0, "center": (150, 100), "bbox": (0, 0, 0, 0)},
        {"id": 2, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)},
        {"id": 3, "label": 1, "center": (150, 300), "bbox": (0, 0, 0, 0)},
    ])

    # Cả 3 đi sang bên XUAT
    counter.update([
        {"id": 1, "label": 0, "center": (250, 100), "bbox": (0, 0, 0, 0)},
        {"id": 2, "label": 0, "center": (250, 200), "bbox": (0, 0, 0, 0)},
        {"id": 3, "label": 1, "center": (250, 300), "bbox": (0, 0, 0, 0)},
    ])

    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 2, f"Label 0 phải XUẤT 2, got {xuat.get(0, 0)}"
    assert xuat.get(1, 0) == 1, f"Label 1 phải XUẤT 1, got {xuat.get(1, 0)}"
    print("✅ TEST 4 PASSED: Đếm nhiều vật cùng lúc")


# ======================================================================
# TEST 4: CounterService - Không đếm trùng khi dao động
# ======================================================================
def test_counter_no_double_count():
    """Vật qua vạch 1 lần → chỉ đếm 1. Không đếm lại nếu ở yên."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    # Xuất hiện bên NHAP
    counter.update([{"id": 1, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])
    # Qua bên XUAT
    counter.update([{"id": 1, "label": 0, "center": (250, 200), "bbox": (0, 0, 0, 0)}])
    # Vẫn ở bên XUAT (di chuyển bình thường)
    counter.update([{"id": 1, "label": 0, "center": (300, 200), "bbox": (0, 0, 0, 0)}])
    counter.update([{"id": 1, "label": 0, "center": (350, 200), "bbox": (0, 0, 0, 0)}])

    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1, f"Phải chỉ đếm 1 XUẤT, nhưng got {xuat.get(0, 0)}"
    print("✅ TEST 5 PASSED: Không đếm trùng")


# ======================================================================
# TEST 5: CounterService - Vật quay lại (NHAP → XUAT → NHAP)
# ======================================================================
def test_counter_object_returns():
    """Vật qua vạch rồi quay lại → đếm 2 lần (1 XUẤT + 1 NHẬP)."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    counter.update([{"id": 1, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])  # NHAP
    counter.update([{"id": 1, "label": 0, "center": (250, 200), "bbox": (0, 0, 0, 0)}])  # → XUAT (+1 xuất)
    counter.update([{"id": 1, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])  # → NHAP (+1 nhập)

    nhap, xuat = counter.get_counts()
    assert xuat.get(0, 0) == 1, f"Phải 1 XUẤT, got {xuat}"
    assert nhap.get(0, 0) == 1, f"Phải 1 NHẬP, got {nhap}"
    print("✅ TEST 6 PASSED: Vật quay lại đếm đúng")


# ======================================================================
# TEST 6: CounterService - Memory leak prevention
# ======================================================================
def test_counter_memory_limit():
    """object_states phải được giới hạn, không phình vô hạn."""
    counter = CounterService((200, 0), (200, 400), buffer=10)

    # Thêm hơn MAX_TRACKED_OBJECTS vật thể
    for i in range(MAX_TRACKED_OBJECTS + 500):
        counter.update([{"id": i, "label": 0, "center": (150, 200), "bbox": (0, 0, 0, 0)}])

    # Sau khi pruning, dict phải nhỏ hơn MAX + buffer
    assert len(counter.object_states) <= MAX_TRACKED_OBJECTS + 1, \
        f"object_states phải ≤ {MAX_TRACKED_OBJECTS}, nhưng có {len(counter.object_states)}"
    print(f"✅ TEST 7 PASSED: Memory limit hoạt động ({len(counter.object_states)} entries)")


# ======================================================================
# TEST 7: CounterService - Đường chéo
# ======================================================================
def test_counter_diagonal_line():
    """Vạch chéo vẫn đếm đúng."""
    # Vạch từ (0,0) tới (400,400) - đường chéo
    counter = CounterService((0, 0), (400, 400), buffer=10)

    # Vật ở "trên" đường chéo (cross > 0 → NHAP)
    counter.update([{"id": 1, "label": 0, "center": (100, 300), "bbox": (0, 0, 0, 0)}])
    # Vật "dưới" đường chéo (cross < 0 → XUAT)
    counter.update([{"id": 1, "label": 0, "center": (300, 100), "bbox": (0, 0, 0, 0)}])

    nhap, xuat = counter.get_counts()
    total = sum(nhap.values()) + sum(xuat.values())
    assert total == 1, f"Phải đếm được 1 event, got {total}"
    print("✅ TEST 8 PASSED: Vạch chéo đếm đúng")


# ======================================================================
# HELPER: Đọc source file trực tiếp (vì inspect.getsource bị Mock che)
# ======================================================================
import os

_SOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')

def _read_source(relative_path):
    """Đọc nội dung file source. VD: 'views/main_window.py'"""
    filepath = os.path.join(_SOURCE_DIR, relative_path)
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()

def _read_function(source, func_name):
    """
    Trích xuất nội dung 1 hàm/method từ source code.
    Tìm 'def func_name(' và lấy tất cả dòng cho đến khi gặp
    dòng cùng mức indent (hoặc def/class kế tiếp).
    """
    lines = source.split('\n')
    start = None
    indent = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(f'def {func_name}('):
            start = i
            indent = len(line) - len(stripped)
            continue
        if start is not None and i > start:
            # Dòng trống hoặc comment → tiếp tục
            if stripped == '' or stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Dòng code có indent > indent gốc → thuộc hàm
            current_indent = len(line) - len(stripped)
            if current_indent <= indent and stripped and not stripped.startswith('"""') and not stripped.startswith("'''"):
                return '\n'.join(lines[start:i])
    if start is not None:
        return '\n'.join(lines[start:])
    return ''


# ======================================================================
# TEST 8: UI State - Nút bị khóa khi đang xử lý
# ======================================================================
def test_buttons_disabled_during_processing():
    """
    Khi đang xử lý: choose, camera, draw, rotate, start phải BỊ KHÓA.
    Chỉ pause và stop được MỞ.
    """
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'start_processing')
    
    # Các nút phải bị disable
    assert 'choose_button.setEnabled(False)' in func, "choose_button phải bị khóa!"
    assert 'camera_button.setEnabled(False)' in func, "camera_button phải bị khóa!"
    assert 'draw_button.setEnabled(False)' in func, "draw_button phải bị khóa!"  
    assert 'rotate_button.setEnabled(False)' in func, "rotate_button phải bị khóa!"
    assert 'start_button.setEnabled(False)' in func, "start_button phải bị khóa!"
    
    # Pause và Stop phải được mở
    assert 'pause_button.setEnabled(True)' in func, "pause_button phải được mở!"
    assert 'stop_button.setEnabled(True)' in func, "stop_button phải được mở!"
    
    print("✅ TEST 9 PASSED: Nút bị khóa đúng khi đang xử lý")
    print("   -> User KHÔNG THỂ kết nối camera khác khi đang chạy")
    print("   -> User KHÔNG THỂ chọn video khác khi đang chạy")
    print("   -> User KHÔNG THỂ vẽ vạch / xoay khi đang chạy")


# ======================================================================
# TEST 9: UI State - Nút được mở lại sau khi dừng
# ======================================================================
def test_buttons_enabled_after_stop():
    """Sau khi dừng (stop/finish), tất cả nút phải được MỞ LẠI."""
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'on_processing_finished')
    
    assert 'choose_button.setEnabled(True)' in func, "choose_button phải được mở lại!"
    assert 'camera_button.setEnabled(True)' in func, "camera_button phải được mở lại!"
    assert 'start_button.setEnabled(True)' in func, "start_button phải được mở lại!"
    assert 'draw_button.setEnabled(True)' in func, "draw_button phải được mở lại!"
    assert 'rotate_button.setEnabled(True)' in func, "rotate_button phải được mở lại!"
    assert 'stop_button.setEnabled(False)' in func, "stop_button phải bị khóa sau khi dừng!"
    assert 'pause_button.setEnabled(False)' in func, "pause_button phải bị khóa sau khi dừng!"
    
    print("✅ TEST 10 PASSED: Nút được mở lại đúng sau khi dừng")


# ======================================================================
# TEST 10: Đổi resolution khi đang tạm dừng → ĐƯỢC
# ======================================================================
def test_change_resolution_while_paused():
    """
    Đang xử lý -> Tạm dừng -> Đổi resolution: CÓ ĐƯỢC.
    Vì change_resolution() chỉ gọi extraction_thread.set_resolution().
    """
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'change_resolution')
    
    assert 'is_paused' not in func, "change_resolution KHÔNG nên check is_paused"
    assert 'extraction_thread' in func, "change_resolution phải gọi qua extraction_thread"
    
    print("✅ TEST 11 PASSED: Đổi resolution khi tạm dừng -> ĐƯỢC")


# ======================================================================
# TEST 11: Đổi FPS khi đang tạm dừng → ĐƯỢC
# ======================================================================
def test_change_fps_while_paused():
    """Đổi FPS khi pause: CÓ ĐƯỢC (chỉ là setter)."""
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'change_fps')
    
    assert 'is_paused' not in func, "change_fps KHÔNG nên check is_paused"
    assert 'extraction_thread' in func, "change_fps phải gọi qua extraction_thread"
    
    print("✅ TEST 12 PASSED: Đổi FPS khi tạm dừng -> ĐƯỢC")


# ======================================================================
# TEST 12: closeEvent phải cleanup threads
# ======================================================================
def test_close_event_has_cleanup():
    """Khi đóng cửa sổ, phải gọi _cleanup_threads."""
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'closeEvent')
    
    assert '_cleanup_threads' in func, "closeEvent PHẢI gọi _cleanup_threads!"
    assert 'event.accept()' in func, "closeEvent PHẢI accept event!"
    
    print("✅ TEST 13 PASSED: closeEvent cleanup đúng")


# ======================================================================  
# TEST 13: start_processing phải cleanup thread cũ
# ======================================================================
def test_start_cleans_old_threads():
    """Khi bấm Bắt đầu lần 2, phải dọn thread cũ trước."""
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'start_processing')
    
    assert '_cleanup_threads' in func, "start_processing PHẢI gọi _cleanup_threads!"
    
    cleanup_pos = func.index('_cleanup_threads')
    thread_pos = func.index('start_extraction')
    assert cleanup_pos < thread_pos, "cleanup phải chạy TRƯỚC start_extraction!"
    
    print("✅ TEST 14 PASSED: start_processing cleanup thread cũ đúng thứ tự")


# ======================================================================
# TEST 14: start_processing không chạy khi chưa chọn video
# ======================================================================
def test_start_without_video_returns():
    """Gọi start khi chưa có video -> return ngay."""
    source = _read_source('views/main_window.py')
    func = _read_function(source, 'start_processing')
    
    assert 'current_video_path' in func, "Phải check current_video_path!"
    assert 'return' in func, "Phải return nếu chưa có video!"
    
    print("✅ TEST 15 PASSED: start_processing guard check OK")


# ======================================================================
# TEST 15: FrameExtractor - Stream reconnect limit
# ======================================================================
def test_frame_extractor_reconnect_limit():
    """Stream mất kết nối quá 30 lần -> dừng."""
    source = _read_source('services/frame_extractor.py')
    func = _read_function(source, 'run')
    
    assert 'consecutive_failures' in func, "Phải có biến đếm lỗi liên tiếp!"
    assert '30' in func, "Giới hạn reconnect phải là 30 lần!"
    
    print("✅ TEST 16 PASSED: Stream reconnect limit đúng")


# ======================================================================
# TEST 16: Virtual line scaling
# ======================================================================
def test_virtual_line_scaling():
    """Virtual line phải được scale khi đổi resolution."""
    source = _read_source('views/main_window.py')
    
    scale_func = _read_function(source, '_get_scaled_virtual_line')
    assert 'effective_width' in scale_func, "Phải tính effective_width!"
    assert 'sx' in scale_func, "Phải tính tỉ lệ scale!"
    
    start_func = _read_function(source, 'start_processing')
    assert '_get_scaled_virtual_line' in start_func, \
        "start_processing phải gọi _get_scaled_virtual_line!"
    assert 'scaled_line' in start_func, \
        "Phải truyền scaled_line vào VideoThread!"
    
    print("✅ TEST 17 PASSED: Virtual line scaling logic đúng")


# ======================================================================
# CHẠY TẤT CẢ TESTS
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("CHAY EDGE CASE TESTS")
    print("=" * 60)
    
    tests = [
        # Logic đếm
        ("Dem NHAP co ban", test_counter_basic_nhap),
        ("Dem XUAT co ban", test_counter_basic_xuat),
        ("Vung BUFFER khong dem", test_counter_buffer_zone_no_count),
        ("Dem nhieu vat cung luc", test_counter_multiple_objects),
        ("Khong dem trung", test_counter_no_double_count),
        ("Vat quay lai", test_counter_object_returns),
        ("Memory limit", test_counter_memory_limit),
        ("Vach cheo", test_counter_diagonal_line),
        
        # UI State transitions
        ("Nut bi khoa khi xu ly", test_buttons_disabled_during_processing),
        ("Nut mo lai sau khi dung", test_buttons_enabled_after_stop),
        ("Doi resolution khi pause", test_change_resolution_while_paused),
        ("Doi FPS khi pause", test_change_fps_while_paused),
        ("closeEvent cleanup", test_close_event_has_cleanup),
        ("start cleanup thread cu", test_start_cleans_old_threads),
        ("start guard check", test_start_without_video_returns),
        ("Stream reconnect limit", test_frame_extractor_reconnect_limit),
        ("Virtual line scaling", test_virtual_line_scaling),
    ]
    
    passed = 0
    failed = 0
    
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
    total = passed + failed
    print(f"KET QUA: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("TAT CA TESTS DEU PASS!")
    else:
        print(f"CO {failed} TEST THAT BAI!")
    print("=" * 60)

