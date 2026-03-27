"""Timestamp OCR helpers and post-processing for video sessions."""

import os
import re
import shutil
import threading
from datetime import datetime, timedelta

import cv2

import configs.settings as settings

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import easyocr
except Exception:
    easyocr = None


class TimestampOCRService:
    """Encapsulate OCR readiness, crop storage, and timestamp normalization."""

    _easyocr_reader = None
    _easyocr_ready = False
    _easyocr_init_attempted = False
    _easyocr_init_lock = threading.Lock()

    def __init__(self):
        self.ready = self._init_tesseract()
        self._ensure_easyocr_reader()
        self.ready = self.ready or self._easyocr_ready

    def can_process_video(self, is_live=False):
        return (
            not is_live
            and settings.TIMESTAMP_SPACE_ENABLED
            and settings.TIMESTAMP_OCR_ENABLED
            and self.ready
        )

    def prepare_session_dir(self, is_live, video_name):
        if not self.can_process_video(is_live=is_live):
            return None
        try:
            settings.TIMESTAMP_SPACE_SESSION_ROOT.mkdir(parents=True, exist_ok=True)
            safe_name = self._safe_video_name(video_name)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            session_dir = settings.TIMESTAMP_SPACE_SESSION_ROOT / f"{safe_name}_{stamp}"
            session_dir.mkdir(parents=True, exist_ok=True)
            return session_dir
        except Exception:
            return None

    @staticmethod
    def cleanup_session_dir(session_dir):
        if session_dir is None:
            return
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def safe_delete_file(path):
        if not path:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def save_crop(self, roi, session_dir, video_name, frame_index):
        """Save one timestamp crop and return its path."""
        try:
            if roi is None or roi.size == 0:
                return ""
            target_dir = session_dir or settings.TIMESTAMP_SPACE_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            safe_name = self._safe_video_name(video_name)
            file_name = f"{safe_name}_{frame_index:08d}.jpg"
            path = target_dir / file_name
            cv2.imwrite(
                str(path),
                roi,
                [cv2.IMWRITE_JPEG_QUALITY, settings.CACHE_IMAGE_QUALITY],
            )
            return str(path)
        except Exception:
            return ""

    def normalize_event_log(self, event_log, fps):
        normalized = [dict(event) for event in (event_log or [])]
        for event in normalized:
            timestamp = event.get("timestamp", "")
            event.pop("_timestamp_path", None)
            if not isinstance(timestamp, str):
                event["timestamp"] = ""
                continue
            frame_index = self._extract_frame_index(timestamp)
            if frame_index is not None:
                event["timestamp"] = self._frame_index_to_video_time(frame_index, fps)
        return normalized

    @classmethod
    def first_valid_event_timestamp(cls, event_log):
        """Return the first event timestamp that can be parsed as a full datetime."""
        for event in event_log or []:
            if not isinstance(event, dict):
                continue
            parsed_dt = cls._parse_timestamp_datetime(event.get("timestamp", ""))
            if parsed_dt is not None:
                return parsed_dt
        return None

    @staticmethod
    def build_output_file_name(parsed_dt, extension):
        """Format an output filename from a parsed datetime and extension."""
        if parsed_dt is None:
            return ""
        ext = str(extension or "").strip().lstrip(".") or "mp4"
        return parsed_dt.strftime(
            f"%H giờ %M phút_ngày %d tháng %m năm %Y.{ext}"
        )

    @classmethod
    def build_output_file_name_from_events(cls, event_log, extension):
        """Return a formatted output filename using the first valid event timestamp."""
        parsed_dt = cls.first_valid_event_timestamp(event_log)
        return cls.build_output_file_name(parsed_dt, extension)

    @classmethod
    def build_output_video_name(cls, parsed_dt):
        """Format the output MP4 filename from a parsed datetime."""
        return cls.build_output_file_name(parsed_dt, "mp4")

    def finalize_event_log(self, event_log, fps):
        """Resolve OCR crops, infer missing timestamps, then normalize output."""
        if not settings.TIMESTAMP_OCR_ENABLED:
            return self.normalize_event_log(event_log, fps)
        if not self.ready:
            print("[Timestamp OCR] OCR chưa sẵn sàng, bỏ qua OCR.")
            return self.normalize_event_log(event_log, fps)

        finalized = [dict(event) for event in (event_log or [])]
        anchors = []
        records = []

        for event in finalized:
            timestamp = event.get("timestamp", "")
            source_path = event.get("_timestamp_path", "") or (
                timestamp
                if isinstance(timestamp, str)
                and self._extract_frame_index(timestamp) is not None
                else ""
            )
            frame_index = self._extract_frame_index(source_path) if source_path else None
            parsed_dt = self._parse_timestamp_datetime(timestamp) if isinstance(timestamp, str) else None

            if source_path and os.path.exists(source_path) and parsed_dt is None:
                text = self.ocr_image(source_path)
                if text:
                    event["timestamp"] = text
                    print(f"[Timestamp OCR] {source_path} -> {text}")
                    parsed_dt = self._parse_timestamp_datetime(text)
                    if parsed_dt is not None and frame_index is not None:
                        anchors.append((frame_index, parsed_dt))
                    event.pop("_timestamp_path", None)
                else:
                    print(f"[Timestamp OCR] {source_path} -> (fail)")
                self.safe_delete_file(source_path)
            elif parsed_dt is not None and frame_index is not None:
                anchors.append((frame_index, parsed_dt))

            records.append((event, source_path or timestamp, frame_index, parsed_dt))

        if anchors and fps > 0:
            base_frame, base_dt = self._choose_reference_anchor(anchors, fps)
            if base_frame is not None:
                for event, original_ts, frame_index, parsed_dt in records:
                    if frame_index is None:
                        continue
                    inferred_dt = base_dt + timedelta(seconds=(frame_index - base_frame) / fps)
                    inferred = inferred_dt.strftime("%d-%m-%Y %H:%M:%S")

                    if parsed_dt is None:
                        event["timestamp"] = inferred
                        print(f"[Timestamp OCR] {original_ts} -> {inferred} (inferred)")
                        continue

                    drift = abs((parsed_dt - inferred_dt).total_seconds())
                    if drift > 2.0:
                        event["timestamp"] = inferred
                        print(f"[Timestamp OCR] {original_ts} -> {inferred} (corrected)")

        return self.normalize_event_log(finalized, fps)

    def ocr_image(self, image_path):
        """OCR one timestamp crop and return a normalized datetime string."""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return ""

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            gray4 = cv2.resize(gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
            gray6 = cv2.resize(gray, None, fx=6.0, fy=6.0, interpolation=cv2.INTER_CUBIC)
            clahe4 = cv2.resize(clahe, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
            clahe6 = cv2.resize(clahe, None, fx=6.0, fy=6.0, interpolation=cv2.INTER_CUBIC)
            gauss6 = cv2.GaussianBlur(gray6, (3, 3), 0)
            gauss_clahe6 = cv2.GaussianBlur(clahe6, (3, 3), 0)
            _, otsu6 = cv2.threshold(gauss_clahe6, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            _, otsu6_inv = cv2.threshold(gauss_clahe6, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            tophat6 = cv2.morphologyEx(gray6, cv2.MORPH_TOPHAT, morph_kernel)
            blackhat6 = cv2.morphologyEx(gray6, cv2.MORPH_BLACKHAT, morph_kernel)

            texts = []
            seen = set()

            for text in self._easyocr_timestamp_candidates(image):
                if text and text not in seen:
                    texts.append(text)
                    seen.add(text)

            parsed = self._majority_parsed_timestamp(texts)
            if parsed:
                return parsed

            if pytesseract is not None:
                for variant, config in [
                    (gray4, "--oem 1 --psm 7"),
                    (gauss6, "--oem 1 --psm 7"),
                    (clahe4, "--oem 1 --psm 7"),
                    (255 - gray4, "--oem 1 --psm 7"),
                    (255 - clahe4, "--oem 1 --psm 7"),
                    (255 - blackhat6, "--oem 1 --psm 7"),
                    (tophat6, "--oem 1 --psm 7"),
                    (otsu6, "--oem 1 --psm 7"),
                    (otsu6_inv, "--oem 1 --psm 7"),
                    (gray6, "--oem 1 --psm 13"),
                    (
                        gray4,
                        f"--oem 1 --psm 7 -c tessedit_char_whitelist={settings.TIMESTAMP_OCR_WHITELIST}",
                    ),
                ]:
                    text = self._run_tesseract(variant, config)
                    if text and text not in seen:
                        texts.append(text)
                        seen.add(text)

            return self._majority_parsed_timestamp(texts)
        except Exception:
            return ""

    def _init_tesseract(self):
        if pytesseract is None:
            return False
        tesseract_cmd = getattr(settings, "TESSERACT_CMD", "") or ""
        if tesseract_cmd:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                return True
            except Exception:
                return False

        default_path = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        if os.path.exists(default_path):
            try:
                pytesseract.pytesseract.tesseract_cmd = default_path
            except Exception:
                return False
        return True

    @classmethod
    def _ensure_easyocr_reader(cls):
        if cls._easyocr_ready:
            return True
        if cls._easyocr_init_attempted or easyocr is None:
            return cls._easyocr_ready
        with cls._easyocr_init_lock:
            if cls._easyocr_ready:
                return True
            if cls._easyocr_init_attempted:
                return cls._easyocr_ready
            cls._easyocr_init_attempted = True
            try:
                cls._easyocr_reader = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    verbose=False,
                    download_enabled=False,
                )
                cls._easyocr_ready = True
            except Exception:
                cls._easyocr_reader = None
                cls._easyocr_ready = False
        return cls._easyocr_ready

    @classmethod
    def _easyocr_timestamp_candidates(cls, image):
        if image is None or not cls._ensure_easyocr_reader() or cls._easyocr_reader is None:
            return []

        texts = []
        seen = set()
        for variant in (image, 255 - image):
            try:
                result = cls._easyocr_reader.readtext(variant, detail=0, paragraph=False)
            except Exception:
                continue
            if not result:
                continue
            merged = " ".join(str(part).strip() for part in result if str(part).strip())
            merged = re.sub(r"\s+", " ", merged).strip()
            if merged and merged not in seen:
                texts.append(merged)
                seen.add(merged)
        return texts

    @staticmethod
    def _run_tesseract(image, config):
        text = pytesseract.image_to_string(
            image,
            lang=settings.TIMESTAMP_OCR_LANG,
            config=config,
        )
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _majority_parsed_timestamp(cls, texts):
        parsed_hits = [cls._parse_timestamp_text(text) for text in texts]
        parsed_hits = [value for value in parsed_hits if value]
        if not parsed_hits:
            return ""

        counts = {}
        first_index = {}
        for index, value in enumerate(parsed_hits):
            counts[value] = counts.get(value, 0) + 1
            first_index.setdefault(value, index)
        return max(counts, key=lambda value: (counts[value], -first_index[value]))

    @staticmethod
    def _safe_video_name(video_name):
        return "".join(
            char if char.isalnum() or char in "-_." else "_"
            for char in str(video_name or "video")
        )

    @staticmethod
    def _frame_index_to_video_time(frame_index, fps):
        if frame_index is None or fps <= 0:
            return ""
        total_seconds = int(frame_index / fps)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _parse_timestamp_text(text):
        normalized = TimestampOCRService._normalize_ocr_scan_text(text)
        if not normalized:
            return ""
        date_parts = TimestampOCRService._extract_date_parts(normalized)
        if date_parts is None:
            return ""
        day, month, year, end_index = date_parts
        time_parts = TimestampOCRService._extract_time_parts(normalized[end_index:])
        if time_parts is None:
            return ""
        hour, minute, second = time_parts
        return f"{day:02d}-{month:02d}-{year:04d} {hour:02d}:{minute:02d}:{second:02d}"

    @staticmethod
    def _normalize_ocr_scan_text(text):
        normalized = (text or "").upper()
        for src, dst in {
            "\u2010": "-",
            "\u2011": "-",
            "\u2012": "-",
            "\u2013": "-",
            "\u2014": "-",
            "\u2212": "-",
            "_": "-",
            ",": ".",
        }.items():
            normalized = normalized.replace(src, dst)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _normalize_ocr_token(token):
        mapped = (token or "").upper().translate(str.maketrans({
            "O": "0",
            "Q": "0",
            "D": "0",
            "I": "1",
            "L": "1",
            "|": "1",
            "!": "1",
            "Z": "2",
            "B": "8",
            "G": "6",
            "?": "7",
        }))
        return re.sub(r"[^0-9]", "", mapped)

    @classmethod
    def _pick_token_value(cls, token, min_value, max_value):
        digits = cls._normalize_ocr_token(token)
        if not digits:
            return None
        candidates = []
        if len(digits) >= 2:
            candidates.extend([digits[:2], digits[-2:]])
        candidates.extend([digits[:1], digits[-1:]])
        seen = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            value = int(candidate)
            if min_value <= value <= max_value:
                return value
        return None

    @classmethod
    def _pick_year_value(cls, token):
        digits = cls._normalize_ocr_token(token)
        if len(digits) < 4:
            return None
        for index in range(0, len(digits) - 3):
            value = int(digits[index:index + 4])
            if 2000 <= value <= 2099:
                return value
        for candidate in (digits[-4:], digits[:4]):
            value = int(candidate)
            if 2000 <= value <= 2099:
                return value
        return None

    @classmethod
    def _extract_date_parts(cls, text):
        head = (text or "")[:24]
        for pattern in [
            r"([0-9A-Z?|]{1,3})\s*[-/ .]+\s*([0-9A-Z?|]{1,3})\s*[-/ .]+\s*([0-9A-Z?|]{4,6})",
            r"([0-9A-Z?|]{2})([0-9A-Z?|]{2})([0-9A-Z?|]{4})",
        ]:
            for match in re.finditer(pattern, head):
                day = cls._pick_token_value(match.group(1), 1, 31)
                month = cls._pick_token_value(match.group(2), 1, 12)
                year = cls._pick_year_value(match.group(3))
                if day is None or month is None or year is None:
                    continue
                return day, month, year, match.end()
        return None

    @classmethod
    def _extract_time_parts(cls, text):
        tail = (text or "")[-20:]
        for pattern in [
            r"([0-9A-Z?|]{1,4})\s*[:;.,-]+\s*([0-9A-Z?|]{1,4})\s*[:;.,-]+\s*([0-9A-Z?|]{1,4})",
            r"([0-9A-Z?|]{1,2})\s+([0-9A-Z?|]{2})\s*[:;.,-]+\s*([0-9A-Z?|]{2})",
        ]:
            matches = list(re.finditer(pattern, tail))
            for match in reversed(matches):
                if any(len(cls._normalize_ocr_token(match.group(index))) < 2 for index in (1, 2, 3)):
                    continue
                hour = cls._pick_token_value(match.group(1), 0, 23)
                minute = cls._pick_token_value(match.group(2), 0, 59)
                second = cls._pick_token_value(match.group(3), 0, 59)
                if hour is not None and minute is not None and second is not None:
                    return hour, minute, second

        tokens = [
            cls._normalize_ocr_token(token)
            for token in re.findall(r"[0-9A-Z?|]{1,8}", tail)
        ]
        tokens = [token for token in tokens if token]
        for index in range(len(tokens) - 1, -1, -1):
            chunk = tokens[index:index + 3]
            if len(chunk) >= 3:
                if len(chunk[0]) < 2 or len(chunk[1]) < 2 or len(chunk[2]) < 2:
                    continue
                hour = cls._pick_token_value(chunk[0], 0, 23)
                minute = cls._pick_token_value(chunk[1], 0, 59)
                second = cls._pick_token_value(chunk[2], 0, 59)
                if hour is not None and minute is not None and second is not None:
                    return hour, minute, second
            if len(chunk) >= 2:
                hour = cls._pick_token_value(chunk[0], 0, 23)
                mmss = chunk[1][-4:]
                if hour is not None and len(mmss) == 4:
                    minute = int(mmss[:2])
                    second = int(mmss[2:])
                    if 0 <= minute <= 59 and 0 <= second <= 59:
                        return hour, minute, second
                hhmm = chunk[0][-4:]
                second_token = cls._pick_token_value(chunk[1], 0, 59)
                if len(hhmm) == 4 and second_token is not None:
                    hour = int(hhmm[:2])
                    minute = int(hhmm[2:])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        return hour, minute, second_token
        return None

    @staticmethod
    def _parse_timestamp_datetime(text):
        if not isinstance(text, str):
            return None
        try:
            return datetime.strptime(text.replace("/", "-"), "%d-%m-%Y %H:%M:%S")
        except Exception:
            return None

    @staticmethod
    def _extract_frame_index(path):
        match = re.search(r"_(\d{8})\.jpg$", os.path.basename(path or ""))
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    @staticmethod
    def _choose_reference_anchor(anchors, fps):
        if not anchors or fps <= 0:
            return None, None

        best_anchor = None
        best_score = -1
        for frame0, dt0 in anchors:
            score = 0
            for frame1, dt1 in anchors:
                expected = (frame1 - frame0) / fps
                observed = (dt1 - dt0).total_seconds()
                if abs(observed - expected) <= 2.0:
                    score += 1
            if score > best_score:
                best_score = score
                best_anchor = (frame0, dt0)
        return best_anchor or anchors[0]
