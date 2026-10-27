"""shortcut_scanner — .lnk kisayollarindan uygulam indeksleme.

Taranan yerler: kullanici Masaustu, genel Masaustu (Public), kullanici ve
tum kullanicilar Baslat Menusu. .lnk hedefleri pywin32 ile cozulur.
Sonuc data/shortcuts_cache.json'da saklanir: {"Gorunen Isim": "exe yolu"}.
24 saatten taze onbellek varsa yeniden tarama yapilmaz (force=True haric).
"""
from __future__ import annotations

import json
import os
import time

from config import settings

CACHE_FILE = settings.data_dir / "shortcuts_cache.json"
CACHE_TTL = 24 * 3600

TOOL_SCHEMA = {
    "name": "refresh_shortcuts",
    "description": (
        "Masaustu ve Baslat Menusu kisayollarini yeniden tarayip uygulama "
        "indeksini gunceller. Yeni oyun/program kurulduysa bunu cagir."
    ),
    "parameters": {"type": "object", "properties": {}},
}


def scan_dirs() -> list[str]:
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA", "")
    programdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    candidates = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Masaüstü"),
        r"C:\Users\Public\Desktop",
        os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    return [d for d in candidates if d and os.path.isdir(d)]


def _resolve_lnk(path: str) -> str | None:
    """Kisayolun hedef exe yolunu doner (cozulemezse None)."""
    try:
        from win32com.client import Dispatch
    except ImportError:
        return None
    try:
        shell = Dispatch("WScript.Shell")
        target = shell.CreateShortCut(path).Targetpath or ""
        target = target.strip().strip('"')
        if target.lower().endswith(".exe") and os.path.isfile(target):
            return target
        return None
    except Exception:  # noqa: BLE001
        return None


def load_index() -> dict[str, str]:
    """Onbellekteki {gorunen_isim: exe_yolu} indeksini doner (yoksa {})."""
    try:
        if CACHE_FILE.is_file():
            raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            entries = raw.get("entries", {}) if isinstance(raw, dict) else {}
            if isinstance(entries, dict):
                return {str(k): str(v) for k, v in entries.items() if v}
    except (OSError, ValueError):
        pass
    return {}


def _cache_fresh() -> bool:
    try:
        if CACHE_FILE.is_file():
            raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and time.time() - float(raw.get("scanned_at", 0)) < CACHE_TTL:
                return True
    except (OSError, ValueError, TypeError):
        pass
    return False


def scan_shortcuts(force: bool = False) -> dict:
    """Kisayollari tara, indeksi kaydet. Donus: {updated, count, ...}."""
    try:
        from win32com.client import Dispatch  # noqa: F401
    except ImportError:
        return {"updated": False, "count": len(load_index()),
                "error": "pywin32 kurulu degil ('pip install pywin32')."}
    if not force and _cache_fresh():
        return {"updated": False, "cached": True, "count": len(load_index())}

    entries: dict[str, str] = {}
    scanned_files = 0
    for base in scan_dirs():
        for root, _dirs, files in os.walk(base, onerror=lambda _e: None):
            for fname in files:
                if not fname.lower().endswith(".lnk"):
                    continue
                scanned_files += 1
                display = os.path.splitext(fname)[0].strip()
                if not display or display in entries:
                    continue
                target = _resolve_lnk(os.path.join(root, fname))
                if target:
                    entries[display] = target

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        CACHE_FILE.write_text(
            json.dumps({"scanned_at": time.time(), "entries": entries},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        return {"updated": False, "count": len(entries), "error": f"Onbellege yazilamadi: {exc}"}
    return {"updated": True, "count": len(entries), "scanned_files": scanned_files}


def refresh_shortcuts() -> dict:
    """Gemini tool'u: zorla yeniden tara."""
    result = scan_shortcuts(force=True)
    if result.get("error"):
        return {"success": False, "error": result["error"]}
    return {"success": True, "message": f"Indeks guncellendi: {result.get('count', 0)} uygulama bulundu."}
