"""open_application — akilli uygulama/oyun acma.

Siralama (ogrenilmis eslesmeler her zaman oncelikli):
  1. apps.json'da tam eslesme → ac.
  2. apps.json'da tek kismi eslesme → ac.
  3. Kisayol indeksinde (shortcuts_cache.json) tam eslesme → ac + apps.json'a ogren.
  4. Fuzzy eslesme (apps + indeks birlikte): tek givenilir aday → ac + ogren;
     birden fazla → ambiguous (butonla sor, secim yine ogrenilir).
  5. Hicbir sey yoksa not_found + yol sorma mesaji (learn_application tool'u ile eklenir).

apps.json boylece zamanla kendi kendine buyuyen bir onbellektir.
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
from pathlib import Path

from config import settings
from tools.shortcut_scanner import load_index

APPS_FILE = settings.data_dir / "apps.json"


def _default_seed_apps() -> dict[str, str]:
    """Her bilgisayarda calisan baslangic uygulamalari.

    Chrome yolu makineye gore degisir (Program Files / Program Files (x86) /
    kullanici kurulumu); var olan ilk yolu kullanir, hicbiri yoksa kaydetmez.
    """
    apps: dict[str, str] = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
    }
    if os.name != "nt":
        return apps
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in chrome_candidates:
        if candidate.is_file():
            apps["chrome"] = str(candidate)
            break
    return apps


SEED_APPS = _default_seed_apps()

FUZZY_THRESHOLD = 0.55

TOOL_SCHEMA = {
    "name": "open_application",
    "description": (
        "Bilgisayarda uygulama veya oyun acar. Exe adi ile gorunen isim farkli "
        "olsa bile kismi/yanlis yazimla bulur (kisaltilmis isim yeterli). Emin "
        "olamadin mi secenegi tahmin etme; ambiguous donerse kullaniciya sor. "
        "Kullanici bir .exe yolu verirse acmak yerine learn_application kullan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Acilacak uygulama/oyun adi (kismi yazim yeterli).",
            },
        },
        "required": ["name"],
    },
}

LEARN_APP_SCHEMA = {
    "name": "learn_application",
    "description": (
        "Yeni bir uygulamayi kalici olarak ogren (apps.json'a kaydet). "
        "Kullanici bir uygulamanin .exe yolunu verdiginde bunu kullan; "
        "sonra open_application ile acmayi dene."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Kayit adi (kisa, kucuk harf)."},
            "path": {"type": "string", "description": "Uygulamanin tam .exe yolu veya komut adi."},
        },
        "required": ["name", "path"],
    },
}


def _normalize(raw: object) -> dict[str, str]:
    if isinstance(raw, dict) and "apps" in raw and isinstance(raw["apps"], list):
        out: dict[str, str] = {}
        for item in raw["apps"]:
            if isinstance(item, dict) and item.get("name") and item.get("path"):
                out[str(item["name"])] = str(item["path"])
        return out
    if isinstance(raw, dict) and "apps" in raw and isinstance(raw["apps"], dict):
        return {str(k): str(v) for k, v in raw["apps"].items()}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if not k.startswith("_")}
    return {}


def load_apps() -> dict[str, str]:
    if APPS_FILE.is_file():
        try:
            apps = _normalize(json.loads(APPS_FILE.read_text(encoding="utf-8")))
            if apps:
                return apps
        except (OSError, ValueError):
            pass
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    APPS_FILE.write_text(json.dumps(SEED_APPS, indent=2, ensure_ascii=False), encoding="utf-8")
    return dict(SEED_APPS)


def save_apps(apps: dict[str, str]) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    APPS_FILE.write_text(json.dumps(apps, indent=2, ensure_ascii=False), encoding="utf-8")


def learn_application(name: str, path: str) -> dict:
    """Manuel/ogrrenilmis eslesmeyi apps.json'a kaydeder."""
    name = (name or "").strip().lower()
    path = (path or "").strip().strip('"')
    if not name or not path:
        return {"success": False, "error": "Uygulama adi ve yolu bos olmamali."}
    if not (os.path.isfile(path) or shutil.which(path)):
        return {"success": False, "error": f"Yol gecerli degil (dosya bulunamadi): {path}"}
    apps = load_apps()
    apps[name] = path
    try:
        save_apps(apps)
    except OSError as exc:
        return {"success": False, "error": f"Kaydedilemedi: {exc}"}
    return {"success": True, "name": name, "path": path,
            "message": f"'{name}' ogrenildi. Simdi acmayi deneyebilirsin."}


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().replace("-", " ").split() if t}


def _fuzzy_score(query: str, candidate: str) -> float:
    """0-1 arasi benzerlik: alt-string + kelime kapsama + sira-orani."""
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c:
        return 0.9
    qt, ct = _tokens(q), _tokens(c)
    if qt and qt <= ct:
        # Sorgudaki tum kelimeler adayda var ("kisa isim" -> "Uzun Uygulama Adi").
        return 0.85
    overlap = len(qt & ct) / max(len(qt), 1) if qt else 0.0
    ratio = difflib.SequenceMatcher(None, q, c).ratio()
    try:
        from rapidfuzz import fuzz

        ratio = max(ratio, fuzz.token_set_ratio(q, c) / 100.0)
    except ImportError:
        pass
    return max(overlap * 0.8, ratio)


def find_candidates(query: str, names: list[str], limit: int = 8) -> list[tuple[str, float]]:
    scored = [(n, _fuzzy_score(query, n)) for n in names]
    scored = [(n, s) for (n, s) in scored if s >= FUZZY_THRESHOLD]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def open_application(name: str) -> dict:
    """Uygulamayi akilli eslesmeyle acar (ogrenen onbellek)."""
    name = (name or "").strip()
    if not name:
        return {"not_found": True, "available_apps": sorted(load_apps().keys())}
    query = name.lower()

    # 1-2) Ogrenilmis eslesmeler (apps.json) oncelikli.
    apps = load_apps()
    lowered = {key.lower(): key for key in apps}
    if query in lowered:
        return _launch(lowered[query], apps[lowered[query]])
    partial = [key for key in apps if query in key.lower() or key.lower() in query]
    if len(partial) == 1:
        return _launch(partial[0], apps[partial[0]])

    # 3) Kisayol indeksinde tam eslesme → ac + ogren (acilamazsa hatayi don).
    index = load_index()
    lowered_idx = {key.lower(): key for key in index}
    if query in lowered_idx:
        real = lowered_idx[query]
        return _launch_and_learn(query, real, index[real])

    # 4) Fuzzy: apps + indeks birlikte (apps agirlikli).
    pool = list(apps.keys()) + [k for k in index if k.lower() not in lowered]
    scored = find_candidates(name, pool)
    if len(scored) == 1:
        pick = scored[0][0]
        if pick in apps:
            return _launch(pick, apps[pick])
        return _launch_and_learn(query, pick, index[pick])
    if len(scored) > 1:
        return _ambiguous(name, [n for (n, _s) in scored])

    # 5) Hicbir sey yok.
    sample = sorted(list(apps.keys()) + list(index.keys()))[:10]
    return {
        "not_found": True,
        "available_apps": sample,
        "message": (
            f"'{name}' adinda bir uygulama bulamadim. Uygulamanin .exe yolunu "
            "veya kisayolun tam adini verir misin? Verdigin bilgiyi kaydedip acmayi deneyecegim."
        ),
    }


def _ambiguous(query: str, candidates: list[str]) -> dict:
    ordered = sorted(candidates)
    return {
        "ambiguous": True,
        "prompt_text": f"'{query}' icin birden fazla eslesme var, hangisini acayim?",
        "options": [{"id": str(i), "label": c} for i, c in enumerate(ordered, start=1)],
        "tool_name": "open_application",
        "base_args": {},
        "choice_param": "name",
        "candidates": ordered,
    }


def _launch_and_learn(key: str, display_name: str, path: str) -> dict:
    """Ac + (acilirsa) apps.json'a ogren. Acilamazsa hata dict'i doner."""
    result = _launch(display_name, path)
    if result.get("opened"):
        try:
            apps = load_apps()
            apps.setdefault(key, path)
            save_apps(apps)
            result["learned_as"] = key
        except OSError:
            pass
    return result


def _launch(display_name: str, path: str) -> dict:
    if not path:
        return {"opened": False, "app": display_name, "error": "Bos yol."}
    has_sep = ("\\" in path or "/" in path)
    if has_sep and not os.path.isfile(path):
        return {"opened": False, "app": display_name, "error": f"Dosya bulunamadi: {path}"}
    try:
        subprocess.Popen([path])  # noqa: S603 — yol kayitli/indeksli uygulamadan gelir
        return {"opened": True, "app": display_name,
                "message": f"'{display_name}' uygulamasi acildi."}
    except Exception as exc:  # noqa: BLE001
        return {"opened": False, "app": display_name, "error": f"Acilamadi: {exc}"}
