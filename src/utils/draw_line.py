"""
Utils: Vẽ vạch ảo + mũi tên NHẬP/XUẤT lên ảnh.

Gồm 3 chức năng:
    1. extend_line            -- Kéo dài đoạn thẳng ra 2 mép ảnh
    2. calculate_virtual_line -- Chuyển tọa độ UI -> ảnh gốc -> extend
    3. draw_line_with_arrows  -- Vẽ vạch ảo + 2 mũi tên vuông góc NHẬP/XUẤT
"""

import cv2
import numpy as np

import configs.settings as settings


def _distance_squared(point_a, point_b):
    """Bình phương khoảng cách giữa 2 điểm (dùng để so sánh, không cần sqrt)."""
    return (point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2


def extend_line(p1, p2, width, height):
    """
    Kéo dài đoạn thẳng p1->p2 ra 2 mép ảnh (giữ nguyên hướng vector).

    Minh họa:
        +------------------+
        |        /         |
        |  p1  /           |   -> Kéo dài thành đường nối 2 mép ảnh
        |    /  p2         |
        |  /               |
        +------------------+

    Cách hoạt động:
        1. Tính phương trình đường thẳng: y = slope * x + y_intercept
        2. Tìm giao điểm với 4 cạnh ảnh (trái, phải, trên, dưới)
        3. Chọn 2 giao điểm gần p1 và p2 nhất

    Returns:
        (start, end) hoặc None nếu 2 điểm trùng nhau.
    """
    x1, y1 = p1
    x2, y2 = p2

    # Hai điểm trùng nhau -> không thể tạo đường thẳng
    if x1 == x2 and y1 == y2:
        return None

    # Trường hợp đặc biệt: đường thẳng dọc hoặc ngang
    if x1 == x2:
        return ((x1, 0), (x1, height))
    if y1 == y2:
        return ((0, y1), (width, y1))

    # Phương trình đường thẳng: y = slope * x + y_intercept
    slope = (y2 - y1) / (x2 - x1)
    y_intercept = y1 - slope * x1

    # Tìm giao điểm với 4 cạnh ảnh
    intersections = []

    # Giao với cạnh trái (x = 0)
    y_at_left = int(y_intercept)
    if 0 <= y_at_left <= height:
        intersections.append((0, y_at_left))

    # Giao với cạnh phải (x = width)
    y_at_right = int(slope * width + y_intercept)
    if 0 <= y_at_right <= height:
        intersections.append((width, y_at_right))

    # Giao với cạnh trên (y = 0) và cạnh dưới (y = height)
    if slope != 0:
        x_at_top = int(-y_intercept / slope)
        if 0 <= x_at_top <= width:
            intersections.append((x_at_top, 0))

        x_at_bottom = int((height - y_intercept) / slope)
        if 0 <= x_at_bottom <= width:
            intersections.append((x_at_bottom, height))

    # Loại bỏ điểm trùng, chọn 2 điểm gần p1 và p2 nhất
    unique_points = list(set(intersections))
    if len(unique_points) >= 2:
        start = min(unique_points, key=lambda p: _distance_squared(p, p1))
        end = min(unique_points, key=lambda p: _distance_squared(p, p2))
        return (start, end)

    return None


def calculate_virtual_line(p1_ui, p2_ui, label_size, image_size):
    """
    Chuyển tọa độ từ UI (VideoLabel) sang ảnh gốc, rồi extend ra mép.

    Vì ảnh được scale để vừa VideoLabel (giữ tỷ lệ), tọa độ chuột trên UI
    khác với tọa độ thực trên ảnh. Function này chuyển đổi ngược lại.

    Args:
        p1_ui, p2_ui: Tọa độ 2 đầu vạch trên VideoLabel (pixel).
        label_size: Kích thước VideoLabel (width, height).
        image_size: Kích thước ảnh gốc (width, height).
    """
    label_w, label_h = label_size
    img_w, img_h = image_size

    # Tính tỷ lệ scale và offset (khoảng trống do giữ tỷ lệ)
    scale = min(label_w / img_w, label_h / img_h)
    offset_x = (label_w - img_w * scale) / 2
    offset_y = (label_h - img_h * scale) / 2

    # Chuyển tọa độ UI -> tọa độ ảnh gốc
    try:
        p1_img = (int((p1_ui[0] - offset_x) / scale), int((p1_ui[1] - offset_y) / scale))
        p2_img = (int((p2_ui[0] - offset_x) / scale), int((p2_ui[1] - offset_y) / scale))
    except ZeroDivisionError:
        return None

    return extend_line(p1_img, p2_img, img_w, img_h)


def draw_line_with_arrows(image, line):
    """
    Vẽ vạch ảo + 2 mũi tên vuông góc chỉ hướng NHẬP/XUẤT.

    Mũi tên NHẬP (xanh lá) chỉ về vùng cross > 0.
    Mũi tên XUẤT (hồng)    chỉ về vùng cross < 0.

    Minh họa:
                 ← NHẬP
           ─────────────── (vạch đỏ)
                 → XUẤT
    """
    if image is None or not line:
        return

    p1, p2 = line
    h, w = image.shape[:2]

    # --- Vẽ vạch ảo chính ---
    cv2.line(image, p1, p2, settings.LINE_COLOR, settings.LINE_THICKNESS)

    # --- Tính vector vuông góc ---
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = (dx ** 2 + dy ** 2) ** 0.5
    if length < 1:
        return

    # Vector đơn vị vuông góc
    # cross product: dx*(cy-p1y) - dy*(cx-p1x)
    # Hướng cross > 0 (NHẬP): (-dy, dx) đã chuẩn hóa
    # Hướng cross < 0 (XUẤT): (dy, -dx) đã chuẩn hóa
    nx = -dy / length  # Hướng NHẬP
    ny = dx / length
    
    # Chiều dài mũi tên (tỷ lệ với kích thước ảnh, tối thiểu 30, tối đa 80 px)
    arrow_len = max(30, min(80, int(min(w, h) * 0.06)))

    # Điểm giữa vạch
    mid_x = (p1[0] + p2[0]) / 2
    mid_y = (p1[1] + p2[1]) / 2

    # --- Mũi tên NHẬP (xanh lá) ---
    nhap_end = (int(mid_x + nx * arrow_len), int(mid_y + ny * arrow_len))
    nhap_start = (int(mid_x), int(mid_y))
    nhap_color = (0, 200, 0)  # Xanh lá

    cv2.arrowedLine(image, nhap_start, nhap_end, nhap_color, 2, tipLength=0.3)

    # Label NHẬP
    label_nhap_x = int(mid_x + nx * (arrow_len + 15))
    label_nhap_y = int(mid_y + ny * (arrow_len + 15))
    cv2.putText(image, "NHAP", (label_nhap_x - 20, label_nhap_y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, nhap_color, 2)

    # --- Mũi tên XUẤT (hồng) ---
    xuat_end = (int(mid_x - nx * arrow_len), int(mid_y - ny * arrow_len))
    xuat_start = (int(mid_x), int(mid_y))
    xuat_color = (200, 0, 200)  # Hồng

    cv2.arrowedLine(image, xuat_start, xuat_end, xuat_color, 2, tipLength=0.3)

    # Label XUẤT
    label_xuat_x = int(mid_x - nx * (arrow_len + 15))
    label_xuat_y = int(mid_y - ny * (arrow_len + 15))
    cv2.putText(image, "XUAT", (label_xuat_x - 20, label_xuat_y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, xuat_color, 2)

