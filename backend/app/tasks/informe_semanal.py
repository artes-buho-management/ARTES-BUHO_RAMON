"""Informe semanal de Ramon (viernes 08:00).

Resumen de la semana + proyeccion de la siguiente.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from app.core.database import SessionLocal
from app.core.calendar_utils import now_local
from app.core.settings import get_settings
from app.google_client import calendar_upcoming
from app.integrations import sheets_crm as crm
from app.integrations.telegram_bot import send_message
from app.decisions import semaforo


def _stats_emails_semana() -> dict[str, Any]:
    if SessionLocal is None:
        return {"total": 0}
    from app.core.models import EmailProcessed
    hace_7d = _dt.datetime.utcnow() - _dt.timedelta(days=7)
    with SessionLocal() as db:
        rows = db.query(EmailProcessed).filter(EmailProcessed.processed_at >= hace_7d).all()
    total = len(rows)
    niveles = {"verde": 0, "amarillo": 0, "rojo": 0}
    acciones: dict[str, int] = {}
    for r in rows:
        niv = r.decision_level or ""
        if niv in niveles:
            niveles[niv] += 1
        acc = r.action_taken or "—"
        acciones[acc] = acciones.get(acc, 0) + 1
    return {"total": total, "niveles": niveles, "acciones": acciones}


def _proxima_semana_agenda() -> list[str]:
    eventos = calendar_upcoming(max_results=20)
    out = []
    limite = now_local() + _dt.timedelta(days=7)
    for ev in eventos:
        start = ev.get("start", {})
        when = start.get("dateTime") or start.get("date", "")
        try:
            dt = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
            if dt > limite:
                continue
        except Exception:
            pass
        out.append(f"{when} — {ev.get('summary', '(sin titulo)')}")
    return out[:10]


def generar() -> dict[str, Any]:
    hoy = now_local().date()
    stats = _stats_emails_semana()
    pendientes_amarillo = len(semaforo.listar_pendientes(nivel="amarillo"))
    pendientes_rojo = len(semaforo.listar_pendientes(nivel="rojo"))
    cobros = []
    try:
        cobros = crm.cobros_pendientes()
    except Exception:
        pass
    agenda = _proxima_semana_agenda()

    return {
        "fecha": hoy.isoformat(),
        "periodo": f"semana hasta {hoy.isoformat()}",
        "stats_emails": stats,
        "decisiones_pendientes": {"amarillo": pendientes_amarillo, "rojo": pendientes_rojo},
        "cobros_pendientes_count": len(cobros),
        "proxima_semana_agenda": agenda,
    }


def _formatear_html(payload: dict[str, Any]) -> str:
    s = payload["stats_emails"]
    niv = s.get("niveles", {})
    lines = [
        "<b>📊 INFORME SEMANAL RAMON</b>",
        f"<i>{payload['fecha']}</i>",
        "",
        "<b>Emails procesados (7d):</b>",
        f"• Total: {s.get('total', 0)}",
        f"• 🟢 Verde: {niv.get('verde', 0)} · 🟡 Amarillo: {niv.get('amarillo', 0)} · 🔴 Rojo: {niv.get('rojo', 0)}",
        "",
        "<b>Decisiones pendientes:</b>",
        f"• 🟡 {payload['decisiones_pendientes']['amarillo']} amarillas",
        f"• 🔴 {payload['decisiones_pendientes']['rojo']} rojas",
        "",
        f"<b>Cobros pendientes:</b> {payload['cobros_pendientes_count']}",
        "",
        "<b>📅 Agenda proxima semana:</b>",
    ]
    for a in payload["proxima_semana_agenda"][:8]:
        lines.append(f"• {a}")
    if not payload["proxima_semana_agenda"]:
        lines.append("• (sin eventos)")
    return "\n".join(lines)


def enviar() -> dict[str, Any]:
    payload = generar()
    try:
        send_message(_formatear_html(payload))
        payload["telegram_sent"] = True
    except Exception as exc:
        payload["telegram_error"] = str(exc)
    return payload
