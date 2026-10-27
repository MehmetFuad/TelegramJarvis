"""JARVIS masaustu uygulamasi — cift tikla calistir (otomatik baslamaz).

Davranis (normal kullanim sirasi):
  1. Arka plan servisi (Gorev Zamanlayici -> run.py) zaten calisiyordur;
     app.py bunu saglik kontroluyle gorur ve SADECE baglanir.
  2. Backend gercekten calismiyorsa (otomatik baslangic kapaliysa) app.py
     kendisi baslatir.
  3. pywebview penceresi acilir; pencere kapatilinca backend CALISMAYA DEVAM EDER.

Onemli detaylar:
  - Saglik kontrolu sistem proxy'sini BAYPAS eder (proxy/VPN, localhost
    istegini disari yonlendirip yanlis "backend yok" sonucuna yol acabiliyordu;
    bu da ikinci bot ornegine ve Telegram Conflict kilitlenmesine neden oluyordu).
  - Baslatma dugmesine basmadan hemen once kontrol tekrarlanir (cift tiklama yarisi).
  - Tum kararlar/hatalar data/app_crash.log'a yazilir (terminal gerekmez).
Kullanim: python app.py  (veya Masaustundeki JARVIS kisayolu)
"""
from __future__ import annotations

import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON311_HOME = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python311"

from config import settings  # noqa: E402

URL = f"http://127.0.0.1:{settings.dashboard_port}"
HEALTH_URL = URL + "/api/health"
CRASH_LOG = BASE_DIR / "data" / "app_crash.log"

HEALTH_TIMEOUT = 2.0
HEALTH_RETRIES = 3


def crash_log(message: str) -> None:
    """Teshis gunlugu: hem terminale hem data/app_crash.log'a yazar."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line)
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _no_proxy_opener() -> urllib.request.OpenerDirector:
    # Sistem proxy'si localhost'u yakalayamasin: dogrudan baglan.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def backend_alive(timeout: float = HEALTH_TIMEOUT, retries: int = HEALTH_RETRIES) -> bool:
    """Backend saglik kontrolu: 200 donerse True. Proxy baypasli + tekrarli."""
    opener = _no_proxy_opener()
    for attempt in range(1, retries + 1):
        try:
            with opener.open(HEALTH_URL, timeout=timeout) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                crash_log(f"backend_alive: backend ulasilamaz ({exc})")
            time.sleep(0.3)
    return False


def _python_launcher() -> str:
    """Backend icin pythonw.exe secer; Python 3.11 (64-bit) onceliklidir.

    WindowsApps altindaki 0 baytlik pythonw.exe stub'i calismadigi icin atlanir.
    """
    adaylar: list[Path] = []
    mevcut = Path(sys.executable)
    if "WindowsApps" not in str(mevcut):
        adaylar.append(mevcut.parent / "pythonw.exe")
        adaylar.append(mevcut)
    adaylar.append(PYTHON311_HOME / "pythonw.exe")
    adaylar.append(PYTHON311_HOME / "python.exe")
    for aday in adaylar:
        if aday.is_file() and aday.stat().st_size > 0:
            return str(aday)
    return sys.executable


def start_backend() -> bool:
    """run.py'yi arka planda baslatir. Oncesinde tekrar kontrol eder (yaris onlemi)."""
    if backend_alive(timeout=HEALTH_TIMEOUT, retries=1):
        crash_log("start_backend: kontrolde backend gorundu, baslatma iptal (cift ornek onlendi).")
        return True
    launcher = _python_launcher()
    try:
        kwargs: dict = {"cwd": str(BASE_DIR)}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        subprocess.Popen([launcher, str(BASE_DIR / "run.py")], **kwargs)  # noqa: S603
        crash_log(f"start_backend: backend baslatildi ({launcher} run.py).")
        return True
    except Exception as exc:  # noqa: BLE001
        crash_log(f"start_backend HATASI: {exc}")
        return False


def wait_for_backend(timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if backend_alive(timeout=HEALTH_TIMEOUT, retries=1):
            return True
        time.sleep(1.0)
    crash_log("wait_for_backend: sure doldu, backend acilamadi.")
    return False


def open_window() -> int:
    try:
        import webview
    except ImportError:
        crash_log("pywebview kurulu degil: pip install pywebview")
        print(f"Gecici olarak tarayicidan acabilirsiniz: {URL}")
        return 1
    crash_log("Pencere aciliyor, mevcut backend'e baglanildi.")
    webview.create_window("JARVIS", URL, width=1200, height=800)
    webview.start()
    print("Pencere kapatildi. Backend arka planda calismaya devam ediyor.")
    return 0


def main() -> int:
    try:
        if backend_alive():
            crash_log("Backend zaten calisiyor, baglaniliyor (ikinci bot baslatilmayacak).")
        else:
            crash_log("Backend calismiyor, arka planda baslatiliyor...")
            if not start_backend():
                return 1
            if not wait_for_backend():
                print("Backend acilamadi. data/app_crash.log dosyasina bakin.")
                return 1
            crash_log("Backend basladi.")
        return open_window()
    except Exception:  # noqa: BLE001
        crash_log("app.py BEKLENMEYEN HATA:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
