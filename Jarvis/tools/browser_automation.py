"""browser_automation — gelismis tarayici + WhatsApp otomasyonu.

whatsapp_send(contact, message):
  "WhatsApp'ta Annem kisisine gir ve NasilSin? yaz" gibi istekleri uctan uca yapar.
  Kritik kural: EN USTTEKI sohbete koru korune tiklamaz; kisinin ADINI
  arama cubugunda arar, OCR ile ISMI ESLESEN dogru sohbet kutusuna tiklar.

Akis:
  1. https://web.whatsapp.com acilir (tarayici yoksa acilir, varsa odaklanir).
  2. Arama cubugu bulunur: once OCR ile "Ara/Search" placeholder'i aranir,
     bulunamazsa Ctrl+F / Ctrl+K denenir, en son Tab-navigasyon fallback'i.
  3. Kisi adi yazilir, sonuclarin yuklenmesi beklenir.
  4. OCR ile kisi adiyla eslesen satir bulunur ve tiklanir (yanlis kisi
     engeli: skor < esik ise tiklama yapilmaz, alternatifler donulur).
  5. Mesaj kutusuna mesaj yazilip Enter ile gonderilir.

browser_search_and_type(url, search_text, submit_text):
  Genel siteler icin: URL ac -> arama cubugunu bul (OCR: "Ara/Search/Search...") ->
  search_text yaz -> Enter; submit_text varsa mesaj kutusuna yazip gonderir.

Hicbir fonksiyon yonetici izni istemez. pyautogui + mss + screen_vision
uizerinden calisir; panoya Turkce karakter guvenligi icin pyperclip
(varsa) kullanilir, yoksa typewrite fallback'i vardir.
"""
from __future__ import annotations

import time
import webbrowser

WHATSAPP_URL = "https://web.whatsapp.com"
LOAD_WAIT = 3.5
SEARCH_WAIT = 1.2

# Bilinen sitelerde OCR'a gerek yok: dogrudan arama URL'sine git (hizli + saglam).
# Anahtarlar bilerek kisa tutuldu ("youtube" gibi): model URL'yi tam yazamasa
# bile ("youtube", "youtu.be"...) hizli yol yakalanir.
DIRECT_SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "youtu": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "yandex": "https://yandex.com/search/?text={q}",
}

WHATSAPP_SEND_SCHEMA = {
    "name": "whatsapp_send",
    "description": (
        "WhatsApp Web uzerinden belirli bir kisiye mesaj gonderir. "
        "Kisiyi arama cubugunda arayip ISMI ESLESEN dogru sohbete tiklar; "
        "en ustteki sohbete asla koru korune tiklamaz. "
        "Ornek: whatsapp_send(contact='Annem', message='NasilSin?'). "
        "WhatsApp Web'de ilk kez QR kodla giris yapilmis olmalidir."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "contact": {
                "type": "string",
                "description": "Sohbet/kiSi adi (orn. 'Annem'). Kismi yazim yeterli.",
            },
            "message": {
                "type": "string",
                "description": "Gonderilecek mesaj metni.",
            },
        },
        "required": ["contact", "message"],
    },
}

BROWSER_SEARCH_SCHEMA = {
    "name": "browser_search",
    "description": (
        "Bir web sayfasinda arama yapar. YouTube/Google/Bing/DuckDuckGo'da "
        "dogrudan arama sonuclarini acar (hizli yol, OCR gerekmez); diger "
        "sitelerde arama cubugunu bulup yazar. Ikinci bir metin (mesaj/form) "
        "gerekiyorsa submit_text ile yazip gonderir. "
        "WhatsApp kisiye mesaj icin whatsapp_send kullan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Acilacak sayfa URL'si (orn. 'https://www.youtube.com').",
            },
            "search_text": {
                "type": "string",
                "description": "Arama metni.",
            },
            "submit_text": {
                "type": "string",
                "description": "Aramadan sonra ikinci kutuya yazilacak metin (opsiyonel).",
            },
        },
        "required": ["url", "search_text"],
    },
}


def _direct_search_url(url: str, query: str) -> str | None:
    """Bilinen site mi? Dogrudan arama URL'si doner (hizli yol), yoksa None."""
    from urllib.parse import quote_plus

    lowered = url.lower()
    for domain, template in DIRECT_SEARCH_URLS.items():
        if domain in lowered:
            return template.format(q=quote_plus(query))
    return None


# --- Kucuk yardimcilar ---------------------------------------------------------

def _require_gui():
    try:
        import pyautogui  # noqa: F401
    except ImportError:
        raise RuntimeError("pyautogui paketi kurulu degil ('pip install pyautogui').")
    try:
        import mss  # noqa: F401
    except ImportError:
        raise RuntimeError("mss paketi kurulu degil ('pip install mss').")


def _paste(text: str) -> None:
    """Turkce karakter guvenli yazim: pano -> Ctrl+V, yoksa direkt yaz."""
    import pyautogui

    try:
        import pyperclip

        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        return
    except ImportError:
        pass
    except Exception:  # noqa: BLE001
        pass
    pyautogui.typewrite(text, interval=0.02)


def _focus_search_box() -> dict:
    """Arama cubuguna odaklanir: OCR tiklama -> Ctrl+K -> Ctrl+F sirasiyla dener."""
    import pyautogui

    from tools.screen_vision import click_text, read_screen

    # 1) OCR ile placeholder'i bul (TR + EN).
    for placeholder in ("Ara", "Search", "Sohbetlerde ara", "Search chats"):
        try:
            res = click_text(placeholder)
        except BaseException:  # noqa: BLE001 — OCR motoru her sartta yutulur
            res = {"success": False}
        if res.get("success"):
            time.sleep(0.4)
            return {"success": True, "method": f"ocr:{placeholder}"}
    # 2) Klavye kestirmeleri (WhatsApp Web: Ctrl+K yeni sohbet odagi, Ctrl+F arama).
    for keys in (("ctrl", "k"), ("ctrl", "f")):
        try:
            pyautogui.hotkey(*keys)
            time.sleep(0.5)
        except Exception:  # noqa: BLE001
            continue
        # Odak gercekten arama kutusunda mi? Hizli OCR kontrolu.
        try:
            screen = read_screen()
            if screen.get("success"):
                return {"success": True, "method": f"hotkey:{'+'.join(keys)}"}
        except Exception:  # noqa: BLE001
            return {"success": True, "method": f"hotkey:{'+'.join(keys)}"}
    return {"success": False,
            "error": "Arama cubugu bulunamadi (OCR + Ctrl+K/Ctrl+F denendi)."}


def _click_matching_chat(contact: str) -> dict:
    """Sonuc listesinden ismi eslesen sohbete tiklar (en usttekine degil)."""
    import pyautogui

    from tools.screen_vision import _run_ocr, _score, _screenshot_bytes

    png = _screenshot_bytes()
    if png is None:
        return {"success": False, "error": "Ekran goruntusu alinamadi."}
    try:
        items, _engine = _run_ocr(png)
    except BaseException as exc:  # noqa: BLE001 — SystemExit dahil
        return {"success": False, "error": str(exc)}
    scored = [(d, _score(contact, d.get("text", ""))) for d in items]
    scored = [(d, s) for (d, s) in scored if s >= 0.55]
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        alts = sorted({d.get("text", "") for d in items if d.get("text")})[:12]
        return {"success": False,
                "error": f"'{contact}' adli sohbet ekranda bulunamadi. Listede yoksa yazimi kontrol et.",
                "alternatives": alts}
    best, score = scored[0]
    # Guvenlik: cok dusuk skorla yanlis kisiye tiklama.
    if score < 0.6 and len(scored) > 1 and (scored[0][1] - scored[1][1]) < 0.05:
        return {"success": False,
                "error": f"'{contact}' icin birden fazla benzer sonuc var, yanlis kisiye tiklamadim.",
                "alternatives": [d.get("text", "") for d, _s in scored[:5]]}
    try:
        pyautogui.moveTo(int(best["x"]), int(best["y"]), duration=0.25)
        time.sleep(0.1)
        pyautogui.click(int(best["x"]), int(best["y"]))
        time.sleep(1.0)
        return {"success": True, "matched": best.get("text", ""),
                "score": round(float(score), 3), "x": int(best["x"]), "y": int(best["y"])}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Sohbete tiklanamadi: {exc}"}


# --- Tool fonksiyonlari -----------------------------------------------------------

def whatsapp_send(contact: str, message: str) -> dict:
    """WhatsApp Web'de kisiyi bulup mesaj gonderir."""
    contact = (contact or "").strip()
    message = (message or "").strip()
    if not contact or not message:
        return {"success": False, "error": "Kisi adi ve mesaj bos olmamali."}
    try:
        _require_gui()
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}
    import pyautogui

    try:
        webbrowser.open(WHATSAPP_URL)
        time.sleep(LOAD_WAIT)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Tarayici acilamadi: {exc}"}

    focus = _focus_search_box()
    if not focus.get("success"):
        return {"success": False, "error": focus.get("error", "Arama cubugu bulunamadi."),
                "hint": "WhatsApp Web acik mi? Ilk kullanimda QR kodla giris gerekir."}

    try:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
        pyautogui.press("backspace")
        time.sleep(0.15)
        _paste(contact)
        time.sleep(SEARCH_WAIT)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Kisi adi yazilamadi: {exc}"}

    clicked = _click_matching_chat(contact)
    if not clicked.get("success"):
        return {"success": False, "step": "find_chat", **{k: v for k, v in clicked.items() if k != "success"}}

    try:
        _paste(message)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(0.5)
        return {"success": True, "contact": clicked.get("matched", contact),
                "message": message,
                "detail": f"'{clicked.get('matched', contact)}' sohbetine mesaj gonderildi."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Mesaj gonderilemedi: {exc}"}


def browser_search(url: str, search_text: str, submit_text: str = "") -> dict:
    """Genel site otomasyonu: bilinen sitede hizli yol, digerinde OCR ile arama."""
    url = (url or "").strip()
    search_text = (search_text or "").strip()
    if not url or not search_text:
        return {"success": False, "error": "URL ve arama metni bos olmamali."}
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    try:
        _require_gui()
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}

    # HIZLI YOL: YouTube/Google/Bing/DDG -> dogrudan sonuclar sayfasi (OCR yok, ~1 sn).
    fast_url = _direct_search_url(url, search_text)
    if fast_url and not (submit_text or "").strip():
        try:
            webbrowser.open(fast_url)
            return {"success": True, "url": fast_url, "search_text": search_text,
                    "method": "direct_url",
                    "detail": f"Arama sonuclari acildi: '{search_text}'."}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Tarayici acilamadi: {exc}"}

    import pyautogui

    from tools.screen_vision import click_text

    try:
        webbrowser.open(fast_url or url)
        time.sleep(LOAD_WAIT)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Tarayici acilamadi: {exc}"}

    # Arama cubugunu bul: yaygin placeholder'lar.
    # OCR bozuksa click_text hata doner (exception degil); o durumda hotkey'e dus.
    ocr_dead = False
    found_method = ""
    for placeholder in ("Ara", "Search", "Ara...", "Search..."):
        try:
            res = click_text(placeholder)
        except BaseException:  # noqa: BLE001
            res = {"success": False, "error": "ocr-crash"}
        if res.get("success"):
            found_method = f"ocr:{placeholder}"
            break
        err = str(res.get("error", ""))
        if "Tesseract" in err or "OCR motoru" in err or "EasyOCR" in err:
            ocr_dead = True
            break
    if ocr_dead and fast_url:
        # OCR calismiyor ama site biliniyor: dogrudan sonuclar sayfasi (kurtarma).
        try:
            webbrowser.open(fast_url)
            return {"success": True, "url": fast_url, "search_text": search_text,
                    "method": "direct_url_fallback",
                    "detail": f"Arama sonuclari acildi: '{search_text}' (OCR kapali oldugu icin hizli yol)."}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Tarayici acilamadi: {exc}"}
    if not found_method:
        try:
            pyautogui.hotkey("ctrl", "k")  # cogu sitede/tarayicida arama odagi
            time.sleep(0.5)
            found_method = "hotkey:ctrl+k"
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"Arama cubugu bulunamadi: {exc}"}
    time.sleep(0.4)
    try:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        _paste(search_text)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(2.0)
        if (submit_text or "").strip():
            _paste(submit_text.strip())
            time.sleep(0.4)
            pyautogui.press("enter")
            time.sleep(0.5)
        return {"success": True, "url": url, "search_text": search_text,
                "method": found_method,
                "detail": f"'{url}' adresinde '{search_text}' arandi."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Arama yazilamadi: {exc}"}
