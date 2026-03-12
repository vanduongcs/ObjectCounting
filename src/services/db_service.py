"""
Database Service: Quản lý SQLite lưu lịch sử xử lý video.

Ai gọi module này?
    - main.py gọi init_db() khi khởi động
    - AIService gọi save_session() khi xử lý xong video
    - HistoryPanel gọi get_all_sessions() để hiển thị danh sách

Schema:
    sessions: id, video_name, output_path, count_nhap (JSON), count_xuat (JSON),
              duration_sec, created_at
"""

import json
import sqlite3
from datetime import datetime

import configs.settings as settings


def init_db():
    """Tạo database và table (clear dữ liệu cũ)."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.DB_PATH))
    # Clear all old data and recreate schema
    conn.execute("DROP TABLE IF EXISTS sessions")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_name TEXT NOT NULL,
            output_path TEXT,
            count_nhap TEXT DEFAULT '{}',
            count_xuat TEXT DEFAULT '{}',
            event_log TEXT DEFAULT '[]',
            duration_sec REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Database ready: {settings.DB_PATH}")


def save_session(video_name, output_path, count_nhap, count_xuat, duration_sec=0, event_log=None):
    """
    Lưu 1 session xử lý vào database.

    Args:
        video_name: Tên file video gốc.
        output_path: Đường dẫn video output đã annotate.
        count_nhap: dict {label: count}
        count_xuat: dict {label: count}
        duration_sec: Thời gian xử lý (giây).
    """
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.execute(
        """INSERT INTO sessions (video_name, output_path, count_nhap, count_xuat, event_log, duration_sec)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            video_name,
            str(output_path) if output_path else "",
            json.dumps(count_nhap, ensure_ascii=False),
            json.dumps(count_xuat, ensure_ascii=False),
            json.dumps(event_log or [], ensure_ascii=False),
            duration_sec,
        ),
    )
    conn.commit()
    conn.close()
    print(f"[DB] Session saved: {video_name}")


def get_all_sessions():
    """
    Lấy tất cả sessions, mới nhất trước.

    Returns:
        list[dict] với keys: id, video_name, output_path, count_nhap, count_xuat,
                             duration_sec, created_at, event_log
    """
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "video_name": row["video_name"],
            "output_path": row["output_path"],
            "count_nhap": json.loads(row["count_nhap"]) if row["count_nhap"] else {},
            "count_xuat": json.loads(row["count_xuat"]) if row["count_xuat"] else {},
            "duration_sec": row["duration_sec"],
            "created_at": row["created_at"],
            "event_log": json.loads(row["event_log"]) if row["event_log"] else [],
        })
    return results


def delete_session(session_id):
    """Xóa 1 session theo ID."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
