"""
Counter Service: Logic đếm đối tượng nhập/xuất.

Sử dụng tích vô hướng (Cross Product) để xác định vật thể nằm bên nào vạch kẻ.
- Đếm TÍCH LŨY: Cứ qua vạch là tăng 1.
- Có vùng đệm (buffer) để tránh đếm trùng khi vật thể dao động ngay trên vạch.
"""

# Số lượng track_id tối đa lưu trong bộ nhớ (tránh memory leak khi chạy stream dài)
MAX_TRACKED_OBJECTS = 10000


class CounterService:
    def __init__(self, line_p1, line_p2, buffer=15):
        """
        Khởi tạo bộ đếm.
        Args:
            line_p1, line_p2: Tọa độ vạch ảo.
            buffer: Vùng đệm quanh vạch (pixel). Mặc định 15px.
                    Giá trị nhỏ → nhạy hơn, giá trị lớn → tránh rung nhưng
                    dễ bỏ sót vật thể xuất hiện ngay trên vạch.
        """
        self.line_p1 = line_p1
        self.line_p2 = line_p2
        self.buffer = buffer

        # Vector hướng của vạch
        self.dx = line_p2[0] - line_p1[0]
        self.dy = line_p2[1] - line_p1[1]
        self.line_length = (self.dx**2 + self.dy**2) ** 0.5

        # Trạng thái vật thể: {track_id: "NHAP" | "XUAT" | None}
        # None = vật xuất hiện trong vùng buffer, chưa xác định được vùng ban đầu
        self.object_states = {}
        
        # Biến đếm: {label_id: so_luong}
        self.count_nhap = {}
        self.count_xuat = {}

    def _get_region(self, cx, cy):
        """
        Xác định vùng của vật thể dựa trên Cross Product.
        - > 0: Bên Trái -> NHAP
        - < 0: Bên Phải -> XUAT
        - Gần 0: BUFFER (vùng đệm quanh vạch, không đếm)
        """
        cross = self.dx * (cy - self.line_p1[1]) - self.dy * (cx - self.line_p1[0])

        if self.line_length > 0:
            distance = abs(cross) / self.line_length
        else:
            distance = 0

        if distance < self.buffer:
            return "BUFFER"

        return "NHAP" if cross > 0 else "XUAT"

    def update(self, detections):
        """
        Cập nhật trạng thái và đếm vật thể trong frame hiện tại.
        """
        for obj in detections:
            obj_id = obj["id"]
            label = obj["label"]
            cx, cy = obj["center"]

            current_region = self._get_region(cx, cy)

            if obj_id not in self.object_states:
                # Giới hạn bộ nhớ
                if len(self.object_states) > MAX_TRACKED_OBJECTS:
                    keys_to_remove = list(self.object_states.keys())[:MAX_TRACKED_OBJECTS // 5]
                    for k in keys_to_remove:
                        del self.object_states[k]

                if current_region == "BUFFER":
                    # Vật xuất hiện ngay trong vùng buffer → đánh dấu "chờ xác định"
                    self.object_states[obj_id] = None
                else:
                    # Vật xuất hiện rõ ràng 1 bên → ghi nhận vùng ban đầu
                    self.object_states[obj_id] = current_region
                continue

            previous_region = self.object_states[obj_id]

            if current_region == "BUFFER":
                # Vật đang ở vùng buffer → chờ, không đếm
                continue

            if previous_region is None:
                # Vật từng xuất hiện trong buffer, giờ đã ra bên nào → ghi nhận vùng ban đầu
                self.object_states[obj_id] = current_region
                continue

            previous_region = self.object_states[obj_id]

            # Nếu chuyển vùng -> Đã qua vạch -> Tăng biến đếm
            if previous_region != current_region:
                if previous_region == "NHAP" and current_region == "XUAT":
                    self.count_xuat[label] = self.count_xuat.get(label, 0) + 1
                elif previous_region == "XUAT" and current_region == "NHAP":
                    self.count_nhap[label] = self.count_nhap.get(label, 0) + 1
                
                # Cập nhật trạng thái mới
                self.object_states[obj_id] = current_region

    def get_counts(self):
        """Trả về kết quả đếm hiện tại."""
        return self.count_nhap, self.count_xuat


