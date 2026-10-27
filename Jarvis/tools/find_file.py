"""find_file tool — yerel diskte dosya arama.

Varsayilan dizinler: Masaüstü, Belgeler, İndirilenler, Resimler
(home dizininden otomatik bulunur). Sadece verilen dizinlerin icinde
arama yapar; sistem kritik klasorlere kendiliginden girmez.
"""
from __future__ import annotations

import os

MAX_RESULTS = 10

TOOL_SCHEMA = {
    "name": "find_file",
    "description": (
        "Kullanicinin bilgisayarinda dosya arar. Dosya adinda gecen "
        "kelimeyle (kismi, buyuk-kucuk harf duyarsiz) eslesen dosyalari "
        "listeler. Tek sonuc bulunursa dosya gonderilmek uzere isaretlenir."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Aranan dosya adi/uzanti/anahtar kelime. Ornek: 'rapor', '.docx'",
            },
            "search_dirs": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Aranacak klasorler (opsiyonel). Verilmezse Masaustu, "
                    "Belgeler, Indirilenler ve Resimler taranir."
                ),
            },
        },
        "required": ["query"],
    },
}


def default_search_dirs() -> list[str]:
    home = os.path.expanduser("~")
    candidates = ["Desktop", "Documents", "Downloads", "Pictures"]
    # Turkce Windows'ta klasor adlari farkli olabilir; yaygin alternatifleri de dene.
    candidates += ["Masaüstü", "Belgeler", "İndirilenler", "Resimler"]
    found: list[str] = []
    for name in candidates:
        path = os.path.join(home, name)
        if os.path.isdir(path) and path not in found:
            found.append(path)
    return found


def find_file(query: str, search_dirs: list[str] | str | None = None) -> dict:
    """Dosya arar; sonucu standart tool dict'i olarak doner."""
    query = (query or "").strip()
    if not query:
        return {"found": False, "count": 0, "files": [], "error": "Bos arama sorgusu."}

    if search_dirs is None:
        dirs = default_search_dirs()
    elif isinstance(search_dirs, str):
        dirs = [search_dirs]
    else:
        dirs = list(search_dirs)

    dirs = [d for d in dirs if d and os.path.isdir(d)]
    if not dirs:
        return {"found": False, "count": 0, "files": [], "error": "Aranacak gecerli klasor yok."}

    needle = query.lower()
    matches: list[dict] = []
    for base in dirs:
        for root, _subdirs, files in os.walk(base, onerror=lambda _e: None):
            for fname in files:
                if needle in fname.lower():
                    full = os.path.join(root, fname)
                    try:
                        size_kb = round(os.path.getsize(full) / 1024, 1)
                    except OSError:
                        continue
                    matches.append({"name": fname, "path": full, "size_kb": size_kb})
                    if len(matches) >= MAX_RESULTS:
                        break
            if len(matches) >= MAX_RESULTS:
                break
        if len(matches) >= MAX_RESULTS:
            break

    result: dict = {"found": bool(matches), "count": len(matches), "files": matches}
    if len(matches) == 1:
        # Tek sonuc: bot bu dosyayi otomatik olarak Telegram'a gonderecek.
        result["file_to_send"] = matches[0]["path"]
        result["message"] = f"1 dosya bulundu ve gonderilmeye hazir: {matches[0]['name']}"
    elif len(matches) > 1:
        # Cok sonuc: secim butonlari icin standart belirsizlik formati.
        result["ambiguous"] = True
        result["prompt_text"] = (
            f"'{query}' icin {len(matches)} dosya buldum, hangisini istiyorsun?"
        )
        result["options"] = [
            {"id": str(i), "label": m["name"], "path": m["path"]}
            for i, m in enumerate(matches, start=1)
        ]
        result["tool_name"] = "find_file"
        result["base_args"] = {"query": query}
    return result
