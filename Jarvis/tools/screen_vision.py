"""screen_vision — OCR ile ekran okuma + koordinat bazli akilli tiklama.

Mimari:
- read_screen(): ekran goruntusu alir (mss) -> OCR motoru ile tum metinleri
  ve kutularini doner. Motor onceligi: EasyOCR (kuruluysa, en dogru) ->
  pytesseract (Tesseract kuruluysa) -> hata mesaji (kurulum yonergesiyle).
- find_text_coordinates(target): hedef metne fuzzy eslesen kutunun merkez
  (x, y) koordinatini doner.
- click_text(target): bul + pyautogui ile tikla. Tiklama sonrasi dogrulama
  icin yeni goruntu alinmaz (hizli akis); gerekiyorsa cagiran tekrar okur.

Kurulum (ik isnan birini sec):
  pip install easyocr            # agir (torch) ama en dogru, kurulum gerekmez
  pip install pytesseract Pillow
  # + Tesseract indir: https://github.com/UB-Mannheim/tesseract/wiki
  #   (PATH'e eklemesen de olur: JARVIS, Program Files'taki v4+ binary'yi
  #   otomatik bulur; PATH'teki eski v3'u ezer. Turkce dil dosyasi yoksa
  #   ilk kullanimda otomatik indirilir.)

Bu modulun hicbir fonksiyonu yonetici izni istemez.
"""
from __future__ import annotations

import difflib
import io
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from config import settings

log = logging.getLogger("jarvis.vision")

TUR_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/tur.traineddata"

_KNOWN_TESS_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

_TESS_STATE: dict = {"ready": False, "binary": "", "version": "", "lang": "eng"}


def _version_of(binary: str) -> tuple[int, str]:
    """Binary'nin major surumunu doner; calismazsa (-1, '')."""
    try:
        proc = subprocess.run([binary, "--version"], capture_output=True, text=True,
                              errors="replace", timeout=10)
        first = (proc.stdout or "").strip().splitlines()
        if not first:
            return -1, ""
        import re

        match = re.search(r"(\d+)\.(\d+)", first[0])
        if not match:
            return -1, first[0][:40]
        return int(match.group(1)), first[0][:60]
    except Exception:  # noqa: BLE001
        return -1, ""


def _candidate_binaries() -> list[str]:
    """PATH + bilinen yollar + TESSDATA_PREFIX komsusundaki tesseract.exe'ler."""
    found: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory.strip().strip('"')) / "tesseract.exe"
        if candidate.is_file():
            found.append(str(candidate))
    for known in _KNOWN_TESS_PATHS:
        if Path(known).is_file() and known not in found:
            found.append(known)
    prefix = os.environ.get("TESSDATA_PREFIX", "").strip().strip('"')
    if prefix:
        candidate = str(Path(prefix) / "tesseract.exe")
        if Path(candidate).is_file() and candidate not in found:
            found.append(candidate)
    return found


def _ensure_tessdata(lang_dir: Path, src_tessdata: Path) -> str:
    """data/tessdata'yi hazirla: eng/osd kopyala, tur yoksa indir.

    Donus: kullanilacak dil kodu ("tur+eng" veya "eng").
    """
    lang_dir.mkdir(parents=True, exist_ok=True)
    for name in ("eng.traineddata", "osd.traineddata"):
        target = lang_dir / name
        if not target.is_file() or target.stat().st_size == 0:
            src = src_tessdata / name
            try:
                if src.is_file():
                    shutil.copyfile(src, target)
            except OSError:
                pass
    tur = lang_dir / "tur.traineddata"
    if not tur.is_file() or tur.stat().st_size < 100_000:
        try:
            import requests

            resp = requests.get(TUR_URL, timeout=60)
            resp.raise_for_status()
            if len(resp.content) > 100_000:
                tur.write_bytes(resp.content)
                log.info("tur.traineddata indirildi (%d bayt).", len(resp.content))
        except Exception as exc:  # noqa: BLE001
            log.warning("tur indirilemedi, eng ile devam: %s", exc)
    if tur.is_file() and tur.stat().st_size > 100_000:
        return "tur+eng"
    return "eng"


def _ensure_tesseract() -> dict:
    """En iyi Tesseract binary'yi sec + izole tessdata hazirla (sonucu cache'ler).

    Donus: {"binary", "version", "lang"} — hazir degilse RuntimeError yukseltir.
    """
    if _TESS_STATE.get("ready"):
        return _TESS_STATE
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract/Pillow kurulu degil ('pip install pytesseract Pillow').") from exc

    best, best_major, best_ver = "", -1, ""
    for candidate in _candidate_binaries():
        major, ver = _version_of(candidate)
        if major > best_major:
            best, best_major, best_ver = candidate, major, ver
    if best_major < 4:
        raise RuntimeError(
            "Kullanilabilir Tesseract (v4+) bulunamadi. "
            "Kur: https://github.com/UB-Mannheim/tesseract/wiki "
            "(PATH'e eklemene gerek yok, JARVIS otomatik bulur)."
        )
    # Izole tessdata: sistemin kirli TESSDATA_PREFIX'inden etkilenme.
    lang_dir = settings.data_dir / "tessdata"
    src_tessdata = Path(best).parent / "tessdata"
    lang = _ensure_tessdata(lang_dir, src_tessdata)

    pytesseract.pytesseract.tesseract_cmd = best
    os.environ["TESSDATA_PREFIX"] = str(lang_dir) + os.sep
    _TESS_STATE.update({"ready": True, "binary": best, "version": best_ver, "lang": lang})
    log.info("Tesseract hazir: %s | %s | dil=%s", best, best_ver, lang)
    return _TESS_STATE


def _preprocess(png: bytes):
    """OCR oncesi iyilestirme: gri ton + 2x buyutme (kucuk ekran yazilari icin).

    Donus: (goruntu, olcek). Koordinatlari gercek ekrana cevirmek icin
    olcege bolmek gerekir.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("L")
    width, height = img.size
    if max(width, height) < 3000:
        img = img.resize((width * 2, height * 2), Image.LANCZOS)
        return img, 2.0
    return img, 1.0

READ_SCREEN_SCHEMA = {
    "name": "read_screen",
    "description": (
        "Ekrandaki tum yazilari OCR ile okur ve metin + koordinat listesi doner. "
        "Bir dugmeyi/metni bulup tiklamadan once kesif icin kullan. "
        "Donus: {texts: [{text, x, y, confidence}]}."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

CLICK_TEXT_SCHEMA = {
    "name": "click_text",
    "description": (
        "Ekranda gorunen bir yaziyi/dugmeyi OCR ile bulup fareyle tiklar. "
        "Ornek: click_text(target='Gonder') veya click_text(target='Annem'). "
        "Ismi ESLESEN hedefe tiklar; yakin eslesme yoksa tiklama yapmaz, "
        "alternatifleri listeler. OCR calismiyorsa hata doner; o durumda "
        "kullanicidan bolge isteyip click_at ile tikla."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Ekranda aranacak yazi (kismi yazim yeterli, orn. 'Gonder').",
            },
            "double_click": {
                "type": "boolean",
                "description": "True ise cift tiklar (varsayilan false).",
            },
        },
        "required": ["target"],
    },
}

CLICK_AT_SCHEMA = {
    "name": "click_at",
    "description": (
        "Ekranin verilen (x, y) koordinatina fareyle tiklar. OCR calismadiginda "
        "veya kullanici bolge tarif ettiginde kullan. Ornek: kullanici 'sag ustte' "
        "dediyse once take_screenshot ile goruntuyu alip konumu tahmin et, "
        "sonra click_at(x=..., y=...) ile tikla. Koordinatlar birincil monitor "
        "pikseli cinsindendir."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "x": {
                "type": "integer",
                "description": "Yatay piksel koordinati (soldan).",
            },
            "y": {
                "type": "integer",
                "description": "Dikey piksel koordinati (ustten).",
            },
            "double_click": {
                "type": "boolean",
                "description": "True ise cift tiklar (varsayilan false).",
            },
        },
        "required": ["x", "y"],
    },
}

_EASYOCR_READER = None
FUZZY_THRESHOLD = 0.55


# --- Ekran goruntusu -------------------------------------------------------

def _screenshot_bytes() -> bytes | None:
    """Birincil monitorun PNG baytlarini doner (mss)."""
    try:
        import mss
    except ImportError:
        return None
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            import mss.tools

            return mss.tools.to_png(shot.rgb, shot.size)
    except Exception:  # noqa: BLE001
        return None


def _screenshot_path() -> Path:
    out_dir = settings.data_dir / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"vision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"


# --- OCR motorlari ----------------------------------------------------------

def _ocr_easyocr(png: bytes) -> list[dict]:
    """EasyOCR: [(bbox, text, conf)] -> standart liste. Agir ama kurulum gerektirmez."""
    global _EASYOCR_READER
    import numpy as np
    from PIL import Image

    try:
        import easyocr
    except ImportError as exc:
        raise RuntimeError("EasyOCR kurulu degil.") from exc
    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["tr", "en"], gpu=False, verbose=False)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    arr = np.array(img)
    raw = _EASYOCR_READER.readtext(arr)
    out = []
    for bbox, text, conf in raw:
        text = (text or "").strip()
        if not text:
            continue
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        out.append({
            "text": text,
            "x": int((min(xs) + max(xs)) / 2),
            "y": int((min(ys) + max(ys)) / 2),
            "confidence": round(float(conf), 3),
        })
    return out


def _ocr_tesseract(png: bytes) -> list[dict]:
    """pytesseract: image_to_data ile kelime kutulari.

    NOT: eski pytesseract surum kontrolu SystemExit yukseltir (BaseException!).
    Bu botu oldurmemesi icin burada yakalanip RuntimeError'a cevrilir.
    Binary secimi + TESSDATA_PREFIX izolasyonu _ensure_tesseract ile yapilir.
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract/Pillow kurulu degil.") from exc
    state = _ensure_tesseract()  # binary + dil burada netlesir
    img, scale = _preprocess(png)
    data = None
    last_err: BaseException | None = None
    for lang in (state["lang"], "eng"):
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
            break
        except BaseException as exc:  # noqa: BLE001 — SystemExit dahil
            last_err = exc
            continue
    if data is None:
        raise RuntimeError(f"Tesseract OCR hatasi: {last_err}") from last_err
    out = []
    n = len(data.get("text", []))
    for i in range(n):
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        text = (data["text"][i] or "").strip()
        if not text or conf < 30:
            continue
        try:
            # Buyutulmus goruntudeki koordinati gercek ekrana indir.
            x = int((data["left"][i] + data["width"][i] // 2) / scale)
            y = int((data["top"][i] + data["height"][i] // 2) / scale)
        except (ValueError, TypeError, KeyError):
            continue
        out.append({"text": text, "x": x, "y": y, "confidence": round(conf / 100.0, 3)})
    # Tesseract kelime kelime doner; yakin kelimeleri satir olarak birlestir.
    # Birlestirme toleransi da olcege gore ayarlanir.
    return _merge_words(out, y_tol=int(12 * scale) if scale > 1 else 12)


def _merge_words(words: list[dict], y_tol: int = 12) -> list[dict]:
    """Ayni satirdaki kelimeleri tek satir metnine birlestir (tiklama icin daha iyi)."""
    if not words:
        return words
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda d: (d["y"], d["x"])):
        placed = False
        for row in rows:
            if abs(row[0]["y"] - w["y"]) <= y_tol:
                row.append(w)
                placed = True
                break
        if not placed:
            rows.append([w])
    merged = []
    for row in rows:
        row.sort(key=lambda d: d["x"])
        merged.append({
            "text": " ".join(d["text"] for d in row),
            "x": sum(d["x"] for d in row) // len(row),
            "y": sum(d["y"] for d in row) // len(row),
            "confidence": round(sum(d["confidence"] for d in row) / len(row), 3),
        })
    return merged


def _run_ocr(png: bytes) -> tuple[list[dict], str]:
    """Mevcut ilk motorla OCR yapar; (sonuclar, motor_adi) doner.

    Tum motor hatalari RuntimeError'a cevrilir (SystemExit dahil) ki
    bot process'i hicbir sartta olmesin.
    """
    try:
        import easyocr  # noqa: F401
        return _ocr_easyocr(png), "easyocr"
    except ImportError:
        pass
    except BaseException as exc:  # noqa: BLE001
        raise RuntimeError(f"EasyOCR hatasi: {exc}") from exc
    try:
        import pytesseract  # noqa: F401
        return _ocr_tesseract(png), "tesseract"
    except ImportError:
        pass
    except RuntimeError:
        raise
    except BaseException as exc:  # noqa: BLE001
        raise RuntimeError(f"Tesseract hatasi: {exc}. Tesseract kurulu mu?") from exc
    raise RuntimeError(
        "OCR motoru bulunamadi. Kurun: 'pip install pytesseract Pillow' "
        "+ Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) "
        "veya 'pip install easyocr'."
    )


# --- Fuzzy eslesme ------------------------------------------------------------

def _score(query: str, candidate: str) -> float:
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c:
        return 0.9
    try:
        from rapidfuzz import fuzz

        return max(
            difflib.SequenceMatcher(None, q, c).ratio(),
            fuzz.token_set_ratio(q, c) / 100.0,
            fuzz.partial_ratio(q, c) / 100.0,
        )
    except ImportError:
        return difflib.SequenceMatcher(None, q, c).ratio()


def find_text_coordinates(target: str, items: list[dict] | None = None) -> dict:
    """Hedef metnin ekran koordinatini bulur (tiklamaz).

    Donus: {"found": True, "x","y","matched_text","score"} veya
           {"found": False, "alternatives": [...]}.
    """
    target = (target or "").strip()
    if not target:
        return {"found": False, "error": "Aranacak metin bos olmamali."}
    if items is None:
        png = _screenshot_bytes()
        if png is None:
            return {"success": False, "found": False,
                    "error": "mss paketi kurulu degil ('pip install mss')."}
        try:
            items, _engine = _run_ocr(png)
        except BaseException as exc:  # noqa: BLE001 — SystemExit dahil, bot yasamali
            return {"success": False, "found": False, "error": str(exc)}
    scored = [(d, _score(target, d.get("text", ""))) for d in items]
    scored = [(d, s) for (d, s) in scored if s >= FUZZY_THRESHOLD]
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        alts = sorted([d.get("text", "") for d in (items or []) if d.get("text")])[:10]
        return {"found": True if False else False, "alternatives": alts,
                "message": f"'{target}' ekranda bulunamadi."}
    best, score = scored[0]
    return {"found": True, "x": int(best["x"]), "y": int(best["y"]),
            "matched_text": best.get("text", ""), "score": round(float(score), 3)}


# --- Tool fonksiyonlari ---------------------------------------------------------

def read_screen() -> dict:
    """Ekrani OCR ile okur; metin + koordinat listesi doner."""
    png = _screenshot_bytes()
    if png is None:
        return {"success": False, "error": "mss paketi kurulu degil ('pip install mss')."}
    path = _screenshot_path()
    try:
        path.write_bytes(png)
    except OSError:
        pass
    try:
        items, engine = _run_ocr(png)
    except BaseException as exc:  # noqa: BLE001 — SystemExit dahil
        return {"success": False, "error": str(exc)}
    return {"success": True, "engine": engine, "count": len(items),
            "texts": items, "screenshot": str(path)}


def click_text(target: str, double_click: bool = False) -> dict:
    """Hedef metni bulup tiklar. Eslesme yoksa tiklama YAPMAZ."""
    target = (target or "").strip()
    if not target:
        return {"success": False, "error": "Tiklanacak metin bos olmamali."}
    png = _screenshot_bytes()
    if png is None:
        return {"success": False, "error": "mss paketi kurulu degil ('pip install mss')."}
    try:
        import pyautogui
    except ImportError:
        return {"success": False, "error": "pyautogui paketi kurulu degil ('pip install pyautogui')."}
    try:
        items, engine = _run_ocr(png)
    except BaseException as exc:  # noqa: BLE001 — SystemExit dahil
        return {"success": False, "error": str(exc)}
    found = find_text_coordinates(target, items)
    if not found.get("found"):
        return {"success": False, "error": f"'{target}' ekranda bulunamadi.",
                "alternatives": found.get("alternatives", [])[:10]}
    x, y = int(found["x"]), int(found["y"])
    try:
        pyautogui.moveTo(x, y, duration=0.25)
        time.sleep(0.1)
        if double_click:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        return {"success": True, "x": x, "y": y,
                "matched_text": found.get("matched_text", ""),
                "score": found.get("score", 0.0), "engine": engine,
                "message": f"'{found.get('matched_text', target)}' konumuna tiklandi ({x},{y})."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Tiklama basarisiz: {exc}"}


def click_at(x: int, y: int, double_click: bool = False) -> dict:
    """Verilen koordinata tiklar (OCR gerekmez). Ekran disina tiklama yapmaz."""
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return {"success": False, "error": "Koordinatlar sayi olmali."}
    try:
        import pyautogui
    except ImportError:
        return {"success": False, "error": "pyautogui paketi kurulu degil ('pip install pyautogui')."}
    try:
        width, height = pyautogui.size()
        if not (0 <= x < width and 0 <= y < height):
            return {"success": False,
                    "error": f"Koordinat ekran disinda ({x},{y}; ekran {width}x{height})."}
        pyautogui.moveTo(x, y, duration=0.25)
        time.sleep(0.1)
        if double_click:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        return {"success": True, "x": x, "y": y,
                "message": f"({x},{y}) konumuna tiklandi."}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Tiklama basarisiz: {exc}"}
