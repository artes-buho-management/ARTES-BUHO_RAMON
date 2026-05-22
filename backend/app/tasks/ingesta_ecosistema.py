"""Ingesta y entrenamiento profundo sobre todo el ecosistema Google de Ramón.

Ramón procesa progresivamente:
- Gmail: sent + inbox (histórico año + actual)
- Calendar: eventos (año pasado + año próximo)
- Drive: archivos propios de la cuenta (hasta N MB por sesión)
- Sheets CRM: dump completo
- Carpetas clave: Zonavit Promotores, Logos, carpeta Ramón

Diseño:
- Estado persistente en /tmp/ramon_ingest_state.json (o Drive si queremos sobrevivir restarts).
- Cada invocación procesa 1 batch pequeño, actualiza estado, pausa.
- Tolera 429 Gemini (retry interno ya implementado) y errores aislados.
- Se ejecuta desde scheduler cada 30 min hasta completar; luego pasa a modo mantenimiento
  (re-escanea cambios recientes).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
import traceback
from pathlib import Path
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod
from app.integrations import drive as drive_mod
from app.integrations import sheets_crm as crm_mod
from app.google_client import calendar, drive as drive_cli
from app.integrations.gemini_brain import _call_gemini, GeminiBrainError, QuotaExceeded


STATE_PATH = Path(os.getenv("RAMON_INGEST_STATE", "/tmp/ramon_ingest_state.json"))
# Si STATE_PATH_DRIVE=true, guardamos tambien una copia en Drive para sobrevivir restarts del contenedor
STATE_DRIVE_NAME = "_ramon_ingest_state.json"
BATCH_MAX_MSGS = 15
BATCH_MAX_EVENTS = 50
BATCH_MAX_DRIVE_FILES = 10
MAX_RUNTIME_SEC = 300  # 5 min por invocación; el scheduler vuelve a lanzar


def _load_state() -> dict[str, Any]:
    try:
        if STATE_PATH.exists():
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "phase": "gmail_sent",      # gmail_sent → gmail_inbox → calendar → crm → drive → mantenimiento
        "gmail_sent_page_token": None,
        "gmail_sent_processed_ids": [],
        "gmail_inbox_page_token": None,
        "gmail_inbox_processed_ids": [],
        "calendar_offset": 0,
        "drive_processed_ids": [],
        "drive_page_token": None,
        "last_run": None,
        "totals": {"gmail_sent": 0, "gmail_inbox": 0, "events": 0, "drive_files": 0},
        "errores": [],
    }


def _save_state(state: dict) -> None:
    state["last_run"] = _dt.datetime.utcnow().isoformat() + "Z"
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _flush_al_drive(titulo: str, contenido: str) -> None:
    """Añade un bloque al Aprendizaje_Ramon.md."""
    try:
        actual = drive_mod.leer_aprendizaje_ramon() or "# Aprendizaje_Ramon.md\n\n"
        bloque = f"\n\n## {titulo}\n\n{contenido.strip()}"
        drive_mod.escribir_aprendizaje_ramon(actual + bloque)
    except Exception:
        pass


# ---------- Fase Gmail sent ----------

def _ingestar_gmail(state: dict, account: str, start_time: float,
                    key_token: str, key_ids: str, total_key: str,
                    query: str) -> bool:
    """Procesa una ventana de correos (por paginación). Devuelve True si queda más."""
    svc = gmail_mod._service(account)  # type: ignore[attr-defined]
    page_token = state.get(key_token)
    processed_ids: set = set(state.get(key_ids, []))
    new_samples: list[str] = []

    while time.time() - start_time < MAX_RUNTIME_SEC:
        resp = svc.users().messages().list(
            userId="me", q=query, maxResults=50, pageToken=page_token,
        ).execute()
        msgs = resp.get("messages", [])
        page_token = resp.get("nextPageToken")

        for m in msgs:
            mid = m["id"]
            if mid in processed_ids:
                continue
            try:
                info = gmail_mod.get_message(account, mid)
                snippet = (info.get("body_text") or "")[:1200]
                new_samples.append(
                    f"--- {info.get('date','')[:25]} | {info.get('subject','')[:80]}\n{snippet}"
                )
                processed_ids.add(mid)
                state["totals"][total_key] = state["totals"].get(total_key, 0) + 1
            except Exception as exc:
                state["errores"].append(f"{account}/{mid}: {exc}")
            if len(new_samples) >= BATCH_MAX_MSGS:
                break
        if len(new_samples) >= BATCH_MAX_MSGS or not page_token:
            break

    state[key_token] = page_token
    state[key_ids] = list(processed_ids)[-5000:]  # limitar tamano

    if new_samples:
        prompt = (
            "Extrae observaciones utiles para Ramon (asistente ARTES BUHO). "
            "JSON compacto con: tono_detectado, saludos, cierres, frases_clave, "
            "preferencias, alertas_criticas, clientes_mencionados, temas."
        )
        try:
            raw = _call_gemini(prompt, "\n\n".join(new_samples), response_json=True, max_tokens=2500, is_email_call=False)
            analisis = json.loads(raw) if raw.strip().startswith("{") else {}
            if analisis:
                _flush_al_drive(
                    f"Ingesta Gmail {account} — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    json.dumps(analisis, ensure_ascii=False, indent=2),
                )
        except QuotaExceeded:
            return True  # reintentar más tarde
        except Exception as exc:
            state["errores"].append(f"gemini_gmail: {exc}")

    return bool(page_token)


# ---------- Fase Calendar ----------

def _ingestar_calendar(state: dict, start_time: float) -> bool:
    offset = state.get("calendar_offset", 0)
    cal = calendar()
    cal_id = get_settings().google_calendar_id or "primary"
    time_min = (_dt.datetime.utcnow() - _dt.timedelta(days=365)).isoformat() + "Z"
    time_max = (_dt.datetime.utcnow() + _dt.timedelta(days=180)).isoformat() + "Z"

    resp = cal.events().list(
        calendarId=cal_id, timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy="startTime", maxResults=BATCH_MAX_EVENTS,
        pageToken=state.get("calendar_page_token"),
    ).execute()
    events = resp.get("items", [])
    next_token = resp.get("nextPageToken")

    resumenes = []
    for ev in events:
        s = ev.get("start", {})
        when = s.get("dateTime") or s.get("date", "")
        resumenes.append(f"{when} | {ev.get('summary','(sin titulo)')} | {(ev.get('description','') or '')[:200]}")
        state["totals"]["events"] += 1

    if resumenes:
        prompt = (
            "Eres Ramon. Analiza estos eventos del calendario de ARTES BUHO. "
            "Devuelve JSON: {patrones_agenda, clientes_recurrentes, fechas_importantes, "
            "tipos_evento_frecuentes, observaciones}."
        )
        try:
            raw = _call_gemini(prompt, "\n".join(resumenes), response_json=True, max_tokens=2000, is_email_call=False)
            analisis = json.loads(raw) if raw.strip().startswith("{") else {}
            if analisis:
                _flush_al_drive(
                    f"Ingesta Calendar — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                    json.dumps(analisis, ensure_ascii=False, indent=2),
                )
        except Exception as exc:
            state["errores"].append(f"gemini_calendar: {exc}")

    state["calendar_offset"] = offset + len(events)
    state["calendar_page_token"] = next_token
    return bool(next_token)


# ---------- Fase CRM ----------

def _ingestar_crm(state: dict) -> bool:
    try:
        rows = crm_mod.read_all()
    except Exception as exc:
        state["errores"].append(f"crm_read: {exc}")
        return False
    if not rows:
        return False
    # Resumen estadístico simple sin mandar todo a Gemini
    resumen = {
        "total_filas": len(rows),
        "cabeceras": list(rows[0].keys()) if rows else [],
        "muestra": rows[:5],
    }
    _flush_al_drive(
        f"Ingesta CRM — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        json.dumps(resumen, ensure_ascii=False, indent=2)[:6000],
    )
    state["totals"]["crm_rows"] = len(rows)
    return False  # una sola pasada


# ---------- Fase Drive ----------

def _ingestar_drive(state: dict, start_time: float) -> bool:
    svc = drive_cli()
    processed = set(state.get("drive_processed_ids", []))
    page_token = state.get("drive_page_token")
    nuevos = []
    while time.time() - start_time < MAX_RUNTIME_SEC:
        resp = svc.files().list(
            q="trashed=false and 'me' in owners",
            fields="files(id,name,mimeType,modifiedTime,size),nextPageToken",
            pageSize=50,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        page_token = resp.get("nextPageToken")
        for f in files:
            if f["id"] in processed:
                continue
            processed.add(f["id"])
            nuevos.append(f)
            state["totals"]["drive_files"] += 1
            if len(nuevos) >= BATCH_MAX_DRIVE_FILES:
                break
        if len(nuevos) >= BATCH_MAX_DRIVE_FILES or not page_token:
            break
    if nuevos:
        lista = "\n".join(f"- {f['name']} ({f['mimeType']}) {f.get('modifiedTime','')}" for f in nuevos)
        _flush_al_drive(
            f"Ingesta Drive — {_dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            lista,
        )
    state["drive_processed_ids"] = list(processed)[-10000:]
    state["drive_page_token"] = page_token
    return bool(page_token)


# ---------- Orquestador fases ----------

PHASES = ["gmail_sent", "gmail_inbox", "calendar", "crm", "drive", "mantenimiento"]


def tick(max_runtime_sec: int = MAX_RUNTIME_SEC) -> dict[str, Any]:
    """Ejecuta un tick: avanza la fase actual. Llamar periodicamente desde scheduler."""
    state = _load_state()
    start = time.time()
    settings = get_settings()

    phase = state.get("phase", "gmail_sent")
    try:
        if phase == "gmail_sent":
            hay_mas = _ingestar_gmail(
                state, settings.gmail_user, start,
                key_token="gmail_sent_page_token", key_ids="gmail_sent_processed_ids",
                total_key="gmail_sent", query="in:sent newer_than:2y",
            )
            if not hay_mas:
                state["phase"] = "gmail_inbox"
        elif phase == "gmail_inbox":
            hay_mas = _ingestar_gmail(
                state, settings.gmail_user, start,
                key_token="gmail_inbox_page_token", key_ids="gmail_inbox_processed_ids",
                total_key="gmail_inbox", query="in:inbox newer_than:2y",
            )
            if not hay_mas:
                state["phase"] = "calendar"
        elif phase == "calendar":
            hay_mas = _ingestar_calendar(state, start)
            if not hay_mas:
                state["phase"] = "crm"
        elif phase == "crm":
            _ingestar_crm(state)
            state["phase"] = "drive"
        elif phase == "drive":
            hay_mas = _ingestar_drive(state, start)
            if not hay_mas:
                state["phase"] = "mantenimiento"
        else:  # mantenimiento
            # Reescanea solo lo reciente
            _ingestar_gmail(
                state, settings.gmail_user, start,
                key_token="maint_gmail_token", key_ids="gmail_sent_processed_ids",
                total_key="gmail_sent", query="in:sent newer_than:7d",
            )
    except QuotaExceeded as exc:
        state["errores"].append(f"quota: {exc}")
    except Exception as exc:
        state["errores"].append(f"{phase}: {exc}\n{traceback.format_exc()[:500]}")

    _save_state(state)
    return {
        "phase": state["phase"],
        "totals": state["totals"],
        "errores": state["errores"][-5:],
        "runtime_s": round(time.time() - start, 2),
    }


def progreso() -> dict[str, Any]:
    return _load_state()


def reset() -> dict:
    if STATE_PATH.exists():
        STATE_PATH.unlink()
    return {"reset": True}
