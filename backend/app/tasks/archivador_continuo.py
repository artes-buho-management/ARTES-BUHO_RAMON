"""Archivador continuo de Gmail.

Corre cada 20 min desde el scheduler. Objetivo: procesar poco a poco TODO el
inbox (nuevos y viejos), no solo los unread. Va comiendose el backlog.

Estrategia:
- Lista los mensajes mas viejos del INBOX que aun no esten en EmailProcessed.
- Procesa N por lote (default 10) con la clasificacion de Gemini.
- Cada email queda: archivado, en basura, escalado o con borrador segun corresponda.
- Respeta rate limit Gemini: si cae QuotaExceeded, corta el lote sin error.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.settings import get_settings
from app.core.database import SessionLocal
from app.core.models import EmailProcessed


log = logging.getLogger("ramon.archivador")


def _ids_ya_procesados(limit: int = 5000) -> set[str]:
    if SessionLocal is None:
        return set()
    try:
        with SessionLocal() as db:
            rows = db.query(EmailProcessed.gmail_id).limit(limit).all()
            return {r[0] for r in rows}
    except Exception:
        return set()


def archivar_lote(max_por_lote: int = 10, query: str = "in:inbox") -> dict[str, Any]:
    """Procesa un lote pequeño del inbox. Vuelve a llamarse desde el scheduler."""
    from app.integrations import gmail as gmail_mod
    from app.tasks.orquestador import procesar_email
    from app.learning.aprendizaje import cargar_contexto_aprendizaje

    settings = get_settings()
    account = settings.gmail_user

    ya_procesados = _ids_ya_procesados()
    try:
        candidatos = gmail_mod.list_messages(account, query=query, max_results=50)
    except Exception as exc:
        return {"error": f"list_messages: {exc}"}

    # Priorizar mas viejos primero (Gmail devuelve del mas reciente al mas viejo)
    pendientes = [m for m in candidatos if m["id"] not in ya_procesados]
    if not pendientes:
        return {"lote": 0, "mensaje": "backlog vacio — todo clasificado"}

    # Coger los mas viejos (final de la lista)
    objetivo = pendientes[-max_por_lote:]

    try:
        aprendizaje_ctx = cargar_contexto_aprendizaje()
    except Exception:
        aprendizaje_ctx = ""

    procesados = 0
    acciones: dict[str, int] = {}
    errores: list[str] = []

    for m in objetivo:
        r = procesar_email(account, m["id"], aprendizaje_ctx=aprendizaje_ctx)
        if r.get("error") == "quota_exceeded":
            errores.append("quota")
            break
        if r.get("error"):
            errores.append(str(r.get("error"))[:100])
            continue
        if r.get("skipped"):
            continue
        procesados += 1
        acc = r.get("accion", "—")
        acciones[acc] = acciones.get(acc, 0) + 1

    return {
        "lote": len(objetivo),
        "procesados": procesados,
        "acciones": acciones,
        "errores": errores[-5:],
        "pendientes_aprox": max(0, len(pendientes) - procesados),
    }


def sync_snapshot() -> dict[str, Any]:
    """Snapshot del estado de Ramon, pensado para consumo desde Consultora (este chat).

    Devuelve contadores, ultimas decisiones, ultimas acciones, aprendizajes recientes.
    """
    import datetime as _dt
    from app.decisions.semaforo import listar_pendientes

    snapshot: dict[str, Any] = {
        "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
        "environment": get_settings().env,
    }

    # Emails procesados
    if SessionLocal is not None:
        try:
            from app.core.models import EmailProcessed, TelegramMessage, Decision
            with SessionLocal() as db:
                snapshot["emails_procesados_total"] = db.query(EmailProcessed).count()
                # Ultimos 10 emails
                ultimos = (
                    db.query(EmailProcessed)
                    .order_by(EmailProcessed.processed_at.desc())
                    .limit(10).all()
                )
                snapshot["ultimos_emails"] = [
                    {
                        "fecha": e.processed_at.isoformat() if e.processed_at else None,
                        "de": e.sender,
                        "asunto": e.subject,
                        "nivel": e.decision_level,
                        "accion": e.action_taken,
                    }
                    for e in ultimos
                ]
                # Decisiones pendientes
                pend_amar = db.query(Decision).filter(
                    Decision.level == "amarillo", Decision.resolved_at.is_(None)
                ).count()
                pend_rojo = db.query(Decision).filter(
                    Decision.level == "rojo", Decision.resolved_at.is_(None)
                ).count()
                snapshot["decisiones_pendientes"] = {"amarillo": pend_amar, "rojo": pend_rojo}
                # Ultimas 10 interacciones Telegram
                tg = (
                    db.query(TelegramMessage)
                    .order_by(TelegramMessage.created_at.desc())
                    .limit(15).all()
                )
                snapshot["ultimas_telegram"] = [
                    {
                        "t": m.created_at.isoformat() if m.created_at else None,
                        "dir": m.direction,
                        "msg": (m.message or "")[:200],
                    }
                    for m in tg
                ]
        except Exception as exc:
            snapshot["db_error"] = str(exc)[:200]

    # Aprendizajes recientes
    try:
        from app.integrations import drive as drive_mod
        chat_md = drive_mod.leer_aprendizaje_chat() or ""
        vps_md = drive_mod.leer_aprendizaje_vps() or ""
        snapshot["aprendizaje_chat_tail"] = chat_md[-1500:] if chat_md else ""
        snapshot["aprendizaje_vps_tail"] = vps_md[-1500:] if vps_md else ""
    except Exception as exc:
        snapshot["drive_error"] = str(exc)[:200]

    snapshot["pendientes_actuales"] = listar_pendientes(limite=10)
    return snapshot
