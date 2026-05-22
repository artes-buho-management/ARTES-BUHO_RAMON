"""Horario laboral de ARTES BUHO (espejo del Google Calendar Workspace).

Ramon respeta estas franjas antes de comunicarse por Telegram:
- Mensajes URGENTES (rojo) → se envian siempre.
- Mensajes normales fuera de franja → se encolan y se entregan en la siguiente franja.

Horario actual (capturado 2026-04-19):
- Lunes    08:00-08:30
- Martes   08:00-14:00
- Miercoles 08:00-08:30  +  19:00-20:30
- Jueves   08:00-08:30
- Viernes  08:00-14:00
- Sabado/Domingo: nada

Configurable via env vars:
- WORK_HOURS_MON="08:00-08:30"
- WORK_HOURS_TUE="08:00-14:00"
- WORK_HOURS_WED="08:00-08:30,19:00-20:30"
- WORK_HOURS_THU="08:00-08:30"
- WORK_HOURS_FRI="08:00-14:00"
- WORK_HOURS_SAT=""
- WORK_HOURS_SUN=""
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Iterable

import pytz

from app.core.settings import get_settings
from app.core.calendar_utils import is_holiday


# Ramon trabaja 24/7 (clasifica, aprende, administra) pero solo se COMUNICA
# con Ruben dentro de esta franja — todos los dias del año.
# Fuera de este horario los mensajes se encolan hasta las 08:00 del día siguiente.
_DEFAULT = {
    0: "08:00-20:30",  # lun
    1: "08:00-20:30",  # mar
    2: "08:00-20:30",  # mie
    3: "08:00-20:30",  # jue
    4: "08:00-20:30",  # vie
    5: "08:00-20:30",  # sab
    6: "08:00-20:30",  # dom
}
_ENV_KEYS = ["WORK_HOURS_MON", "WORK_HOURS_TUE", "WORK_HOURS_WED",
             "WORK_HOURS_THU", "WORK_HOURS_FRI", "WORK_HOURS_SAT", "WORK_HOURS_SUN"]

# Cola persistente de mensajes que esperan a franja horaria.
QUEUE_PATH = Path(os.getenv("RAMON_TG_QUEUE", "/tmp/ramon_tg_queue.json"))


def _tz():
    return pytz.timezone(get_settings().timezone)


def _parse_windows(raw: str) -> list[tuple[_dt.time, _dt.time]]:
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


def _windows_for(dow: int) -> list[tuple[_dt.time, _dt.time]]:
    raw = os.getenv(_ENV_KEYS[dow], _DEFAULT[dow])
    return _parse_windows(raw)


def is_working_now(now: _dt.datetime | None = None) -> bool:
    tz = _tz()
    now = now or _dt.datetime.now(tz)
    if now.tzinfo is None:
        now = tz.localize(now)
    if is_holiday(now.date()):
        return False
    t = now.time()
    for (s, e) in _windows_for(now.weekday()):
        if s <= t <= e:
            return True
    return False


def next_working_start(from_dt: _dt.datetime | None = None) -> _dt.datetime | None:
    """Proximo inicio de franja laboral."""
    tz = _tz()
    now = from_dt or _dt.datetime.now(tz)
    if now.tzinfo is None:
        now = tz.localize(now)
    for delta in range(0, 14):
        day = (now + _dt.timedelta(days=delta)).date()
        if is_holiday(day):
            continue
        windows = _windows_for(day.weekday())
        for (s, _) in windows:
            dt = tz.localize(_dt.datetime.combine(day, s))
            if dt > now:
                return dt
    return None


# ---------------- Cola Telegram diferida ----------------


def _cargar_cola() -> list[dict]:
    try:
        if QUEUE_PATH.exists():
            return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _guardar_cola(items: list[dict]) -> None:
    try:
        QUEUE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def encolar(text: str, parse_mode: str = "HTML", chat_id: str | None = None) -> None:
    cola = _cargar_cola()
    cola.append({
        "text": text,
        "parse_mode": parse_mode,
        "chat_id": chat_id,
        "added_at": _dt.datetime.utcnow().isoformat() + "Z",
    })
    _guardar_cola(cola)


def vaciar_cola() -> int:
    """Envia todos los mensajes encolados (solo si estamos en franja)."""
    if not is_working_now():
        return 0
    # Importacion diferida para evitar ciclo
    from app.integrations.telegram_bot import send_message
    cola = _cargar_cola()
    if not cola:
        return 0
    enviados = 0
    resto: list[dict] = []
    for item in cola:
        try:
            send_message(item["text"], chat_id=item.get("chat_id"), parse_mode=item.get("parse_mode", "HTML"))
            enviados += 1
        except Exception:
            resto.append(item)
    _guardar_cola(resto)
    return enviados


def estado() -> dict:
    return {
        "working_now": is_working_now(),
        "next_start": (next_working_start() or "").isoformat() if next_working_start() else None,
        "queue_size": len(_cargar_cola()),
        "windows_today": [
            f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
            for (s, e) in _windows_for(_dt.datetime.now(_tz()).weekday())
        ],
    }
