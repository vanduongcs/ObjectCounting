"""
Utils: Xử lý vẽ vạch ảo và overlay vùng Nhập/Xuất.
"""

import cv2
import numpy as np


def extend_line(p1, p2, width, height):
    """
    Kéo dài đoạn thẳng p1-p2 ra 2 mép ảnh.
    Giữ nguyên hướng vẽ ban đầu (vector p1->p2).
    """
    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2 and y1 == y2:
        return None

    # Trường hợp đặc biệt: đường thẳng đứng hoặc ngang
    if x1 == x2:
        return ((x1, 0), (x1, height))
    if y1 == y2:
        return ((0, y1), (width, y1))

    # Tính phương trình đường thẳng y = mx + c
    m = (y2 - y1) / (x2 - x1)
    c = y1 - m * x1

    # Tìm giao điểm với 4 cạnh ảnh
    points = []
    
    # Giao với cạnh trái (x=0) và phải (x=width)
    y_left = int(c)
    if 0 <= y_left <= height: points.append((0, y_left))
    
    y_right = int(m * width + c)
    if 0 <= y_right <= height: points.append((width, y_right))

    if m != 0:
        # Giao với cạnh trên (y=0) và dưới (y=height)
        x_top = int(-c / m)
        if 0 <= x_top <= width: points.append((x_top, 0))
        
        x_bot = int((height - c) / m)
        if 0 <= x_bot <= width: points.append((x_bot, height))

    def distance_squared(pt1, pt2):
        return (pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2

    unique_points = list(set(points))
    if len(unique_points) >= 2:
        # Chọn điểm gần p1 nhất làm đầu, gần p2 nhất làm cuối để giữ hướng vector
        start = min(unique_points, key=lambda p: distance_squared(p, p1))
        end = min(unique_points, key=lambda p: distance_squared(p, p2))
        return (start, end)

    return None


def calculate_virtual_line(p1_ui, p2_ui, label_size, image_size):
    """
    Chuyển đổi tọa độ từ UI (VideoLabel) sang tọa độ ảnh gốc.
    Do ảnh hiển thị trên UI bị scale khác với ảnh gốc.
    """
    w_lbl, h_lbl = label_size
    w_img, h_img = image_size

    # Tính tỷ lệ scale và padding
    scale = min(w_lbl / w_img, h_lbl / h_img)
    dx = (w_lbl - w_img * scale) / 2
    dy = (h_lbl - h_img * scale) / 2

    # Map ngược từ UI về ảnh gốc
    try:
        p1_img = (int((p1_ui[0] - dx) / scale), int((p1_ui[1] - dy) / scale))
        p2_img = (int((p2_ui[0] - dx) / scale), int((p2_ui[1] - dy) / scale))
    except ZeroDivisionError:
        return None

    return extend_line(p1_img, p2_img, w_img, h_img)


def draw_region_overlay(image, line, nhap_color=(255, 0, 0), xuat_color=(255, 0, 255), alpha=0.1):
    """
    Vẽ vùng Nhập (Xanh) và Xuất (Tím) bán trong suốt lên ảnh.
    Chia ảnh thành 2 đa giác dựa trên đường vạch ảo.
    
    Thuật toán: Đi theo chu vi hình chữ nhật theo chiều kim đồng hồ.
    Đường vạch chia chu vi thành 2 cung. Mỗi cung + đường vạch = 1 đa giác.
    """
    if image is None or not line:
        return

    h, w = image.shape[:2]
    p1, p2 = line

    # Hàm tính khoảng cách trên chu vi (clockwise từ góc trên-trái)
    # Chu vi: Top(0→w) → Right(w→w+h) → Bottom(w+h→2w+h) → Left(2w+h→2w+2h)
    def perimeter_dist(p):
        x, y = p
        if y <= 0: return x                  # Cạnh trên: 0 → w
        if x >= w: return w + y              # Cạnh phải: w → w+h
        if y >= h: return w + h + (w - x)    # Cạnh dưới: w+h → 2w+h
        return 2 * w + h + (h - y)           # Cạnh trái: 2w+h → 2w+2h

    # 4 góc ảnh với khoảng cách chu vi
    corners = [
        ((0, 0), 0),
        ((w, 0), w),
        ((w, h), w + h),
        ((0, h), 2 * w + h),
    ]

    d1 = perimeter_dist(p1)
    d2 = perimeter_dist(p2)

    # Đảm bảo dA < dB (pA đến trước pB trên chu vi)
    if d1 <= d2:
        pA, pB, dA, dB = p1, p2, d1, d2
    else:
        pA, pB, dA, dB = p2, p1, d2, d1

    # Chia corners thành 2 nhóm:
    # Nhóm 1 (cung ngắn A→B): góc có dA < dist < dB
    # Nhóm 2 (cung dài B→...→A): góc có dist > dB HOẶC dist < dA
    group1_corners = [pt for pt, cd in corners if dA < cd < dB]
    
    # Nhóm 2: phải giữ đúng thứ tự theo chiều clockwise (B→End rồi Start→A)
    g2_after_B = [pt for pt, cd in corners if cd > dB]    # Sau B
    g2_before_A = [pt for pt, cd in corners if cd < dA]   # Trước A
    group2_corners = g2_after_B + g2_before_A

    # Tạo 2 đa giác
    poly_nhap = [pA] + group1_corners + [pB]
    poly_xuat = [pB] + group2_corners + [pA]

    # Vẽ và tô màu bán trong suốt
    overlay = image.copy()
    cv2.fillPoly(overlay, [np.array(poly_nhap, np.int32).reshape((-1, 1, 2))], nhap_color)
    cv2.fillPoly(overlay, [np.array(poly_xuat, np.int32).reshape((-1, 1, 2))], xuat_color)
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)

    # Vẽ đường biên đỏ
    cv2.line(image, p1, p2, (0, 0, 255), 2)

