"""
Counter Service: Đếm đối tượng nhập/xuất qua vạch ảo.

Nguyên lý hoạt động:
    Dùng Cross Product để xác định vật ở bên nào vạch.
    Khi vật đổi vùng (NHAP -> XUAT hoặc ngược lại) -> tăng biến đếm.

Chống đếm nhấp nháy (flicker):
    1. Debounce -- vật phải ở vùng mới ≥ 2 frames liên tiếp
    2. Cooldown sau đếm -- sau khi đếm, khóa object N frames

Minh họa:
                    Vạch ảo (p1 -> p2)
                        |
        Vùng NHẬP       |       Vùng XUẤT
       (cross > 0)      |      (cross < 0)
                        |
"""

from datetime import datetime

import configs.settings as settings

# Giới hạn event log — video dài có thể tạo hàng nghìn events
MAX_EVENT_LOG_SIZE = 10000


class CounterService:
    def __init__(self, line_p1, line_p2, fps=30, is_live=False):
        """
        Args:
            line_p1, line_p2: Tọa độ 2 đầu vạch ảo (tuple x, y).
            fps: FPS thực tế (dùng tính video time).
            is_live: True = camera live (dùng system clock), False = video file.
        """
        self.line_p1 = line_p1
        self.line_p2 = line_p2

        # Timing
        self._fps = fps if fps > 0 else 30
        self._is_live = is_live
        self._current_frame_index = 0

        # Vector hướng của vạch ảo (dùng cho cross product)
        self.dx = line_p2[0] - line_p1[0]
        self.dy = line_p2[1] - line_p1[1]

        # Trạng thái vùng ĐÃ XÁC NHẬN: {track_id: "NHAP" | "XUAT"}
        self.object_states = {}

        # Debounce: {track_id: {"region": str, "count": int}}
        self._pending_region = {}

        # Cooldown: {track_id: remaining_frames}
        self._cooldowns = {}

        # Frame counter nội bộ
        self._frame_count = 0

        # Bộ đếm: {label_id: số_lượng}
        self.count_nhap = {}
        self.count_xuat = {}

        # Event log
        self._event_log = []

        # LRU tracking
        self._last_seen_frame = {}

    def _apply_count_action(self, label, action):
        """Apply net unmatched counts: opposite direction cancels first."""
        if action == "Nhập":
            if self.count_xuat.get(label, 0) > 0:
                self.count_xuat[label] -= 1
                if self.count_xuat[label] <= 0:
                    self.count_xuat.pop(label, None)
            else:
                self.count_nhap[label] = self.count_nhap.get(label, 0) + 1
            return

        if action == "Xuất":
            if self.count_nhap.get(label, 0) > 0:
                self.count_nhap[label] -= 1
                if self.count_nhap[label] <= 0:
                    self.count_nhap.pop(label, None)
            else:
                self.count_xuat[label] = self.count_xuat.get(label, 0) + 1

    def _get_side(self, cx, cy):
        """
        Xác định vật ở bên nào vạch dựa trên cross product.

        Returns: "NHAP" hoặc "XUAT" (không có BUFFER).
        """
        cross = self.dx * (cy - self.line_p1[1]) - self.dy * (cx - self.line_p1[0])
        return "NHAP" if cross > 0 else "XUAT"

    def _prune_old_tracks(self):
        """Xóa 20% track ít gặp nhất khi vượt giới hạn."""
        if len(self.object_states) > settings.MAX_TRACKED_OBJECTS:
            sorted_by_lru = sorted(
                self.object_states.keys(),
                key=lambda k: self._last_seen_frame.get(k, 0)
            )
            keys_to_remove = sorted_by_lru[:settings.MAX_TRACKED_OBJECTS // 5]
            for key in keys_to_remove:
                del self.object_states[key]
                self._pending_region.pop(key, None)
                self._cooldowns.pop(key, None)
                self._last_seen_frame.pop(key, None)

    def update(self, detections):
        """
        Cập nhật trạng thái và đếm cho frame hiện tại.

        Logic đơn giản:
            1. Vật mới → gán vùng ngay lập tức (NHAP hoặc XUAT)
            2. Vật đổi vùng → debounce 2 frame → đếm
            3. Cooldown sau đếm → tránh đếm trùng
        """
        self._frame_count += 1
        self._tick_cooldowns()
        event_items = []

        for obj in detections:
            obj_id = obj["id"]
            label = obj["label"]

            # Bỏ qua class không nằm trong whitelist
            if settings.COUNTING_CLASSES is not None and label not in settings.COUNTING_CLASSES:
                continue

            cx, cy = obj["center"]

            # Cập nhật LRU
            self._last_seen_frame[obj_id] = self._frame_count

            current_side = self._get_side(cx, cy)

            # --- Vật mới → gán vùng ngay lập tức ---
            if obj_id not in self.object_states:
                self._prune_old_tracks()
                self.object_states[obj_id] = current_side
                continue

            confirmed_side = self.object_states[obj_id]

            # --- Cùng vùng → reset pending ---
            if current_side == confirmed_side:
                self._pending_region.pop(obj_id, None)
                continue

            # --- Khác vùng → debounce ---
            pending = self._pending_region.get(obj_id)
            if pending and pending["region"] == current_side:
                pending["count"] += 1
            else:
                self._pending_region[obj_id] = {"region": current_side, "count": 1}
                pending = self._pending_region[obj_id]

            # Cần ≥ 2 frame liên tiếp ở vùng mới
            if pending["count"] < 2:
                continue

            # --- Xác nhận đổi vùng ---
            self._pending_region.pop(obj_id, None)

            # Đang cooldown → bỏ qua
            if obj_id in self._cooldowns:
                continue

            # Đếm
            action = None
            if confirmed_side == "NHAP" and current_side == "XUAT":
                action = "Xuất"
            elif confirmed_side == "XUAT" and current_side == "NHAP":
                action = "Nhập"

            if action:
                self._apply_count_action(label, action)
                ts = self._get_timestamp()
                evt = {
                    "label": label,
                    "action": action,
                    "timestamp": ts,
                }
                self._event_log.append(evt)
                event_items.append(evt)
                if len(self._event_log) > MAX_EVENT_LOG_SIZE:
                    self._event_log = self._event_log[-MAX_EVENT_LOG_SIZE:]

            self.object_states[obj_id] = current_side
            self._cooldowns[obj_id] = settings.COUNTER_COOLDOWN_FRAMES

        return event_items

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
