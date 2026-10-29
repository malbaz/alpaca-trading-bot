"""
حالة النظام الدائمة (SQLite) — مشتركة بين كل الأجزاء وتبقى بعد إعادة التشغيل.

دورة حياة السهم:
  NONE -> PENDING_BUY -> OPEN -> PENDING_SELL -> NONE
تتغير الحالة فقط عند تأكيد Alpaca (trade_updates) وليس عند إرسال الأمر.
"""
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from config import settings

_lock = threading.RLock()

ACTIVE_STATES = ("PENDING_BUY", "OPEN", "PENDING_SELL")


def _conn():
    c = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    return c


_db = _conn()


def _ensure_column(table: str, name: str, ddl: str):
    """إضافة عمود لجدول موجود دون فقدان البيانات (ترقية آمنة)."""
    cols = [r["name"] for r in _db.execute(f"PRAGMA table_info({table})")]
    if name not in cols:
        _db.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init():
    with _lock:
        _db.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            qty REAL DEFAULT 0,
            entry_price REAL DEFAULT 0,
            target REAL DEFAULT 0,
            stop REAL DEFAULT 0,
            order_id TEXT,
            client_order_id TEXT,
            bracket INTEGER DEFAULT 0,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS trades_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, day TEXT, symbol TEXT, side TEXT,
            qty REAL, price REAL, reason TEXT
        );
        CREATE TABLE IF NOT EXISTS cooldown (
            symbol TEXT PRIMARY KEY, until REAL
        );
        """)
        # أعمدة الوقف المتحرك (تُضاف تلقائيًا للقواعد القديمة)
        _ensure_column("positions", "peak_price", "peak_price REAL DEFAULT 0")
        _ensure_column("positions", "trailing", "trailing INTEGER DEFAULT 0")
        _ensure_column("positions", "stop_order_id", "stop_order_id TEXT")
        # جني الربح الجزئي: 1 = بِيع جزء من الكمية بالفعل
        _ensure_column("positions", "partial_done", "partial_done INTEGER DEFAULT 0")
        _db.commit()


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get(symbol: str) -> Optional[Dict[str, Any]]:
    with _lock:
        r = _db.execute("SELECT * FROM positions WHERE symbol=?", (symbol.upper(),)).fetchone()
        return dict(r) if r else None


def state_of(symbol: str) -> str:
    row = get(symbol)
    return row["state"] if row else "NONE"


def upsert(symbol: str, **fields):
    symbol = symbol.upper()
    fields["updated_at"] = time.time()
    with _lock:
        if get(symbol):
            sets = ", ".join(f"{k}=?" for k in fields)
            _db.execute(f"UPDATE positions SET {sets} WHERE symbol=?", (*fields.values(), symbol))
        else:
            fields.setdefault("state", "NONE")
            cols = ", ".join(["symbol", *fields])
            qs = ", ".join("?" * (len(fields) + 1))
            _db.execute(f"INSERT INTO positions ({cols}) VALUES ({qs})", (symbol, *fields.values()))
        _db.commit()


def clear(symbol: str):
    with _lock:
        _db.execute("DELETE FROM positions WHERE symbol=?", (symbol.upper(),))
        _db.commit()


def try_reserve(symbol: str, max_open: int) -> bool:
    """حجز ذرّي للسهم: يمنع الشراء المكرر وتجاوز حد المراكز."""
    symbol = symbol.upper()
    with _lock:
        if state_of(symbol) != "NONE":
            return False
        if active_count() >= max_open:
            return False
        if in_cooldown(symbol):
            return False
        upsert(symbol, state="PENDING_BUY")
        return True


def active() -> List[Dict[str, Any]]:
    with _lock:
        q = f"SELECT * FROM positions WHERE state IN ({','.join('?' * len(ACTIVE_STATES))})"
        return [dict(r) for r in _db.execute(q, ACTIVE_STATES).fetchall()]


def active_count() -> int:
    return len(active())


def log_trade(symbol, side, qty, price, reason=""):
    with _lock:
        _db.execute("INSERT INTO trades_log (ts, day, symbol, side, qty, price, reason) VALUES (?,?,?,?,?,?,?)",
                    (time.time(), today(), symbol.upper(), side, qty, price, reason))
        _db.commit()


def buys_today() -> int:
    with _lock:
        return _db.execute("SELECT COUNT(*) FROM trades_log WHERE day=? AND side='buy'", (today(),)).fetchone()[0]


def set_cooldown(symbol: str, minutes: int):
    with _lock:
        _db.execute("INSERT OR REPLACE INTO cooldown (symbol, until) VALUES (?, ?)",
                    (symbol.upper(), time.time() + minutes * 60))
        _db.commit()


def in_cooldown(symbol: str) -> bool:
    with _lock:
        r = _db.execute("SELECT until FROM cooldown WHERE symbol=?", (symbol.upper(),)).fetchone()
        return bool(r and r["until"] > time.time())
