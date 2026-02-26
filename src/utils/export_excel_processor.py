"""
Export Excel Processor: Xử lý xuất dữ liệu ra file Excel/CSV.
"""

import csv
import datetime
import os


def export_to_csv(filepath, count_nhap, count_xuat):
    """
    Xuất dữ liệu đếm ra file CSV (Excel mở được).
    
    Args:
        filepath: Đường dẫn lưu file.
        count_nhap: Dict {label: count} cho cột NHAP.
        count_xuat: Dict {label: count} cho cột XUAT.
    """
    # Gộp tất cả label
    all_labels = set(count_nhap.keys()) | set(count_xuat.keys())
    sorted_labels = sorted(all_labels)

    try:
        with open(filepath, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            
            # Header
            writer.writerow(["Loại hàng", "Số lượng Nhập", "Số lượng Xuất", "Thời gian xuất"])
            
            # Data rows
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for label in sorted_labels:
                nhap = count_nhap.get(label, 0)
                xuat = count_xuat.get(label, 0)
                writer.writerow([label, nhap, xuat, now_str])
                
        return True, "Xuất file thành công!"
    except Exception as e:
        return False, f"Lỗi xuất file: {str(e)}"
