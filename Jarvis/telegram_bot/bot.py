"""JARVIS Telegram bot — Faz 8: ortak cekirdek (channel_flow) uzerinden calisir.

Telegram kanali session anahtari "telegram:<user_id>"dir; masaustu
uygulamasi "desktop_app:local" kullanir (karismaz).
Buton verisi callback_data'da degil session_state'teki pending_action'da tutulur.
"""
from __future__ import annotations

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings
from core import channel_flow as flow
from core.pending_flow import MAX_BUTTONS, parse_callback
from core.session_state import (
    clear_history,
    clear_pending_action,
    get_pending_action,
    set_pending_action,
)
from core.status import mark_message, request_stop, set_bot_running
from telegram_bot.auth import is_authorized, reject_unauthorized

log = logging.getLogger("jarvis.bot")

MAX_MESSAGE_LEN = 4000
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
TIMEOUT_TEXT = "Bu islem zaman asimina ugradi, tekrar dener misin?"


def _key(user_id: int) -> str:
    return flow.session_key(flow.TELEGRAM_CHANNEL, user_id)


async def send_processing_notice(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Isleniyor, birazdan sonucu gonderecegim..."
        )


async def send_long_text(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return
    for i in range(0, len(text), MAX_MESSAGE_LEN):
        await message.reply_text(text[i : i + MAX_MESSAGE_LEN])


async def send_files(update: Update, files: list[str]) -> None:
    """Tool'larin urettigi dosyalari Telegram'a gonderir."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    for path in files:
        if not path or not os.path.isfile(path):
            log.warning("Gonderilecek dosya bulunamadi: %r", path)
            continue
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                with open(path, "rb") as fh:
                    await chat.send_photo(photo=fh, caption=os.path.basename(path))
            else:
                with open(path, "rb") as fh:
                    await chat.send_document(document=fh, filename=os.path.basename(path))
            log.info("Dosya gonderildi: %s", path)
        except Exception as exc:  # noqa: BLE001
            log.exception("Dosya gonderilemedi (%s): %s", path, exc)
            await message.reply_text(f"Dosya bulunmustu ama gonderilemedi: {os.path.basename(path)}")


async def send_files_from_chat(chat, notify, files: list[str]) -> None:
    for path in files:
        if not path or not os.path.isfile(path):
            continue
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                with open(path, "rb") as fh:
                    await chat.send_photo(photo=fh, caption=os.path.basename(path))
            else:
                with open(path, "rb") as fh:
                    await chat.send_document(document=fh, filename=os.path.basename(path))
        except Exception as exc:  # noqa: BLE001
            log.exception("Dosya gonderilemedi (%s): %s", path, exc)
            await notify.reply_text(f"Dosya gonderilemedi: {os.path.basename(path)}")


async def _keep_typing(chat, stop_event: asyncio.Event) -> None:
    """Gemini cevaplarken typing gostergesini canli tutar."""
    try:
        while not stop_event.is_set():
            try:
                await chat.send_action(ChatAction.TYPING)
            except Exception:  # noqa: BLE001 — gosterge basarisizligi onemsiz
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        pass


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Evet", callback_data="confirm:yes"),
          InlineKeyboardButton("Hayir", callback_data="confirm:no")]]
    )


def _choice_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(str(opt.get("label", "?"))[:60], callback_data=f"choice:{opt.get('id')}")]
        for opt in (options or [])[:MAX_BUTTONS]
    ]
    return InlineKeyboardMarkup(rows)


async def _remove_markup(context: ContextTypes.DEFAULT_TYPE, key: str, message=None) -> None:
    """Butonlari kaldir (cift tiklamayi onler)."""
    try:
        if message is not None:
            await message.edit_reply_markup(reply_markup=None)
            return
        pending = get_pending_action(key)
        if pending and pending.get("chat_id") and pending.get("message_id"):
            await context.bot.edit_message_reply_markup(
                chat_id=pending["chat_id"], message_id=pending["message_id"], reply_markup=None
            )
    except Exception:  # noqa: BLE001 — mesaj silinmisse onemsiz
        pass


async def _deliver_resolution(chat, notify, result: dict) -> None:
    """Cozum sonucunu gonder: once dosyalar, sonra metin."""
    if result.get("files"):
        await send_files_from_chat(chat, notify, result["files"])
    await notify.reply_text((result.get("reply") or "")[:MAX_MESSAGE_LEN])


# --- Komutlar ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text(
        "Merhaba! Ben JARVIS.\n"
        "Su an Faz 8 modundayim: uygulamalarini ismen bulup acabilir, medyayi kontrol edebilirim.\n"
        "Komutlar: /help /ping /reset /kapat"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text(
        "JARVIS Faz 8 yardim:\n"
        "/start - selamlama\n"
        "/help - bu mesaj\n"
        "/ping - botun yasadigini dogrular\n"
        "/reset - konusma gecmisini temizler\n"
        "/kapat - JARVIS'i duzgunce kapatir\n\n"
        "Ornekler: 'Notepad ac', 'Steam ac', 'sesi 20 yap', 'muzigi duraklat'."
    )


async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text("Pong! JARVIS aktif.")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    key = _key(update.effective_user.id)
    clear_history(key)
    clear_pending_action(key)
    log.info("Gecmis+pending temizlendi: %s", key)
    await update.effective_message.reply_text(
        "Konusma gecmisini temizledim, sifirdan basliyoruz."
    )


async def kapat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    log.info("Kapatma istendi: user_id=%s", update.effective_user.id)
    await update.effective_message.reply_text("Kapatiliyor, gorusuruz!")
    request_stop()


# --- Callback handler ---

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if not is_authorized(update.effective_user.id):
        await reject_unauthorized(update)
        try:
            await query.answer()
        except Exception:  # noqa: BLE001
            pass
        return
    key = _key(update.effective_user.id)
    kind, value = parse_callback(query.data or "")
    try:
        await query.answer()
    except Exception:  # noqa: BLE001
        pass

    if kind is None:
        await query.message.reply_text("Bilinmeyen buton.")
        return
    if get_pending_action(key) is None:
        from core.logger import log_decision

        log_decision(update.effective_user.id, "ZAMANASIMI", f"callback={query.data}")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            pass
        await query.message.reply_text(TIMEOUT_TEXT)
        return

    if kind == "confirm":
        await _remove_markup(context, key, message=query.message)
        result = flow.resolve_confirmation(key, value == "yes")
    else:
        await _remove_markup(context, key, message=query.message)
        result = flow.resolve_choice(key, value)
    await _deliver_resolution(update.effective_chat, query.message, result)


# --- Sohbet (ortak cekirdek) ---

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    if update.effective_message is None:
        return
    key = _key(update.effective_user.id)
    text = update.effective_message.text or ""
    mark_message()

    had_pending = get_pending_action(key) is not None
    if had_pending:
        # Butonlu sorunun butonlarini temizle (yazi ile cevap verildiyse).
        await _remove_markup(context, key)

    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update.effective_chat, stop_event))
    try:
        result = await asyncio.to_thread(flow.process_text, key, text)
    finally:
        stop_event.set()
        typing_task.cancel()

    new_pending = result.get("pending")
    if new_pending:
        if new_pending.get("type") == "confirmation":
            markup = _confirmation_keyboard()
        else:
            markup = _choice_keyboard(new_pending.get("options", []))
        sent = await update.effective_message.reply_text(
            result["reply"][:MAX_MESSAGE_LEN], reply_markup=markup)
        new_pending["chat_id"] = sent.chat_id
        new_pending["message_id"] = sent.message_id
        from core.session_state import set_pending_action

        set_pending_action(key, new_pending)
        return

    await send_files(update, result.get("files", []))
    await send_long_text(update, result["reply"])


async def non_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text(
        "Dosya/fotograf aldim, ancak gonderdigin dosyalari isleme henuz yok."
    )


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN bulunamadi. .env dosyasini olusturun.")
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("kapat", kapat_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    app.add_handler(
        MessageHandler(
            (filters.ATTACHMENT | filters.VOICE | filters.VIDEO | filters.PHOTO)
            & ~filters.COMMAND,
            non_text_handler,
        )
    )
    return app


async def run_polling() -> None:
    """Polling dongusu. Conflict olursa (baska ornek calisiyorsa) sessizce cekilir.

    Normal donus / Conflict durumunda exception firlatilmaz; boylece run.py'deki
    crash-recovery bu ornegi yeniden baslatmaya calismaz (dashboard yasamaya
    devam eder, diger ornek Telegram'i tasir).
    """
    app = build_application()
    log.info("JARVIS Telegram botu baslatiliyor (polling)...")
    await app.initialize()
    await app.start()
    try:
        try:
            await app.updater.start_polling(drop_pending_updates=True)
        except Conflict:
            log.error(
                "JARVIS zaten baska bir yerde calisiyor, bu ornek Telegram "
                "baglantisi kurmayacak. (Conflict: ayni token ile baska bir "
                "bot polling yapiyor.)"
            )
            return
        set_bot_running(True)
        log.info("Bot calisiyor. Durdurmak icin Ctrl+C.")
        import asyncio as _asyncio

        stop = _asyncio.Event()
        try:
            await stop.wait()
        except (_asyncio.CancelledError, KeyboardInterrupt):
            pass
    finally:
        set_bot_running(False)
        log.info("Bot kapatiliyor...")
        try:
            await app.updater.stop()
        except Exception:
            pass
        try:
            await app.stop()
        except Exception:
            pass
        try:
            await app.shutdown()
        except Exception:
            pass
