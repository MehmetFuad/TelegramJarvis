"""web_search tool — API keysiz internet aramasi (duckduckgo-search).

Ham sonuclari (baslik/ozet/link) doner; ozetleyip Turkce anlatma isi Gemini'nindir.
"""
from __future__ import annotations

TOOL_SCHEMA = {
    "name": "web_search",
    "description": (
        "Internette metin aramasi yapar; baslik, kisa ozet ve link listesi "
        "doner. Sonuclari KENDI cumlelerinle ozetle, ham linkleri oldugu gibi "
        "kopyalama."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Arama sorgusu.",
            },
            "max_results": {
                "type": "integer",
                "description": "En fazla sonuc sayisi (1-10, varsayilan 5).",
            },
        },
        "required": ["query"],
    },
}


def _get_ddgs():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS
        return DDGS
    except ImportError as exc:
        raise RuntimeError(
            "duckduckgo-search paketi kurulu degil ('pip install duckduckgo-search')."
        ) from exc


def web_search(query: str, max_results: int = 5) -> dict:
    """Arama yapar; sonucu standart tool dict'i olarak doner."""
    query = (query or "").strip()
    if not query:
        return {"success": False, "error": "Arama sorgusu bos olmamali."}
    try:
        max_results = max(1, min(int(max_results or 5), 10))
    except (TypeError, ValueError):
        max_results = 5
    try:
        DDGS = _get_ddgs()
        with DDGS() as ddgs:
            raw = ddgs.text(query, max_results=max_results) or []
        results = [
            {
                "title": str(item.get("title", "")),
                "snippet": str(item.get("body", "")),
                "url": str(item.get("href", "")),
            }
            for item in raw
        ]
        return {"success": True, "results": results}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Arama basarisiz (rate-limit olabilir): {exc}"}
