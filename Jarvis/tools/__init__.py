"""Tool registry — JARVIS'in tum yeteneklerinin tek kayit noktasi.

Yeni tool eklemek icin:
  1. tools/ altina <ad>.py dosyasi yaz (TOOL_SCHEMA + fonksiyon icermeli).
  2. Asagidaki _REGISTRY listesine bir satir ekle.
Bu kadar — Gemini sEmasi otomatik uretilir, calistirma otomatik baglanir.

Her registry girdisi:
    {"name": ..., "description": ..., "parameters": {...JSON schema...},
     "function": <cagrilabilir>}
"""
from __future__ import annotations

from tools.browser_automation import BROWSER_SEARCH_SCHEMA, WHATSAPP_SEND_SCHEMA
from tools.browser_automation import browser_search, whatsapp_send
from tools.create_document import TOOL_SCHEMA as CREATE_DOC_SCHEMA
from tools.create_document import create_document
from tools.find_file import TOOL_SCHEMA as FIND_FILE_SCHEMA
from tools.find_file import find_file
from tools.media_control import MEDIA_CONTROL_SCHEMA, SET_VOLUME_SCHEMA
from tools.media_control import media_control, set_volume
from tools.open_application import LEARN_APP_SCHEMA
from tools.open_application import TOOL_SCHEMA as OPEN_APP_SCHEMA
from tools.open_application import learn_application, open_application
from tools.run_command import TOOL_SCHEMA as RUN_COMMAND_SCHEMA
from tools.run_command import run_command
from tools.screen_vision import CLICK_AT_SCHEMA, CLICK_TEXT_SCHEMA, READ_SCREEN_SCHEMA
from tools.screen_vision import click_at, click_text, read_screen
from tools.shortcut_scanner import TOOL_SCHEMA as SCAN_SCHEMA
from tools.shortcut_scanner import refresh_shortcuts
from tools.take_screenshot import TOOL_SCHEMA as SCREENSHOT_SCHEMA
from tools.take_screenshot import take_screenshot
from tools.web_search import TOOL_SCHEMA as WEB_SEARCH_SCHEMA
from tools.web_search import web_search
from tools.youtube import GET_LATEST_VIDEO_SCHEMA, REGISTER_CHANNEL_SCHEMA
from tools.youtube import get_latest_video, register_channel

_REGISTRY: list[dict] = [
    {
        "name": FIND_FILE_SCHEMA["name"],
        "description": FIND_FILE_SCHEMA["description"],
        "parameters": FIND_FILE_SCHEMA["parameters"],
        "function": find_file,
    },
    {
        "name": RUN_COMMAND_SCHEMA["name"],
        "description": RUN_COMMAND_SCHEMA["description"],
        "parameters": RUN_COMMAND_SCHEMA["parameters"],
        "function": run_command,
    },
    {
        "name": OPEN_APP_SCHEMA["name"],
        "description": OPEN_APP_SCHEMA["description"],
        "parameters": OPEN_APP_SCHEMA["parameters"],
        "function": open_application,
    },
    {
        "name": SCREENSHOT_SCHEMA["name"],
        "description": SCREENSHOT_SCHEMA["description"],
        "parameters": SCREENSHOT_SCHEMA["parameters"],
        "function": take_screenshot,
    },
    {
        "name": CREATE_DOC_SCHEMA["name"],
        "description": CREATE_DOC_SCHEMA["description"],
        "parameters": CREATE_DOC_SCHEMA["parameters"],
        "function": create_document,
    },
    {
        "name": GET_LATEST_VIDEO_SCHEMA["name"],
        "description": GET_LATEST_VIDEO_SCHEMA["description"],
        "parameters": GET_LATEST_VIDEO_SCHEMA["parameters"],
        "function": get_latest_video,
    },
    {
        "name": REGISTER_CHANNEL_SCHEMA["name"],
        "description": REGISTER_CHANNEL_SCHEMA["description"],
        "parameters": REGISTER_CHANNEL_SCHEMA["parameters"],
        "function": register_channel,
    },
    {
        "name": WEB_SEARCH_SCHEMA["name"],
        "description": WEB_SEARCH_SCHEMA["description"],
        "parameters": WEB_SEARCH_SCHEMA["parameters"],
        "function": web_search,
    },
    {
        "name": LEARN_APP_SCHEMA["name"],
        "description": LEARN_APP_SCHEMA["description"],
        "parameters": LEARN_APP_SCHEMA["parameters"],
        "function": learn_application,
    },
    {
        "name": SCAN_SCHEMA["name"],
        "description": SCAN_SCHEMA["description"],
        "parameters": SCAN_SCHEMA["parameters"],
        "function": refresh_shortcuts,
    },
    {
        "name": MEDIA_CONTROL_SCHEMA["name"],
        "description": MEDIA_CONTROL_SCHEMA["description"],
        "parameters": MEDIA_CONTROL_SCHEMA["parameters"],
        "function": media_control,
    },
    {
        "name": SET_VOLUME_SCHEMA["name"],
        "description": SET_VOLUME_SCHEMA["description"],
        "parameters": SET_VOLUME_SCHEMA["parameters"],
        "function": set_volume,
    },
    {
        "name": WHATSAPP_SEND_SCHEMA["name"],
        "description": WHATSAPP_SEND_SCHEMA["description"],
        "parameters": WHATSAPP_SEND_SCHEMA["parameters"],
        "function": whatsapp_send,
    },
    {
        "name": BROWSER_SEARCH_SCHEMA["name"],
        "description": BROWSER_SEARCH_SCHEMA["description"],
        "parameters": BROWSER_SEARCH_SCHEMA["parameters"],
        "function": browser_search,
    },
    {
        "name": READ_SCREEN_SCHEMA["name"],
        "description": READ_SCREEN_SCHEMA["description"],
        "parameters": READ_SCREEN_SCHEMA["parameters"],
        "function": read_screen,
    },
    {
        "name": CLICK_TEXT_SCHEMA["name"],
        "description": CLICK_TEXT_SCHEMA["description"],
        "parameters": CLICK_TEXT_SCHEMA["parameters"],
        "function": click_text,
    },
    {
        "name": CLICK_AT_SCHEMA["name"],
        "description": CLICK_AT_SCHEMA["description"],
        "parameters": CLICK_AT_SCHEMA["parameters"],
        "function": click_at,
    },
]


def list_tools() -> list[dict]:
    """Kayitli tool'larin kopyasini doner."""
    return [dict(entry) for entry in _REGISTRY]


def get_tool(name: str) -> dict | None:
    for entry in _REGISTRY:
        if entry["name"] == name:
            return entry
    return None


def execute_tool(name: str, args: dict | None = None) -> dict:
    """Tool'u guvenli sekilde calistirir; her durumda dict doner (crash yok).

    BaseException da yakalanir (pytesseract SystemExit gibi): tek bir tool
    hatasi butun bot process'ini olduremez. Gercek kapatma sinyalleri
    (KeyboardInterrupt/Cancelled) aynen yukseltilir.
    """
    import asyncio

    entry = get_tool(name)
    if entry is None:
        return {"error": f"Bilinmeyen tool: {name}"}
    args = dict(args or {})
    # Gemini'nin fazladan gonderdigi alanlari ele (sadece semadaki parametreler).
    allowed = set(entry["parameters"].get("properties", {}).keys())
    filtered = {k: v for k, v in args.items() if k in allowed}
    try:
        result = entry["function"](**filtered)
    except TypeError as exc:
        return {"error": f"Parametre hatasi ({name}): {exc}"}
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise
    except BaseException as exc:  # noqa: BLE001 — SystemExit dahil
        return {"error": f"Tool hatasi ({name}): {exc}"}
    if not isinstance(result, dict):
        return {"result": result}
    return result


def get_function_declarations():
    """Registry'yi google-genai function_declarations formatina cevirir.

    google SDK import'u bilerek fonksiyon icinde yapilir: paket kurulu
    degilse bile tools modulu ve testler calisabilsin.
    """
    from google.genai import types

    return [
        types.FunctionDeclaration(
            name=entry["name"],
            description=entry["description"],
            parameters_json_schema=entry["parameters"],
        )
        for entry in _REGISTRY
    ]
