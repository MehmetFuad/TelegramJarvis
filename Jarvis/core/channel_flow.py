"""Ortak konusma cekirdegi — Telegram, masaustu metin ve ses ayni akisi kullanir.

Her kanal kendi session anahtariyla calisir ("telegram:<id>", "desktop_app:local"),
boylece gecmis ve bekleyen onaylar kanallar arasi karismaz.

Fonksiyonlar telegram/HTTP bagimsizdir; arayuz katmani (bot.py / server.py)
sadece sonucu gosterir (mesaj gonderme, buton, dosya linki).
"""
from __future__ import annotations

import logging
import os

from config import settings
from core.gemini_brain import finalize_with_tool_result, run_conversation
from core.logger import log_decision
from core.pending_flow import find_option, is_explicit_answer
from core.session_state import (
    add_message,
    clear_pending_action,
    get_history,
    get_pending_action,
)
from tools import execute_tool

log = logging.getLogger("jarvis.flow")

TELEGRAM_CHANNEL = "telegram"
DESKTOP_CHANNEL = "desktop_app"

TIMEOUT_TEXT = "Bu islem zaman asimina ugradi, tekrar dener misin?"


def session_key(channel: str, user: str | int) -> str:
    return f"{channel}:{user}"


def _uid_from_key(key: str) -> int:
    try:
        tail = str(key).rsplit(":", 1)[1]
        return int(tail) if tail.isdigit() else 0
    except (IndexError, ValueError):
        return 0


def process_text(key: str, text: str) -> dict:
    """Bir metin komutu uctan uca isler: {reply, files, pending|None}."""
    uid = _uid_from_key(key)

    # Bekleyen aksiyon varken acik cevap degilse eski aksiyon iptal olur.
    pending = get_pending_action(key)
    if pending is not None:
        answer = is_explicit_answer(text)
        ptype = pending.get("type")
        if (ptype == "confirmation" and answer in ("yes", "no")) or (
            ptype == "choice" and answer is not None and answer.startswith("choice:")
        ):
            if answer in ("yes", "no"):
                return resolve_confirmation(key, answer == "yes")
            return resolve_choice(key, answer.split(":", 1)[1])
        clear_pending_action(key)
        log_decision(uid, "IPTAL", f"yeni mesaj eski aksiyonu iptal etti: {text[:80]!r}")
        add_message(key, "tool", "Bekleyen soru iptal edildi, kullanici yeni bir sey sordu.")

    history = get_history(key)
    add_message(key, "user", text)
    log.info("Komut [%s]: %r", key, text[:200])
    result = run_conversation(text, history)
    for entry in result.get("transcript", []):
        add_message(key, entry.get("role", "tool"), entry.get("content", ""))
    reply = result.get("reply", "Bos cevap geldi, tekrar dener misin?")
    add_message(key, "assistant", reply)
    return {"reply": reply, "files": result.get("files", []), "pending": result.get("pending")}


def resolve_confirmation(key: str, decision: bool) -> dict:
    """Onay cozumu: {reply, files}. Buton ve yazi cevaplari ortaktir."""
    uid = _uid_from_key(key)
    pending = get_pending_action(key)
    if pending is None or pending.get("type") != "confirmation":
        return {"reply": TIMEOUT_TEXT if pending is None else "Bekleyen bir onay yok.",
                "files": [], "expired": True}
    clear_pending_action(key)
    tool_name = pending.get("tool_name", "?")
    tool_args = pending.get("tool_args", {})
    if not decision:
        log_decision(uid, "RET", f"{tool_name} {tool_args}",
                     tool_name=tool_name, tool_args=tool_args, user_choice="HAYIR")
        add_message(key, "tool", "Kullanici onayi: HAYIR (islem iptal edildi).")
        add_message(key, "assistant", "Iptal edildi.")
        return {"reply": "Iptal edildi.", "files": []}

    log_decision(uid, "ONAY", f"{tool_name} {tool_args}",
                 tool_name=tool_name, tool_args=tool_args, user_choice="EVET")
    add_message(key, "tool", "Kullanici onayi: EVET.")
    result = execute_tool(tool_name, tool_args)
    files = [result["file_to_send"]] if result.get("file_to_send") else []
    summary = {k: v for k, v in result.items() if k != "file_to_send"}
    add_message(key, "tool", f"Onayli calisma sonucu: {summary}"[:1500])
    event = f"Kullanici islemi onayladi ve '{tool_name}' calisti. Sonuc: {summary}."
    reply = finalize_with_tool_result(get_history(key), event)
    add_message(key, "assistant", reply)
    return {"reply": reply, "files": files}


def resolve_choice(key: str, option_id: str) -> dict:
    """Secim cozumu: {reply, files}."""
    uid = _uid_from_key(key)
    pending = get_pending_action(key)
    if pending is None or pending.get("type") != "choice":
        return {"reply": TIMEOUT_TEXT if pending is None else "Bekleyen bir secim yok.",
                "files": [], "expired": True}
    option = find_option(pending.get("options", []), option_id)
    if option is None:
        return {"reply": "Gecersiz secim, listeden bir secenek sec.",
                "files": [], "expired": False}
    clear_pending_action(key)
    tool_name = pending.get("tool_name", "?")
    label = str(option.get("label", "?"))
    log_decision(uid, "SECIM", f"{tool_name} -> {label}", tool_name=tool_name, user_choice=label)
    add_message(key, "tool", f"Kullanici secimi: {label}.")

    files: list[str] = []
    summary: dict = {}
    if option.get("path") and os.path.isfile(str(option["path"])):
        files = [str(option["path"])]
        summary = {"sent_file": label}
    else:
        choice_param = pending.get("choice_param")
        if choice_param:
            args = dict(pending.get("base_args", {}))
            args[choice_param] = label
            result = execute_tool(tool_name, args)
            if result.get("file_to_send"):
                files = [result["file_to_send"]]
            summary = {k: v for k, v in result.items() if k != "file_to_send"}
        else:
            summary = {"secim": label, "uyari": "secim cozumu tanimsiz"}
    add_message(key, "tool", f"Secim sonucu: {summary}"[:1500])
    event = f"Kullanici '{label}' secenegini secti. Sonuc: {summary}."
    reply = finalize_with_tool_result(get_history(key), event)
    add_message(key, "assistant", reply)
    return {"reply": reply, "files": files}


def transcribe_and_answer(key: str, audio_bytes: bytes, mime_type: str = "audio/webm") -> dict:
    """Ses kaydini metne cevirip normal akisa sokar: {transcript, reply, files}."""
    from core.status import mark_gemini

    try:
        from google import genai  # noqa: F401  (paket kontrolu)
    except ImportError:
        return {"error": "Ses icin google-genai paketi gerekli ('pip install google-genai')."}
    from config import settings as _settings
    if not (_settings.gemini_api_keys or _settings.gemini_api_key):
        return {"error": "GEMINI_API_KEY_1 eksik."}
    if not audio_bytes or len(audio_bytes) > 8 * 1024 * 1024:
        return {"error": "Ses verisi bos veya cok buyuk (en fazla 8 MB)."}
    try:
        from core.gemini_brain import transcribe_with_failover

        transcript = transcribe_with_failover(audio_bytes, mime_type or "audio/webm")
        mark_gemini(True)
        if not transcript:
            return {"error": "Seste anlasilir bir konusma bulunamadi."}
        if len(transcript) < 4:
            # Cok kisa/belirsiz transkript: yanlis islem yapma, tekrar iste.
            # (Orn. "beni ara" gibi yanlis anlasilmis tek kelimelik cikti.)
            return {
                "transcript": transcript,
                "reply": (
                    f"Sizi tam anlayamadim, kulagima '{transcript}' gibi geldi. "
                    "Lutfen komutu biraz daha yavas ve net tekrar soyler misin?"
                ),
                "files": [],
                "pending": None,
            }
        out = process_text(key, transcript)
        out["transcript"] = transcript
        return out
    except Exception as exc:  # noqa: BLE001
        log.exception("Ses isleme hatasi: %s", exc)
        try:
            mark_gemini(False)
        except Exception:  # noqa: BLE001
            pass
        return {"error": "Ses islenemedi, tekrar dener misin? (Detay terminalde.)"}
