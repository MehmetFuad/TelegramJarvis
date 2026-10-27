"""Loglama — konsol + SQLite (kalici) + donen dosya (arsiv).

- Konsol: her zaman.
- SQLite data/jarvis.db: logs + decisions tablolari (dashboard buradan okur).
- Dosya data/jarvis.log: 1 MB donen arsiv (hata ayiklama icin birakildi).
- 50.000 satiri asan tablolar otomatik budanir (prune_logs).

SQLite yazmalari thread-safe'dir (kilit + check_same_thread=False + WAL).
Loglama asla crash etmez: tum hatalar sessiz yutulur.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_ROWS = 50000
PRUNE_EVERY_WRITES = 200

DECISIONS_LOGGER = "jarvis.decisions"

_db_path: Path | None = None
_db_lock = threading.Lock()
_write_count = 0


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS logs("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "level TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS decisions("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "user_id INTEGER NOT NULL DEFAULT 0, action_type TEXT NOT NULL DEFAULT '', "
        "tool_name TEXT NOT NULL DEFAULT '', tool_args TEXT NOT NULL DEFAULT '{}', "
        "result TEXT NOT NULL DEFAULT '', user_choice TEXT NOT NULL DEFAULT '')"
    )
    conn.commit()
    return conn


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


class _SQLiteHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if _db_path is None:
            return
        try:
            with _db_lock:
                conn = _connect(_db_path)
                try:
                    conn.execute(
                        "INSERT INTO logs(timestamp, level, source, message) VALUES(?,?,?,?)",
                        (_now(), record.levelname, record.name, record.getMessage()[:2000]),
                    )
                    conn.commit()
                finally:
                    conn.close()
            _maybe_prune()
        except Exception:  # noqa: BLE001
            pass


def _maybe_prune() -> None:
    global _write_count
    _write_count += 1
    if _write_count % PRUNE_EVERY_WRITES == 0:
        try:
            prune_logs(MAX_ROWS)
        except Exception:  # noqa: BLE001
            pass


def prune_logs(max_rows: int = MAX_ROWS, db_path: Path | None = None) -> dict:
    """Her tabloyu max_rows satirla sinirlar (en eskiler silinir)."""
    path = Path(db_path) if db_path else _db_path
    if path is None or not path.is_file():
        return {"logs": 0, "decisions": 0}
    removed = {}
    with _db_lock:
        conn = _connect(path)
        try:
            for table in ("logs", "decisions"):
                (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                if count > max_rows:
                    conn.execute(
                        f"DELETE FROM {table} WHERE id NOT IN "
                        f"(SELECT id FROM {table} ORDER BY id DESC LIMIT ?)",
                        (max_rows,),
                    )
                    removed[table] = count - max_rows
                else:
                    removed[table] = 0
            conn.commit()
        finally:
            conn.close()
    return removed


def setup_logging(level: str = "INFO", log_dir: str | Path | None = None,
                  db_path: str | Path | None = None) -> None:
    global _db_path
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))

    try:
        from config import settings

        directory = Path(log_dir) if log_dir else settings.data_dir
    except Exception:  # noqa: BLE001
        directory = Path("data")
    _db_path = Path(db_path) if db_path else (directory / "jarvis.db")
    try:
        conn = _connect(_db_path)
        conn.close()
    except Exception:  # noqa: BLE001
        pass

    if not any(isinstance(h, _SQLiteHandler) for h in root.handlers):
        root.addHandler(_SQLiteHandler())
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
            file_handler = RotatingFileHandler(
                directory / "jarvis.log", maxBytes=1_000_000,
                backupCount=3, encoding="utf-8",
            )
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
            )
            root.addHandler(file_handler)
    except Exception:  # noqa: BLE001
        pass

    for noisy in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    prune_logs(MAX_ROWS)


def get_recent_logs(limit: int = 50) -> list[dict]:
    """Dashboard /api/logs icin: en yeniden eskiye."""
    limit = max(1, min(int(limit or 50), 200))
    if _db_path is None or not _db_path.is_file():
        return []
    try:
        with _db_lock:
            conn = _connect(_db_path)
            try:
                rows = conn.execute(
                    "SELECT timestamp, level, source, message FROM logs "
                    "ORDER BY id DESC LIMIT ?", (limit,),
                ).fetchall()
            finally:
                conn.close()
        return [{"time": t, "level": lv, "logger": src, "message": msg}
                for (t, lv, src, msg) in rows]
    except Exception:  # noqa: BLE001
        return []


def get_recent_decisions(limit: int = 50) -> list[dict]:
    """Dashboard /api/decisions icin: en yeniden eskiye (frontend uyumlu)."""
    limit = max(1, min(int(limit or 50), 200))
    if _db_path is None or not _db_path.is_file():
        return []
    try:
        with _db_lock:
            conn = _connect(_db_path)
            try:
                rows = conn.execute(
                    "SELECT timestamp, user_id, action_type, tool_name, tool_args, result, user_choice "
                    "FROM decisions ORDER BY id DESC LIMIT ?", (limit,),
                ).fetchall()
            finally:
                conn.close()
        out = []
        for (t, uid, action, tool, args, result, choice) in rows:
            summary = f"{action} user_id={uid} {tool} {args}"
            if choice:
                summary += f" -> {choice}"
            if result:
                summary += f" | {result[:200]}"
            out.append({"time": t, "level": "INFO", "logger": DECISIONS_LOGGER,
                        "message": summary, "action_type": action,
                        "tool_name": tool, "user_choice": choice})
        return out
    except Exception:  # noqa: BLE001
        return []


def log_decision(user_id: int, kind: str, detail: str, tool_name: str = "",
                 tool_args: dict | None = None, result: str = "",
                 user_choice: str = "") -> None:
    """Onay/secim kararlarini hem log'a hem decisions tablosuna yazar."""
    logging.getLogger(DECISIONS_LOGGER).info("%s user_id=%s %s", kind, user_id, detail)
    if _db_path is None:
        return
    try:
        args_json = json.dumps(tool_args or {}, ensure_ascii=False, default=str)[:2000]
        with _db_lock:
            conn = _connect(_db_path)
            try:
                conn.execute(
                    "INSERT INTO decisions(timestamp, user_id, action_type, tool_name, "
                    "tool_args, result, user_choice) VALUES(?,?,?,?,?,?,?)",
                    (_now(), int(user_id or 0), kind, tool_name,
                     args_json, str(result)[:2000], str(user_choice)[:200]),
                )
                conn.commit()
            finally:
                conn.close()
        _maybe_prune()
    except Exception:  # noqa: BLE001
        pass
