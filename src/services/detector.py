"""Object detector wrapper for YOLO + OpenVINO backends."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from openvino import Core
from ultralytics import YOLO
from ultralytics.trackers.byte_tracker import BYTETracker
import yaml

import configs.settings_interface as ui_settings
import configs.settings_theme as theme_settings
from src.utils.result_parser import parse_tracking_results
import configs.settings as settings


class _TrackerBoxes:
    """Minimal adapter so BYTETracker can consume OpenVINO detections."""

    def __init__(self, xywh, conf, cls):
        self.xywh = xywh
        self.conf = conf
        self.cls = cls

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, idx):
        return _TrackerBoxes(self.xywh[idx], self.conf[idx], self.cls[idx])


def _empty_openvino_predictions():
    return (
        np.empty((0, 4), dtype=np.float32),
        np.empty((0,), dtype=np.float32),
        np.empty((0,), dtype=np.int32),
    )


def _select_best_openvino_device() -> str:
    """Prefer Intel iGPU, then CPU, then AUTO."""
    try:
        available = Core().available_devices
        print(f"[OpenVINO] Thiet bi kha dung: {available}")

        if any(d.startswith("GPU") for d in available):
            print("[OpenVINO] Su dung Intel iGPU")
            return "GPU"

        print("[OpenVINO] Su dung CPU")
        return "CPU"
    except Exception as e:
        print(f"[OpenVINO] Khong the kiem tra thiet bi, dung AUTO: {e}")
        return "AUTO"


def _select_best_torch_device() -> str:
    """Prefer CUDA for `.pt` models when available."""
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
        if not self._is_openvino:
            self._tracker = None
            return
        args = self._load_tracker_args()
        self._tracker = BYTETracker(args, frame_rate=int(round(self._tracker_fps)))
        self._tracker_frame_id = 0

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
        try:
            path = Path(model_path)
        except TypeError:
            return model_path
        return str(path)

    @staticmethod
    def _boxes_xyxy_to_xywh(boxes_xyxy):
        x1 = boxes_xyxy[:, 0]
        y1 = boxes_xyxy[:, 1]
        x2 = boxes_xyxy[:, 2]
        y2 = boxes_xyxy[:, 3]
        width = x2 - x1
        height = y2 - y1
        center_x = x1 + width / 2
        center_y = y1 + height / 2
        return np.stack([center_x, center_y, width, height], axis=1).astype(np.float32)

    def _warmup_openvino(self):
        print(f"[OpenVINO] Warming up tren {self.device}...")
        h, w = self._ov_input_hw
        dummy = np.zeros((1, 3, h, w), dtype=np.float32)
        _ = self._ov_compiled([dummy])[self._ov_output_layer]
        print("[OpenVINO] Warmup hoan tat.")

    def _warmup_torch(self):
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        print(f"[Torch] Warming up tren {self.device}...")
        try:
            self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
            print("[Torch] Warmup hoan tat.")
        except Exception as e:
            print(f"[Torch] Warmup {self.device} that bai: {e}, chuyen sang CPU...")
            self.device = "cpu"
            try:
                self.yolo_model.predict(dummy, device=self.device, verbose=False, conf=self.conf)
                print("[Torch] Warmup CPU hoan tat.")
            except Exception as e2:
                print(f"[Torch] Warmup CPU cung that bai (bo qua): {e2}")

    @staticmethod
    def _letterbox(img, new_shape, color=(114, 114, 114)):
        shape = img.shape[:2]
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        new_unpad = (int(round(shape[1] * r)), int(round(shape[0] * r)))
        dw = (new_shape[1] - new_unpad[0]) / 2
        dh = (new_shape[0] - new_unpad[1]) / 2

        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
        img = cv2.copyMakeBorder(
            img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color
        )
        return img, r, (dw, dh)

    def _get_class_color(self, cls_id: int) -> tuple[int, int, int]:
        if cls_id in self._class_color_cache:
            return self._class_color_cache[cls_id]
        palette = theme_settings.CLASS_COLOR_PALETTE
        color = palette[int(cls_id) % len(palette)]
        self._class_color_cache[cls_id] = color
        return color

    @staticmethod
    def _frame_dims(frame_shape) -> tuple[int, int]:
        if len(frame_shape) >= 2:
            return int(frame_shape[1]), int(frame_shape[0])
        return 640, 480

    def _use_compact_overlay(self, frame_shape) -> bool:
        frame_w, frame_h = self._frame_dims(frame_shape)
        return frame_w <= 640 or frame_h <= 480

    def _get_text_scale(self, frame_shape) -> float:
        frame_w, _frame_h = self._frame_dims(frame_shape)
        if self._use_compact_overlay(frame_shape):
            return ui_settings.OVERLAY_LABEL_FONT_SCALE_COMPACT
        if frame_w <= 960:
            return ui_settings.OVERLAY_LABEL_FONT_SCALE_SMALL
        if frame_w <= 1280:
            return ui_settings.OVERLAY_LABEL_FONT_SCALE_MEDIUM
        return ui_settings.OVERLAY_LABEL_FONT_SCALE_LARGE

    def _get_ui_scale(self, frame_shape) -> float:
        h = frame_shape[0] if len(frame_shape) >= 2 else 480
        w = frame_shape[1] if len(frame_shape) >= 2 else 640
        target_w = getattr(ui_settings, "UI_TARGET_WIDTH", 800)
        target_h = getattr(ui_settings, "UI_TARGET_HEIGHT", 600)
        return min(target_w / w, target_h / h)

    def _get_overlay_line_thickness(self, frame_shape) -> int:
        frame_w, _frame_h = self._frame_dims(frame_shape)
        if frame_w <= 960:
            return ui_settings.OVERLAY_BOX_THICKNESS_SMALL
        return ui_settings.OVERLAY_BOX_THICKNESS_LARGE

    @staticmethod
    def _to_numpy_array(value, dtype=None):
        if value is None:
            return np.empty((0,), dtype=dtype or np.float32)
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        arr = np.asarray(value)
        if dtype is not None:
            arr = arr.astype(dtype, copy=False)
        return arr

    def _format_detection_label(self, name, score, show_conf=True) -> str:
        if show_conf:
            return f"{name} {score:.1f}"
        return name

    def _iter_openvino_predictions(self, raw_results):
        boxes = raw_results.get("boxes_xyxy", [])
        scores = raw_results.get("scores", [])
        classes = raw_results.get("classes", [])
        for (x1, y1, x2, y2), score, cls_id in zip(boxes, scores, classes):
            yield float(x1), float(y1), float(x2), float(y2), float(score), int(cls_id)

    def _iter_ultralytics_predictions(self, raw_results):
        if not raw_results:
            return
        result = raw_results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return

        xyxy = self._to_numpy_array(getattr(boxes, "xyxy", None), dtype=np.float32)
        confs = self._to_numpy_array(getattr(boxes, "conf", None), dtype=np.float32)
        classes = self._to_numpy_array(getattr(boxes, "cls", None), dtype=np.int32)
        count = min(len(xyxy), len(confs), len(classes))
        for idx in range(count):
            x1, y1, x2, y2 = xyxy[idx][:4]
            yield float(x1), float(y1), float(x2), float(y2), float(confs[idx]), int(classes[idx])

    def _draw_prediction_rows(self, frame, rows, show_conf=True):
        font_scale = self._get_text_scale(frame.shape)
        compact = self._use_compact_overlay(frame.shape)
        font_thickness = ui_settings.OVERLAY_FONT_THICKNESS
        box_thickness = self._get_overlay_line_thickness(frame.shape)
        label_pad_x = (
            ui_settings.OVERLAY_LABEL_PAD_X_COMPACT
            if compact
            else ui_settings.OVERLAY_LABEL_PAD_X_DEFAULT
        )
        label_pad_y = (
            ui_settings.OVERLAY_LABEL_PAD_Y_COMPACT
            if compact
            else ui_settings.OVERLAY_LABEL_PAD_Y_DEFAULT
        )
        frame_h, frame_w = frame.shape[:2]

        for x1, y1, x2, y2, score, cls_id in rows:
            p1 = (int(round(x1)), int(round(y1)))
            p2 = (int(round(x2)), int(round(y2)))
            p1 = (
                max(0, min(frame_w - 1, p1[0])),
                max(0, min(frame_h - 1, p1[1])),
            )
            p2 = (
                max(0, min(frame_w - 1, p2[0])),
                max(0, min(frame_h - 1, p2[1])),
            )
            color = self._get_class_color(int(cls_id))
            cv2.rectangle(frame, p1, p2, color, box_thickness)

            name = self.names.get(int(cls_id), str(int(cls_id)))
            label = self._format_detection_label(name, float(score), show_conf=show_conf)
            (text_w, text_h), baseline = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                font_thickness,
            )
            label_left = p1[0]
            label_top = max(0, p1[1] - text_h - baseline - (label_pad_y * 2))
            label_bottom = min(frame_h - 1, label_top + text_h + baseline + (label_pad_y * 2))
            label_right = min(frame_w - 1, label_left + text_w + (label_pad_x * 2))
            cv2.rectangle(
                frame,
                (label_left, label_top),
                (label_right, label_bottom),
                color,
                -1,
            )
            text_y = min(frame_h - 1, label_bottom - baseline - label_pad_y)
            cv2.putText(
                frame,
                label,
                (label_left + label_pad_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                theme_settings.DETECTION_LABEL_TEXT_COLOR,
                font_thickness,
                cv2.LINE_AA,
            )
        return frame

    def _ov_predict(self, frame):
        h_in, w_in = self._ov_input_hw
        img, r, (dw, dh) = self._letterbox(frame, (h_in, w_in))
        img = img[:, :, ::-1]
        img = img.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        img = np.ascontiguousarray(img)

        output = self._ov_compiled([img])[self._ov_output_layer]
        output = output[0]
        if output.size == 0:
            return _empty_openvino_predictions()

        scores = output[:, 4]
        mask = scores >= self.conf
        if not np.any(mask):
            return _empty_openvino_predictions()

        boxes = output[mask, :4].astype(np.float32)
        scores = scores[mask].astype(np.float32)
        classes = output[mask, 5].astype(np.int32)

        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - dw) / r
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - dh) / r

        h0, w0 = frame.shape[:2]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w0 - 1)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h0 - 1)

        box_w = boxes[:, 2] - boxes[:, 0]
        box_h = boxes[:, 3] - boxes[:, 1]
        valid = (box_w > 1) & (box_h > 1) & np.isfinite(boxes).all(axis=1) & np.isfinite(scores)
        if not np.any(valid):
            return _empty_openvino_predictions()

        return boxes[valid], scores[valid], classes[valid]

    def has_detections(self, raw_results) -> bool:
        if isinstance(raw_results, dict):
            boxes = raw_results.get("boxes_xyxy")
            return boxes is not None and len(boxes) > 0
        if not raw_results:
            return False
        result = raw_results[0]
        boxes = getattr(result, "boxes", None)
        return boxes is not None and len(boxes) > 0

    def _render_openvino_predictions(self, frame, raw_results, show_conf=True):
        return self._draw_prediction_rows(
            frame,
            self._iter_openvino_predictions(raw_results),
            show_conf=show_conf,
        )

    def _render_ultralytics_predictions(self, frame, raw_results, show_conf=True):
        return self._draw_prediction_rows(
            frame,
            self._iter_ultralytics_predictions(raw_results),
            show_conf=show_conf,
        )

    @staticmethod
    def _tracks_to_detections(tracks):
        detections = []
        for track in tracks:
            x1, y1, x2, y2, tid, score, cls_id, _idx = track.tolist()
            width = x2 - x1
            height = y2 - y1
            if width <= 1 or height <= 1:
                continue
            center_x = x1 + width / 2
            center_y = y1 + height / 2
            if not (np.isfinite(center_x) and np.isfinite(center_y)):
                continue
            detections.append(
                {
                    "id": int(tid),
                    "label": int(cls_id),
                    "conf": float(score),
                    "center": (float(center_x), float(center_y)),
                    "bbox_wh": (float(width), float(height)),
                }
            )
        return detections

    def render(self, frame, raw_results, show_boxes=True, show_conf=True):
        if isinstance(raw_results, dict):
            if not raw_results or not show_boxes:
                return frame
            return self._render_openvino_predictions(
                frame,
                raw_results,
                show_conf=show_conf,
            )
        if not raw_results or not show_boxes:
            return frame
        return self._render_ultralytics_predictions(
            frame,
            raw_results,
            show_conf=show_conf,
        )

    def track(self, frame):
        """Run detection + tracking and return raw and parsed outputs."""
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

            filtered = _TrackerBoxes(
                self._boxes_xyxy_to_xywh(boxes_xyxy),
                scores,
                classes,
            )

            if self._tracker is None:
                self._init_tracker()

            tracks = self._tracker.update(filtered, img=frame, feats=None)
            return raw_results, self._tracks_to_detections(tracks)

        results = self.yolo_model.track(
            frame,
            persist=True,
            verbose=False,
            conf=self.conf,
            iou=0.25,
            max_det=5000,
            device=self.device,
            tracker="bytetrack.yaml",
            imgsz=settings.DETECTION_IMGSZ,
        )

        return results, parse_tracking_results(results)

    def reset_tracker(self):
        """Reset tracker state before starting a new source."""
        if self._is_openvino:
            if self._tracker:
                self._tracker.reset()
            self._tracker_frame_id = 0
            return

        if not (hasattr(self.yolo_model, "predictor") and self.yolo_model.predictor):
            return

        predictor = self.yolo_model.predictor

        if hasattr(predictor, "trackers"):
            delattr(predictor, "trackers")

        try:
            from ultralytics.trackers.basetrack import BaseTrack

            BaseTrack._count = 0
        except ImportError:
            pass

        print("[Detector] Tracker reset hoan tat (ID counter = 0)")
