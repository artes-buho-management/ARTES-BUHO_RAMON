"""Modo ENTRENAMIENTO de Ramon.

Durante N dias:
- Ramon SOLO lee, clasifica, etiqueta, archiva y APRENDE.
- Cero escritura externa: no envia emails, no responde, no publica.
- Cada 6h genera una auditoria con metricas y la sube a Drive.
- Notifica por Telegram cada auditoria.

Se activa via POST /training/start?days=5.
Se desactiva solo al llegar la fecha fin.

El estado se guarda en PostgreSQL (tabla system_logs con key=training_until)
para que sobreviva a reinicios del pod.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from app.core.database import SessionLocal
from app.core.models import SystemLog

log = logging.getLogger("ramon.training")

_TRAINING_KEY = "training_until"


def get_training_until() -> datetime | None:
    """Devuelve la fecha/hora hasta la que esta activo el modo entrenamiento."""
    with SessionLocal() as sess:
        row = (sess.query(SystemLog)
               .filter(SystemLog.message == _TRAINING_KEY)
               .order_by(SystemLog.id.desc())
               .first())
        if not row or not row.details:
            return None
        try:
            data = json.loads(row.details)
            end = data.get("until_iso")
            if end:
                return datetime.fromisoformat(end)
        except Exception:
            return None
    return None


def is_training_active() -> bool:
    end = get_training_until()
    return end is not None and end > datetime.utcnow()


def start_training(days: int = 5, until_iso: str | None = None) -> dict[str, Any]:
    if until_iso:
        try:
            end = datetime.fromisoformat(until_iso.replace("Z", ""))
        except Exception:
            raise ValueError(f"until_iso invalido: {until_iso}")
    else:
        if days < 1 or days > 60:
            raise ValueError("days debe estar entre 1 y 60")
        end = datetime.utcnow() + timedelta(days=days)
    with SessionLocal() as sess:
        sess.add(SystemLog(
            level="INFO",
            message=_TRAINING_KEY,
            details=json.dumps({
                "until_iso": end.isoformat(),
                "started_iso": datetime.utcnow().isoformat(),
                "days": days,
            }),
        ))
        sess.commit()
    log.info(f"Modo entrenamiento activo hasta {end.isoformat()}Z")
    return {"ok": True, "training_until_utc": end.isoformat(), "days": days}


def stop_training() -> dict[str, Any]:
    """Cancela el modo entrenamiento (marca until en el pasado)."""
    past = datetime.utcnow() - timedelta(days=1)
    with SessionLocal() as sess:
        sess.add(SystemLog(
            level="INFO", message=_TRAINING_KEY,
            details=json.dumps({"until_iso": past.isoformat(), "cancelled": True}),
        ))
        sess.commit()
    return {"ok": True, "cancelled": True}


def status() -> dict[str, Any]:
    end = get_training_until()
    active = is_training_active()
    remaining = None
    if end:
        delta = end - datetime.utcnow()
        remaining = max(0, int(delta.total_seconds() / 3600))
    return {
        "active": active,
        "until_utc": end.isoformat() if end else None,
        "hours_remaining": remaining,
    }


# --------- Auditoria automatica ----------

_AUDIT_SYSTEM_PROMPT = (
    "Eres un auditor senior del sistema Ramon (asistente ejecutivo de ARTES BUHO). "
    "Se te dan metricas reales de las ultimas horas. Tu mision: "
    "1) detectar errores o patrones anomalos, "
    "2) proponer mejoras concretas, "
    "3) cruzar datos entre metricas para descubrir insights, "
    "4) evaluar si la cascada IA esta siendo eficiente, "
    "5) senalar tareas que deberian optimizarse. "
    "Responde en castellano de Espana, conciso, en formato markdown con "
    "secciones: ## Errores detectados, ## Insights cruzados, ## Mejoras propuestas, "
    "## Puntuacion global (0-100). No inventes datos: si una metrica es 0 dilo."
)


def run_audit() -> dict[str, Any]:
    """Audita estado de Ramon. Durante entrenamiento se llama cada 5 min."""
    import os
    from app.integrations import brain_router
    from app.google_client import drive as _drive_service
    from googleapiclient.http import MediaInMemoryUpload
    from sqlalchemy import func
    from app.core.models import EmailProcessed, Decision, TelegramMessage

    ts = datetime.utcnow()
    # Metricas
    with SessionLocal() as sess:
        emails_24h = sess.query(func.count(EmailProcessed.id)).filter(
            EmailProcessed.created_at >= ts - timedelta(hours=24)
        ).scalar() or 0
        decisions_24h = sess.query(func.count(Decision.id)).filter(
            Decision.created_at >= ts - timedelta(hours=24)
        ).scalar() or 0
        tg_24h = sess.query(func.count(TelegramMessage.id)).filter(
            TelegramMessage.created_at >= ts - timedelta(hours=24)
        ).scalar() or 0

    cascade = brain_router.status()
    configured = sum(1 for v in cascade.values()
                     if v.get("configured") or v.get("available"))

    training = status()

    # Llamar al cerebro TIER CRITICA para analisis profundo
    ia_analysis = ""
    ia_cerebro = "none"
    try:
        user_data = (f"Metricas Ramon {ts.isoformat()}Z:\n"
                     f"- Emails 24h: {emails_24h}\n"
                     f"- Decisiones 24h: {decisions_24h}\n"
                     f"- Mensajes Telegram 24h: {tg_24h}\n"
                     f"- Cascada IA configurada: {configured}/9\n"
                     f"- Proveedores en cooldown: "
                     f"{[n for n,v in cascade.items() if (v.get('cooldown_s') or 0)>0]}\n"
                     f"- Modo training restante (h): {status()['hours_remaining']}")
        ia_analysis, ia_cerebro = brain_router.generate(
            _AUDIT_SYSTEM_PROMPT, user_data, max_tokens=800, tier="critica"
        )
    except Exception as exc:
        ia_analysis = f"[analisis IA no disponible: {exc}]"

    # Informe markdown
    md_lines = [
        f"# Auditoria Ramon - {ts.strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"## Modo entrenamiento",
        f"- Activo: **{training['active']}**",
        f"- Hasta: {training['until_utc']}",
        f"- Horas restantes: {training['hours_remaining']}",
        "",
        f"## Metricas ultimas 24h",
        f"- Emails procesados: {emails_24h}",
        f"- Decisiones tomadas: {decisions_24h}",
        f"- Mensajes Telegram: {tg_24h}",
        "",
        f"## Cascada IA",
        f"- Configuradas: {configured}/9",
    ]
    for name, info in cascade.items():
        rank = info.get("rank", "?")
        model = info.get("model", "?")
        cd = info.get("cooldown_s", 0) or 0
        md_lines.append(f"  - rank={rank} {name}: {model} (cooldown={cd}s)")
    md_lines.append("")
    md_lines.append(f"## Analisis IA (cerebro={ia_cerebro})")
    md_lines.append("")
    md_lines.append(ia_analysis or "(sin analisis)")
    md = "\n".join(md_lines)

    # Guardar a Drive /01_Aprendizaje/training_<date>.md
    saved: dict = {}
    try:
        root = os.getenv("DRIVE_FOLDER_RAMON", "").strip()
        if not root:
            raise RuntimeError("DRIVE_FOLDER_RAMON no configurado")
        drive = _drive_service()
        # Localizar 01_Aprendizaje (crea si falta)
        q = (f"'{root}' in parents and trashed=false "
             "and mimeType='application/vnd.google-apps.folder' "
             "and name='01_Aprendizaje'")
        r = drive.files().list(q=q, fields='files(id)', pageSize=1).execute()
        files = r.get('files', [])
        if files:
            folder_id = files[0]['id']
        else:
            created = drive.files().create(
                body={"name": "01_Aprendizaje",
                      "mimeType": "application/vnd.google-apps.folder",
                      "parents": [root]}, fields='id').execute()
            folder_id = created['id']
        fname = f"training_audit_{ts.strftime('%Y-%m-%d_%H%M')}.md"
        media = MediaInMemoryUpload(md.encode("utf-8"), mimetype="text/markdown")
        uploaded = drive.files().create(
            body={"name": fname, "parents": [folder_id]},
            media_body=media, fields='id,name'
        ).execute()
        saved = {"id": uploaded['id'], "name": uploaded['name']}
    except Exception as exc:
        saved = {"error": str(exc)}

    return {
        "timestamp_utc": ts.isoformat(),
        "training": training,
        "metrics_24h": {
            "emails": emails_24h,
            "decisions": decisions_24h,
            "telegram": tg_24h,
        },
        "cascade_configured": configured,
        "drive_saved": saved,
    }
