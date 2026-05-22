"""Bot Telegram de Ramon.

Funciones:
- enviar_mensaje: enviar texto a Ruben
- enviar_informe: informe diario formateado
- bot polling: escuchar mensajes de Ruben (loop asincrono)
- comandos: /informe, /agenda, /pendientes, /urgente, /ayuda
- lenguaje natural: delegar a Gemini para responder
"""
from __future__ import annotations

import asyncio
import html
import os
from typing import Any

import httpx

from app.core.settings import get_settings


class TelegramError(Exception):
    pass


TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    t = get_settings().telegram_bot_token
    if not t:
        raise TelegramError("TELEGRAM_BOT_TOKEN no configurado")
    return t


def _chat_id() -> str:
    c = get_settings().telegram_chat_id
    if not c:
        raise TelegramError("TELEGRAM_CHAT_ID no configurado")
    return c


def send_message(text: str, chat_id: str | None = None, parse_mode: str = "HTML", urgent: bool = False) -> dict[str, Any]:
    """Envia un mensaje a Ruben (o al chat indicado).

    Respeta su horario laboral:
    - Si es URGENT, se envia siempre.
    - Si no y estamos fuera de franja, se encola y se entrega cuando empiece.
    """
    if not urgent:
        try:
            from app.core.horario import is_working_now, encolar
            if not is_working_now():
                encolar(text, parse_mode=parse_mode, chat_id=chat_id)
                return {"queued": True, "reason": "fuera_de_horario_laboral"}
        except Exception:
            pass  # si falla la logica de horario, no bloqueamos el envio
    url = TELEGRAM_API.format(token=_token(), method="sendMessage")
    payload = {
        "chat_id": chat_id or _chat_id(),
        "text": text[:4096],
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    r = httpx.post(url, json=payload, timeout=15.0)
    r.raise_for_status()
    return r.json()


def get_updates(offset: int | None = None, timeout: int = 5) -> list[dict[str, Any]]:
    """Obtiene actualizaciones pendientes. Sirve para detectar Chat ID."""
    url = TELEGRAM_API.format(token=_token(), method="getUpdates")
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    r = httpx.get(url, params=params, timeout=timeout + 5)
    r.raise_for_status()
    return r.json().get("result", [])


def detect_chat_id_from_updates() -> str | None:
    """Busca el chat_id del primer usuario que haya escrito al bot."""
    try:
        updates = get_updates()
    except Exception:
        return None
    for upd in reversed(updates):  # priorizar lo mas reciente
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") and chat.get("type") == "private":
            return str(chat["id"])
    return None


def send_welcome(chat_id: str) -> dict[str, Any]:
    """Mensaje de bienvenida de Ramon a Ruben."""
    text = (
        "<b>¡Hola RUBEN!</b> 👋\n\n"
        "Soy <b>Ramón</b>, tu Asistente Ejecutivo Autónomo.\n\n"
        "A partir de ahora trabajo para ti 24/7 desde el VPS:\n"
        "• Leo y clasifico tu Gmail\n"
        "• Gestiono Calendar y CRM\n"
        "• Te mando el informe diario a las 08:15\n"
        "• Respondo cualquier pregunta que me hagas\n\n"
        "<b>Comandos disponibles:</b>\n"
        "/informe — Informe del dia\n"
        "/agenda — Proximos eventos\n"
        "/pendientes — Emails pendientes\n"
        "/urgente — Solo lo urgente\n"
        "/cobros — Cobros pendientes\n"
        "/ayuda — Esta lista\n\n"
        "O simplemente habla conmigo en lenguaje natural.\n\n"
        "🛡️ <b>Modo activo:</b> Solo borradores (primera semana). No envio nada automaticamente hasta que confies en mi criterio.\n\n"
        "Un abrazo,\n<i>Ramón</i>"
    )
    return send_message(text, chat_id=chat_id)


def send_error(exc: Exception) -> None:
    """Notificar errores criticos al admin."""
    try:
        send_message(f"⚠️ <b>Error en Ramon:</b>\n<code>{html.escape(str(exc))[:1000]}</code>")
    except Exception:
        pass


_DIAS_ES = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
_MESES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}


def _emoji_tipo(titulo: str) -> str:
    t = (titulo or "").lower()
    if "bloqueado" in t or "autoblock" in t:
        return "⬛"
    if "videollamada" in t or "meet" in t:
        return "🎥"
    if "bolo" in t or "after you" in t or "sesion" in t or "sesión" in t:
        return "🎧"
    if "reunión" in t or "reunion" in t or "booking" in t or "management" in t:
        return "👥"
    if "train" in t or "ave" in t or "viaje" in t:
        return "🚆"
    if "factura" in t or "pago" in t or "cobro" in t:
        return "💰"
    if "revisión" in t or "revision" in t or "seguimiento" in t:
        return "🔍"
    if "venecia" in t or "hotel" in t:
        return "🌍"
    return "📌"


def _formatear_evento(ev_str: str) -> str:
    """Convierte '2026-04-20T14:00:00+02:00 — Titulo' a formato legible TDAH.

    Salida: '🎥 MAR 21 · 20:45 · Videollamada Daniel Abad'
    """
    import datetime as _dt
    if " — " not in ev_str and " - " not in ev_str:
        return f"📌 {ev_str[:80]}"
    sep = " — " if " — " in ev_str else " - "
    when_raw, _, titulo = ev_str.partition(sep)
    when_raw = when_raw.strip()
    titulo = titulo.strip()

    emoji = _emoji_tipo(titulo)
    # Limpiar titulos largos
    if "ramon_autoblock" in titulo.lower():
        titulo = "Bloqueado (no disponible)"
    if len(titulo) > 60:
        titulo = titulo[:57] + "..."

    # Parse fecha
    try:
        if "T" in when_raw:
            dt = _dt.datetime.fromisoformat(when_raw.replace("Z", "+00:00"))
            dia_abrev = _DIAS_ES.get(dt.weekday(), "?")[:3].upper()
            hora = dt.strftime("%H:%M")
            return f"{emoji} <b>{dia_abrev} {dt.day} {_MESES_ES.get(dt.month, '')}</b> · <b>{hora}</b> · {titulo}"
        else:
            d = _dt.date.fromisoformat(when_raw[:10])
            dia_abrev = _DIAS_ES.get(d.weekday(), "?")[:3].upper()
            return f"{emoji} <b>{dia_abrev} {d.day} {_MESES_ES.get(d.month, '')}</b> · <i>todo el día</i> · {titulo}"
    except Exception:
        return f"{emoji} {when_raw} · {titulo}"


def format_report(data: dict[str, Any]) -> str:
    """Formatea el informe diario — visual TDAH-friendly."""
    import datetime as _dt
    fecha_raw = data.get("fecha", "")
    try:
        f = _dt.date.fromisoformat(fecha_raw)
        dia = _DIAS_ES.get(f.weekday(), "")
        fecha_bonita = f"{dia} {f.day} de {_MESES_ES.get(f.month, '')} de {f.year}"
    except Exception:
        fecha_bonita = fecha_raw

    lines: list[str] = [
        "<b>🌅 INFORME DE RAMÓN</b>",
        f"<i>{fecha_bonita}</i>",
    ]

    urgente = [u for u in data.get("urgente", []) if u and u.strip()]
    if urgente:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("🚨 <b>URGENTE</b>")
        for item in urgente[:10]:
            lines.append(f"• {item}")

    agenda = data.get("agenda", [])
    if agenda:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("📅 <b>AGENDA</b>")
        for ev in agenda[:15]:
            lines.append(f"  {_formatear_evento(ev)}")

    emails = data.get("emails_pendientes", [])
    if emails:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append(f"📧 <b>EMAILS PROCESADOS</b> ({len(emails)})")
        # Agrupar por nivel
        verdes = [e for e in emails if "VERDE" in e.upper()]
        amarillos = [e for e in emails if "AMARILLO" in e.upper()]
        rojos = [e for e in emails if "ROJO" in e.upper()]
        if rojos:
            lines.append(f"  🔴 {len(rojos)} rojos")
        if amarillos:
            lines.append(f"  🟡 {len(amarillos)} amarillos")
        if verdes:
            lines.append(f"  🟢 {len(verdes)} verdes")

    personal = data.get("personal", [])
    if personal:
        lines.append("")
        lines.append(f"💬 <b>BUZÓN PERSONAL</b> · {len(personal)} mensajes nuevos")

    cobros = data.get("cobros", [])
    if cobros:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 <b>COBROS PENDIENTES</b> ({len(cobros)})")
        for c in cobros[:5]:
            lines.append(f"  • {str(c)[:120]}")

    bolos = data.get("bolos", [])
    if bolos:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("🎧 <b>BOLOS PRÓXIMOS (14 días)</b>")
        for b in bolos[:10]:
            lines.append(f"  {_formatear_evento(b)}")

    alertas = [a for a in data.get("alertas", []) if a]
    if alertas:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ <b>ALERTAS</b>")
        for a in alertas[:10]:
            lines.append(f"  • {a}")

    if data.get("modo_solo_borradores"):
        lines.append("")
        lines.append("🛡️ <i>Modo: solo borradores (primera semana)</i>")

    return "\n".join(lines)
