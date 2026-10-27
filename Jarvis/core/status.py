"""Paylasilan durum — bot ve dashboard ayni process'te bu modulu kullanir.

Bot yazar (bot_running, son mesaj, Gemini cagri sonucu, cokus bilgisi),
dashboard okur. Kapatma istekleri de buradan koordine edilir.
Sadece standart kutuphane kullanir (import dongusu riski yok).
"""
from __future__ import annotations

import threading
import time

_started_at = time.time()
_lock = threading.Lock()
_state = {
    "bot_running": False,
    "last_message_at": None,   # epoch saniye
    "message_count": 0,
    "gemini_ok": None,         # True / False / None (henuz cagri yok)
    "last_gemini_at": None,    # epoch saniye
    "last_crash": None,        # {"time": str, "service": str, "reason": str}
}

# Duzgun kapatma: /kapat komutu veya dashboard Durdur butonu tetikler.
shutdown_requested = threading.Event()
_stop_loop = None
_stop_event = None


def set_bot_running(value: bool) -> None:
    with _lock:
        _state["bot_running"] = bool(value)


def mark_message() -> None:
    with _lock:
        _state["last_message_at"] = time.time()
        _state["message_count"] += 1


def mark_gemini(success: bool) -> None:
    with _lock:
        _state["gemini_ok"] = bool(success)
        _state["last_gemini_at"] = time.time()


def set_last_crash(service: str, reason: str) -> None:
    with _lock:
        _state["last_crash"] = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "service": service,
            "reason": str(reason)[:300],
        }


def snapshot() -> dict:
    """Dashboard'un /api/status icin okudugu durum kopyasi."""
    with _lock:
        data = dict(_state)
    data["uptime_seconds"] = int(time.time() - _started_at)
    return data


def set_stop_event(loop, event) -> None:
    """run.py baslangicta ana event loop'un durma olayini kaydeder."""
    global _stop_loop, _stop_event
    _stop_loop = loop
    _stop_event = event


def request_stop() -> None:
    """Duzgun kapatma ister (/kapat, dashboard Durdur). Thread-safe."""
    shutdown_requested.set()
    try:
        if _stop_loop is not None and _stop_event is not None:
            _stop_loop.call_soon_threadsafe(_stop_event.set)
    except Exception:  # noqa: BLE001 — loop kapanmissa onemsiz
        pass
