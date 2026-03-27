"""
Tracklet Stitcher: Lightweight ID bridging for ByteTrack.

Goal:
- When ByteTrack drops an ID (occlusion) and assigns a new one,
  remap the new ID to the old ID to keep counting stable.

Design:
- Simple, fast, conservative (avoid wrong merges)
- Works with existing detection dicts: {id, label, center, bbox_wh, conf}
"""

import math

import configs.settings as settings


def _bbox_from_det(det):
    cx, cy = det.get("center", (0.0, 0.0))
    w, h = det.get("bbox_wh", (0.0, 0.0))
    x1 = cx - w / 2.0
    y1 = cy - h / 2.0
    x2 = cx + w / 2.0
    y2 = cy + h / 2.0
    area = max(0.0, w) * max(0.0, h)
    return (x1, y1, x2, y2), area


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class TrackletStitcher:
    """Simple ID stitcher to bridge short occlusions."""

    def __init__(self, fps=30, frame_width=0, frame_height=0):
        self.fps = max(1, int(round(fps)))
        self.frame_width = int(frame_width) if frame_width else 0
        self.frame_height = int(frame_height) if frame_height else 0

        self.max_lost_frames = int(getattr(settings, "TRACKLET_MAX_LOST_FRAMES", 15))
        self.min_observe_frames = int(getattr(settings, "TRACKLET_MIN_OBSERVE_FRAMES", 3))
        self.max_lost_tracks = int(getattr(settings, "TRACKLET_MAX_LOST_TRACKS", 200))
        self.iou_thresh = float(getattr(settings, "TRACKLET_IOU_THRESHOLD", 0.3))
        self.max_dist_px = int(getattr(settings, "TRACKLET_MAX_DISTANCE_PIXELS", 80))
        self.max_dist_ratio = float(getattr(settings, "TRACKLET_MAX_DISTANCE_RATIO", 0.0))
        self.size_ratio_min = float(getattr(settings, "TRACKLET_SIZE_RATIO_MIN", 0.5))
        self.size_ratio_max = float(getattr(settings, "TRACKLET_SIZE_RATIO_MAX", 2.0))
        self.remap_ttl = int(getattr(settings, "TRACKLET_REMAP_TTL", 60))
        self.missing_to_lost = int(getattr(settings, "TRACKLET_MISSING_TO_LOST", 2))
        self.cooldown_frames = int(getattr(settings, "TRACKLET_REMAP_COOLDOWN", 5))
        self.direction_min_cos = float(getattr(settings, "TRACKLET_DIRECTION_MIN_COS", 0.15))
        self.min_speed_for_direction = float(getattr(settings, "TRACKLET_MIN_SPEED_FOR_DIRECTION", 6.0))
        self.min_confidence = float(getattr(settings, "TRACKLET_MIN_CONFIDENCE", 0.20))

        self._frame = 0
        self._active = {}
        self._lost = {}
        self._remap = {}
        self._cooldown = {}

    def set_frame_size(self, width, height):
        if width > 0 and height > 0:
            self.frame_width = int(width)
            self.frame_height = int(height)

    def _get_max_dist(self):
        if self.max_dist_ratio > 0 and self.frame_width > 0 and self.frame_height > 0:
            base = min(self.frame_width, self.frame_height)
            return max(10, int(round(base * self.max_dist_ratio)))
        return self.max_dist_px

    def _resolve_id(self, raw_id):
        entry = self._remap.get(raw_id)
        if entry is None:
            return raw_id
        entry["last_seen"] = self._frame
        return entry["target"]

    def _eligible(self, det, lost_state):
        if det.get("label") != lost_state.get("label"):
            return False
        if (self._frame - lost_state.get("last_seen", 0)) > self.max_lost_frames:
            return False
        if lost_state.get("id") in self._cooldown:
            return False
        if float(det.get("conf", 0.0)) < self.min_confidence:
            return False
        new_area = det.get("_area", 0.0)
        old_area = lost_state.get("area", 0.0)
        if new_area > 0 and old_area > 0:
            ratio = new_area / old_area
            if ratio < self.size_ratio_min or ratio > self.size_ratio_max:
                return False
        if not self._direction_ok(det, lost_state):
            return False
        return True

    def _lost_age(self, state):
        return max(0, self._frame - state.get("last_seen", self._frame))

    def _predict_center(self, state):
        sx, sy = state.get("center", (0.0, 0.0))
        vx, vy = state.get("velocity", (0.0, 0.0))
        lost_age = self._lost_age(state)
        return sx + vx * lost_age, sy + vy * lost_age

    def _distance_to_state(self, det, state):
        cx, cy = det.get("center", (0.0, 0.0))
        px, py = self._predict_center(state)
        return math.hypot(cx - px, cy - py)

    def _dynamic_max_dist(self, det, state, base_max_dist):
        det_w, det_h = det.get("bbox_wh", (0.0, 0.0))
        st_bbox = state.get("bbox", (0.0, 0.0, 0.0, 0.0))
        st_w = max(0.0, st_bbox[2] - st_bbox[0])
        st_h = max(0.0, st_bbox[3] - st_bbox[1])
        diag = max(det_w, st_w) + max(det_h, st_h)
        lost_age = self._lost_age(state)
        age_scale = min(1.8, 1.0 + max(0, lost_age - 1) * 0.18)
        return max(base_max_dist, diag * 0.45 * age_scale)

    def _direction_ok(self, det, state):
        vx, vy = state.get("velocity", (0.0, 0.0))
        speed = math.hypot(vx, vy)
        if speed < self.min_speed_for_direction:
            return True

        sx, sy = state.get("center", (0.0, 0.0))
        cx, cy = det.get("center", (sx, sy))
        dx = cx - sx
        dy = cy - sy
        move = math.hypot(dx, dy)
        if move < 1.0:
            return True

        cos_sim = (vx * dx + vy * dy) / (speed * move)
        return cos_sim >= self.direction_min_cos

    def _create_state(self, det, seed=None):
        bbox, area = _bbox_from_det(det)
        center = det.get("center", (0.0, 0.0))
        state = {
            "id": det.get("id"),
            "label": det.get("label"),
            "center": center,
            "prev_center": center,
            "velocity": (0.0, 0.0),
            "bbox": bbox,
            "area": area,
            "last_seen": self._frame,
            "seen_frames": 1,
            "missing": 0,
        }
        if seed is not None:
            state["seen_frames"] = max(seed.get("seen_frames", 1), 1)
            state["prev_center"] = seed.get("prev_center", center)
            state["velocity"] = seed.get("velocity", (0.0, 0.0))
        return state

    def _update_state(self, state, det):
        bbox, area = _bbox_from_det(det)
        prev_center = state.get("center", det.get("center", (0.0, 0.0)))
        new_center = det.get("center", prev_center)
        prev_vx, prev_vy = state.get("velocity", (0.0, 0.0))
        inst_vx = new_center[0] - prev_center[0]
        inst_vy = new_center[1] - prev_center[1]
        state["label"] = det.get("label")
        state["prev_center"] = prev_center
        state["center"] = new_center
        state["velocity"] = (
            prev_vx * 0.5 + inst_vx * 0.5,
            prev_vy * 0.5 + inst_vy * 0.5,
        )
        state["bbox"] = bbox
        state["area"] = area
        state["last_seen"] = self._frame
        state["seen_frames"] = state.get("seen_frames", 0) + 1
        state["missing"] = 0

    def _tick_cooldown(self):
        expired = [k for k, v in self._cooldown.items() if v <= 1]
        for k in expired:
            del self._cooldown[k]
        for k in list(self._cooldown.keys()):
            self._cooldown[k] -= 1

    def _cleanup(self):
        expired = [
            tid for tid, st in self._lost.items()
            if (self._frame - st.get("last_seen", 0)) > self.max_lost_frames
        ]
        for tid in expired:
            del self._lost[tid]

        if len(self._lost) > self.max_lost_tracks:
            items = sorted(self._lost.items(), key=lambda kv: kv[1].get("last_seen", 0))
            to_remove = len(self._lost) - self.max_lost_tracks
            for i in range(to_remove):
                del self._lost[items[i][0]]

        remap_expired = [
            raw_id for raw_id, info in self._remap.items()
            if (self._frame - info.get("last_seen", 0)) > self.remap_ttl
        ]
        for raw_id in remap_expired:
            del self._remap[raw_id]

    def _best_match_iou(self, det, lost_pool):
        best_id = None
        best_iou = 0.0
        for tid, st in lost_pool.items():
            if not self._eligible(det, st):
                continue
            iou = _iou(det.get("_bbox"), st.get("bbox"))
            if iou > best_iou:
                best_iou = iou
                best_id = tid
        if best_id is not None and best_iou >= self.iou_thresh:
            return best_id, best_iou
        return None, 0.0

    def _best_match_dist(self, det, lost_pool, max_dist):
        best_id = None
        best_dist = 1e9
        for tid, st in lost_pool.items():
            if not self._eligible(det, st):
                continue
            dist = self._distance_to_state(det, st)
            allowed_dist = self._dynamic_max_dist(det, st, max_dist)
            if dist > allowed_dist:
                continue
            if dist < best_dist:
                best_dist = dist
                best_id = tid
        if best_id is not None:
            return best_id, best_dist
        return None, None

    def process(self, detections, frame_shape=None):
        """Process detections for one frame and return detections with remapped IDs."""
        self._frame += 1
        self._tick_cooldown()

        if frame_shape is not None and self.frame_width == 0:
            h, w = frame_shape[:2]
            self.set_frame_size(w, h)

        resolved = []
        for det in detections or []:
            if "id" not in det:
                continue
            new_det = dict(det)
            raw_id = new_det["id"]
            new_det["_raw_id"] = raw_id
            new_det["id"] = self._resolve_id(raw_id)
            bbox, area = _bbox_from_det(new_det)
            new_det["_bbox"] = bbox
            new_det["_area"] = area
            resolved.append(new_det)

        new_dets = []
        current_ids = set()
        for det in resolved:
            tid = det["id"]
            current_ids.add(tid)
            if tid in self._active:
                self._update_state(self._active[tid], det)
            elif tid in self._lost:
                seed = self._lost.pop(tid)
                self._active[tid] = self._create_state(det, seed=seed)
            else:
                new_dets.append(det)

        used_lost = set()
        max_dist = self._get_max_dist()
        candidates = []
        for idx, det in enumerate(new_dets):
            match_id, score_iou = self._best_match_iou(det, self._lost)
            if match_id is not None:
                candidates.append((1.0 - score_iou, idx, match_id))
                continue
            match_id, dist = self._best_match_dist(det, self._lost, max_dist)
            if match_id is not None:
                candidates.append((1.0 + dist / max_dist, idx, match_id))

        candidates.sort(key=lambda x: x[0])

        used_new = set()
        for _score, idx, lost_id in candidates:
            if idx in used_new or lost_id in used_lost:
                continue
            det = new_dets[idx]
            raw_id = det.get("_raw_id", det["id"])

            det["id"] = lost_id
            self._remap[raw_id] = {"target": lost_id, "last_seen": self._frame}

            seed = self._lost.pop(lost_id)
            self._active[lost_id] = self._create_state(det, seed=seed)

            if self.cooldown_frames > 0:
                self._cooldown[lost_id] = self.cooldown_frames

            used_new.add(idx)
            used_lost.add(lost_id)

        for idx, det in enumerate(new_dets):
            if idx in used_new:
                continue
            tid = det["id"]
            if tid not in self._active:
                self._active[tid] = self._create_state(det)

        current_ids = {det["id"] for det in resolved}

        for tid in list(self._active.keys()):
            if tid in current_ids:
                continue
            state = self._active[tid]
            state["missing"] = state.get("missing", 0) + 1
            if state["missing"] >= self.missing_to_lost:
                if state.get("seen_frames", 0) >= self.min_observe_frames:
                    self._lost[tid] = dict(state)
                del self._active[tid]

        self._cleanup()

        for det in resolved:
            det.pop("_raw_id", None)
            det.pop("_bbox", None)
            det.pop("_area", None)

        return resolved
