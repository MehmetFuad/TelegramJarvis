"""youtube tool — kayitli kanallarin son videosunu RSS ile acma.

API key YOK: https://www.youtube.com/feeds/videos.xml?channel_id=... adresi
feedparser ile okunur; feed'in ilk girdisi en yeni videodur.
Kanal kayitlari data/channels.json'da {"ad": "UC..."} formatinda tutulur.
"""
from __future__ import annotations

import json
import webbrowser

from config import settings

CHANNELS_FILE = settings.data_dir / "channels.json"
RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

GET_LATEST_VIDEO_SCHEMA = {
    "name": "get_latest_video",
    "description": (
        "Kayitli bir YouTube kanalinin EN SON yuklenen videosunu varsayilan "
        "tarayicida direkt acar (arama sayfasi degil, videonun kendisi). "
        "Kanal kayitli degilse once channel_id sorulmali, sonra register_channel "
        "ile kaydedilip tekrar denenmeli."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "channel_name": {
                "type": "string",
                "description": "Kanal adi (channels.json'daki kayit adi, kucuk harf duyarsiz).",
            },
        },
        "required": ["channel_name"],
    },
}

REGISTER_CHANNEL_SCHEMA = {
    "name": "register_channel",
    "description": (
        "Yeni bir YouTube kanalini channels.json'a kaydeder. channel_id, kanal "
        "sayfasindan bulunur (24 karakter, UC ile baslar)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Kayit adi (kisa, kucuk harf; ornek: 'ornek-kanal').",
            },
            "channel_id": {
                "type": "string",
                "description": "Kanalin channel_id degeri (UC ile baslar).",
            },
        },
        "required": ["name", "channel_id"],
    },
}


def _normalize(raw: object) -> dict[str, str]:
    """channels.json'un farkli formatlarini {ad: channel_id} sozlugune cevirir."""
    if not isinstance(raw, dict):
        return {}
    boxed = raw.get("channels")
    if isinstance(boxed, dict):
        items = boxed
    elif isinstance(boxed, list):
        # Eski placeholder/liste formati: [{"name":..., "channel_id":...}]
        out: dict[str, str] = {}
        for item in boxed:
            if isinstance(item, dict) and item.get("name") and item.get("channel_id"):
                out[str(item["name"])] = str(item["channel_id"])
        return out
    elif "channels" not in raw:
        items = {k: v for k, v in raw.items() if not k.startswith("_")}
    else:
        return {}
    return {str(k): str(v) for k, v in items.items()}


def load_channels() -> dict[str, str]:
    if CHANNELS_FILE.is_file():
        try:
            channels = _normalize(json.loads(CHANNELS_FILE.read_text(encoding="utf-8")))
            if channels:
                return channels
        except (OSError, ValueError):
            pass
    return {}


def save_channels(channels: dict[str, str]) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    CHANNELS_FILE.write_text(
        json.dumps(channels, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_latest_video(channel_name: str) -> dict:
    """Kayitli kanalin son videosunu tarayicida acar."""
    try:
        import feedparser
    except ImportError:
        return {"success": False, "error": "feedparser paketi kurulu degil ('pip install feedparser')."}

    name = (channel_name or "").strip()
    if not name:
        return {"success": False, "error": "Kanal adi bos olmamali."}
    channels = load_channels()
    lowered = {k.lower(): (k, v) for k, v in channels.items()}
    if name.lower() not in lowered:
        return {
            "not_found": True,
            "channel_name": name,
            "message": (
                f"'{name}' kayitli kanallar arasinda yok. Kanalin channel_id'sini "
                "biliyor musun? (Kanal sayfasina gidip kaynagi goruntuyleyerek ya da "
                "bir online aractan bulunabilir.)"
            ),
        }
    display, channel_id = lowered[name.lower()]
    try:
        feed = feedparser.parse(RSS_URL.format(channel_id=channel_id))
        entries = getattr(feed, "entries", []) or []
        if not entries:
            return {"success": False, "error": f"'{display}' icin video bulunamadi (RSS bosa dondu)."}
        video_url = entries[0].get("link", "")
        video_title = entries[0].get("title", "")
        if not video_url:
            return {"success": False, "error": f"'{display}' icin video baglantisi okunamadi."}
        webbrowser.open(video_url)
        return {
            "success": True,
            "opened_url": video_url,
            "message": f"'{display}' kanalinin son videosu acildi: {video_title or video_url}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"Video alinamadi: {exc}"}


def register_channel(name: str, channel_id: str) -> dict:
    """Kanali channels.json'a kaydeder."""
    name = (name or "").strip().lower()
    channel_id = (channel_id or "").strip()
    if not name or not channel_id:
        return {"success": False, "error": "Kanal adi ve channel_id bos olmamali."}
    if not (channel_id.startswith("UC") and len(channel_id) >= 10):
        return {
            "success": False,
            "error": "channel_id gecersiz gorunuyor (UC ile baslayan uzun bir kod olmali).",
        }
    channels = load_channels()
    channels[name] = channel_id
    try:
        save_channels(channels)
    except OSError as exc:
        return {"success": False, "error": f"Kaydedilemedi: {exc}"}
    return {
        "success": True,
        "name": name,
        "channel_id": channel_id,
        "message": f"'{name}' kanali kaydedildi. Simdi son videosunu acabilirim.",
    }
