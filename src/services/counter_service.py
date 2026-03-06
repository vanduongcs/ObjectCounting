"""
Counter Service: Đếm đối tượng nhập/xuất qua vạch ảo.

Nguyên lý hoạt động:
    Dùng Cross Product để xác định vật ở bên nào vạch.
    Khi vật đổi vùng (NHAP -> XUAT hoặc ngược lại) -> tăng biến đếm.

Chống đếm nhấp nháy (flicker):
    1. Vùng BUFFER quanh vạch -- bỏ qua khi vật đứng quá gần
    2. Xác nhận vùng (debounce) -- vật phải ở vùng mới ≥ N frames liên tiếp
    3. Cooldown sau đếm -- sau khi đếm, khóa object N frames

Minh họa:
                    Vạch ảo (p1 -> p2)
                        |
        Vùng NHẬP       |       Vùng XUẤT
       (cross > 0)      |      (cross < 0)
                        |
                <- buffer ->
"""

from datetime import datetime

import configs.settings as settings


class CounterService:
    def __init__(self, line_p1, line_p2, buffer=None, fps=30, is_live=False):
        """
        Args:
            line_p1, line_p2: Tọa độ 2 đầu vạch ảo (tuple x, y).
            buffer: Vùng đệm quanh vạch (pixel). None = dùng settings.COUNTER_BUFFER_PIXELS.
            fps: FPS thực tế (dùng tính video time).
            is_live: True = camera live (dùng system clock), False = video file.
        """
        self.line_p1 = line_p1
        self.line_p2 = line_p2
        self.buffer = buffer if buffer is not None else settings.COUNTER_BUFFER_PIXELS

        # Timing
        self._fps = fps if fps > 0 else 30
        self._is_live = is_live
        self._current_frame_index = 0

        # Vector hướng của vạch ảo (dùng cho cross product)
        self.dx = line_p2[0] - line_p1[0]
        self.dy = line_p2[1] - line_p1[1]
        self.line_length = (self.dx ** 2 + self.dy ** 2) ** 0.5

        # Trạng thái vùng ĐÃ XÁC NHẬN của mỗi vật: {track_id: "NHAP" | "XUAT" | None}
        self.object_states = {}

        # Debounce: {track_id: {"region": str, "count": int}}
        # Đếm số frame liên tiếp vật ở vùng mới (chưa xác nhận)
        self._pending_region = {}

        # Cooldown: {track_id: remaining_frames}
        # Sau khi đếm, khóa object không cho đếm lại trong N frames
        self._cooldowns = {}

        # Frame counter nội bộ
        self._frame_count = 0

        # Bộ đếm: {label_id: số_lượng}
        self.count_nhap = {}
        self.count_xuat = {}

        # Event log: mỗi sự kiện nhập/xuất được ghi lại
        self._event_log = []

    def _get_region(self, cx, cy):
        """
        Xác định vật ở vùng nào dựa trên cross product.

        Cross product của vector vạch (dx, dy) với vector (cx - p1.x, cy - p1.y):
            cross = dx * (cy - p1.y) - dy * (cx - p1.x)

        - cross > 0  -> bên trái vạch  -> NHẬP
        - cross < 0  -> bên phải vạch  -> XUẤT
        - |cross| / line_length < buffer -> quá gần vạch -> BUFFER (bỏ qua)
        """
        cross = self.dx * (cy - self.line_p1[1]) - self.dy * (cx - self.line_p1[0])

        # Khoảng cách từ điểm đến vạch = |cross| / chiều dài vạch
        distance = abs(cross) / self.line_length if self.line_length > 0 else 0

        if distance < self.buffer:
            return "BUFFER"
        if cross > 0:
            return "NHAP"
        return "XUAT"

    def _prune_old_tracks(self):
        """Xóa 20% track cũ nhất khi vượt giới hạn (Python dict giữ insertion order)."""
        if len(self.object_states) > settings.MAX_TRACKED_OBJECTS:
            keys_to_remove = list(self.object_states.keys())[:settings.MAX_TRACKED_OBJECTS // 5]
            for key in keys_to_remove:
                del self.object_states[key]

    def update(self, detections):
        """
        Cập nhật trạng thái và đếm cho frame hiện tại.

        Args:
            detections: list[dict] với keys: id, label, center (cx, cy).
        """
        self._frame_count += 1
        self._tick_cooldowns()

        for obj in detections:
            obj_id = obj["id"]
            label = obj["label"]

            # Bỏ qua class không nằm trong whitelist
            if settings.COUNTING_CLASSES is not None and label not in settings.COUNTING_CLASSES:
                continue

            cx, cy = obj["center"]
            current_region = self._get_region(cx, cy)

            # --- Vật thể mới xuất hiện ---
            if obj_id not in self.object_states:
                self._prune_old_tracks()
                if current_region == "BUFFER":
                    self.object_states[obj_id] = None
                else:
                    self.object_states[obj_id] = current_region
                continue

            confirmed_region = self.object_states[obj_id]

            # --- Đang ở buffer → reset pending, chờ ra ngoài ---
            if current_region == "BUFFER":
                self._pending_region.pop(obj_id, None)
                continue

            # --- Chưa xác định vùng ban đầu → ghi nhận lần đầu ---
            if confirmed_region is None:
                self.object_states[obj_id] = current_region
                continue

            # --- Cùng vùng đã xác nhận → reset pending ---
            if current_region == confirmed_region:
                self._pending_region.pop(obj_id, None)
                continue

            # --- Khác vùng → bắt đầu / tiếp tục debounce ---
            pending = self._pending_region.get(obj_id)
            if pending and pending["region"] == current_region:
                pending["count"] += 1
            else:
                # Vùng mới khác pending trước đó → reset
                self._pending_region[obj_id] = {"region": current_region, "count": 1}
                pending = self._pending_region[obj_id]

            # Chưa đủ frames xác nhận → chờ tiếp
            if pending["count"] < settings.COUNTER_CONFIRM_FRAMES:
                continue

            # --- Đã xác nhận đổi vùng → kiểm tra cooldown rồi đếm ---
            self._pending_region.pop(obj_id, None)

            # Nếu đang cooldown → chỉ cập nhật vùng, KHÔNG đếm
            if obj_id in self._cooldowns:
                self.object_states[obj_id] = current_region
                continue

            # Đếm (triệt tiêu: nhập hủy xuất và ngược lại)
            action = None
            if confirmed_region == "NHAP" and current_region == "XUAT":
                # Sự kiện Xuất: nếu có nhập trước đó → hủy 1 nhập, ngược lại → cộng xuất
                if self.count_nhap.get(label, 0) > 0:
                    self.count_nhap[label] -= 1
                else:
                    self.count_xuat[label] = self.count_xuat.get(label, 0) + 1
                action = "Xuất"
            elif confirmed_region == "XUAT" and current_region == "NHAP":
                # Sự kiện Nhập: nếu có xuất trước đó → hủy 1 xuất, ngược lại → cộng nhập
                if self.count_xuat.get(label, 0) > 0:
                    self.count_xuat[label] -= 1
                else:
                    self.count_nhap[label] = self.count_nhap.get(label, 0) + 1
                action = "Nhập"

            if action:
                self._event_log.append({
                    "label": label,
                    "action": action,
                    "timestamp": self._get_timestamp(),
                })

            self.object_states[obj_id] = current_region
            self._cooldowns[obj_id] = settings.COUNTER_COOLDOWN_FRAMES

    def _tick_cooldowns(self):
        """Giảm cooldown mỗi frame."""
        expired = [tid for tid, v in self._cooldowns.items() if v <= 1]
        for tid in expired:
            del self._cooldowns[tid]
        for tid in self._cooldowns:
            self._cooldowns[tid] -= 1

    def set_frame_index(self, idx):
        """Cập nhật frame index hiện tại (gọi bởi AIService mỗi frame)."""
        self._current_frame_index = idx

    def _get_timestamp(self):
        """Trả về timestamp dựa vào nguồn video."""
        if self._is_live:
            return datetime.now().strftime("%H:%M:%S")
        # Video file: tính từ frame index và FPS
        total_seconds = int(self._current_frame_index / self._fps)
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def get_counts(self):
        """Trả về (count_nhap, count_xuat) -- mỗi cái là dict {label: count}."""
        return self.count_nhap, self.count_xuat

    def get_event_log(self):
        """Trả về danh sách sự kiện [{label, action, timestamp}, ...]."""
        return self._event_log
