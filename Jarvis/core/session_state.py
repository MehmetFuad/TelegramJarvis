"""Kisa sureli hafiza + bekleyen aksiyonlar (kullanici bazinda, RAM'de).

Gecmis formati: [{"role": "user"|"assistant"|"tool", "content": str}, ...]

pending_action formati:
    {"type": "confirmation"|"choice",
     "tool_name": str,            # onayda calistirilacak / secimde kaynak tool
     "tool_args": {...},          # confirmation: onaylanirsa calistirilacak argumanlar
     "base_args": {...},          # choice: yeniden calistirmede taban argumanlar
     "choice_param": str|None,    # choice: secilen label'in yazilacagi parametre adi
     "options": [{"id","label",...}],  # choice: buton secenekleri
     "created_at": float}         # time.time()

5 dakikadan (PENDING_TIMEOUT) eski aksiyonlar gecersiz sayilir ve
okununca otomatik temizlenir.
"""
from __future__ import annotations

import threading
import time
from collections import deque

MAX_HISTORY = 10
PENDING_TIMEOUT = 300  # saniye (5 dakika)

_lock = threading.Lock()
_store: dict[int, deque] = {}
_pending: dict[int, dict] = {}


def add_message(user_id: int, role: str, content: str) -> None:
    """Kullanicinin gecmisine bir mesaj ekler (en fazla son N mesaj tutulur)."""
    with _lock:
        history = _store.setdefault(user_id, deque(maxlen=MAX_HISTORY))
        history.append({"role": role, "content": content})


def get_history(user_id: int) -> list[dict]:
    """Kullanicinin konusma gecmisini kopya olarak doner (eskiden yeniye)."""
    with _lock:
        return list(_store.get(user_id, []))


def clear_history(user_id: int) -> None:
    """Kullanicinin konusma gecmisini temizler (/reset komutu kullanir)."""
    with _lock:
        _store.pop(user_id, None)


def set_pending_action(user_id: int, action: dict) -> None:
    """Bekleyen aksiyonu kaydeder (created_at otomatik basilir)."""
    with _lock:
        entry = dict(action)
        entry["created_at"] = time.time()
        _pending[user_id] = entry


def get_pending_action(user_id: int) -> dict | None:
    """Bekleyen aksiyonu doner; suresi dolmussa temizleyip None doner."""
    with _lock:
        entry = _pending.get(user_id)
        if entry is None:
            return None
        if time.time() - float(entry.get("created_at", 0)) > PENDING_TIMEOUT:
            _pending.pop(user_id, None)
            return None
        return dict(entry)


def clear_pending_action(user_id: int) -> None:
    """Bekleyen aksiyonu iptal eder/temizler."""
    with _lock:
        _pending.pop(user_id, None)
