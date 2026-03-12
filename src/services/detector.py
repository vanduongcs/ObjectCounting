"""
Detector Service: Wrapper cho model YOLO + OpenVINO.

Ai gọi module này?
    - AIService._process_frame() (services/ai_service.py) gọi detector.track()

Module này gọi ai?
    - YOLO (ultralytics) -- chạy inference (detect + track)
    - OpenVINO (openvino) -- chọn device tối ưu (iGPU / CPU)
    - result_parser (utils/result_parser.py) -- parse kết quả YOLO thành dict

Luồng dữ liệu:
    frame (numpy) -> YOLO.track() -> raw_results (YOLO objects)
                                  -> parse_tracking_results() -> detections (list[dict])
"""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from openvino import Core
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
import yaml

try:
    from ocsort.ocsort import OCSort
except Exception:
    OCSort = None

from src.utils.result_parser import parse_tracking_results
import configs.settings as settings


def _select_best_openvino_device() -> str:
    """
    Chọn thiết bị tối ưu cho OpenVINO inference.
    Ưu tiên: Intel iGPU > CPU > AUTO.
    """
    # Ultralytics kiểm tra CUDA trước; nếu torch không có CUDA thì "GPU" sẽ gây lỗi.
    try:
        import torch
        if not torch.cuda.is_available():
            return "CPU"
    except Exception:
        pass

    try:
        from openvino import Core
        available = Core().available_devices
        print(f"[OpenVINO] Thiết bị khả dụng: {available}")

        if any(d.startswith("GPU") for d in available):
            print("[OpenVINO] Sử dụng Intel iGPU")
            return "GPU"

        print("[OpenVINO] Sử dụng CPU")
        return "CPU"
    except Exception as e:
        print(f"[OpenVINO] Không thể kiểm tra thiết bị, dùng AUTO: {e}")
        return "AUTO"


def _select_best_torch_device() -> str:
    """
    Chọn thiết bị cho PyTorch model (.pt).
    Ưu tiên CUDA nếu có, fallback CPU.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
    except Exception:
        pass
    return "cpu"


class ObjectDetector:
    def __init__(self, model_path, conf=None):
        self.conf = conf if conf is not None else settings.DETECTION_CONFIDENCE
        self._model_path = self._resolve_model_path(model_path)
        self._is_openvino = self._is_openvino_path(self._model_path)
        self.device = _select_best_openvino_device() if self._is_openvino else _select_best_torch_device()
        self._tracker = None
        self._tracker_type = getattr(settings, "TRACKER_TYPE", "ocsort")
        self._use_ocsort = (self._tracker_type == "ocsort" and OCSort is not None)
        self._tracker_fps = settings.DEFAULT_FPS
        self._tracker_frame_id = 0
        self._ov_core = None
        self._ov_compiled = None
        self._ov_output_layer = None
        self._ov_input_hw = (settings.DETECTION_IMGSZ, settings.DETECTION_IMGSZ)
        self.names = {}
        self.yolo_model = None
        self._class_color_cache = {}

        if self._is_openvino:
            self._init_openvino()
        else:
            self.yolo_model = YOLO(self._model_path, task="detect")
            self.names = getattr(self.yolo_model, "names", {})
            self._warmup_torch()
        self._init_tracker()

    @staticmethod
    def _is_openvino_path(model_path) -> bool:
        try:
            path = Path(model_path)
        except TypeError:
            return False
        if path.is_dir():
            return any(path.glob("*.xml"))
        return path.suffix.lower() == ".xml"

    def _find_ov_xml(self, model_path: Path) -> tuple[Path, Path]:
        if model_path.is_dir():
            xml = model_path / "best.xml"
            if not xml.exists():
                xmls = list(model_path.glob("*.xml"))
                xml = xmls[0] if xmls else None
            if xml is None:
                raise FileNotFoundError(f"No .xml found in {model_path}")
            return model_path, xml
        if model_path.suffix.lower() == ".xml":
            return model_path.parent, model_path
        raise FileNotFoundError(f"OpenVINO model path invalid: {model_path}")

    def _load_ov_metadata(self, model_dir: Path):
        meta_path = model_dir / "metadata.yaml"
        if not meta_path.exists():
            return
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return

        names = data.get("names", {})
        if isinstance(names, dict):
            # keys may be strings -> convert to int
            self.names = {int(k): v for k, v in names.items()}
        imgsz = data.get("imgsz")
        if isinstance(imgsz, (list, tuple)) and len(imgsz) == 2:
            self._ov_input_hw = (int(imgsz[0]), int(imgsz[1]))

    def _init_openvino(self):
        model_path = Path(self._model_path)
        model_dir, xml_path = self._find_ov_xml(model_path)
        self._load_ov_metadata(model_dir)

        self._ov_core = Core()
        ov_model = self._ov_core.read_model(str(xml_path))
        self._ov_compiled = self._ov_core.compile_model(ov_model, self.device)
        self._ov_output_layer = self._ov_compiled.output(0)

        # Input shape: [1,3,H,W]
        try:
            ishape = self._ov_compiled.input(0).shape
            if len(ishape) == 4 and ishape[2] and ishape[3]:
                self._ov_input_hw = (int(ishape[2]), int(ishape[3]))
        except Exception:
            pass

        self._warmup_openvino()

    def _load_tracker_args(self):
        defaults = {
            "track_high_thresh": 0.25,
            "track_low_thresh": 0.1,
            "new_track_thresh": 0.25,
            "track_buffer": 30,
            "match_thresh": 0.8,
            "fuse_score": True,
        }
        cfg_path = settings.BASE_DIR / "configs" / "bytetrack_custom.yaml"
        try:
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for k in list(defaults.keys()):
                    if k in data:
                        defaults[k] = data[k]
        except Exception:
            pass
        return SimpleNamespace(**defaults)

    def _init_tracker(self):
        if self._use_ocsort:
            self._tracker = self._init_ocsort()
            self._tracker_frame_id = 0
            return
        if not self._is_openvino:
            self._tracker = None
            return
        args = self._load_tracker_args()
        self._tracker = BYTETracker(args, frame_rate=int(round(self._tracker_fps)))
        self._tracker_frame_id = 0

    def _init_ocsort(self):
        if OCSort is None:
            print("[Tracker] OC-SORT chưa được cài, fallback ByteTrack.")
            self._use_ocsort = False
            return None
        try:
            return OCSort(
                det_thresh=float(self.conf),
                max_age=30,
                min_hits=3,
                iou_threshold=0.3,
                delta_t=3,
                asso_func="iou",
                inertia=0.2,
                use_byte=False,
            )
        except Exception:
            try:
                return OCSort(float(self.conf))
            except Exception:
                return OCSort()

    def set_fps(self, fps):
        if not self._is_openvino:
            return
        if fps and fps > 0:
            self._tracker_fps = fps
        self._init_tracker()

    def advance_tracker_frame(self, frame_id: int):
        if not self._is_openvino or not self._tracker or not hasattr(self._tracker, "frame_id"):
            return
        if frame_id < 1:
            return
        if self._tracker_frame_id == 0:
            self._tracker_frame_id = frame_id
            self._tracker.frame_id = frame_id - 1
            return
        if frame_id <= self._tracker_frame_id:
            return
        delta = frame_id - self._tracker_frame_id
        self._tracker_frame_id = frame_id
        if delta == 1:
            return
        self._tracker.frame_id += (delta - 1)

    @staticmethod
    def _resolve_model_path(model_path):
        """
        Chuẩn hóa đường dẫn model (file hoặc thư mục).
        """
        try:
            path = Path(model_path)
        except TypeError:
            return model_path
        return str(path)

    def _warmup_openvino(self):
        print(f"[OpenVINO] Warming up trên {self.device}...")
        h, w = self._ov_input_hw
        dummy = np.zeros((1, 3, h, w), dtype=np.float32)
        _ = self._ov_compiled([dummy])[self._ov_output_layer]
        print("[OpenVINO] Warmup hoàn tất.")

    def _warmup_torch(self):
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        print(f"[Torch] Warming up trên {self.device}...")
        try:
            self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
            print("[Torch] Warmup hoàn tất.")
        except Exception as e:
            print(f"[Torch] Warmup {self.device} thất bại: {e}, chuyển sang CPU...")
            self.device = "cpu"
            try:
                self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
                print("[Torch] Warmup CPU hoàn tất.")
            except Exception as e2:
                print(f"[Torch] Warmup CPU cũng thất bại (bỏ qua): {e2}")

    @staticmethod
    def _letterbox(img, new_shape, color=(114, 114, 114)):
        # Match Ultralytics letterbox (rect=False -> auto=False)
        shape = img.shape[:2]  # h, w
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
        dw = (new_shape[1] - new_unpad[0]) / 2
        dh = (new_shape[0] - new_unpad[1]) / 2

        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(
            img, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=color
        )
        return img, r, (dw, dh)

    def _get_class_color(self, cls_id: int) -> tuple[int, int, int]:
        """Deterministic BGR color for a class id."""
        if cls_id in self._class_color_cache:
            return self._class_color_cache[cls_id]
        palette = [
            (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
            (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
            (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
            (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
            (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
        ]
        color = palette[int(cls_id) % len(palette)]
        self._class_color_cache[cls_id] = color
        return color

    def _get_text_scale(self, frame_shape) -> float:
        """Scale text size based on UI target size to keep on-screen size consistent."""
        ui_scale = self._get_ui_scale(frame_shape)
        base = getattr(settings, "UI_BASE_FONT_SCALE", 0.7)
        return max(0.3, base / ui_scale) if ui_scale > 0 else base

    def _get_ui_scale(self, frame_shape) -> float:
        h = frame_shape[0] if len(frame_shape) >= 2 else 480
        w = frame_shape[1] if len(frame_shape) >= 2 else 640
        target_w = getattr(settings, "UI_TARGET_WIDTH", 800)
        target_h = getattr(settings, "UI_TARGET_HEIGHT", 600)
        return min(target_w / w, target_h / h)

    def _ov_predict(self, frame):
        h_in, w_in = self._ov_input_hw
        img, r, (dw, dh) = self._letterbox(frame, (h_in, w_in))
        # BGR -> RGB to match Ultralytics preprocessing
        img = img[:, :, ::-1]
        img = img.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        img = np.ascontiguousarray(img)

        output = self._ov_compiled([img])[self._ov_output_layer]
        output = output[0]  # (N,6)
        if output.size == 0:
            return np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.int32)

        scores = output[:, 4]
        mask = scores >= self.conf
        if not np.any(mask):
            return np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.int32)

        boxes = output[mask, :4].astype(np.float32)
        scores = scores[mask].astype(np.float32)
        classes = output[mask, 5].astype(np.int32)

        # scale back to original image size
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - dw) / r
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - dh) / r

        # clip
        h0, w0 = frame.shape[:2]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w0 - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h0 - 1)

        # filter degenerate / non-finite
        w = boxes[:, 2] - boxes[:, 0]
        h = boxes[:, 3] - boxes[:, 1]
        valid = (w > 1) & (h > 1) & np.isfinite(boxes).all(axis=1) & np.isfinite(scores)
        if not np.any(valid):
            return np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.float32), np.empty((0,), dtype=np.int32)

        return boxes[valid], scores[valid], classes[valid]

    @staticmethod
    def _iou_xyxy(a, b) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter_w = max(0.0, x2 - x1)
        inter_h = max(0.0, y2 - y1)
        inter = inter_w * inter_h
        if inter <= 0:
            return 0.0
        area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
        area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _assign_classes_by_iou(self, track_boxes, det_boxes, det_classes, det_scores):
        n = len(track_boxes)
        classes_out = np.full((n,), -1, dtype=np.int32)
        scores_out = np.zeros((n,), dtype=np.float32)
        if n == 0 or len(det_boxes) == 0:
            return classes_out, scores_out
        for i, tbox in enumerate(track_boxes):
            best_iou = 0.0
            best_idx = -1
            for j, dbox in enumerate(det_boxes):
                iou = self._iou_xyxy(tbox, dbox)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = j
            if best_idx >= 0:
                classes_out[i] = int(det_classes[best_idx])
                scores_out[i] = float(det_scores[best_idx])
        return classes_out, scores_out

    def _update_ocsort(self, boxes_xyxy, scores, classes, frame_shape):
        if self._tracker is None:
            self._init_tracker()
        if self._tracker is None:
            return np.empty((0, 5), dtype=np.float32)
        if len(boxes_xyxy) == 0:
            return np.empty((0, 5), dtype=np.float32)
        dets = np.concatenate([boxes_xyxy, scores[:, None]], axis=1).astype(np.float32)
        try:
            if hasattr(self._tracker, "update_public"):
                return self._tracker.update_public(
                    boxes_xyxy.astype(np.float32),
                    classes.astype(np.int32),
                    scores.astype(np.float32),
                )
            try:
                return self._tracker.update(dets)
            except TypeError:
                h, w = frame_shape[:2]
                return self._tracker.update(dets, (h, w), (h, w))
        except Exception as e:
            print(f"[Tracker] OC-SORT update lỗi: {e}")
            return np.empty((0, 5), dtype=np.float32)

    def _tracks_to_detections(self, tracks, det_boxes, det_classes, det_scores):
        if tracks is None:
            return []
        tracks = np.asarray(tracks)
        if tracks.size == 0:
            return []
        if tracks.ndim == 1:
            tracks = tracks.reshape(1, -1)

        if tracks.shape[1] >= 6:
            track_classes = tracks[:, 5].astype(np.int32)
            track_scores = np.ones((len(tracks),), dtype=np.float32)
        else:
            track_classes, track_scores = self._assign_classes_by_iou(
                tracks[:, :4], det_boxes, det_classes, det_scores
            )

        detections = []
        for i, t in enumerate(tracks):
            x1, y1, x2, y2 = t[:4]
            tid = int(t[4]) if t.shape[0] >= 5 else i
            w = x2 - x1
            h = y2 - y1
            if w <= 1 or h <= 1:
                continue
            cx = x1 + w / 2
            cy = y1 + h / 2
            if not (np.isfinite(cx) and np.isfinite(cy)):
                continue
            detections.append({
                "id": int(tid),
                "label": int(track_classes[i]),
                "conf": float(track_scores[i]),
                "center": (float(cx), float(cy)),
                "bbox_wh": (float(w), float(h)),
            })
        return detections

    def has_detections(self, raw_results) -> bool:
        if isinstance(raw_results, dict):
            boxes = raw_results.get("boxes_xyxy")
            return boxes is not None and len(boxes) > 0
        if self._is_openvino:
            if not raw_results:
                return False
            boxes = raw_results.get("boxes_xyxy")
            return boxes is not None and len(boxes) > 0
        return bool(raw_results)

    def render(self, frame, raw_results, show_boxes=True):
        if isinstance(raw_results, dict):
            if not raw_results:
                return frame
            if not show_boxes:
                return frame
            boxes = raw_results.get("boxes_xyxy", [])
            scores = raw_results.get("scores", [])
            classes = raw_results.get("classes", [])
            font_scale = self._get_text_scale(frame.shape)
            ui_scale = self._get_ui_scale(frame.shape)
            base_text_thick = getattr(settings, "UI_BASE_TEXT_THICKNESS", 2)
            base_box_thick = getattr(settings, "UI_BASE_BOX_THICKNESS", 2)
            font_thickness = max(1, int(round(base_text_thick / ui_scale))) if ui_scale > 0 else base_text_thick
            box_thickness = max(1, int(round(base_box_thick / ui_scale))) if ui_scale > 0 else base_box_thick
            for (x1, y1, x2, y2), score, cls_id in zip(boxes, scores, classes):
                p1 = (int(x1), int(y1))
                p2 = (int(x2), int(y2))
                name = self.names.get(int(cls_id), str(int(cls_id)))
                label = f"{name} {score:.2f}"
                color = self._get_class_color(int(cls_id))
                cv2.rectangle(frame, p1, p2, color, box_thickness)

                (tw, th), base = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
                )
                text_x = p1[0]
                text_y = max(p1[1] - 6, th + 6)
                cv2.rectangle(
                    frame,
                    (text_x, text_y - th - base - 4),
                    (text_x + tw + 6, text_y + 2),
                    color,
                    -1,
                )
                cv2.putText(
                    frame, label, (text_x + 3, text_y - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255),
                    font_thickness, cv2.LINE_AA
                )
            return frame

        # PyTorch path
        result = raw_results[0]
        return result.plot(boxes=show_boxes, masks=False)

    def track(self, frame):
        """
        Detect + Track đối tượng bằng ByteTrack mặc định.
        Returns: (raw_results, parsed_detections)
            - raw_results: Kết quả gốc từ YOLO (để vẽ plot)
            - parsed_detections: List[dict] đã parse (để đếm)
        """
        frame = np.ascontiguousarray(frame)
        if self._is_openvino:
            boxes_xyxy, scores, classes = self._ov_predict(frame)
            raw_results = {
                "boxes_xyxy": boxes_xyxy,
                "scores": scores,
                "classes": classes,
            }

            if len(boxes_xyxy) == 0:
                return raw_results, []

            if self._use_ocsort:
                tracks = self._update_ocsort(boxes_xyxy, scores, classes, frame.shape)
                detections = self._tracks_to_detections(tracks, boxes_xyxy, classes, scores)
                return raw_results, detections

            # Convert to center xywh for ByteTrack
            x1 = boxes_xyxy[:, 0]
            y1 = boxes_xyxy[:, 1]
            x2 = boxes_xyxy[:, 2]
            y2 = boxes_xyxy[:, 3]
            w = x2 - x1
            h = y2 - y1
            cx = x1 + w / 2
            cy = y1 + h / 2
            xywh = np.stack([cx, cy, w, h], axis=1).astype(np.float32)

            class _BoxesLike:
                def __init__(self, xywh_arr, conf_arr, cls_arr):
                    self.xywh = xywh_arr
                    self.conf = conf_arr
                    self.cls = cls_arr

                def __len__(self):
                    return len(self.conf)

                def __getitem__(self, idx):
                    return _BoxesLike(self.xywh[idx], self.conf[idx], self.cls[idx])

            filtered = _BoxesLike(xywh, scores, classes)

            if self._tracker is None:
                self._init_tracker()

            tracks = self._tracker.update(filtered, img=frame, feats=None)
            detections = []
            for t in tracks:
                x1, y1, x2, y2, tid, score, cls_id, _idx = t.tolist()
                w = x2 - x1
                h = y2 - y1
                if w <= 1 or h <= 1:
                    continue
                cx = x1 + w / 2
                cy = y1 + h / 2
                if not (np.isfinite(cx) and np.isfinite(cy)):
                    continue
                detections.append({
                    "id": int(tid),
                    "label": int(cls_id),
                    "conf": float(score),
                    "center": (float(cx), float(cy)),
                    "bbox_wh": (float(w), float(h)),
                })
            return raw_results, detections

        if self._use_ocsort:
            results = self.yolo_model.predict(
                frame,
                verbose=False,
                conf=self.conf,
                iou=0.25,
                max_det=5000,
                device=self.device,
                imgsz=settings.DETECTION_IMGSZ,
            )
            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                raw_results = {
                    "boxes_xyxy": np.empty((0, 4), dtype=np.float32),
                    "scores": np.empty((0,), dtype=np.float32),
                    "classes": np.empty((0,), dtype=np.int32),
                }
                return raw_results, []

            boxes_xyxy = result.boxes.xyxy.cpu().numpy().astype(np.float32)
            scores = result.boxes.conf.cpu().numpy().astype(np.float32)
            classes = result.boxes.cls.cpu().numpy().astype(np.int32)
            raw_results = {
                "boxes_xyxy": boxes_xyxy,
                "scores": scores,
                "classes": classes,
            }
            tracks = self._update_ocsort(boxes_xyxy, scores, classes, frame.shape)
            detections = self._tracks_to_detections(tracks, boxes_xyxy, classes, scores)
            return raw_results, detections

        # Default Ultralytics tracking for PyTorch model
        results = self.yolo_model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf,
            iou=0.25,        # NMS IoU threshold (default 0.7 loại quá nhiều bbox gần nhau)
            max_det=5000,     # Tối đa 300 detections/frame
            device=self.device,
            tracker="bytetrack.yaml",
            imgsz=settings.DETECTION_IMGSZ,
        )

        return results, parse_tracking_results(results)

    def reset_tracker(self):
        """Reset tracker hoàn toàn khi chuyển video mới.

        Xóa toàn bộ tracker state (bao gồm ID counter) để bắt đầu sạch.
        Gọi khi: dừng video → chọn video mới → bấm Bắt đầu.
        """
        if self._use_ocsort:
            self._tracker = self._init_ocsort()
            self._tracker_frame_id = 0
            return

        if self._is_openvino:
            if self._tracker:
                self._tracker.reset()
            self._tracker_frame_id = 0
            return

        if not (hasattr(self.yolo_model, 'predictor') and self.yolo_model.predictor):
            return

        predictor = self.yolo_model.predictor

        # Xóa tracker instances → ultralytics tạo mới hoàn toàn
        if hasattr(predictor, 'trackers'):
            delattr(predictor, 'trackers')

        # Reset ID counter về 0 → video mới bắt đầu từ ID 1
        try:
            from ultralytics.trackers.basetrack import BaseTrack
            BaseTrack._count = 0
        except ImportError:
            pass

        print("[Detector] Tracker reset hoàn tất (ID counter = 0)")
