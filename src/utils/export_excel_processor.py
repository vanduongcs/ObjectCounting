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

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side


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
            for evt in event_log:
                if evt["label"] == label:
                    ws.append([evt["action"], evt["timestamp"]])

            ws.column_dimensions["A"].width = 12
            ws.column_dimensions["B"].width = 12

        wb.save(filepath)
        return True, "Xuất file thành công!"

    except Exception as e:
        return False, f"Lỗi xuất file: {str(e)}"
