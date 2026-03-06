"""Tạo file __init__.py cho tất cả thư mục chưa có."""

import os

for root, dirs, files in os.walk("."):
    if "__init__.py" not in files:
        init_path = os.path.join(root, "__init__.py")
        with open(init_path, "a") as f:
            pass
        print(f"Created: {init_path}")