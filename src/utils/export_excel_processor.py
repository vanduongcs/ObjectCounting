"""
Export Excel: Xuất dữ liệu đếm nhập/xuất ra file Excel nhiều sheet.

Ai gọi module này?
    - MainWindow.export_data() (views/main_window.py) khi user bấm "Xuất Excel".

Dữ liệu đến từ đâu?
    - MainWindow.latest_counts_nhap / latest_counts_xuat — tổng đếm
    - AIService.last_event_log — danh sách sự kiện chi tiết

Cấu trúc file Excel:
    Sheet "Tổng hợp": Tên hàng hóa | Số lượng
    Sheet "<tên hàng>": Hành động | Thời gian  (mỗi loại hàng 1 sheet)
"""

import os
import re

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side

try:
    import cv2
except Exception:
    cv2 = None

try:
    import pytesseract
except Exception:
    pytesseract = None

import configs.settings as settings

_TESS_READY = None


def _ensure_tesseract():
    global _TESS_READY
    if _TESS_READY is not None:
        return _TESS_READY
    if pytesseract is None or cv2 is None:
        _TESS_READY = False
        return False
    tcmd = getattr(settings, "TESSERACT_CMD", "") or ""
    if tcmd and os.path.exists(tcmd):
        try:
            pytesseract.pytesseract.tesseract_cmd = tcmd
            _TESS_READY = True
            return True
        except Exception:
            _TESS_READY = False
            return False
    default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_path):
        try:
            pytesseract.pytesseract.tesseract_cmd = default_path
        except Exception:
            pass
    _TESS_READY = True
    return True


def _ocr_timestamp_from_image(image_path):
    if not settings.TIMESTAMP_OCR_ENABLED:
        return ""
    if not _ensure_tesseract():
        return ""
    if not os.path.exists(image_path):
        return ""
    img = cv2.imread(image_path)
    if img is None:
        return ""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_LINEAR)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, th2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    config = f"--psm 7 -c tessedit_char_whitelist={settings.TIMESTAMP_OCR_WHITELIST}"

    def _run_ocr(img_in):
        txt = pytesseract.image_to_string(img_in, lang=settings.TIMESTAMP_OCR_LANG, config=config)
        txt = re.sub(r"[^0-9:/\\- ]+", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    texts = [_run_ocr(th1), _run_ocr(th2)]
    pattern = settings.TIMESTAMP_OCR_REGEX
    for t in texts:
        m = re.search(pattern, t)
        if m:
            date_m = re.search(r"\d{2}[-/]\d{2}[-/]\d{4}", m.group(0))
            time_m = re.search(r"\d{2}:\d{2}:\d{2}", m.group(0))
            if date_m and time_m:
                return f"{date_m.group(0)} {time_m.group(0)}"
            return m.group(0)

    for t in texts:
        date_m = re.search(r"\d{2}[-/]\d{2}[-/]\d{4}", t)
        time_m = re.search(r"\d{2}:\d{2}:\d{2}", t)
        if date_m and time_m:
            return f"{date_m.group(0)} {time_m.group(0)}"
    return ""


def export_to_excel(filepath, count_nhap, count_xuat, event_log=None):
    """
    Xuất dữ liệu đếm ra file Excel nhiều sheet.

    Args:
        filepath: Đường dẫn file .xlsx (do user chọn qua dialog).
        count_nhap: dict {tên_loại: số_lượng_nhập}
        count_xuat: dict {tên_loại: số_lượng_xuất}
        event_log: list[dict] — [{label, action, timestamp}, ...]

    Returns:
        (success: bool, message: str)
    """
    if event_log is None:
        event_log = []

    all_labels = sorted(set(count_nhap.keys()) | set(count_xuat.keys()))

    # Preprocess event_log: OCR timestamp images if needed
    processed_events = []
    ocr_cache = {}
    for evt in event_log:
        ts = evt.get("timestamp", "")
        if isinstance(ts, str) and os.path.exists(ts):
            if ts not in ocr_cache:
                text = _ocr_timestamp_from_image(ts)
                ocr_cache[ts] = text if text else ts
            ts_out = ocr_cache[ts]
        else:
            ts_out = ts
        processed_events.append({
            "label": evt.get("label"),
            "action": evt.get("action"),
            "timestamp": ts_out,
        })

    try:
        wb = Workbook()

        # ===== Sheet 1: Tổng hợp =====
        ws_summary = wb.active
        ws_summary.title = "Tổng hợp"

        # Header
        header_font = Font(bold=True, size=11)
        thin_border = Border(
            bottom=Side(style="thin", color="999999"),
        )

        ws_summary.append(["Tên hàng hóa", "Số lượng nhập", "Số lượng xuất"])
        for cell in ws_summary[1]:
            cell.font = header_font
            cell.border = thin_border

        # Data
        for label in all_labels:
            ws_summary.append([
                label,
                count_nhap.get(label, 0),
                count_xuat.get(label, 0),
            ])

        # Auto-width
        ws_summary.column_dimensions["A"].width = 20
        ws_summary.column_dimensions["B"].width = 15
        ws_summary.column_dimensions["C"].width = 15

        # ===== Sheet per-product: chi tiết sự kiện =====
        for label in all_labels:
            # Tên sheet giới hạn 31 ký tự (Excel limit)
            sheet_name = label[:31]
            ws = wb.create_sheet(title=sheet_name)

            ws.append(["Hành động", "Thời gian"])
            for cell in ws[1]:
                cell.font = header_font
                cell.border = thin_border

            # Filter events cho label này
            for evt in processed_events:
                if evt["label"] == label:
                    ws.append([evt["action"], evt["timestamp"]])

            ws.column_dimensions["A"].width = 12
            ws.column_dimensions["B"].width = 12

        wb.save(filepath)
        return True, "Xuất file thành công!"

    except Exception as e:
        return False, f"Lỗi xuất file: {str(e)}"
