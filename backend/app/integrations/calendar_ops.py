"""Operaciones de Calendar estandarizadas por Ramon.

Todos los eventos que Ramon crea van con:
- transparency: opaque (marca a Ruben como "No disponible")
- Google Meet auto-generado
- autoRecording + autoSmartNotes (notas con Gemini) cuando Workspace lo permita
- Host se marca como requerido (para que Gemini note-taking funcione)
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.settings import get_settings
from app.google_client import calendar as _cal_client


# Paleta Google Calendar (colorId). Adaptada al TDAH de Ruben — contrastes claros.
# Referencia Google: 1 Lavender, 2 Sage, 3 Grape, 4 Flamingo, 5 Banana,
#                    6 Tangerine, 7 Peacock, 8 Graphite, 9 Blueberry, 10 Basil, 11 Tomato
COLORES = {
    "critico":    "11",  # rojo (Tomato) — bolos cerrados, cobros vencidos, deadlines
    "importante": "6",   # naranja (Tangerine) — marca ARTES BUHO, videollamadas VIP
    "videollamada": "6", # naranja — reuniones con clientes
    "bolo":       "11",  # rojo — gig confirmado
    "admin":      "9",   # azul (Blueberry) — gestoria, facturas
    "revision":   "5",   # amarillo (Banana) — seguimientos, press kit enviado
    "completado": "10",  # verde (Basil) — cerrado OK
    "personal":   "3",   # morado (Grape)
    "bloqueo":    "8",   # gris (Graphite) — RAMON_AUTOBLOCK
    "viaje":      "2",   # verde claro (Sage) — desplazamientos
    "meet":       "6",   # naranja — sinonimo videollamada
    "default":    "6",   # naranja por defecto (marca)
}


def color_por_tipo(tipo: str) -> str:
    """Devuelve el colorId de Google Calendar para un tipo/importancia dado."""
    return COLORES.get((tipo or "").lower().strip(), COLORES["default"])


def crear_evento(
    *,
    summary: str,
    description: str = "",
    start_iso: str,
    end_iso: str,
    timezone: str | None = None,
    attendees: list[str] | None = None,
    location: str = "",
    with_meet: bool = True,
    auto_recording: bool = True,
    auto_transcription: bool = True,
    auto_smart_notes: bool = True,
    send_updates: str = "all",
    calendar_id: str | None = None,
    tipo: str = "default",
    color_id: str | None = None,
) -> dict[str, Any]:
    """Crea un evento con ajustes estandar Ramon."""
    tz = timezone or get_settings().timezone
    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": tz},
        "end":   {"dateTime": end_iso,   "timeZone": tz},
        # NO DISPONIBLE por defecto (bloquea booking de Ramon y de Google)
        "transparency": "opaque",
        "visibility": "default",
        "reminders": {"useDefault": True},
        # Color por importancia (TDAH-friendly)
        "colorId": color_id or color_por_tipo(tipo),
    }
    if location:
        body["location"] = location
    if attendees:
        body["attendees"] = [
            {"email": a} if isinstance(a, str) else a for a in attendees
        ]
    if with_meet:
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
        # Activar grabacion + transcripcion + notas Gemini.
        # Disponible en Google Workspace Business Standard+.
        # Si la API no los soporta en tu tier, se ignoran silenciosamente.
        conf_props: dict[str, Any] = {}
        if auto_recording:
            conf_props["autoRecordingGenerationType"] = "ON"
        if auto_transcription:
            conf_props["autoTranscriptionGenerationType"] = "ON"
        if auto_smart_notes:
            conf_props["autoSmartNotesGenerationType"] = "ON"
        if conf_props:
            body["conferenceData"]["parameters"] = {"addOnParameters": {"parameters": conf_props}}

    cal = _cal_client()
    cid = calendar_id or get_settings().google_calendar_id or "primary"
    ev = cal.events().insert(
        calendarId=cid,
        body=body,
        conferenceDataVersion=1,
        sendUpdates=send_updates,
    ).execute()
    return ev


def meet_link(ev: dict) -> str:
    for entry in ev.get("conferenceData", {}).get("entryPoints", []):
        if entry.get("entryPointType") == "video":
            return entry.get("uri", "")
    return ""


def marcar_no_disponible(event_id: str, calendar_id: str | None = None) -> dict[str, Any]:
    """Fuerza transparency=opaque en un evento existente (por si alguien lo creo 'disponible')."""
    cal = _cal_client()
    cid = calendar_id or get_settings().google_calendar_id or "primary"
    return cal.events().patch(
        calendarId=cid, eventId=event_id, body={"transparency": "opaque"},
    ).execute()
