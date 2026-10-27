"""Bekleyen-aksiyon akisi icin saf (telegram-bagimsiz) yardimcilar.

Bu modul telegram paketini import etmez; boylece testler ve beyin katmani
dogrudan kullanabilir. Buton insasi ve gonderimi telegram_bot/bot.py'dedir.
"""
from __future__ import annotations

YES_WORDS = {"evet", "e", "tamam", "olur", "onayla", "onayliyorum", "yap", "calistir"}
NO_WORDS = {"hayir", "hayır", "h", "iptal", "vazgec", "vazgeç", "yok", "yapma"}

MAX_BUTTONS = 8


def parse_callback(data: str) -> tuple[str | None, str | None]:
    """callback_data'yi cozer: ("confirm", "yes"|"no") veya ("choice", id)."""
    if not data:
        return None, None
    if data == "confirm:yes":
        return "confirm", "yes"
    if data == "confirm:no":
        return "confirm", "no"
    if data.startswith("choice:"):
        option_id = data.split(":", 1)[1].strip()
        if option_id:
            return "choice", option_id
    return None, None


def is_explicit_answer(text: str) -> str | None:
    """Serbest metin acik bir cevap mi? Donus: "yes" | "no" | "choice:<id>" | None.

    Sadece tek kelimelik / kisa net cevaplar kabul edilir; normal sohbet
    ("evet, bir de sunu yap" gibi) cevap sayilmaz.
    """
    cleaned = (text or "").strip().lower()
    if not cleaned or len(cleaned) > 12:
        return None
    if cleaned.isdigit():
        return f"choice:{cleaned}"
    if cleaned in YES_WORDS:
        return "yes"
    if cleaned in NO_WORDS:
        return "no"
    return None


def find_option(options: list[dict], option_id: str) -> dict | None:
    for opt in options or []:
        if str(opt.get("id")) == str(option_id):
            return opt
    return None


def numbered_list(prompt_text: str, options: list[dict]) -> str:
    """Secenekleri numarali metin olarak dizer (butonlarin yaninda metin de olur)."""
    lines = [prompt_text]
    for i, opt in enumerate(options[:MAX_BUTTONS], start=1):
        lines.append(f"{i}. {opt.get('label', '?')}")
    if len(options) > MAX_BUTTONS:
        lines.append(f"(+{len(options) - MAX_BUTTONS} secenek daha var, ismini yazarak secebilirsin.)")
    return "\n".join(lines)
