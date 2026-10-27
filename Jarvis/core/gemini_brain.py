"""JARVIS beyin — function calling + onay/secim pending akisi + coklu API key failover.

Ozellikler:
- Varsayilan model: gemini-3.5-flash-lite (config/GEMINI_MODEL ile degistirilebilir).
- API anahtar havuzu: settings.gemini_api_keys sirasiyla denenir.
  Her YENI konusma turu (run_conversation/finalize/transcribe) 1. anahtarla
  baslar; 429 / kota / rate-limit / gecici ag hatasinda otomatik olarak
  siradaki anahtara gecer. Tum anahtarlar biterse basa donulup her key
  icin en fazla 2 deneme yapilir (toplam deneme = key_sayisi, dongusel degil).
- Context KORUNUR: failover'da `contents` listesi aynen korunur, sadece
  client degisir; konusma gecmsei sifirlanmaz. Session history RAM'de
  (session_state) durdugu icin key degisimi onu etkilemez.
- Hangi key'in calistigi log'lanir (anahtarin kendisi ASLA loglanmaz,
  sadece index + son 4 hanesi).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

from config import settings
from core.status import mark_gemini
from tools import execute_tool, get_function_declarations

log = logging.getLogger("jarvis.brain")

SYSTEM_PROMPT = (
    "Sen JARVIS adinda Turkce konusan, kisa ve net cevaplar veren bir "
    "kisisel asistansin. Artik gercek dunyada islem yapabiliyorsun: dosya "
    "bulabilir, terminal komutu calistirabilir, uygulama acabilirsin. "
    "Belirsiz bir istek geldiginde asla tahmin etme, kullaniciya net bir "
    "soru sor. Tehlikeli veya geri alinamaz komutlarda mutlaka onay iste. "
    "Bir tool 'ambiguous', 'requires_confirmation' veya 'not_found' gibi "
    "bir alan donerse bunu dogal dilde soruya cevir, kendin secim yapma. "
    "Onay veya secim gerektiginde kullaniciya buton gosterilecegini bil; "
    "sorunu kisa tut, secenekleri teker teker yazmana gerek yok. "
    "Artik ekran goruntusu alabiliyor, Word belgesi olusturabiliyor, "
    "YouTube'da kayitli kanallarin son videosunu direkt acabiliyor ve "
    "internette arama yapabiliyorsun. Ekran goruntusu icin asla klavye "
    "kisayolu kullanma (Prt Sc / Win+Shift+S yasak), her zaman "
    "take_screenshot tool'unu kullan. Web arama sonuclarini kendi "
    "cumlelerinle ozetle, ham linkleri oldugu gibi kopyalama. "
    "Artik sesli komutlari anlayabiliyorsun (masaustu uygulamasi uzerinden), "
    "medya/ses kontrolu yapabiliyorsun (muzik isteklerinde hangi uygulamanin "
    "acik oldugunu sorma, media_control/set_volume dogrudan kullan) ve "
    "uygulama/oyun isimlerini tam bilmesen de (kismi/yanlis yazim) bulabiliyorsun. "
    "WhatsApp veya tarayici otomasyonu istendiginde (orn. 'WhatsApp'ta Anneme yaz') "
    "whatsapp_send tool'unu kullan; kisiyi arama cubugunda arayip ISMI ESLESEN "
    "dogru sohbete tikla, en usttekine koru korune tiklama. Ekranda bir yazi/dugme "
    "bulman gerektiginde once read_screen ile OCR yap, sonra click_text ile "
    "hedefin koordinatina tikla. Ses seviyesi 0-100 arasi set_volume ile ayarlanir. "
    "Ses ve medya islerinde ASLA run_command kullanma (SendKeys ile ses/medya "
    "tusu yasak): ses icin SADECE set_volume, oynat/duraklat/sessiz icin SADECE "
    "media_control kullan, tek tool cagrisi yeterlidir, ikinci bir komut ekleme. "
    "YouTube'da arama istendiginde browser_search(url='https://www.youtube.com', "
    "search_text=...) kullan; kendisi dogrudan sonuclar sayfasini acar. "
    "read_screen/click_text bir 'Tesseract/EasyOCR/OCR motoru' hatasi donerse "
    "OCR kapali demektir: web aramalarinda IS R A R ETME, browser_search kullan "
    "(hizli yolu kendisi bulur). Kullanicidan bolge tarifi alirsan click_at ile "
    "o koordinata tikla; 'bolge soyle' diye bosa oyalama, once take_screenshot "
    "ile gorup tahmini koordinata tiklamayi dene."
)

MAX_TOOL_STEPS = 5

# --- Coklu API key havuzu -------------------------------------------------

_lock = threading.Lock()
_clients: dict[int, object] = {}
_active_key_index: int = 0  # son basarili key; yeni tur yine 0'dan baslar (istenen davranis)


def _keys() -> list[str]:
    keys = list(settings.gemini_api_keys or [])
    if not keys and getattr(settings, "gemini_api_key", ""):
        keys = [settings.gemini_api_key]
    return keys


def _mask(key: str) -> str:
    key = key or ""
    return f"***{key[-4:]}" if len(key) > 4 else "***"


def _build_client(index: int):
    """Belirtilen index'teki key ile client kurar (cache'li)."""
    global _clients
    keys = _keys()
    if not keys:
        raise RuntimeError(
            "GEMINI_API_KEY_1 bos. .env dosyasindaki GEMINI_API_KEY_1 degerini doldurun."
        )
    if not (0 <= index < len(keys)):
        raise RuntimeError(f"API key index disi: {index}")
    with _lock:
        if index not in _clients:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "google-genai paketi kurulu degil. 'pip install -r requirements.txt' calistir."
                ) from exc
            _clients[index] = genai.Client(api_key=keys[index])
        return _clients[index]


def _is_retryable(exc: Exception) -> bool:
    """Rate-limit/kota/gecici hata mi? Bu tur hatalarda siradaki key denenir."""
    msg = str(exc)
    upper = msg.upper()
    low = msg.lower()
    retry_tokens = (
        "429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE", "LIMIT",
        "503", "UNAVAILABLE", "500", "INTERNAL", "TIMEOUT",
        "DEADLINE", "TIMED OUT", "CONNECTION", "RESET",
        "INVALID_ARGUMENT",  # yanlis key de havuzda denensin
        "API KEY", "API_KEY", "UNAUTHENTICATED", "PERMISSION_DENIED",
    )
    return any(tok in upper or tok.lower() in low for tok in retry_tokens)


def _is_model_error(exc: Exception) -> bool:
    """GEMINI_MODEL adi gecersiz/erisilemez mi? (Key degistirmek cozmez -> hizli bitir.)"""
    msg = str(exc)
    upper = msg.upper()
    if "MODEL" not in upper:
        return False
    markers = (
        "NOT_FOUND", "404", "IS NOT FOUND", "NOT FOUND", "DOES NOT EXIST",
        "NOT SUPPORTED", "UNSUPPORTED", "INVALID MODEL", "MODEL NOT",
    )
    return any(marker in upper for marker in markers)


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    lowered = msg.lower()
    if "model" in lowered and (
        "bulunamiyor" in lowered or "kullanilamiyor" in lowered
        or "not_found" in lowered or "404" in lowered
    ):
        return (
            f"GEMINI_MODEL ayari kullanilamiyor: '{settings.gemini_model}'. "
            "Google'da yayinlanmis gecerli bir model adi yaz (orn. gemini-3.5-flash-lite). "
            "Model adini degistirdiysen .env'i kaydedip JARVIS'i yeniden baslat."
        )
    if "API key" in msg or "API_KEY" in msg or "INVALID_ARGUMENT" in msg:
        return (
            "Gemini API anahtarlari gecersiz gorunuyor (tum yedekler denendi). "
            ".env dosyasindaki GEMINI_API_KEY_1 (ve varsa _2/_3) degerlerini kontrol et."
        )
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in lowered:
        return "Gemini su an yogun (tum anahtarlarda kota/limit asimi). Biraz bekleyip tekrar dene."
    if "timeout" in lowered or "deadline" in lowered or "timed out" in lowered:
        return "Gemini cevap verirken zaman asimina ugradi. Tekrar dener misin?"
    if "pip install" in msg:
        return msg
    return "Gemini'ye ulasamadim, birazdan tekrar dene. (Detay terminale yazildi.)"


def generate_with_failover(call_fn):
    """call_fn(client, key_index) -> response.

    Her cagri 0. key'den baslar (istenen: her konusmada 1. key ile basla).
    Basarisiz key'de siradakine gecer, basarili key'i hatirlar.
    Context disarida tutuldugu icin gecmis kaybolmaz.
    Tum key'ler biterse son hatayi yukseltir.
    """
    global _active_key_index
    keys = _keys()
    if not keys:
        raise RuntimeError(
            "GEMINI_API_KEY_1 bos. .env dosyasindaki GEMINI_API_KEY_1 degerini doldurun."
        )
    last_exc: Exception | None = None
    for index in range(len(keys)):
        try:
            client = _build_client(index)
            result = call_fn(client, index)
            with _lock:
                _active_key_index = index
            if index > 0:
                log.warning("Gemini failover: key #%d (%s) ile basarili.", index + 1, _mask(keys[index]))
            return result
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Gemini key #%d (%s) hata: %s", index + 1, _mask(keys[index]), exc)
            # Model adi yanlissa diger anahtarlari denemek bosuna; hemen bitir.
            if _is_model_error(exc):
                raise RuntimeError(
                    f"GEMINI_MODEL kullanilamiyor: '{settings.gemini_model}' "
                    "(model bulunamadi/erisilemiyor). Google'da yayinlanmis gecerli bir "
                    "model adi kullan ve .env'i kaydedip JARVIS'i yeniden baslat."
                ) from exc
            # Son key degilse siradakine gec (kota yenilenmesi icin kisa bekleme).
            if index < len(keys) - 1:
                time.sleep(0.2)
                continue
            break
    assert last_exc is not None
    raise last_exc


def get_active_key_info() -> dict:
    """Teshis icin: key sayisi + aktif index (secret YOK)."""
    keys = _keys()
    return {"key_count": len(keys), "active_index": _active_key_index,
            "model": settings.gemini_model}


# --- Gemini icerik yardimcilari -------------------------------------------

def _history_to_contents(history: list[dict], types):
    """Session gecmisini Gemini formatina cevirir (assistant->model, diger->user)."""
    contents = []
    for item in history or []:
        role_in = item.get("role", "user")
        text = str(item.get("content", ""))
        if not text:
            continue
        role = "model" if role_in == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    return contents


def _summarize_result(name: str, result: dict) -> str:
    """Tool sonucunu Gemini'ye verilecek kisa metne cevirir."""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(result)
    if len(text) > 1500:
        text = text[:1500] + "... [kirpildi]"
    return f"Tool '{name}' sonucu: {text}"


def _pending_from_result(call_name: str, call_args: dict, result: dict) -> dict | None:
    """Tool sonucundan pending_action dict'i cikarir (yoksa None)."""
    if result.get("requires_confirmation"):
        return {
            "type": "confirmation",
            "tool_name": result.get("tool_name") or call_name,
            "tool_args": result.get("tool_args") or dict(call_args),
        }
    if result.get("ambiguous"):
        return {
            "type": "choice",
            "tool_name": result.get("tool_name") or call_name,
            "base_args": result.get("base_args") or {},
            "choice_param": result.get("choice_param"),
            "options": list(result.get("options") or []),
        }
    return None


def _pending_reply_text(result: dict) -> str:
    if result.get("requires_confirmation"):
        return result.get("confirmation_text") or "Bu islem onay gerektiriyor. Onayliyor musun?"
    if result.get("ambiguous"):
        from core.pending_flow import numbered_list

        return numbered_list(
            result.get("prompt_text") or "Birden fazla secenek var, hangisi?",
            result.get("options") or [],
        )
    return ""


def _build_tool_config(types):
    declarations = get_function_declarations()
    tools_param = [types.Tool(function_declarations=declarations)]
    config_kwargs: dict = {"system_instruction": SYSTEM_PROMPT, "tools": tools_param}
    # SDK otomatik function calling (AFC) KAPALI: dongu kontrolu bizde.
    afc_cls = getattr(types, "AutomaticFunctionCallingConfig", None)
    if afc_cls is not None:
        try:
            config_kwargs["automatic_function_calling"] = afc_cls(disable=True)
        except Exception:  # noqa: BLE001
            pass
    return types.GenerateContentConfig(**config_kwargs)


# --- Ana konusma dongusu ----------------------------------------------------

def run_conversation(message: str, history: list[dict] | None = None) -> dict:
    """Tam konusma turu: tool loop + dosya toplama + transcript + pending.

    Donus: {"reply": str, "files": [...], "transcript": [...], "pending": dict|None}
    pending doluysa bot buton gosterip aksiyonu session'a kaydetmelidir.
    Failover: her generate_content cagrisi havuz uzerinden gecer; `contents`
    listesi korunur, history sifirlanmaz.
    """
    history = history or []
    try:
        from google.genai import types
    except ImportError:
        return {
            "reply": "google-genai paketi kurulu degil. 'pip install -r requirements.txt' calistir.",
            "files": [],
            "transcript": [],
            "pending": None,
        }
    try:
        config = _build_tool_config(types)
    except Exception as exc:  # noqa: BLE001
        log.exception("Beyin hazirlanamadi: %s", exc)
        return {"reply": _friendly_error(exc), "files": [], "transcript": [], "pending": None}

    contents = _history_to_contents(history, types)
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    files: list[str] = []
    transcript: list[dict] = []
    seen_calls: dict[str, int] = {}

    def _one_step(client, _idx, _contents=contents, _config=config):
        return client.models.generate_content(
            model=settings.gemini_model, contents=_contents, config=_config
        )

    try:
        for _step in range(MAX_TOOL_STEPS + 1):
            # Her adimda failover'li cagri; contents korunur (context kaybi yok).
            resp = generate_with_failover(_one_step)
            mark_gemini(True)
            calls = getattr(resp, "function_calls", None) or []
            if not calls:
                text = (getattr(resp, "text", None) or "").strip()
                if not text:
                    text = "Gemini'den bos cevap geldi, tekrar dener misin?"
                return {"reply": text, "files": files, "transcript": transcript, "pending": None}

            response_parts = []
            for call in calls:
                args = dict(call.args or {})
                sig = call.name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True,
                                                   default=str)
                seen_calls[sig] = seen_calls.get(sig, 0) + 1
                log.info("Tool cagrisi: %s(%s)", call.name, json.dumps(args, ensure_ascii=False)[:300])
                if seen_calls[sig] > 2:
                    log.warning("Tekrar cagri engellendi (3. kez): %s", sig[:200])
                    result = {"error": (
                        f"'{call.name}' ayni parametrelerle 3 kez cagrildi ve sonuc degismedi. "
                        "Tekrar deneme; elindeki sonucla kullaniciya cevap ver."
                    )}
                else:
                    result = execute_tool(call.name, args)
                summary = _summarize_result(call.name, result)
                transcript.append({"role": "tool", "content": summary})

                file_path = result.get("file_to_send")
                if file_path and isinstance(file_path, str) and os.path.isfile(file_path):
                    files.append(file_path)

                pending = _pending_from_result(call.name, args, result)
                if pending is not None:
                    reply = _pending_reply_text(result)
                    return {
                        "reply": reply,
                        "files": files,
                        "transcript": transcript,
                        "pending": pending,
                    }

                response_parts.append(
                    types.Part.from_function_response(
                        name=call.name, response={"result": result}
                    )
                )

            try:
                contents.append(resp.candidates[0].content)
            except (AttributeError, IndexError):
                pass
            contents.append(types.Content(role="user", parts=response_parts))

        return {
            "reply": "Cok fazla art arda islem gerekti, ilk adimlari yaptim. Devami icin tekrar yaz.",
            "files": files,
            "transcript": transcript,
            "pending": None,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("Gemini API hatasi: %s", exc)
        mark_gemini(False)
        return {"reply": _friendly_error(exc), "files": files, "transcript": transcript, "pending": None}


def finalize_with_tool_result(history: list[dict] | None, event_text: str) -> str:
    """Onay/secim cozuldu: tool sonucunu dogal kapanis mesajina cevirir (toolsuz tek cagri)."""
    try:
        from google.genai import types
    except ImportError:
        return "google-genai paketi kurulu degil."
    contents = _history_to_contents(history or [], types)
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(
                text=f"{event_text}\nBunu kullaniciya kisa Turkce bir mesajla bildir, gereksiz detay verme."
            )],
        )
    )

    def _call(client, _idx):
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )

    try:
        resp = generate_with_failover(_call)
        mark_gemini(True)
        text = (getattr(resp, "text", None) or "").strip()
        return text or "Islem tamamlandi."
    except Exception as exc:  # noqa: BLE001
        log.exception("Finalize hatasi: %s", exc)
        mark_gemini(False)
        return _friendly_error(exc)


def transcribe_with_failover(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """Ses transkripti (failover'li). channel_flow.transcribe_and_answer kullanir."""
    from google.genai import types

    transcript_holder: dict = {}

    def _call(client, _idx):
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/webm")],
            )],
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Bu ses kaydinda konusulan Turkce cumleleri KELIMESI KELIMESINE "
                    "metne cevir. Sadece transkripti dondur; yorum, cevap veya aciklama "
                    "ekleme, noktalama disinda hicbir seyi degistirme."
                ),
            ),
        )
        transcript_holder["text"] = (getattr(resp, "text", None) or "").strip()
        return resp

    generate_with_failover(_call)
    mark_gemini(True)
    return transcript_holder.get("text", "")


def ask_gemini(message: str, history: list[dict] | None = None) -> str:
    """Uyumluluk sarmalayici: sadece nihai metin cevabi doner."""
    return run_conversation(message, history)["reply"]
