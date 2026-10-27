"""Telegram yetkilendirme — sadece whitelist'teki kullaniciya cevap verilir."""
from __future__ import annotations

import logging

from telegram import Update

from config import settings

log = logging.getLogger("jarvis.auth")


def is_authorized(user_id: int | None) -> bool:
    return user_id is not None and user_id == settings.allowed_telegram_user_id


async def reject_unauthorized(update: Update) -> None:
    user = update.effective_user
    log.warning(
        "Yetkisiz erisim engellendi: user_id=%s username=%s text=%r",
        getattr(user, "id", None),
        getattr(user, "username", None),
        (update.effective_message.text if update.effective_message else None),
    )
