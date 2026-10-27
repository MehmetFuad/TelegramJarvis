"""JARVIS dashboard backend — FastAPI, sadece 127.0.0.1 dinler.

Endpoint'ler:
    GET  /                        -> kontrol paneli (index.html)
    GET  /api/status              -> bot/Gemini durumu (boolean'lar, asla secret yok)
    GET  /api/logs?limit=50       -> son log kayitlari
    GET  /api/decisions?limit=50  -> onay/ret/secim gecmisi
    GET  /api/apps                -> kayitli uygulamalar
    POST /api/apps                -> {"action":"add","name","path"} veya {"action":"delete","name"}
    GET  /api/channels            -> kayitli kanallar
    POST /api/channels            -> {"action":"add","name","channel_id"} veya {"action":"delete","name"}
    GET  /api/health              -> {"status": "ok"}
    POST /api/shutdown            -> duzgun kapatma ister
    POST /api/chat                -> masaustu metin komutu (Telegram ile ayni cekirdek)
    POST /api/chat/resolve        -> masaustu onay/secim cozumu
    POST /api/voice_command       -> ses kaydi (base64) -> transkript + cevap
    GET  /api/files?rel=...       -> data/ altindaki uretilmis dosyalari indirir
    POST /api/scan-shortcuts      -> kisayol indeksini yeniler

run.py tarafindan ayni process'te calistirilir (run_dashboard).
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import settings
from core import status as shared_status
from core.channel_flow import (
    DESKTOP_CHANNEL,
    process_text,
    resolve_choice,
    resolve_confirmation,
    session_key,
    transcribe_and_answer,
)
from core.logger import get_recent_decisions, get_recent_logs

log = logging.getLogger("jarvis.dashboard")

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "static" / "index.html"

DESKTOP_KEY = session_key(DESKTOP_CHANNEL, "local")

app = FastAPI(title="JARVIS Dashboard", docs_url=None, redoc_url=None, openapi_url=None)


class AppChange(BaseModel):
    action: str  # "add" | "delete"
    name: str = ""
    path: str = ""


class ChannelChange(BaseModel):
    action: str  # "add" | "delete"
    name: str = ""
    channel_id: str = ""


@app.get("/")
async def index():
    if not INDEX_FILE.is_file():
        raise HTTPException(status_code=500, detail="Arayuz dosyasi bulunamadi.")
    return FileResponse(INDEX_FILE)


@app.get("/api/status")
async def api_status():
    from tools import list_tools

    snap = shared_status.snapshot()
    last_msg = snap["last_message_at"]
    last_gem = snap["last_gemini_at"]
    return {
        "bot_running": snap["bot_running"],
        "gemini_ok": snap["gemini_ok"],
        "uptime_seconds": snap["uptime_seconds"],
        "message_count": snap["message_count"],
        "last_message_at": _fmt_ts(last_msg),
        "last_gemini_at": _fmt_ts(last_gem),
        # Sadece boolean: gercek degerler ASLA donulmez.
        "telegram_configured": bool(settings.telegram_bot_token),
        "gemini_configured": bool(settings.gemini_api_keys or settings.gemini_api_key),
        "gemini_key_count": len(settings.gemini_api_keys or []),
        "gemini_model": settings.gemini_model,
        "tool_count": len(list_tools()),
        "last_crash": snap.get("last_crash"),
    }


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


@app.post("/api/shutdown")
async def api_shutdown():
    shared_status.request_stop()
    log.info("Dashboard: kapatma istendi.")
    return {"ok": True, "message": "Kapatiliyor."}


def _fmt_ts(epoch: float | None) -> str | None:
    if not epoch:
        return None
    import time

    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


@app.get("/api/logs")
async def api_logs(limit: int = 50):
    return {"logs": get_recent_logs(limit)}


@app.get("/api/decisions")
async def api_decisions(limit: int = 50):
    return {"decisions": get_recent_decisions(limit)}


@app.get("/api/apps")
async def api_apps():
    from tools.open_application import load_apps

    apps = load_apps()
    return {"apps": [{"name": k, "path": v} for k, v in sorted(apps.items())]}


@app.post("/api/apps")
async def api_apps_change(change: AppChange):
    from tools.open_application import APPS_FILE, load_apps

    apps = load_apps()
    action = change.action.strip().lower()
    name = change.name.strip()
    if action == "add":
        if not name or not change.path.strip():
            raise HTTPException(status_code=400, detail="Uygulama adi ve dosya yolu gerekli.")
        apps[name] = change.path.strip()
        _write_flat(APPS_FILE, apps)
        log.info("Dashboard: uygulama eklendi: %s", name)
        return {"ok": True, "apps": [{"name": k, "path": v} for k, v in sorted(apps.items())]}
    if action == "delete":
        key = next((k for k in apps if k.lower() == name.lower()), None)
        if key is None:
            raise HTTPException(status_code=404, detail="Uygulama bulunamadi.")
        del apps[key]
        _write_flat(APPS_FILE, apps)
        log.info("Dashboard: uygulama silindi: %s", key)
        return {"ok": True, "apps": [{"name": k, "path": v} for k, v in sorted(apps.items())]}
    raise HTTPException(status_code=400, detail="action 'add' veya 'delete' olmali.")


def _write_flat(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


@app.get("/api/channels")
async def api_channels():
    from tools.youtube import load_channels

    channels = load_channels()
    return {"channels": [{"name": k, "channel_id": v} for k, v in sorted(channels.items())]}


@app.post("/api/channels")
async def api_channels_change(change: ChannelChange):
    from tools.youtube import load_channels, register_channel, save_channels

    action = change.action.strip().lower()
    name = change.name.strip().lower()
    if action == "add":
        result = register_channel(name, change.channel_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Kaydedilemedi."))
        log.info("Dashboard: kanal eklendi: %s", name)
        channels = load_channels()
        return {"ok": True, "channels": [{"name": k, "channel_id": v} for k, v in sorted(channels.items())]}
    if action == "delete":
        channels = load_channels()
        key = next((k for k in channels if k.lower() == name), None)
        if key is None:
            raise HTTPException(status_code=404, detail="Kanal bulunamadi.")
        del channels[key]
        save_channels(channels)
        log.info("Dashboard: kanal silindi: %s", key)
        return {"ok": True, "channels": [{"name": k, "channel_id": v} for k, v in sorted(channels.items())]}
    raise HTTPException(status_code=400, detail="action 'add' veya 'delete' olmali.")


class ChatIn(BaseModel):
    message: str = ""


class ChatResolveIn(BaseModel):
    kind: str = ""  # "confirm" | "choice"
    value: str = ""  # "yes" | "no" | option_id


class VoiceIn(BaseModel):
    audio_base64: str = ""
    mime_type: str = "audio/webm"


class ScanIn(BaseModel):
    force: bool = True


def _file_refs(files: list[str]) -> list[dict]:
    """Mutlak dosya yollari -> guvenli indirme linkleri (data/ icinde olmali)."""
    refs = []
    data_root = settings.data_dir.resolve()
    for path in files or []:
        try:
            rel = Path(path).resolve().relative_to(data_root).as_posix()
        except (OSError, ValueError):
            continue
        refs.append({"name": Path(path).name, "url": f"/api/files?rel={rel}"})
    return refs


def _pending_view(pending: dict | None) -> dict | None:
    if not pending:
        return None
    return {
        "type": pending.get("type"),
        "options": [
            {"id": str(o.get("id")), "label": str(o.get("label", "?"))}
            for o in (pending.get("options") or [])
        ],
    }


@app.post("/api/chat")
async def api_chat(body: ChatIn):
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Mesaj bos olmamali.")
    result = await asyncio.to_thread(process_text, DESKTOP_KEY, text)
    return {"reply": result.get("reply", ""),
            "files": _file_refs(result.get("files", [])),
            "pending": _pending_view(result.get("pending"))}


@app.post("/api/chat/resolve")
async def api_chat_resolve(body: ChatResolveIn):
    kind = body.kind.strip().lower()
    value = body.value.strip()
    if kind == "confirm" and value in ("yes", "no"):
        result = await asyncio.to_thread(resolve_confirmation, DESKTOP_KEY, value == "yes")
    elif kind == "choice" and value:
        result = await asyncio.to_thread(resolve_choice, DESKTOP_KEY, value)
    else:
        raise HTTPException(status_code=400, detail="kind 'confirm'/'choice', value 'yes'/'no'/id olmali.")
    return {"reply": result.get("reply", ""),
            "files": _file_refs(result.get("files", [])),
            "pending": None}


@app.post("/api/voice_command")
async def api_voice_command(body: VoiceIn):
    try:
        audio = base64.b64decode(body.audio_base64 or "", validate=True)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Ses verisi cozulemedi (base64).")
    result = await asyncio.to_thread(transcribe_and_answer, DESKTOP_KEY, audio,
                                     body.mime_type or "audio/webm")
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return {"transcript": result.get("transcript", ""),
            "reply": result.get("reply", ""),
            "files": _file_refs(result.get("files", [])),
            "pending": _pending_view(result.get("pending"))}


@app.get("/api/files")
async def api_files(rel: str = ""):
    data_root = settings.data_dir.resolve()
    try:
        target = (data_root / rel).resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="Gecersiz dosya yolu.")
    try:
        target.relative_to(data_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Erisim engellendi.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Dosya bulunamadi.")
    return FileResponse(target, filename=target.name)


@app.post("/api/scan-shortcuts")
async def api_scan_shortcuts(body: ScanIn):
    from tools.shortcut_scanner import scan_shortcuts

    result = await asyncio.to_thread(scan_shortcuts, body.force)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


async def run_dashboard() -> None:
    """run.py tarafindan cagrilir: sadece localhost dinler.

    log_config=None ZORUNLU: uvicorn'un kendi dictConfig'i core/logger.py ile
    catisip "Unable to configure formatter" hatasiyla servisi dusuruyordu.
    Boylece tek logging kurulumu (bizimki) gecerli olur.
    """
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.dashboard_host or "127.0.0.1",
            port=settings.dashboard_port,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    )
    log.info("Dashboard dinliyor: http://%s:%s", settings.dashboard_host or "127.0.0.1",
             settings.dashboard_port)
    await server.serve()
