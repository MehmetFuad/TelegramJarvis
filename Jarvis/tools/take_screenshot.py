"""take_screenshot tool — birincil monitorun programatik goruntusu.

mss kullanir; klavye kisayolu (Prt Sc / Win+Shift+S) veya herhangi bir
Windows arayuzu acmaz. Kayit: data/screenshots/screenshot_<tarih>.png
"""
from __future__ import annotations

from datetime import datetime

from config import settings

TOOL_SCHEMA = {
    "name": "take_screenshot",
    "description": (
        "Bilgisayarin birincil monitorunun ekran goruntusunu alir ve PNG "
        "dosyasi olarak kaydeder. Ekran goruntusu istendiginde HER ZAMAN bu "
        "tool kullanilir; klavye kisayolu veya baska yontem denenmez."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def take_screenshot() -> dict:
    """Ekran goruntusu alir; sonucu standart tool dict'i olarak doner."""
    try:
        import mss
    except ImportError:
        return {"success": False, "error": "mss paketi kurulu degil ('pip install mss')."}
    try:
        out_dir = settings.data_dir / "screenshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"screenshot_{stamp}.png"
        with mss.mss() as sct:
            # monitors[0] = tum ekranlarin birlesimi, monitors[1] = birincil monitor.
            sct.shot(mon=1, output=str(path))
        if not path.is_file():
            return {"success": False, "error": "Goruntu dosyasi olusturulamadi."}
        return {"success": True, "file_to_send": str(path)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Ekran goruntusu alinamadi: {exc}"}
