"""JARVIS config — .env dosyasindaki ayarlari okuyan tek merkezi modul."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _clean_key(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def _parse_key_list() -> list[str]:
    """API anahtarlarini toplar. STANDART KULLANIM: GEMINI_API_KEY_1/_2/_3.

    Sirayla denenir:
      1. GEMINI_API_KEY_1  (tek anahtar kullananlar sadece bunu doldurur)
      2. GEMINI_API_KEY_2  (yedek; _1 limitlenirse devreye girer)
      3. GEMINI_API_KEY_3  (ikinci yedek)
    Geriye uyumluluk icin (belgelerde onerilmez):
      4. GEMINI_API_KEYS="key1,key2" (virgulle ayrilmis liste)
      5. GEMINI_API_KEY (eski tekil alan; listenin sonuna eklenir)
    Bos ve tekrar eden anahtarlar elenir; sira korunur.
    """
    keys: list[str] = []

    def add(value: str) -> None:
        value = _clean_key(value)
        if value and value not in keys:
            keys.append(value)

    for i in (1, 2, 3):
        add(_get_env(f"GEMINI_API_KEY_{i}"))
    for part in _get_env("GEMINI_API_KEYS").replace(";", ",").replace("\n", ",").split(","):
        add(part)
    add(_get_env("GEMINI_API_KEY"))
    return keys


@dataclass
class Settings:
    telegram_bot_token: str = field(default_factory=lambda: _get_env("TELEGRAM_BOT_TOKEN"))
    allowed_telegram_user_id: int = field(
        default_factory=lambda: int(_get_env("ALLOWED_TELEGRAM_USER_ID", "0") or 0)
    )
    gemini_api_key: str = field(default_factory=lambda: _get_env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _get_env("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    gemini_api_keys: list[str] = field(default_factory=_parse_key_list)
    dashboard_host: str = field(default_factory=lambda: _get_env("DASHBOARD_HOST", "127.0.0.1"))
    dashboard_port: int = field(
        default_factory=lambda: int(_get_env("DASHBOARD_PORT", "8000") or 8000)
    )
    log_level: str = field(default_factory=lambda: _get_env("LOG_LEVEL", "INFO"))
    data_dir: Path = field(default_factory=lambda: BASE_DIR / _get_env("DATA_DIR", "data"))

    def validate_for_bot(self) -> list[str]:
        errors: list[str] = []
        if not self.telegram_bot_token or ":" not in self.telegram_bot_token:
            errors.append("TELEGRAM_BOT_TOKEN eksik/gecersiz. .env dosyasini kontrol edin.")
        if not self.allowed_telegram_user_id:
            errors.append("ALLOWED_TELEGRAM_USER_ID eksik. .env dosyasini kontrol edin.")
        if not self.gemini_api_keys:
            errors.append(
                "Gemini anahtari eksik. .env dosyasinda GEMINI_API_KEY_1 doldurulmali. "
                "(Yedekler icin GEMINI_API_KEY_2 / GEMINI_API_KEY_3 kullanilabilir.)"
            )
        return errors

    @property
    def gemini_key_count(self) -> int:
        return len(self.gemini_api_keys or [])


settings = Settings()
