"""media_control — medya tusu simulasyonu + sistem ses seviyesi.

media_control: pyautogui ile sanal medya tuslari (uygulama bagimsiz:
Spotify, YouTube, herhangi bir player).
set_volume: pycaw ile Windows ana ses seviyesi (0-100). Yonetici izni
GEREKTIRMEZ; standart kullanici baglaminda calisir.

Ses kisikligi / tutmama sorununun kok nedenleri ve cozumleri:
1. COM baslatilmamasi (CO_E_NOTINITIALIZED) -> pythoncom.CoInitialize()
2. Sessize alinmis (mute) kanal -> once SetMute(0), sonra seviye yazilir
3. Surucu gec cevap verir -> yaz -> 120ms bekle -> geri oku -> tutmazsa
   en fazla 3 kez tekrar dene (retry dongusu)
4. Float hassasiyeti (0.19999 vs 0.20) -> tolerans 2 puan, int'e yuvarla
"""
from __future__ import annotations

import time

MEDIA_KEYMAP = {
    "play_pause": "playpause",
    "next": "nexttrack",
    "previous": "prevtrack",
    "mute": "mute",
}

MEDIA_CONTROL_SCHEMA = {
    "name": "media_control",
    "description": (
        "Medya oynatmayi kontrol eder: play_pause (oynat/duraklat), "
        "next (sonraki parca), previous (onceki parca), mute (sessiz). "
        "Hangi uygulamanin acik oldugunu sorma, direkt kullan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "play_pause | next | previous | mute",
            },
        },
        "required": ["action"],
    },
}

SET_VOLUME_SCHEMA = {
    "name": "set_volume",
    "description": (
        "Windows sistem ses seviyesini ayarlar (0-100). "
        "Hangi uygulamanin acik oldugunu sorma, direkt kullan. "
        "Ornek: 'sesi 20 yap' -> set_volume(level=20)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "level": {
                "type": "integer",
                "description": "Ses seviyesi: 0 (sessiz) ile 100 (tam ses) arasi.",
            },
        },
        "required": ["level"],
    },
}

_VOLUME_TOLERANCE = 2
_VOLUME_RETRIES = 3


def media_control(action: str) -> dict:
    """Medya tusuna basar; sonucu standart tool dict'i olarak doner."""
    action = (action or "").strip().lower()
    if action not in MEDIA_KEYMAP:
        return {"success": False,
                "error": f"Bilinmeyen medya komutu: {action!r} (play_pause/next/previous/mute)."}
    try:
        import pyautogui
    except ImportError:
        return {"success": False, "error": "pyautogui paketi kurulu degil ('pip install pyautogui')."}
    try:
        pyautogui.press(MEDIA_KEYMAP[action])
        return {"success": True, "action": action,
                "message": f"Medya komutu gonderildi: {action}."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Medya tusu gonderilemedi: {exc}"}


def _ensure_com() -> None:
    """pycaw/comtypes icin COM'u hazirla (yoksa sessizce gec)."""
    try:
        import pythoncom

        try:
            pythoncom.CoInitialize()
        except Exception:  # noqa: BLE001
            pass  # zaten baslatilmis olabilir (S_FALSE / RPC_E_CHANGED_MODE)
    except ImportError:
        pass  # pywin32 yoksa comtypes kendi basina dener


def _get_volume_iface():
    """pycaw ses arayuzu (lazy import). Kurulum/ortam hatasinda exception yukseltir."""
    _ensure_com()
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except ImportError as exc:
        raise RuntimeError(
            "pycaw/comtypes kurulu degil ('pip install pycaw comtypes')."
        ) from exc
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def get_volume() -> dict:
    """Guncel ses seviyesini + mute durumunu okur (teshis icin)."""
    try:
        volume = _get_volume_iface()
        level = int(round(volume.GetMasterVolumeLevelScalar() * 100))
        try:
            muted = bool(volume.GetMute())
        except Exception:  # noqa: BLE001
            muted = False
        return {"success": True, "actual_level": level, "muted": muted}
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Ses okunamadi: {exc}"}


def set_volume(level: int) -> dict:
    """Sistem sesini 0-100 arasi ayarlar, mute'u kaldirir, yaz-okur-dogrular.

    Yonetici izni gerekmez. Donus her zaman actual_level icerir; iddia ile
    gercek arasinda fark varsa success=false doner (Gemini kullaniciya
    yanlis "ayarlandi" demez).
    """
    try:
        level = int(level)
    except (TypeError, ValueError):
        return {"success": False, "error": "Ses seviyesi 0-100 arasi bir sayi olmali."}
    level = max(0, min(100, level))
    target = level / 100.0

    try:
        volume = _get_volume_iface()
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Ses arayuzu acilamadi: {exc}"}

    last_error = ""
    actual = -1
    try:
        # 1) Mute varsa kaldir (yoksa %50 yazsan bile ses gelmez -> "kisiklik" hissi).
        try:
            if volume.GetMute():
                volume.SetMute(0, None)
                time.sleep(0.05)
        except Exception:  # noqa: BLE001
            pass
        # 2) Yaz -> bekle -> oku; tutmazsa tekrarla.
        for _attempt in range(_VOLUME_RETRIES):
            try:
                volume.SetMasterVolumeLevelScalar(target, None)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(0.15)
                continue
            time.sleep(0.12)
            try:
                actual = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(0.15)
                continue
            if abs(actual - level) <= _VOLUME_TOLERANCE:
                break
            time.sleep(0.15)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Ses ayarlanamadi: {exc}"}

    if abs(actual - level) > _VOLUME_TOLERANCE:
        detail = f" (son hata: {last_error})" if last_error and actual < 0 else ""
        return {"success": False, "level": level, "actual_level": actual,
                "error": f"Ses %{level} istenip %{actual} oldu; tekrar deneyin.{detail}"}
    return {"success": True, "level": level, "actual_level": actual,
            "message": f"Ses seviyesi %{actual} yapildi."}
