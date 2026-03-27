"""Helpers for mapping and drawing the virtual counting line."""

import cv2
import numpy as np

import configs.settings_interface as ui_settings
import configs.settings_theme as theme_settings


def _distance_squared(point_a, point_b):
    return (point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2


def _overlay_scale(image):
    height, width = image.shape[:2]
    target_w = getattr(ui_settings, "UI_TARGET_WIDTH", 800)
    target_h = getattr(ui_settings, "UI_TARGET_HEIGHT", 600)
    ui_scale = min(target_w / width, target_h / height) if width > 0 and height > 0 else 1.0
    return (1.0 / ui_scale) if ui_scale > 0 else 1.0


def extend_line(p1, p2, width, height):
    """Extend a segment until it touches the image borders."""
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and y1 == y2:
        return None
    if x1 == x2:
        return (x1, 0), (x1, height)
    if y1 == y2:
        return (0, y1), (width, y1)

    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - slope * x1
    intersections = []

    y_at_left = int(intercept)
    if 0 <= y_at_left <= height:
        intersections.append((0, y_at_left))

    y_at_right = int(slope * width + intercept)
    if 0 <= y_at_right <= height:
        intersections.append((width, y_at_right))

    x_at_top = int(-intercept / slope)
    if 0 <= x_at_top <= width:
        intersections.append((x_at_top, 0))

    x_at_bottom = int((height - intercept) / slope)
    if 0 <= x_at_bottom <= width:
        intersections.append((x_at_bottom, height))

    unique_points = list(set(intersections))
    if len(unique_points) < 2:
        return None
    start = min(unique_points, key=lambda point: _distance_squared(point, p1))
    end = min(unique_points, key=lambda point: _distance_squared(point, p2))
    return start, end


def calculate_virtual_line(p1_ui, p2_ui, label_size, image_size):
    """Map two UI points back to image coordinates and extend the line."""
    label_w, label_h = label_size
    image_w, image_h = image_size
    scale = min(label_w / image_w, label_h / image_h)
    offset_x = (label_w - image_w * scale) / 2
    offset_y = (label_h - image_h * scale) / 2

    try:
        p1_img = (int((p1_ui[0] - offset_x) / scale), int((p1_ui[1] - offset_y) / scale))
        p2_img = (int((p2_ui[0] - offset_x) / scale), int((p2_ui[1] - offset_y) / scale))
    except ZeroDivisionError:
        return None

    return extend_line(p1_img, p2_img, image_w, image_h)


def draw_line_with_arrows(image, line):
    """Draw the virtual line and directional arrows for enter/exit sides."""
    if image is None or not line:
        return

    p1, p2 = line
    scale_factor = _overlay_scale(image)
    line_thickness = max(1, int(round(ui_settings.LINE_THICKNESS * scale_factor)))
    cv2.line(image, p1, p2, theme_settings.VIRTUAL_LINE_COLOR, line_thickness)

    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = float(np.hypot(dx, dy))
    if length < 1:
        return

    normal_x = -dy / length
    normal_y = dx / length
    arrow_len = max(15, int(round(getattr(ui_settings, "UI_BASE_ARROW_LEN", 50) * scale_factor)))
    arrow_thickness = max(1, int(round(2 * scale_factor)))
    label_offset = arrow_len + int(round(30 * scale_factor))
    text_offset_x = int(round(20 * scale_factor))
    text_offset_y = int(round(5 * scale_factor))
    text_scale = getattr(ui_settings, "UI_BASE_FONT_SCALE", 0.7) * scale_factor
    text_thickness = max(1, int(round(2 * scale_factor)))

    mid_x = (p1[0] + p2[0]) / 2
    mid_y = (p1[1] + p2[1]) / 2

    enter_color = theme_settings.LINE_ENTER_COLOR
    enter_end = (int(mid_x + normal_x * arrow_len), int(mid_y + normal_y * arrow_len))
    cv2.arrowedLine(
        image,
        (int(mid_x), int(mid_y)),
        enter_end,
        enter_color,
        arrow_thickness,
        tipLength=0.3,
    )
    cv2.putText(
        image,
        "NHAP",
        (
            int(mid_x + normal_x * label_offset) - text_offset_x,
            int(mid_y + normal_y * label_offset) + text_offset_y,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        text_scale,
        enter_color,
        text_thickness,
    )

    exit_color = theme_settings.LINE_EXIT_COLOR
    exit_end = (int(mid_x - normal_x * arrow_len), int(mid_y - normal_y * arrow_len))
    cv2.arrowedLine(
        image,
        (int(mid_x), int(mid_y)),
        exit_end,
        exit_color,
        arrow_thickness,
        tipLength=0.3,
    )
    cv2.putText(
        image,
        "XUAT",
        (
            int(mid_x - normal_x * label_offset) - text_offset_x,
            int(mid_y - normal_y * label_offset) + text_offset_y,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        text_scale,
        exit_color,
        text_thickness,
    )
