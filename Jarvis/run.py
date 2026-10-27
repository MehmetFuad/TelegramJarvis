"""JARVIS giris noktasi — Faz 7: kendini toparlayan servis + dashboard.

- Bot ve dashboard izole task'ler: coken servis 3 sn sonra yeniden baslar;
  art arda 5 cokus olursa 60 sn beklenir (basit backoff).
- /kapat komutu veya dashboard Durdur butonu duzgun kapatma ister.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time

from config import settings
from core import status as shared_status
from core.logger import setup_logging

log = logging.getLogger("jarvis.run")

BASE_RESTART_DELAY = 3
BACKOFF_AFTER_FAILURES = 5
BACKOFF_DELAY = 60
HEALTHY_RUN_SECONDS = 60


def check_config() -> bool:
    errors = settings.validate_for_bot()
    if errors:
        for e in errors:
            log.error(e)
        print("\nYapilandirma hatasi:")
        for e in errors:
            print(f"  - {e}")
        print("\n.env.example dosyasini .env olarak kopyalayip icini doldurun.\n")
        return False
    return True


async def _run_service(name: str, coro_fn, stop_event: asyncio.Event,
                       base_delay: float = BASE_RESTART_DELAY,
                       backoff_delay: float = BACKOFF_DELAY) -> None:
    """Servisi surekli ayakta tutar; cokerse bekleyip yeniden baslatir."""
    failures = 0
    while not stop_event.is_set() and not shared_status.shutdown_requested.is_set():
        started = time.monotonic()
        try:
            await coro_fn()
            # Normal bitis (orn. Telegram Conflict yuzunden cekilme): yeniden baslatma.
            log.info("%s normal sekilde durdu, yeniden baslatilmayacak.", name)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            failures += 1
            if time.monotonic() - started > HEALTHY_RUN_SECONDS:
                failures = 1  # uzun sure yasadiysa sayaci sifirla
            reason = f"{type(exc).__name__}: {exc}"
            log.exception("%s coktu (%d. kez): %s", name, failures, reason)
            shared_status.set_last_crash(name, reason)
            delay = backoff_delay if failures >= BACKOFF_AFTER_FAILURES else base_delay
            log.info("%s %s sn sonra yeniden baslatilacak.", name, delay)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
                return
            except asyncio.TimeoutError:
                continue


async def main_async() -> None:
    from dashboard.server import run_dashboard
    from telegram_bot.bot import run_polling

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    shared_status.set_stop_event(loop, stop_event)

    print(f"\nDashboard: http://{settings.dashboard_host or '127.0.0.1'}:{settings.dashboard_port} adresinden erisilebilir.\n")
    bot_task = asyncio.create_task(
        _run_service("Telegram botu", run_polling, stop_event))
    dash_task = asyncio.create_task(
        _run_service("Dashboard", run_dashboard, stop_event))
    await stop_event.wait()
    log.info("Kapatma istendi, servisler durduruluyor...")
    for task in (bot_task, dash_task):
        task.cancel()
    await asyncio.gather(bot_task, dash_task, return_exceptions=True)


def main() -> int:
    setup_logging(settings.log_level)
    log.info("JARVIS baslatiliyor (Faz 7)...")
    if not check_config():
        return 1
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log.info("Kullanici durdurdu (Ctrl+C).")
    log.info("JARVIS kapandi, gorusuruz!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
