"""Sistema de disponibilidad para videollamadas de Ramon.

Fuente booking: https://calendar.app.google/krozPuqdzL2pyHRL6
"Reunion de Booking - ARTES BUHO" (citas de 15 min).

Configuracion real (capturada 2026-04-19):
- Dias: martes, miercoles, viernes
- Franjas:
    - martes/viernes  09:00-14:00
    - miercoles       19:30-21:00
- Slot: 15 minutos
- Cadencia: cada 30 minutos (gap entre citas)
- Zona horaria: Europe/Madrid

Reglas adicionales de Ramon (mas estrictas que el booking):
- BLOQUEAR DIA COMPLETO si hay cualquier evento de dia completo (tipo "VENECIA",
  viajes, dias fuera). Google Calendar no lo hace automaticamente si el all-day
  esta marcado "disponible", pero para Ramon esos dias estan fuera de juego.
- Respetar antelacion minima (24h por defecto).
- Respetar FreeBusy para evitar solapes con eventos con hora concreta.

Todo configurable via env vars (opcional):
- BOOKING_DAYS="tue,wed,fri"
- BOOKING_WINDOWS_TUE="09:00-14:00"
- BOOKING_WINDOWS_WED="19:30-21:00"
- BOOKING_WINDOWS_THU=""  (vacio = bloqueado)
- BOOKING_WINDOWS_FRI="09:00-14:00"
- BOOKING_SLOT_MIN=15
- BOOKING_CADENCE_MIN=30
- BOOKING_MIN_LEAD_HOURS=24
- BOOKING_HORIZON_DAYS=30
- BOOKING_BLOCK_ALLDAY=true
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any

import pytz

from app.core.settings import get_settings
from app.google_client import calendar as _cal_client
from app.core.calendar_utils import is_workday


BOOKING_URL = os.getenv("BOOKING_URL", "https://calendar.app.google/aPFUMS7JtrWpfRfn9")

_DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DAY_ABBR = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}

_DEFAULT_WINDOWS = {
    "tue": "09:00-14:00",
    "wed": "19:30-21:00",
    "fri": "09:00-14:00",
}


def _parse_windows(raw: str) -> list[tuple[_dt.time, _dt.time]]:
    """Acepta '09:00-14:00' o '09:00-13:00,14:00-17:00' o vacio."""
    if not raw or not raw.strip():
        return []
    out: list[tuple[_dt.time, _dt.time]] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" not in part:
            continue
        a, b = part.split("-", 1)
        try:
            sh, sm = (int(x) for x in a.strip().split(":"))
            eh, em = (int(x) for x in b.strip().split(":"))
            out.append((_dt.time(sh, sm), _dt.time(eh, em)))
        except ValueError:
            continue
    return out


def _config() -> dict:
    raw_days = os.getenv("BOOKING_DAYS", "tue,wed,fri").lower()
    active_days = [d.strip() for d in raw_days.split(",") if d.strip() in _DAY_MAP]

    windows: dict[int, list[tuple[_dt.time, _dt.time]]] = {}
    for d_abbr in active_days:
        env_key = f"BOOKING_WINDOWS_{d_abbr.upper()}"
        raw = os.getenv(env_key, _DEFAULT_WINDOWS.get(d_abbr, ""))
        ws = _parse_windows(raw)
        if ws:
            windows[_DAY_MAP[d_abbr]] = ws

    return {
        "windows_by_dow": windows,
        "slot_min": int(os.getenv("BOOKING_SLOT_MIN", "15")),
        "cadence_min": int(os.getenv("BOOKING_CADENCE_MIN", "30")),
        "lead_hours": int(os.getenv("BOOKING_MIN_LEAD_HOURS", "24")),
        "horizon_days": int(os.getenv("BOOKING_HORIZON_DAYS", "30")),
        "block_allday": os.getenv("BOOKING_BLOCK_ALLDAY", "true").lower() in {"1", "true", "yes"},
    }


def _tz():
    return pytz.timezone(get_settings().timezone)


def _calendar_ids_a_consultar() -> list[str]:
    """Devuelve la lista de calendarios a tener en cuenta para solapes.

    Incluye:
    - Calendario primario (variable GOOGLE_CALENDAR_ID)
    - Todos los calendarios donde el usuario tiene rol owner/writer
    - Excluye cumpleanos y calendarios que coincidan con BOOKING_IGNORE_CALS
    """
    ignorar = {s.strip().lower() for s in os.getenv("BOOKING_IGNORE_CALS", "cumpleaños,cumpleanos,birthdays").split(",")}
    primary = get_settings().google_calendar_id or "primary"
    ids = {primary}
    try:
        cal = _cal_client()
        resp = cal.calendarList().list(minAccessRole="reader", showHidden=False).execute()
        for c in resp.get("items", []):
            summary = (c.get("summary") or "").strip().lower()
            if any(tok in summary for tok in ignorar):
                continue
            # Solo contar calendarios donde el usuario esta: primary o owner/writer
            role = c.get("accessRole", "")
            if c.get("primary") or role in ("owner", "writer"):
                ids.add(c["id"])
    except Exception:
        pass
    return list(ids)


def _events_in_range(start: _dt.datetime, end: _dt.datetime) -> list[dict]:
    """Lista eventos del calendario primario en el rango (para deteccion all-day)."""
    cal = _cal_client()
    cal_id = get_settings().google_calendar_id or "primary"
    resp = cal.events().list(
        calendarId=cal_id,
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=500,
    ).execute()
    return resp.get("items", [])


def _busy_ranges_multi(start: _dt.datetime, end: _dt.datetime) -> list[tuple[_dt.datetime, _dt.datetime]]:
    """FreeBusy sobre TODOS los calendarios del usuario. Devuelve ventanas ocupadas."""
    cal = _cal_client()
    ids = _calendar_ids_a_consultar()
    body = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "timeZone": get_settings().timezone,
        "items": [{"id": i} for i in ids],
    }
    try:
        resp = cal.freebusy().query(body=body).execute()
    except Exception:
        return []
    busy: list[tuple[_dt.datetime, _dt.datetime]] = []
    for cal_id, data in resp.get("calendars", {}).items():
        for b in data.get("busy", []):
            try:
                busy.append((
                    _dt.datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
                    _dt.datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
                ))
            except ValueError:
                continue
    return busy


# Titulos de all-day que NO bloquean (son tags informativos, no ausencias).
# Ampliable via env var BOOKING_ALLDAY_IGNORE.
_ALLDAY_IGNORE_DEFAULT = {"casa", "home", "cumpleaños", "cumpleanos", "birthday"}


def _titulos_ignorados() -> set[str]:
    base = set(_ALLDAY_IGNORE_DEFAULT)
    extra = os.getenv("BOOKING_ALLDAY_IGNORE", "")
    for t in extra.split(","):
        t = t.strip().lower()
        if t:
            base.add(t)
    return base


def _dias_bloqueados_por_allday(events: list[dict]) -> set[_dt.date]:
    """Detecta eventos de dia completo (start.date sin dateTime) que representan AUSENCIA.

    Ignora titulos tipo "Casa", "Home", "Cumpleanos" (tags informativos).
    Solo cuentan como bloqueo: VENECIA, viajes, dias fuera, bolos all-day, etc.
    """
    ignorar = _titulos_ignorados()
    bloqueados: set[_dt.date] = set()
    for ev in events:
        start = ev.get("start", {})
        end = ev.get("end", {})
        if "date" not in start or "dateTime" in start:
            continue
        titulo = (ev.get("summary") or "").strip().lower()
        if any(tok in titulo for tok in ignorar):
            continue
        try:
            d0 = _dt.date.fromisoformat(start["date"])
            d1 = _dt.date.fromisoformat(end.get("date", start["date"]))
        except ValueError:
            continue
        cur = d0
        while cur < d1:
            bloqueados.add(cur)
            cur += _dt.timedelta(days=1)
        if d1 == d0:
            bloqueados.add(d0)
    return bloqueados


def _busy_ranges(events: list[dict]) -> list[tuple[_dt.datetime, _dt.datetime]]:
    """Eventos con hora concreta (no all-day) como ventanas ocupadas."""
    out: list[tuple[_dt.datetime, _dt.datetime]] = []
    for ev in events:
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        if not s or not e:
            continue
        try:
            out.append((
                _dt.datetime.fromisoformat(s.replace("Z", "+00:00")),
                _dt.datetime.fromisoformat(e.replace("Z", "+00:00")),
            ))
        except ValueError:
            continue
    return out


def _overlaps(slot_start, slot_end, busy):
    for bs, be in busy:
        if slot_start < be and bs < slot_end:
            return True
    return False


def _candidate_slots() -> list[_dt.datetime]:
    cfg = _config()
    tz = _tz()
    now = _dt.datetime.now(tz)
    earliest = now + _dt.timedelta(hours=cfg["lead_hours"])
    horizon = now + _dt.timedelta(days=cfg["horizon_days"])

    slots: list[_dt.datetime] = []
    day = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.date() <= horizon.date():
        dow = day.weekday()
        windows = cfg["windows_by_dow"].get(dow, [])
        if windows and is_workday(day.date()):
            for (t_start, t_end) in windows:
                start_dt = tz.localize(_dt.datetime.combine(day.date(), t_start))
                end_dt = tz.localize(_dt.datetime.combine(day.date(), t_end))
                cur = start_dt
                while cur + _dt.timedelta(minutes=cfg["slot_min"]) <= end_dt:
                    if cur >= earliest:
                        slots.append(cur)
                    cur += _dt.timedelta(minutes=cfg["cadence_min"])
        day += _dt.timedelta(days=1)
    return slots


def _filter_slots_by_tipo(slots: list[_dt.datetime], tipo: str) -> list[_dt.datetime]:
    """Filtra slots segun tipo de interlocutor (politica comercial de Ruben).

    - "novios"        → SOLO miercoles 19:30 (franja particulares)
    - "profesional"   → SOLO martes y viernes 09:00-14:00 (promotores, empresas, ayuntamientos, agencias)
    - "any"           → sin filtro
    """
    t = tipo.lower().strip()
    if t == "novios":
        return [s for s in slots if s.weekday() == 2 and s.hour == 19 and s.minute == 30]
    if t == "profesional":
        return [s for s in slots if s.weekday() in (1, 4) and 9 <= s.hour < 14]
    return slots


def slots_libres(max_results: int = 10, tipo: str = "any") -> list[dict[str, Any]]:
    cfg = _config()
    candidatos = _candidate_slots()
    candidatos = _filter_slots_by_tipo(candidatos, tipo)
    if not candidatos:
        return []
    tz = _tz()
    start_range = candidatos[0].astimezone(pytz.UTC)
    end_range = (candidatos[-1] + _dt.timedelta(minutes=cfg["slot_min"])).astimezone(pytz.UTC)

    try:
        events = _events_in_range(start_range, end_range)
    except Exception:
        events = []

    bloqueados = _dias_bloqueados_por_allday(events) if cfg["block_allday"] else set()
    busy = _busy_ranges_multi(start_range, end_range)

    libres: list[dict[str, Any]] = []
    for s in candidatos:
        if s.date() in bloqueados:
            continue
        e = s + _dt.timedelta(minutes=cfg["slot_min"])
        s_utc, e_utc = s.astimezone(pytz.UTC), e.astimezone(pytz.UTC)
        if _overlaps(s_utc, e_utc, busy):
            continue
        libres.append({
            "start": s.isoformat(),
            "end": e.isoformat(),
            "start_local": s.strftime("%A %d/%m/%Y %H:%M"),
            "duration_min": cfg["slot_min"],
            "timezone": get_settings().timezone,
        })
        if len(libres) >= max_results:
            break
    return libres


_DIA_ES = {
    "Monday": "lunes", "Tuesday": "martes", "Wednesday": "miercoles",
    "Thursday": "jueves", "Friday": "viernes", "Saturday": "sabado", "Sunday": "domingo",
}
_MES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def formato_humano_es(slot_iso: str) -> str:
    dt = _dt.datetime.fromisoformat(slot_iso)
    dia = _DIA_ES.get(dt.strftime("%A"), dt.strftime("%A").lower())
    mes = _MES_ES.get(dt.month, str(dt.month))
    return f"{dia} {dt.day} de {mes} a las {dt.strftime('%H:%M')}"


def dias_bloqueados_proximos(horizonte_dias: int = 30) -> list[dict[str, str]]:
    """Devuelve los dias bloqueados por eventos de dia completo (para diagnostico)."""
    tz = _tz()
    now = _dt.datetime.now(tz)
    start = now.astimezone(pytz.UTC)
    end = (now + _dt.timedelta(days=horizonte_dias)).astimezone(pytz.UTC)
    try:
        events = _events_in_range(start, end)
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for ev in events:
        s = ev.get("start", {})
        if "date" in s and "dateTime" not in s:
            out.append({
                "fecha": s["date"],
                "titulo": ev.get("summary", "(sin titulo)"),
                "id": ev.get("id", ""),
            })
    return out


RAMON_BLOCK_TAG = "RAMON_AUTOBLOCK"


def _ya_bloqueado(events: list[dict], start: _dt.datetime, end: _dt.datetime) -> bool:
    """Detecta si ya existe un evento RAMON_AUTOBLOCK cubriendo el rango."""
    for ev in events:
        if RAMON_BLOCK_TAG not in (ev.get("description") or "") and \
           RAMON_BLOCK_TAG not in (ev.get("summary") or ""):
            continue
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        if not s or not e:
            continue
        try:
            bs = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            be = _dt.datetime.fromisoformat(e.replace("Z", "+00:00"))
        except ValueError:
            continue
        if bs <= start and be >= end:
            return True
    return False


def sincronizar_bloqueos(dry_run: bool = True) -> dict[str, Any]:
    """Crea eventos 'BLOQUEADO - RAMON_AUTOBLOCK' cubriendo las franjas de booking
    en los dias con evento de dia completo (VENECIA, viajes, etc.).

    Asi la booking page de Google no ofrecera slots esos dias, porque
    Google oculta slots si la agenda esta ocupada.

    Args:
        dry_run: si True, solo lista lo que crearia. Si False, crea los eventos.

    Returns:
        { "bloqueos_creados": [...], "omitidos_existentes": N, "dry_run": bool }
    """
    cfg = _config()
    tz = _tz()
    now = _dt.datetime.now(tz)
    horizon = now + _dt.timedelta(days=cfg["horizon_days"])

    events = _events_in_range(now.astimezone(pytz.UTC), horizon.astimezone(pytz.UTC))
    bloqueados = _dias_bloqueados_por_allday(events)

    cal = _cal_client()
    cal_id = get_settings().google_calendar_id or "primary"

    creados: list[dict] = []
    omitidos = 0

    for fecha in sorted(bloqueados):
        if fecha < now.date():
            continue
        if fecha > horizon.date():
            continue
        dow = fecha.weekday()
        windows = cfg["windows_by_dow"].get(dow, [])
        if not windows:
            continue
        # Obtener titulo del all-day significativo (no "Casa") que cubra esa fecha
        ignorar = _titulos_ignorados()
        titulo_allday = "evento dia completo"
        for ev in events:
            st = ev.get("start", {})
            en = ev.get("end", {})
            if "date" not in st or "dateTime" in st:
                continue
            title = (ev.get("summary") or "").strip()
            if any(tok in title.lower() for tok in ignorar):
                continue
            try:
                d0 = _dt.date.fromisoformat(st["date"])
                d1 = _dt.date.fromisoformat(en.get("date", st["date"]))
            except ValueError:
                continue
            if d0 <= fecha < d1 or d0 == fecha:
                titulo_allday = title
                break
        for (t_start, t_end) in windows:
            start_dt = tz.localize(_dt.datetime.combine(fecha, t_start))
            end_dt = tz.localize(_dt.datetime.combine(fecha, t_end))
            if _ya_bloqueado(events, start_dt.astimezone(pytz.UTC), end_dt.astimezone(pytz.UTC)):
                omitidos += 1
                continue
            body = {
                "summary": f"BLOQUEADO — {titulo_allday} [{RAMON_BLOCK_TAG}]",
                "description": (
                    f"Bloqueo automatico creado por Ramon.\n"
                    f"Motivo: dia con evento de dia completo '{titulo_allday}'.\n"
                    f"Cubre la franja de booking de Ramon.\n"
                    f"Tag: {RAMON_BLOCK_TAG}"
                ),
                "start": {"dateTime": start_dt.isoformat(), "timeZone": get_settings().timezone},
                "end":   {"dateTime": end_dt.isoformat(),   "timeZone": get_settings().timezone},
                "transparency": "opaque",  # marca como ocupado
                "visibility": "private",
                "colorId": "8",  # gris (Graphite) — bloqueos Ramon
            }
            if dry_run:
                creados.append({
                    "fecha": fecha.isoformat(),
                    "franja": f"{t_start.strftime('%H:%M')}-{t_end.strftime('%H:%M')}",
                    "motivo": titulo_allday,
                    "creado": False,
                })
            else:
                resp = cal.events().insert(
                    calendarId=cal_id, body=body, sendUpdates="none",
                ).execute()
                creados.append({
                    "fecha": fecha.isoformat(),
                    "franja": f"{t_start.strftime('%H:%M')}-{t_end.strftime('%H:%M')}",
                    "motivo": titulo_allday,
                    "event_id": resp.get("id"),
                    "html_link": resp.get("htmlLink"),
                    "creado": True,
                })

    return {
        "dry_run": dry_run,
        "dias_bloqueados_detectados": sorted([d.isoformat() for d in bloqueados]),
        "bloqueos_a_crear" if dry_run else "bloqueos_creados": creados,
        "omitidos_existentes": omitidos,
    }


def limpiar_bloqueos(dry_run: bool = True) -> dict[str, Any]:
    """Elimina todos los eventos RAMON_AUTOBLOCK del calendario (proximos dias)."""
    cfg = _config()
    tz = _tz()
    now = _dt.datetime.now(tz)
    horizon = now + _dt.timedelta(days=cfg["horizon_days"])
    events = _events_in_range(now.astimezone(pytz.UTC), horizon.astimezone(pytz.UTC))
    cal = _cal_client()
    cal_id = get_settings().google_calendar_id or "primary"

    borrados: list[dict] = []
    for ev in events:
        if RAMON_BLOCK_TAG not in (ev.get("description") or "") and \
           RAMON_BLOCK_TAG not in (ev.get("summary") or ""):
            continue
        info = {"id": ev.get("id"), "summary": ev.get("summary"), "start": ev.get("start", {}).get("dateTime")}
        if not dry_run:
            try:
                cal.events().delete(calendarId=cal_id, eventId=ev["id"], sendUpdates="none").execute()
                info["deleted"] = True
            except Exception as exc:
                info["error"] = str(exc)
        borrados.append(info)
    return {"dry_run": dry_run, "bloqueos": borrados, "count": len(borrados)}


def bloque_prompt_disponibilidad(max_results: int = 8) -> str:
    try:
        libres = slots_libres(max_results=max_results)
        bloqueados = dias_bloqueados_proximos()
    except Exception as exc:
        return (
            "# DISPONIBILIDAD VIDEOLLAMADAS\n\n"
            f"No he podido leer la agenda ({exc}). "
            "No propongas horas concretas; dile al cliente que le confirmas en breve."
        )
    if not libres:
        return (
            "# DISPONIBILIDAD VIDEOLLAMADAS\n\n"
            "No hay huecos disponibles en los proximos dias. "
            "No propongas horas. Pide al cliente sus preferencias y marca nivel_decision=amarillo."
        )
    lines = [
        "# DISPONIBILIDAD VIDEOLLAMADAS (OBLIGATORIO)",
        "",
        f"Ramon SOLO puede proponer videollamadas en estas franjas ({get_settings().timezone}).",
        f"Slots de {libres[0]['duration_min']} minutos.",
        f"Booking page oficial: {BOOKING_URL}",
        "",
        "Franjas LIBRES:",
    ]
    for s in libres:
        lines.append(f"- {formato_humano_es(s['start'])} ({s['duration_min']} min)")
    if bloqueados:
        lines.append("")
        lines.append("Dias BLOQUEADOS (no proponer nada esos dias):")
        for b in bloqueados[:10]:
            lines.append(f"- {b['fecha']}: {b['titulo']}")
    lines.extend([
        "",
        "Reglas:",
        "- Si propones videollamada, usa SIEMPRE una franja de la lista LIBRES.",
        "- Propon 2-3 opciones al cliente para que elija.",
        "- NUNCA propongas en dias BLOQUEADOS ni fuera de las franjas.",
        "- Si el cliente pide una hora que no esta en la lista, ofrecele las mas cercanas.",
    ])
    return "\n".join(lines)
