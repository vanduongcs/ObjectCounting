"""
Tracklet Stitcher: Ghép nối quỹ đạo bị đứt do che khuất lâu.

Ai gọi module này?
    - AIService._process_frame() (services/ai_service.py) gọi stitcher.process()

Module này làm gì?
    Nằm GIỮA detector.track() và counter.update().
    Khi ByteTrack mất ID_A (vì bị che quá lâu) rồi gán ID_B mới,
    module này phát hiện và ép ID_B kế thừa ID_A, giữ chuỗi trạng thái liền mạch.

7 lớp bảo vệ chống ghép nhầm:
    1. Same-label: chỉ ghép cùng loại đối tượng
    2. Min observation: track phải sống ≥ N frames mới đủ tư cách
    3. Velocity direction: hướng xuất hiện lại phải hợp lý
    4. Spatial boundary: vị trí dự đoán không ra ngoài frame
    5. Confidence gate: detection mới phải đủ tin cậy
    6. Cooldown: sau ghép, khóa track N frames tránh chain-remap
    7. Active collision: new detection trùng bbox với vật đang active → reject
"""

import math
from collections import OrderedDict

import configs.settings as settings


class TrackletStitcher:
    """
    Wrapper ghép nối ID bị mất do che khuất lâu.

    Cách dùng:
        stitcher = TrackletStitcher(fps=30)
        # Mỗi frame:
        detections = stitcher.process(detections)
    """

    def __init__(self, fps=30, frame_width=1920, frame_height=1080,
                 max_lost_seconds=None):
        """
        Args:
            fps: FPS của video (dùng để tính Δt từ frame count).
            frame_width, frame_height: Kích thước frame (cho spatial boundary check).
            max_lost_seconds: Thời gian tối đa giữ track mất (giây).
                              None = dùng settings.TRACK_BUFFER_SECONDS.
        """
        self.fps = max(fps, 1)
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.max_lost_seconds = (max_lost_seconds if max_lost_seconds is not None
                                 else settings.TRACK_BUFFER_SECONDS)

        # Track đang active: {track_id: TrackHistory}
        self._active_tracks = {}

        # Pool track đã mất: OrderedDict {track_id: LostTrackInfo}
        self._lost_pool = OrderedDict()

        # Bảng remap: {new_id: {"target": original_id, "frame": frame_count}} — ánh xạ ID mới về ID gốc
        self._remap_table = {}

        # Cooldown: {track_id: remaining_frames}
        self._cooldowns = {}

        # Bộ đếm frame hiện tại
        self._frame_count = 0

        # Chu kỳ dọn dẹp (mỗi 300 frames)
        self._cleanup_interval = max(int(self.fps * 10), 300)

    # ─── PUBLIC ───────────────────────────────────────────────────────

    def process(self, detections):
        """
        Xử lý detections của 1 frame, trả về detections đã remap ID.

        Args:
            detections: list[dict] từ result_parser, mỗi dict có:
                id, label, conf, center (cx, cy), bbox_wh (w, h)

        Returns:
            list[dict] — cùng format, nhưng ID có thể đã được remap.
        """
        self._frame_count += 1
        self._tick_cooldowns()

        current_ids = set()
        new_detections = []       # Detection có ID chưa từng thấy
        existing_detections = []  # Detection có ID đã biết

        for det in detections:
            resolved_id = self._resolve_id(det["id"])
            det_copy = dict(det)
            det_copy["id"] = resolved_id
            current_ids.add(resolved_id)

            if resolved_id in self._active_tracks:
                existing_detections.append(det_copy)
            else:
                new_detections.append(det_copy)

        # Bước 1: Cập nhật history cho track đã biết
        for det in existing_detections:
            self._update_track_history(det)

        # Bước 2: Phát hiện track biến mất → đưa vào lost pool
        self._detect_lost_tracks(current_ids)

        # Bước 3: Ghép nối new IDs với lost pool
        remapped_new = self._try_stitch(new_detections, existing_detections)

        # Bước 4: ID mới thực sự → tạo track history mới
        for det in remapped_new:
            if det["id"] not in self._active_tracks:
                self._create_track(det)

        # Bước 5: Dọn dẹp lost pool (expired) + state cũ
        self._cleanup_lost_pool()
        if self._frame_count % self._cleanup_interval == 0:
            self._cleanup_stale_state()

        return existing_detections + remapped_new

    def set_frame_size(self, width, height):
        """Cập nhật kích thước frame (gọi khi biết size thực tế)."""
        self.frame_width = width
        self.frame_height = height

    # ─── INTERNAL: Track History ──────────────────────────────────────

    def _create_track(self, det):
        """Tạo track history mới cho một detection."""
        cx, cy = det["center"]
        w, h = det.get("bbox_wh", (0, 0))
        self._active_tracks[det["id"]] = {
            "label": det["label"],
            "positions": [(cx, cy)],  # Lịch sử vị trí (giữ tối đa 10)
            "bbox_wh": (w, h),
            "velocity": (0.0, 0.0),   # (vx, vy) pixel/frame
            "frame_count": 1,         # Số frame đã quan sát
            "last_frame": self._frame_count,
        }

    def _update_track_history(self, det):
        """Cập nhật vị trí và vận tốc cho track đang active."""
        track = self._active_tracks[det["id"]]
        cx, cy = det["center"]
        w, h = det.get("bbox_wh", (0, 0))

        # Tính vận tốc (smoothed: trung bình với vận tốc cũ)
        if track["positions"]:
            prev_cx, prev_cy = track["positions"][-1]
            raw_vx = cx - prev_cx
            raw_vy = cy - prev_cy
            old_vx, old_vy = track["velocity"]
            # Exponential moving average (α=0.3)
            α = 0.3
            track["velocity"] = (
                α * raw_vx + (1 - α) * old_vx,
                α * raw_vy + (1 - α) * old_vy,
            )

        # Lưu vị trí (giữ tối đa 10 gần nhất)
        track["positions"].append((cx, cy))
        if len(track["positions"]) > 10:
            track["positions"].pop(0)

        track["bbox_wh"] = (w, h)
        track["frame_count"] += 1
        track["last_frame"] = self._frame_count
        track["label"] = det["label"]

    # ─── INTERNAL: Lost Pool ──────────────────────────────────────────

    def _detect_lost_tracks(self, current_ids):
        """Phát hiện track biến mất và đưa vào lost pool."""
        lost_ids = []
        for tid, track in self._active_tracks.items():
            if tid not in current_ids:
                # Track biến mất frame này
                frames_missing = self._frame_count - track["last_frame"]
                if frames_missing >= 2:
                    # Đã mất ≥2 frames liên tiếp → coi là lost
                    lost_ids.append(tid)

        for tid in lost_ids:
            track = self._active_tracks.pop(tid)

            # Guard 2: Chỉ đưa vào pool nếu đã quan sát đủ lâu
            if track["frame_count"] < settings.STITCH_MIN_OBSERVE_FRAMES:
                continue

            # Giới hạn pool size
            if len(self._lost_pool) >= settings.STITCH_MAX_LOST_TRACKS:
                self._lost_pool.popitem(last=False)  # Xóa cũ nhất (FIFO)

            self._lost_pool[tid] = {
                "label": track["label"],
                "last_pos": track["positions"][-1],
                "velocity": track["velocity"],
                "bbox_wh": track["bbox_wh"],
                "lost_frame": self._frame_count,
                "positions_history": list(track["positions"]),
            }

    def _cleanup_lost_pool(self):
        """Xóa track đã hết thời gian chờ."""
        max_lost_frames = int(self.max_lost_seconds * self.fps)
        expired = [
            tid for tid, info in self._lost_pool.items()
            if (self._frame_count - info["lost_frame"]) > max_lost_frames
        ]
        for tid in expired:
            del self._lost_pool[tid]

    # ─── INTERNAL: Stitching Logic ────────────────────────────────────

    def _try_stitch(self, new_detections, existing_detections=None):
        """
        Thử ghép new detections với lost pool.
        Dùng cost-based greedy matching.
        """
        if not new_detections or not self._lost_pool:
            return new_detections

        # Tính cost matrix: candidates[i] = (new_det_idx, lost_id, cost)
        candidates = []
        for i, det in enumerate(new_detections):
            # Guard 5: Confidence gate
            if det.get("conf", 1.0) < settings.STITCH_CONFIDENCE_GATE:
                continue

            # Guard 7: Active collision — nếu new detection trùng bbox
            # với vật đang active → skip (đây là vật khác, không phải lost track)
            if self._has_active_collision(det, existing_detections):
                continue

            for lost_id, lost_info in self._lost_pool.items():
                cost = self._compute_cost(det, lost_info)
                if cost is not None and cost < settings.STITCH_COST_THRESHOLD:
                    candidates.append((i, lost_id, cost))

        # Greedy optimal matching: sắp xếp theo cost thấp nhất
        candidates.sort(key=lambda x: x[2])

        matched_new = set()
        matched_lost = set()
        result = list(new_detections)

        for new_idx, lost_id, cost in candidates:
            if new_idx in matched_new or lost_id in matched_lost:
                continue

            # Thực hiện remap
            old_new_id = result[new_idx]["id"]
            result[new_idx] = dict(result[new_idx])
            result[new_idx]["id"] = lost_id

            # Ghi vào remap table (kèm timestamp)
            self._remap_table[old_new_id] = {
                "target": lost_id,
                "frame": self._frame_count,
            }

            # Khôi phục track history từ lost pool
            lost_info = self._lost_pool[lost_id]
            self._active_tracks[lost_id] = {
                "label": lost_info["label"],
                "positions": lost_info["positions_history"],
                "bbox_wh": result[new_idx].get("bbox_wh", lost_info["bbox_wh"]),
                "velocity": lost_info["velocity"],
                "frame_count": len(lost_info["positions_history"]),
                "last_frame": self._frame_count,
            }
            self._update_track_history(result[new_idx])

            # Guard 6: Cooldown
            self._cooldowns[lost_id] = settings.STITCH_REMAP_COOLDOWN

            matched_new.add(new_idx)
            matched_lost.add(lost_id)

            print(f"[Stitcher] REMAP: ID {old_new_id} → ID {lost_id} "
                  f"(cost={cost:.3f})")

        # Xóa lost tracks đã match
        for lost_id in matched_lost:
            if lost_id in self._lost_pool:
                del self._lost_pool[lost_id]

        return result

    def _compute_cost(self, det, lost_info):
        """
        Tính cost ghép giữa 1 new detection và 1 lost track.
        Returns: float cost, hoặc None nếu bị reject bởi guards.
        """
        # ── Guard 1: Same label ──
        if det["label"] != lost_info["label"]:
            return None

        # ── Tính Δt (số frame mất) ──
        frames_lost = self._frame_count - lost_info["lost_frame"]
        seconds_lost = frames_lost / self.fps

        if seconds_lost > self.max_lost_seconds:
            return None

        # ── Distance score (có velocity prediction) ──
        lx, ly = lost_info["last_pos"]
        vx, vy = lost_info["velocity"]

        # Dự đoán vị trí: last_pos + velocity × frames_lost
        pred_x = lx + vx * frames_lost
        pred_y = ly + vy * frames_lost

        # Guard 4: Spatial boundary — vị trí dự đoán có hợp lý không?
        margin = 50
        if (pred_x < -margin or pred_x > self.frame_width + margin or
                pred_y < -margin or pred_y > self.frame_height + margin):
            pred_x, pred_y = lx, ly

        cx, cy = det["center"]
        distance = math.hypot(cx - pred_x, cy - pred_y)

        if distance > settings.STITCH_MAX_DISTANCE:
            return None

        distance_score = distance / settings.STITCH_MAX_DISTANCE

        # ── Size score ──
        det_w, det_h = det.get("bbox_wh", (0, 0))
        lost_w, lost_h = lost_info["bbox_wh"]

        if det_w > 0 and det_h > 0 and lost_w > 0 and lost_h > 0:
            det_area = det_w * det_h
            lost_area = lost_w * lost_h
            size_ratio = abs(det_area - lost_area) / max(det_area, lost_area)
            if size_ratio > settings.STITCH_SIZE_RATIO_THRESH:
                return None
            size_score = size_ratio / settings.STITCH_SIZE_RATIO_THRESH
        else:
            size_score = 0.5

        # ── Time score ──
        time_score = seconds_lost / self.max_lost_seconds

        # ── Direction score (Guard 3) ──
        direction_score = self._compute_direction_score(
            det, lost_info, pred_x, pred_y, frames_lost
        )
        if direction_score is None:
            return None

        # ── Tổng hợp cost ──
        cost = (settings.STITCH_W_DISTANCE * distance_score +
                settings.STITCH_W_SIZE * size_score +
                settings.STITCH_W_TIME * time_score +
                settings.STITCH_W_DIRECTION * direction_score)

        return cost

    def _compute_direction_score(self, det, lost_info, pred_x, pred_y, frames_lost):
        """
        Kiểm tra hướng di chuyển có consistent không.

        Returns:
            float 0.0-1.0 (0=cùng hướng, 1=ngược hướng), hoặc None nếu reject.
        """
        vx, vy = lost_info["velocity"]
        speed = math.hypot(vx, vy)

        if speed < 1.0:
            return 0.0

        lx, ly = lost_info["last_pos"]
        cx, cy = det["center"]
        dx = cx - lx
        dy = cy - ly
        move_dist = math.hypot(dx, dy)

        if move_dist < 1.0:
            return 0.0

        cos_sim = (vx * dx + vy * dy) / (speed * move_dist)

        # Guard 3: Nếu ngược hướng VÀ di chuyển xa → reject
        if cos_sim < -0.5 and move_dist > 50:
            return None

        direction_score = (1.0 - cos_sim) / 2.0
        return direction_score

    # ─── INTERNAL: Helpers ────────────────────────────────────────────

    @staticmethod
    def _compute_iou(det_a, det_b):
        """
        Tính IoU giữa 2 detection dựa trên center + bbox_wh.
        Returns: float 0.0-1.0
        """
        ax, ay = det_a["center"]
        aw, ah = det_a.get("bbox_wh", (0, 0))
        bx, by = det_b["center"]
        bw, bh = det_b.get("bbox_wh", (0, 0))

        if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
            return 0.0

        # Chuyển center+wh → x1y1x2y2
        a_x1, a_y1 = ax - aw / 2, ay - ah / 2
        a_x2, a_y2 = ax + aw / 2, ay + ah / 2
        b_x1, b_y1 = bx - bw / 2, by - bh / 2
        b_x2, b_y2 = bx + bw / 2, by + bh / 2

        # Intersection
        ix1 = max(a_x1, b_x1)
        iy1 = max(a_y1, b_y1)
        ix2 = min(a_x2, b_x2)
        iy2 = min(a_y2, b_y2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0

        inter = (ix2 - ix1) * (iy2 - iy1)
        area_a = aw * ah
        area_b = bw * bh
        union = area_a + area_b - inter

        return inter / union if union > 0 else 0.0

    def _has_active_collision(self, det, existing_detections):
        """
        Guard 7: Kiểm tra new detection có overlap với active track nào không.

        Nếu IoU ≥ STITCH_COLLISION_IOU_THRESH → trả True (collision).
        Mục đích: khi vật A mất track rồi xuất hiện lại chồng lên B,
        detection mới overlap B → reject stitch → tránh cướp ID.
        """
        if not existing_detections:
            return False

        thresh = settings.STITCH_COLLISION_IOU_THRESH
        for ex_det in existing_detections:
            if self._compute_iou(det, ex_det) >= thresh:
                return True
        return False

    def _resolve_id(self, raw_id):
        """Tra cứu remap table: nếu ID đã bị remap trước đó, trả về ID gốc."""
        entry = self._remap_table.get(raw_id)
        if entry:
            return entry["target"]
        return raw_id

    def _tick_cooldowns(self):
        """Giảm cooldown mỗi frame, xóa khi hết."""
        expired = [tid for tid, cd in self._cooldowns.items() if cd <= 1]
        for tid in expired:
            del self._cooldowns[tid]
        for tid in self._cooldowns:
            self._cooldowns[tid] -= 1

    def _cleanup_stale_state(self):
        """Dọn dẹp state cũ định kỳ để tránh tích lũy."""
        max_age = int(self.max_lost_seconds * self.fps * 2)

        # Xóa remap entries cũ
        stale_remaps = [
            k for k, v in self._remap_table.items()
            if (self._frame_count - v["frame"]) > max_age
        ]
        for k in stale_remaps:
            del self._remap_table[k]

        # Xóa active tracks không xuất hiện quá lâu
        stale_tracks = [
            tid for tid, track in self._active_tracks.items()
            if (self._frame_count - track["last_frame"]) > max_age
        ]
        for tid in stale_tracks:
            del self._active_tracks[tid]

        if stale_remaps or stale_tracks:
            print(f"[Stitcher] Cleanup: {len(stale_remaps)} remaps, "
                  f"{len(stale_tracks)} stale tracks removed")
