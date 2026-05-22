"""Bot Telegram bidireccional (protocolo v4 seccion 21).

- Polling cada 30s (gestionado por scheduler).
- Comandos: /informe /agenda /pendientes /urgente /cobros /buscar /ayuda
- Lenguaje natural: delega a Gemini via answer_question.
- Persiste conversaciones en Postgres (TelegramMessage).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from app.core.database import SessionLocal
from app.core.models import TelegramMessage
from app.core.settings import get_settings
from app.integrations.telegram_bot import send_message, get_updates, TelegramError, TELEGRAM_API
from app.integrations.gemini_brain import answer_question, GeminiBrainError, QuotaExceeded, _call_gemini


log = logging.getLogger("ramon.telegram.bidi")

_LAST_UPDATE_FILE = "/tmp/ramon_last_update_id.txt"


def _read_last_update_id() -> int | None:
    try:
        with open(_LAST_UPDATE_FILE, "r") as f:
            return int(f.read().strip() or 0) or None
    except Exception:
        return None


def _write_last_update_id(uid: int) -> None:
    try:
        with open(_LAST_UPDATE_FILE, "w") as f:
            f.write(str(uid))
    except Exception:
        pass


def _persist(direction: str, chat_id: str, text: str, meta: dict | None = None) -> None:
    if SessionLocal is None:
        return
    try:
        with SessionLocal() as db:
            db.add(TelegramMessage(direction=direction, chat_id=chat_id, message=text, meta=meta or {}))
            db.commit()
    except Exception:
        pass


# --- Comandos ---

def _cmd_ayuda() -> str:
    return (
        "<b>Comandos de Ramón</b>\n\n"
        "/informe — Informe diario\n"
        "/agenda — Proximos eventos\n"
        "/pendientes — Decisiones pendientes\n"
        "/urgente — Solo lo critico\n"
        "/cobros — Cobros pendientes\n"
        "/buscar &lt;texto&gt; — Busqueda en CRM/emails\n"
        "/ayuda — Esta lista\n\n"
        "O simplemente hablame en lenguaje natural."
    )


def _cmd_informe() -> str:
    """Informe rápido sin lanzar procesamiento pesado (que tarda minutos).

    Devuelve snapshot actual: agenda, cobros, decisiones pendientes, últimos emails.
    El procesamiento completo lo hace el scheduler a las 08:00.
    """
    import datetime as _dt
    try:
        from app.google_client import calendar_upcoming
        from app.integrations.sheets_crm import cobros_pendientes
        from app.decisions.semaforo import listar_pendientes

        hoy = _dt.date.today().isoformat()
        lines = [f"<b>📊 INFORME RÁPIDO</b>", f"<i>{hoy}</i>", ""]

        # Agenda próximas 5
        try:
            eventos = calendar_upcoming(max_results=5)
            if eventos:
                lines.append("<b>📅 Próximos eventos:</b>")
                for ev in eventos[:5]:
                    s = ev.get("start", {})
                    when = s.get("dateTime") or s.get("date", "")
                    titulo = ev.get("summary", "(sin título)")[:60]
                    # Formato legible
                    try:
                        dt = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
                        fecha_str = dt.strftime("%d/%m %H:%M")
                    except Exception:
                        fecha_str = when[:10]
                    lines.append(f"• {fecha_str} — {titulo}")
                lines.append("")
        except Exception:
            pass

        # Decisiones pendientes
        try:
            amar = listar_pendientes(nivel="amarillo")
            rojo = listar_pendientes(nivel="rojo")
            if amar or rojo:
                lines.append("<b>🚦 Decisiones pendientes:</b>")
                if rojo:
                    lines.append(f"🔴 {len(rojo)} rojas")
                if amar:
                    lines.append(f"🟡 {len(amar)} amarillas")
                lines.append("")
        except Exception:
            pass

        # Cobros
        try:
            cobros = cobros_pendientes()
            if cobros:
                lines.append(f"<b>💰 Cobros pendientes:</b> {len(cobros)}")
                lines.append("")
        except Exception:
            pass

        lines.append("<i>Informe completo con Gemini: cada día a las 08:15.</i>")
        return "\n".join(lines)
    except Exception as exc:
        return f"⚠️ No pude generar el resumen rápido: {exc}. Prueba /agenda o /pendientes."


_DIAS_ES = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
_MESES_ES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
             7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}


def _emoji_evento(titulo: str) -> str:
    t = (titulo or "").lower()
    if "bloqueado" in t or "autoblock" in t:
        return "⬛"
    if "videollamada" in t or "meet" in t:
        return "🎥"
    if "bolo" in t or "after you" in t or "sesion" in t or "sesión" in t:
        return "🎧"
    if "reunión" in t or "reunion" in t or "booking" in t or "management" in t:
        return "👥"
    if "train" in t or "ave" in t or "viaje" in t or "flight" in t:
        return "🚆"
    if "factura" in t or "pago" in t or "cobro" in t or "gestoría" in t or "gestoria" in t:
        return "💰"
    if "revisión" in t or "revision" in t or "seguimiento" in t:
        return "🔍"
    if "venecia" in t or "hotel" in t:
        return "🌍"
    if "casa" in t:
        return "🏠"
    return "📌"


def _cmd_agenda() -> str:
    import datetime as _dt
    try:
        from app.google_client import calendar_upcoming
        eventos = calendar_upcoming(max_results=20)
    except Exception as exc:
        return f"No pude leer Calendar: {exc}"
    if not eventos:
        return "📅 No hay eventos próximos."

    # Agrupar por fecha
    por_dia: dict[_dt.date, list[dict]] = {}
    for ev in eventos:
        s = ev.get("start", {})
        raw = s.get("dateTime") or s.get("date", "")
        is_allday = "dateTime" not in s and "date" in s
        try:
            if is_allday:
                fecha = _dt.date.fromisoformat(raw)
                hora = None
            else:
                dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
                # Ajustar a local TZ si es aware
                try:
                    import pytz as _pytz
                    from app.core.settings import get_settings
                    tz = _pytz.timezone(get_settings().timezone)
                    if dt.tzinfo:
                        dt = dt.astimezone(tz)
                except Exception:
                    pass
                fecha = dt.date()
                hora = dt.strftime("%H:%M")
        except Exception:
            continue
        por_dia.setdefault(fecha, []).append({
            "hora": hora,
            "titulo": ev.get("summary", "(sin título)"),
        })

    hoy = _dt.date.today()
    manana = hoy + _dt.timedelta(days=1)

    lines = ["<b>📅 AGENDA PRÓXIMA</b>", ""]
    for fecha in sorted(por_dia.keys()):
        # Cabecera del día
        dia_nombre = _DIAS_ES.get(fecha.weekday(), "?")
        mes = _MESES_ES.get(fecha.month, str(fecha.month))
        if fecha == hoy:
            header = f"<b>HOY · {dia_nombre} {fecha.day} {mes}</b>"
        elif fecha == manana:
            header = f"<b>MAÑANA · {dia_nombre} {fecha.day} {mes}</b>"
        else:
            header = f"<b>{dia_nombre} {fecha.day} {mes}</b>"
        lines.append(f"━━━━━━━━━━━━━━━━")
        lines.append(header)
        for item in sorted(por_dia[fecha], key=lambda x: (x["hora"] or "ZZ")):
            titulo = item["titulo"]
            emoji = _emoji_evento(titulo)
            hora = item["hora"]
            # Limpiar titulos largos
            if "bloqueado" in titulo.lower() and "ramon_autoblock" in titulo.lower():
                titulo_clean = "Bloqueado (no disponible)"
            else:
                titulo_clean = titulo[:70]
            if hora:
                lines.append(f"  {emoji} <b>{hora}</b> · {titulo_clean}")
            else:
                lines.append(f"  {emoji} <i>todo el día</i> · {titulo_clean}")
        lines.append("")
    return "\n".join(lines)


def _cmd_pendientes() -> str:
    from app.decisions.semaforo import listar_pendientes
    amarillos = listar_pendientes(nivel="amarillo")
    rojos = listar_pendientes(nivel="rojo")
    if not amarillos and not rojos:
        return "✅ <b>Todo al día</b>\n\nNo hay decisiones pendientes ahora mismo."

    out = ["<b>🚦 DECISIONES PENDIENTES</b>", ""]
    if rojos:
        out.append("━━━━━━━━━━━━━━━━━")
        out.append(f"🔴 <b>ROJAS</b> · {len(rojos)} pendientes · <i>las decides tú</i>")
        out.append("")
        for d in rojos[:8]:
            tema = d['topic'][:90]
            out.append(f"  🔴 <b>#{d['id']}</b> — {tema}")
        out.append("")
    if amarillos:
        out.append("━━━━━━━━━━━━━━━━━")
        out.append(f"🟡 <b>AMARILLAS</b> · {len(amarillos)} pendientes · <i>Ramón propone, tú apruebas</i>")
        out.append("")
        for d in amarillos[:8]:
            tema = d['topic'][:90]
            out.append(f"  🟡 <b>#{d['id']}</b> — {tema}")
    return "\n".join(out)


def _cmd_urgente() -> str:
    from app.decisions.semaforo import listar_pendientes
    rojos = listar_pendientes(nivel="rojo")
    if not rojos:
        return "✅ <b>Nada urgente</b>\n\nTodo tranquilo. Puedes respirar. 🌬️"
    out = ["<b>🚨 URGENTE — decide TÚ</b>", ""]
    for d in rojos[:12]:
        out.append(f"🔴 <b>#{d['id']}</b>")
        out.append(f"   {d['topic'][:110]}")
        if d.get('proposal'):
            out.append(f"   <i>Propuesta:</i> {d['proposal'][:110]}")
        out.append("")
    return "\n".join(out)


def _cmd_cobros() -> str:
    try:
        from app.integrations import sheets_crm as crm
        pendientes = crm.cobros_pendientes()
    except Exception as exc:
        return f"⚠️ No pude leer el CRM: {exc}"
    if not pendientes:
        return "✅ <b>Sin cobros pendientes</b>\n\nNadie te debe dinero según el CRM. 🎉"
    out = [f"<b>💰 COBROS PENDIENTES</b> · {len(pendientes)} total", ""]
    for p in pendientes[:10]:
        # Coger solo campos más relevantes
        cliente = ""
        importe = ""
        for k, v in p.items():
            k_lower = k.lower()
            if not v:
                continue
            if "client" in k_lower or "nombre" in k_lower:
                cliente = cliente or str(v)[:40]
            if "importe" in k_lower or "precio" in k_lower or "€" in str(v):
                importe = importe or str(v)[:20]
        linea = f"  💰 <b>{cliente or 'Sin nombre'}</b>"
        if importe:
            linea += f" · {importe}"
        out.append(linea)
    return "\n".join(out)


def _cmd_buscar(arg: str) -> str:
    if not arg.strip():
        return "🔍 <b>Búsqueda</b>\n\nUso: <code>/buscar [nombre o texto]</code>\nEjemplo: <code>/buscar loren</code>"
    try:
        from app.integrations import sheets_crm as crm
        hits = crm.buscar_por_nombre(arg)
    except Exception as exc:
        return f"⚠️ Error buscando: {exc}"
    if not hits:
        return f"🔍 <b>Sin resultados</b> para <i>{arg}</i>\n\nPrueba con otro término o /agenda /pendientes."
    out = [f"<b>🔍 RESULTADOS</b> para <i>{arg}</i>", ""]
    for h in hits[:5]:
        campos = [(k, v) for k, v in list(h.items())[:8] if v]
        if not campos:
            continue
        out.append("━━━━━━━━━━━━━━━━━")
        for k, v in campos[:5]:
            out.append(f"  <b>{k[:20]}</b>: {str(v)[:80]}")
        out.append("")
    return "\n".join(out)


COMMAND_HANDLERS = {
    "/ayuda": lambda _a: _cmd_ayuda(),
    "/help": lambda _a: _cmd_ayuda(),
    "/start": lambda _a: _cmd_ayuda(),
    "/informe": lambda _a: _cmd_informe(),
    "/agenda": lambda _a: _cmd_agenda(),
    "/pendientes": lambda _a: _cmd_pendientes(),
    "/urgente": lambda _a: _cmd_urgente(),
    "/cobros": lambda _a: _cmd_cobros(),
    "/buscar": lambda a: _cmd_buscar(a),
}


def _download_telegram_file(file_id: str) -> tuple[bytes, str]:
    """Descarga un archivo (voz, foto, doc) por file_id. Devuelve (bytes, mime)."""
    token = get_settings().telegram_bot_token
    # 1) getFile para obtener file_path
    r = httpx.get(TELEGRAM_API.format(token=token, method="getFile"),
                  params={"file_id": file_id}, timeout=10.0)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    # 2) Descargar
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    rr = httpx.get(url, timeout=30.0)
    rr.raise_for_status()
    mime = "audio/ogg" if file_path.endswith((".oga", ".ogg")) else (
        "audio/mpeg" if file_path.endswith(".mp3") else "application/octet-stream"
    )
    return rr.content, mime


def _transcribir_voz(audio_bytes: bytes, mime: str = "audio/ogg") -> str:
    """Transcribe audio usando Gemini 2.5 Flash (multimodal)."""
    import json as _json
    api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_GENAI_API_KEY", "")
    if not api_key:
        return "[no hay GEMINI_API_KEY]"
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "Transcribe literalmente este audio en espanol. Devuelve SOLO el texto transcrito, sin comentarios."},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ],
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000},
    }
    try:
        r = httpx.post(url, params={"key": api_key}, json=payload, timeout=60.0)
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return "[transcripcion vacia]"
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:
        return f"[error transcripcion: {exc}]"


# Frases-tigger que indican feedback/aprendizaje directo (protocolo 20.2)
_LEARNING_HINTS = (
    "a partir de ahora", "de ahora en adelante", "siempre que", "nunca ",
    "recuerda que", "apunta que", "recuerdalo", "no olvides",
    "cambia", "prefiero", "odio", "me gusta", "mejor si",
    "cuando pase", "regla nueva", "importante:",
)


def _es_aprendizaje(texto: str) -> bool:
    t = texto.lower()
    return any(h in t for h in _LEARNING_HINTS)


def _registrar_aprendizaje_desde_chat(texto: str, origen: str = "telegram") -> None:
    """Si el mensaje parece feedback, lo guarda en Aprendizaje_desde_VPS.md."""
    if not _es_aprendizaje(texto):
        return
    try:
        from app.learning.aprendizaje import registrar_desde_vps
        registrar_desde_vps(
            categoria="PROCESOS",
            situacion=f"Ruben escribio por {origen}: {texto[:300]}",
            aprendizaje=texto.strip(),
            afecta_a="comportamiento general de Ramon",
        )
    except Exception as exc:
        log.warning(f"registrar aprendizaje fallo: {exc}")


_QUICK_PATTERNS = [
    (("hola", "ey", "buenas", "que tal", "qué tal", "como estas", "cómo estás", "puedes hablar", "puedo hablar"),
     "¡Claro Rubén, aquí estoy! 👋 Cuéntame qué necesitas."),
    (("gracias", "grcs", "mil gracias"), "A ti siempre 🙌"),
    (("buenos dias", "buenos días"), "¡Buenos días, Rubén! ☕ ¿Por dónde arrancamos?"),
    (("buenas noches",), "Buenas noches 🌙 Mañana seguimos."),
    (("estas ahi", "estás ahí", "me lees"), "Sí, estoy 👋 ¿Qué pasa?"),
    (("te quiero", "te amo"), "Yo también te aprecio 🧡"),
]


def _respuesta_rapida(text: str) -> str | None:
    t = text.lower().strip().rstrip("?!.")
    # Solo para mensajes cortos (evita falsos positivos)
    if len(t) > 60:
        return None
    for patterns, reply in _QUICK_PATTERNS:
        for p in patterns:
            if p in t:
                return reply
    return None


def _handle_text(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    # Respuestas instantaneas para saludos (sin consumir Gemini)
    quick = _respuesta_rapida(text)
    if quick and not cmd.startswith("/"):
        return quick
    handler = COMMAND_HANDLERS.get(cmd)
    if handler:
        try:
            return handler(arg)
        except Exception as exc:
            log.exception("handler error")
            return f"⚠️ Error en {cmd}: {exc}"
    # Lenguaje natural: Gemini (o fallback Ollama si esta activado)
    contexto = "Estas respondiendo a ARTES BUHO por Telegram. Se breve y util. Sin markdown complejo."
    try:
        return answer_question(text, context=contexto)
    except QuotaExceeded as exc:
        # Intentar Ollama directo si gemini_brain no lo hizo
        try:
            from app.integrations import ollama_fallback
            if ollama_fallback.available():
                from app.prompts.ramon_system import build_system_prompt
                return ollama_fallback.answer(text, build_system_prompt(), contexto)
        except Exception:
            pass
        return ("⚠️ Estoy al límite de cuota de mi cerebro principal y el respaldo local "
                "aún no está disponible. Te respondo en cuanto pueda (o usa /informe /agenda "
                "/pendientes para consultar lo ya procesado).")
    except GeminiBrainError as exc:
        try:
            from app.integrations import ollama_fallback
            if ollama_fallback.available():
                from app.prompts.ramon_system import build_system_prompt
                return ollama_fallback.answer(text, build_system_prompt(), contexto)
        except Exception:
            pass
        return f"⚠️ Error de cerebro: {exc}. Prueba /ayuda para ver comandos directos."


def poll_once() -> dict[str, Any]:
    """Procesa updates pendientes una vez. Llamar cada 30s desde scheduler."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"skipped": "no_token"}
    allowed_chat = settings.telegram_chat_id

    last = _read_last_update_id()
    offset = (last + 1) if last else None
    try:
        updates = get_updates(offset=offset, timeout=1)
    except TelegramError:
        return {"error": "telegram_error"}
    except Exception as exc:
        log.debug(f"poll error: {exc}")
        return {"error": str(exc)}

    processed = 0
    for upd in updates:
        uid = upd.get("update_id")
        if uid is not None:
            _write_last_update_id(uid)
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))

        # Seguridad: solo responder al chat autorizado de Ruben
        if allowed_chat and chat_id and chat_id != allowed_chat:
            log.warning(f"Mensaje rechazado de chat_id {chat_id}")
            continue

        # Voz: descargar, transcribir y tratar como texto
        transcripcion = ""
        if "voice" in msg or "audio" in msg:
            audio = msg.get("voice") or msg.get("audio") or {}
            fid = audio.get("file_id")
            if fid:
                try:
                    data, mime = _download_telegram_file(fid)
                    transcripcion = _transcribir_voz(data, mime=mime)
                    # Responder con la transcripcion para confirmacion
                    send_message(f"🎙️ Transcripcion: <i>{transcripcion[:500]}</i>", chat_id=chat_id or None, urgent=True)
                except Exception as exc:
                    log.warning(f"voz fallo: {exc}")

        text = transcripcion or (msg.get("text") or "").strip()
        if not text:
            continue

        _persist("in", chat_id, text, meta={"update_id": uid, "tipo": "voz" if transcripcion else "texto"})

        # Aprendizaje si aplica
        _registrar_aprendizaje_desde_chat(text, origen="telegram_voz" if transcripcion else "telegram")

        # Si la pregunta va a ir a IA (no comando rápido), avisa de que puede tardar
        parts_early = text.strip().split(maxsplit=1)
        cmd_early = parts_early[0].lower() if parts_early else ""
        quick = _respuesta_rapida(text) if not cmd_early.startswith("/") else None
        if not quick and cmd_early not in COMMAND_HANDLERS:
            # Es una pregunta que cae en IA, avisa primero
            try:
                send_message("🧠 Dame un momento, pienso bien la respuesta...", chat_id=chat_id or None, urgent=True)
            except Exception:
                pass

        reply = _handle_text(text)
        try:
            # Respuestas del bot van siempre (usuario las pidio)
            send_message(reply, chat_id=chat_id or None, urgent=True)
            _persist("out", chat_id, reply)
        except Exception as exc:
            log.warning(f"No se pudo responder: {exc}")
        processed += 1

    return {"processed": processed}
