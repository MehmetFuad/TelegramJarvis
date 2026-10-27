"""run_command tool — guvenli shell wrapper.

Tehlikeli komutlar calistirilmaz; bunun yerine onay istenmek uzere
{"requires_confirmation": True, ...} donulur. Cikti 2000 karaktere kirpilir.
"""
from __future__ import annotations

import subprocess

COMMAND_TIMEOUT = 30
MAX_OUTPUT_CHARS = 2000

# Kara liste: bu ifadelerden birini iceren komut calistirilmadan once onay ister.
DANGEROUS_KEYWORDS = [
    "del ",
    "erase ",
    "rm ",
    "rmdir",
    "rd /s",
    "deltree",
    "format",
    "shutdown",
    "diskpart",
    "reg delete",
    "reg add",
    "cipher /w",
    "takeown",
    "icacls",
    "net user",
    "net localgroup",
    "bcdedit",
    "mkfs",
    "dd if=",
    ":(){",
    "chmod",
    "chown",
    "sfc /scannow",
]

TOOL_SCHEMA = {
    "name": "run_command",
    "description": (
        "Windows terminal komutu calistirir ve ciktisini doner. Ornek: "
        "saat/tarih ogrenme, klasor listeleme. Silme, format, kapatma gibi "
        "tehlikeli komutlar calistirilmadan once onay ister. "
        "Ekran goruntusu almak icin bu tool'u KULLANMA, take_screenshot "
        "tool'unu kullan (klavye kisayolu ile ekran goruntusu alinmaz). "
        "Ses/medya isleri icin KULLANMA: ses icin set_volume, medya icin "
        "media_control kullan (SendKeys ile ses/medya tusu YASAK)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Calistirilacak terminal komutu. Ornek: 'time /t'",
            },
        },
        "required": ["command"],
    },
}


# Ses/medya tuslarinin SendKeys karsiliklari: set_volume/media_control varken
# run_command ile kullanilmalari YASAK (cift islem + yanlis davranis yapiyordu).
FORBIDDEN_SENDKEYS_HINT = (
    "Ses/medya kontrolu icin run_command/SendKeys YASAK. "
    "Ses seviyesi icin set_volume(level=...), oynat/duraklat/sessiz icin "
    "media_control(action=...) tool'unu kullan."
)


def _is_media_sendkeys(command: str) -> bool:
    lowered = command.lower()
    if "sendkeys" not in lowered:
        return False
    media_markers = (
        "[char]173", "[char]174", "[char]175", "[char]179",  # mute/vol/play
        "playpause", "nexttrack", "prevtrack", "(char)173",
        "volume", "mute", "media",
    )
    return any(marker in lowered for marker in media_markers)


def is_dangerous(command: str) -> str | None:
    """Komut tehlikeliyse eslesen anahtar kelimeyi, degilse None doner."""
    lowered = f" {command.lower()} "
    for keyword in DANGEROUS_KEYWORDS:
        if keyword in lowered:
            return keyword.strip()
    return None


def run_command(command: str) -> dict:
    """Komutu calistirir; sonucu standart tool dict'i olarak doner."""
    command = (command or "").strip()
    if not command:
        return {"success": False, "stdout": "", "stderr": "Bos komut.", "returncode": -1}

    if _is_media_sendkeys(command):
        return {"success": False, "stdout": "", "stderr": FORBIDDEN_SENDKEYS_HINT,
                "returncode": -1, "error": FORBIDDEN_SENDKEYS_HINT}

    hit = is_dangerous(command)
    if hit:
        return {
            "requires_confirmation": True,
            "confirmation_text": (
                f"Bu komut tehlikeli gorunuyor ('{hit}' iceriyor) ve "
                f"calistirilmadi:\n{command}\nCalistirmami onayliyor musun?"
            ),
            "tool_name": "run_command",
            "tool_args": {"command": command},
            "command": command,
            "reason": f"Komut tehlikeli gorunuyor ('{hit}' iceriyor).",
        }

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Komut {COMMAND_TIMEOUT} saniyede bitmedi (timeout).",
            "returncode": -1,
            "timeout": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "stdout": "", "stderr": f"Calistirma hatasi: {exc}", "returncode": -1}

    return {
        "success": proc.returncode == 0,
        "stdout": (proc.stdout or "")[:MAX_OUTPUT_CHARS],
        "stderr": (proc.stderr or "")[:MAX_OUTPUT_CHARS],
        "returncode": proc.returncode,
    }
