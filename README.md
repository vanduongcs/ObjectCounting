# ObjectCounting

Ứng dụng desktop kiểm đếm đối tượng qua vạch ảo, sử dụng YOLO + OpenVINO.
Đồ án tốt nghiệp.

## Yêu cầu

- Python 3.10+
- Windows / Linux

## Cài đặt

```bash
pip install -r requirements.txt
```

## Sử dụng

```bash
python -m src.main
```

Hoặc chạy file `run.bat` (Windows).

### Các bước sử dụng:

1. **Chọn video** hoặc **Kết nối camera** (hỗ trợ RTSP/HTTP stream)
2. **Vẽ vạch ảo** — kéo chuột trên video để vẽ đường đếm
3. **Bắt đầu** — ứng dụng sẽ detect + track + đếm đối tượng qua vạch
4. **Xuất CSV** — lưu kết quả đếm ra file

## Kiến trúc

```
ObjectCounting/
├── configs/          # Cấu hình (settings, tracker config)
├── models/           # YOLO models (OpenVINO format)
├── src/
│   ├── services/     # Logic chính (AI, Counter, Detector, FrameExtractor)
│   ├── views/        # Giao diện PyQt6
│   └── utils/        # Helpers (draw, export, Qt adapter)
├── tests/            # Unit tests
└── requirements.txt
```

## Công nghệ

- **YOLO** (Ultralytics) — Object Detection + Segmentation
- **OpenVINO** — Tối ưu inference cho Intel CPU/iGPU
- **ByteTrack** — Multi-object tracking
- **PyQt6** — Giao diện desktop
- **OpenCV** — Xử lý video/ảnh
