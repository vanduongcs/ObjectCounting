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


def _loads_json_or_default(raw_value, default):
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _ensure_schema(conn):
    """Ensure sessions table exists and has required columns without deleting data."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()
    if row is None:
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
        return

    existing = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    required = {
        "video_name": "TEXT DEFAULT ''",
        "output_path": "TEXT DEFAULT ''",
        "count_nhap": "TEXT DEFAULT '{}'",
        "count_xuat": "TEXT DEFAULT '{}'",
        "event_log": "TEXT DEFAULT '[]'",
        "duration_sec": "REAL DEFAULT 0",
        "created_at": "TEXT DEFAULT ''",
    }
    for col, ddl in required.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {ddl}")


def init_db():
    """Tao database va table (khong xoa lich su cu)."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(settings.DB_PATH))
    _ensure_schema(conn)
    conn.commit()
    conn.close()
    print(f"[DB] Database ready: {settings.DB_PATH}")


def save_session(video_name, output_path, count_nhap, count_xuat, duration_sec=0, event_log=None):
    """Luu 1 session xu ly vao database."""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(str(settings.DB_PATH))
    cur = conn.execute(
        """INSERT INTO sessions
           (video_name, output_path, count_nhap, count_xuat, event_log, duration_sec, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            video_name,
            str(output_path) if output_path else "",
            json.dumps(count_nhap, ensure_ascii=False),
            json.dumps(count_xuat, ensure_ascii=False),
            json.dumps(event_log or [], ensure_ascii=False),
            duration_sec,
            created_at,
        ),
    )
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    print(f"[DB] Session saved: {video_name}")
    return session_id


def update_session_event_log(session_id, event_log):
    """Cap nhat event_log cho 1 session da luu."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.execute(
        "UPDATE sessions SET event_log = ? WHERE id = ?",
        (json.dumps(event_log or [], ensure_ascii=False), session_id),
    )
    conn.commit()
    conn.close()


def update_session_output_path(session_id, output_path):
    """Cap nhat output_path cho 1 session da luu."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.execute(
        "UPDATE sessions SET output_path = ? WHERE id = ?",
        (str(output_path) if output_path else "", session_id),
    )
    conn.commit()
    conn.close()


def get_all_sessions():
    """Lay tat ca sessions, moi nhat truoc."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    results = []
    for row in rows:
        created_at = row["created_at"] if "created_at" in row.keys() else ""
        results.append({
            "id": row["id"],
            "video_name": row["video_name"],
            "output_path": row["output_path"],
            "count_nhap": _loads_json_or_default(row["count_nhap"], {}),
            "count_xuat": _loads_json_or_default(row["count_xuat"], {}),
            "duration_sec": row["duration_sec"],
            "created_at": created_at,
            "event_log": _loads_json_or_default(row["event_log"], []),
        })
    return results


def delete_session(session_id):
    """Xóa 1 session theo ID."""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
