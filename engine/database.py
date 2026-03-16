"""
EarthOne — SQLite Database
Handles analytics tracking and email subscriber storage.
Lightweight, zero-dependency (uses stdlib sqlite3).
"""

import sqlite3
import threading
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "earthone.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Thread-safe connection getter."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            path TEXT DEFAULT '',
            meta TEXT DEFAULT '',
            ip TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'homepage',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_analytics_event ON analytics(event);
        CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics(created_at);
        CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def track_event(event: str, path: str = "", meta: str = "", ip: str = ""):
    """Record an analytics event."""
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO analytics (event, path, meta, ip) VALUES (?, ?, ?, ?)",
            (event, path, meta, ip),
        )
        conn.commit()
    except Exception:
        pass  # Never crash the app for analytics


def get_analytics_summary() -> dict:
    """Get a summary of analytics data."""
    conn = _get_conn()
    today = datetime.now().strftime("%Y-%m-%d")

    total_views = conn.execute("SELECT COUNT(*) FROM analytics WHERE event='page_view'").fetchone()[0]
    today_views = conn.execute(
        "SELECT COUNT(*) FROM analytics WHERE event='page_view' AND created_at >= ?",
        (today,)
    ).fetchone()[0]
    total_shares = conn.execute("SELECT COUNT(*) FROM analytics WHERE event='share_click'").fetchone()[0]
    total_api = conn.execute("SELECT COUNT(*) FROM analytics WHERE event='api_call'").fetchone()[0]
    total_subs = conn.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]

    # Daily views for the last 30 days
    daily = conn.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM analytics WHERE event='page_view'
        GROUP BY DATE(created_at)
        ORDER BY day DESC LIMIT 30
    """).fetchall()

    return {
        "total_views": total_views,
        "today_views": today_views,
        "total_shares": total_shares,
        "total_api_calls": total_api,
        "total_subscribers": total_subs,
        "daily_views": [{"date": r["day"], "count": r["cnt"]} for r in daily],
    }


# ---------------------------------------------------------------------------
# Email subscribers
# ---------------------------------------------------------------------------

def add_subscriber(email: str, source: str = "homepage") -> dict:
    """Add an email subscriber. Returns status."""
    email = email.strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "error": "Invalid email address"}

    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO subscribers (email, source) VALUES (?, ?)",
            (email, source),
        )
        conn.commit()
        return {"ok": True, "message": "Subscribed successfully"}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "Already subscribed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_subscribers() -> list[dict]:
    """Get all subscribers."""
    conn = _get_conn()
    rows = conn.execute("SELECT email, source, created_at FROM subscribers ORDER BY created_at DESC").fetchall()
    return [{"email": r["email"], "source": r["source"], "created_at": r["created_at"]} for r in rows]
