"""Orquestador de tareas diarias de Ramon (protocolo v4 seccion 8).

Secuencia 08:00 dia laborable:
 1. Validar dia laborable Coslada
 2. Leer Aprendizaje (Chat + VPS + Ramon maestro)
 3. Procesar emails nuevos de manager@ y personal
 4. Para cada uno: clasificar con Gemini, aplicar accion, registrar
 5. Revisar Calendar y detectar conflictos
 6. Listar cobros pendientes >7 dias
 7. Generar informe diario
 8. Enviarlo por Telegram a las 08:15
 9. Subir copia PDF a Drive/02_Diario
10. Registrar aprendizaje si detecta patrones
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from app.core.calendar_utils import is_workday, today_local, now_local
from app.core.settings import get_settings
from app.core.database import SessionLocal
from app.core.models import EmailProcessed, SystemLog
from app.integrations import gmail as gmail_mod
from app.integrations import signatures as sig_mod
from app.integrations import sheets_crm as crm_mod
from app.integrations.gemini_brain import classify_email, GeminiBrainError, QuotaExceeded
from app.integrations.telegram_bot import send_message, format_report, send_error
from app.decisions import semaforo
from app.learning import aprendizaje as apr


log = logging.getLogger("ramon.orquestador")


def _log_evento(nivel: str, fuente: str, mensaje: str, meta: dict | None = None) -> None:
    log.log(getattr(logging, nivel.upper(), logging.INFO), f"[{fuente}] {mensaje}")
    if SessionLocal is None:
        return
    try:
        with SessionLocal() as db:
            db.add(SystemLog(level=nivel, source=fuente, message=mensaje, meta=meta or {}))
            db.commit()
    except Exception:
        pass


def _ya_procesado(msg_id: str) -> bool:
    if SessionLocal is None:
        return False
    try:
        with SessionLocal() as db:
            return db.query(EmailProcessed).filter(EmailProcessed.gmail_id == msg_id).first() is not None
    except Exception:
        return False


def _marcar_procesado(
    *, msg_id: str, account: str, thread_id: str,
    sender: str, subject: str, clasificacion: dict[str, Any], accion: str,
) -> None:
    if SessionLocal is None:
        return
    try:
        with SessionLocal() as db:
            row = EmailProcessed(
                gmail_id=msg_id,
                account=account,
                thread_id=thread_id,
                sender=sender[:255],
                subject=subject[:500],
                category=clasificacion.get("categoria"),
                urgency=clasificacion.get("urgencia"),
                decision_level=clasificacion.get("nivel_decision"),
                action_taken=accion,
                claude_response=clasificacion,
            )
            db.add(row)
            db.commit()
    except Exception as exc:
        _log_evento("warn", "orquestador", f"No se pudo persistir EmailProcessed: {exc}")


def procesar_email(account: str, msg_id: str, *, aprendizaje_ctx: str) -> dict[str, Any]:
    """Procesa un email: lee, clasifica, ejecuta la accion correspondiente."""
    if _ya_procesado(msg_id):
        return {"skipped": True, "reason": "ya procesado"}

    try:
        msg = gmail_mod.get_message(account, msg_id)
    except Exception as exc:
        return {"error": f"get_message: {exc}"}

    sender = msg["from"]
    sender_email = gmail_mod.extract_email_address(sender)
    subject = msg["subject"]
    body = msg["body_text"][:6000]

    # Cruce con CRM
    crm_row = None
    try:
        if sender_email:
            crm_row = crm_mod.buscar_por_email(sender_email)
    except Exception as exc:
        _log_evento("warn", "orquestador", f"CRM lookup fallo: {exc}")

    extra_context = ""
    if crm_row:
        extra_context = f"CRM MATCH: {crm_row}"

    # Inyectar franjas libres (videollamadas) — solo si el email parece pedir reunion
    try:
        from app.core.availability import bloque_prompt_disponibilidad
        txt_lower = (subject + " " + body).lower()
        if any(k in txt_lower for k in ["videollamada", "meet", "reunion", "reunión", "llamar", "hablamos", "conocer"]):
            disp = bloque_prompt_disponibilidad(max_results=8)
            extra_context = (extra_context + "\n\n" + disp).strip()
    except Exception:
        pass

    # Clasificacion con Gemini
    try:
        clasificacion = classify_email(
            from_email=sender_email or sender,
            subject=subject,
            body=body,
            account=account,
            thread_context=msg.get("snippet", ""),
            learning_md=aprendizaje_ctx + ("\n\n" + extra_context if extra_context else ""),
        )
    except QuotaExceeded as exc:
        _log_evento("warn", "gemini", f"Quota: {exc}")
        return {"error": "quota_exceeded", "detail": str(exc)}
    except GeminiBrainError as exc:
        _log_evento("error", "gemini", f"Error: {exc}")
        return {"error": "gemini_error", "detail": str(exc)}

    # Ajuste semaforo
    nivel = semaforo.ajustar_nivel(
        clasificacion.get("nivel_decision", "amarillo"),
        subject, body,
    )
    clasificacion["nivel_decision"] = nivel
    accion_original = clasificacion.get("accion", "crear_borrador")

    # Forzar solo borradores en cuenta personal y en modo conservador
    if account == get_settings().gmail_personal and accion_original == "responder_auto":
        clasificacion["accion"] = "crear_borrador"
    if get_settings().draft_only and accion_original == "responder_auto":
        clasificacion["accion"] = "crear_borrador"

    accion = clasificacion["accion"]

    # Ejecutar accion
    try:
        resultado = _ejecutar_accion(account, msg, clasificacion)
    except Exception as exc:
        _log_evento("error", "orquestador", f"Accion {accion} fallo: {exc}")
        resultado = {"error": str(exc)}

    # Registrar
    _marcar_procesado(
        msg_id=msg_id, account=account, thread_id=msg.get("thread_id", ""),
        sender=sender, subject=subject, clasificacion=clasificacion, accion=accion,
    )
    if nivel in {"amarillo", "rojo"}:
        semaforo.registrar(
            nivel=nivel,
            tema=f"Email: {subject[:120]}",
            propuesta=(clasificacion.get("borrador_cuerpo") or "")[:500],
        )
    return {"ok": True, "accion": accion, "nivel": nivel, "resultado": resultado}


def _ejecutar_accion(account: str, msg: dict, clasif: dict) -> dict[str, Any]:
    accion = clasif.get("accion", "crear_borrador")
    etiquetas = clasif.get("etiquetas", []) or []

    if accion == "ignorar":
        if etiquetas:
            gmail_mod.apply_labels(account, msg["id"], add=etiquetas)
        return {"ignored": True}

    if accion == "archivar":
        gmail_mod.apply_labels(account, msg["id"], add=["ESTADO/ARCHIVADO", *etiquetas])
        gmail_mod.archive(account, msg["id"])
        return {"archived": True}

    if accion == "basura":
        gmail_mod.mover_a_basura(account, msg["id"])
        return {"basura": True}

    if accion in {"crear_borrador", "responder_auto"}:
        asunto = clasif.get("borrador_asunto") or f"Re: {msg['subject']}"
        cuerpo_txt = (clasif.get("borrador_cuerpo") or "").strip()
        if not cuerpo_txt:
            return {"skipped": "borrador vacio"}
        firma = sig_mod.select_signature(
            categoria=clasif.get("categoria", ""),
            account=account,
            firma_sugerida=clasif.get("firma_a_usar"),
        )
        closing = "Un abrazo fuerte," if firma == "after_you" else "Un abrazo,"
        html = sig_mod.render_email(body_text=cuerpo_txt, signature=firma, closing=closing)
        sender_email = gmail_mod.extract_email_address(msg["from"])

        if accion == "crear_borrador" or get_settings().draft_only:
            draft = gmail_mod.create_draft(
                account,
                to=sender_email,
                subject=asunto,
                body_html=html,
                thread_id=msg.get("thread_id"),
                in_reply_to=msg.get("message_id", ""),
                references=msg.get("references", ""),
            )
            gmail_mod.apply_labels(account, msg["id"], add=["ESTADO/REVISION", *etiquetas])
            return {"draft_id": draft.get("id"), "firma": firma}

        # Respuesta automatica (solo si draft_only=false y accion=responder_auto)
        sent = gmail_mod.send_message(
            account,
            to=sender_email,
            subject=asunto,
            body_html=html,
            thread_id=msg.get("thread_id"),
            in_reply_to=msg.get("message_id", ""),
            references=msg.get("references", ""),
        )
        gmail_mod.apply_labels(account, msg["id"], add=["ESTADO/ARCHIVADO", *etiquetas])
        return {"sent_id": sent.get("id"), "firma": firma}

    if accion == "escalar":
        gmail_mod.apply_labels(account, msg["id"], add=["ESTADO/ACCION", *etiquetas])
        return {"escalated": True}

    return {"unknown_action": accion}


def _listar_nuevos(account: str, limite: int = 30) -> list[str]:
    try:
        mensajes = gmail_mod.safe_list_unread(account, max_results=limite)
        return [m["id"] for m in mensajes]
    except Exception as exc:
        _log_evento("warn", "orquestador", f"list_unread {account}: {exc}")
        return []


def _resumen_por_cuenta(results: list[dict]) -> list[str]:
    out = []
    for r in results:
        if r.get("error"):
            continue
        if r.get("skipped"):
            continue
        nivel = r.get("nivel", "?")
        acc = r.get("accion", "?")
        out.append(f"{nivel.upper()} · {acc}")
    return out


def ejecutar_rutina_diaria(force: bool = False) -> dict[str, Any]:
    """Punto de entrada de la rutina 08:00. Devuelve payload del informe."""
    settings = get_settings()
    hoy = today_local()

    if not force and not is_workday(hoy):
        _log_evento("info", "orquestador", f"{hoy} no es laborable, skip")
        return {"skipped": True, "reason": "no_laborable", "fecha": hoy.isoformat()}

    _log_evento("info", "orquestador", f"Arranque rutina diaria {hoy}")

    # Asegurar estructura Drive y aprendizaje inicial
    try:
        apr.inicializar_archivos_si_vacios()
    except Exception as exc:
        _log_evento("warn", "orquestador", f"init aprendizaje fallo: {exc}")

    try:
        aprendizaje_ctx = apr.cargar_contexto_aprendizaje()
    except Exception as exc:
        _log_evento("warn", "orquestador", f"leer aprendizaje fallo: {exc}")
        aprendizaje_ctx = ""

    # Procesar manager@
    manager_results: list[dict] = []
    for mid in _listar_nuevos(settings.gmail_user):
        r = procesar_email(settings.gmail_user, mid, aprendizaje_ctx=aprendizaje_ctx)
        manager_results.append(r)
        if r.get("error") == "quota_exceeded":
            break

    # Procesar personal (solo lectura + borradores)
    personal_results: list[dict] = []
    for mid in _listar_nuevos(settings.gmail_personal, limite=20):
        r = procesar_email(settings.gmail_personal, mid, aprendizaje_ctx=aprendizaje_ctx)
        personal_results.append(r)
        if r.get("error") == "quota_exceeded":
            break

    # Agenda del dia (Calendar)
    agenda = []
    try:
        from app.google_client import calendar_upcoming
        for ev in calendar_upcoming(max_results=10):
            start = ev.get("start", {})
            when = start.get("dateTime") or start.get("date", "")
            agenda.append(f"{when} — {ev.get('summary', '(sin titulo)')}")
    except Exception as exc:
        _log_evento("warn", "orquestador", f"calendar: {exc}")

    # Cobros pendientes
    cobros = []
    try:
        for c in crm_mod.cobros_pendientes():
            cobros.append(str({k: v for k, v in c.items() if v})[:180])
    except Exception as exc:
        _log_evento("warn", "orquestador", f"cobros: {exc}")

    # Alertas
    alertas = []
    errors_gemini = sum(1 for r in manager_results + personal_results if r.get("error"))
    if errors_gemini:
        alertas.append(f"{errors_gemini} fallos Gemini")
    pendientes_amarillo_rojo = sum(
        1 for r in manager_results + personal_results
        if r.get("nivel") in {"amarillo", "rojo"}
    )
    if pendientes_amarillo_rojo:
        alertas.append(f"{pendientes_amarillo_rojo} decisiones pendientes (amarillo/rojo)")

    payload = {
        "fecha": hoy.isoformat(),
        "urgente": [r.get("resultado", {}).get("subject", "") for r in manager_results if r.get("nivel") == "rojo"],
        "agenda": agenda,
        "emails_pendientes": _resumen_por_cuenta(manager_results),
        "personal": _resumen_por_cuenta(personal_results),
        "cobros": cobros,
        "bolos": [],  # se rellena con busqueda dedicada en Calendar con titulo "BOLO"
        "alertas": alertas,
        "modo_solo_borradores": settings.draft_only,
        "_stats": {
            "manager_total": len(manager_results),
            "personal_total": len(personal_results),
            "hora": now_local().isoformat(),
        },
    }
    return payload


def enviar_informe_telegram(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        texto = format_report(payload)
        return send_message(texto)
    except Exception as exc:
        send_error(exc)
        raise


def ejecutar_y_enviar() -> dict[str, Any]:
    """Entrada completa: rutina + informe Telegram."""
    try:
        payload = ejecutar_rutina_diaria()
        if payload.get("skipped"):
            return payload
        enviar_informe_telegram(payload)
        return {"ok": True, **payload}
    except Exception as exc:
        send_error(exc)
        _log_evento("error", "orquestador", f"Fallo general: {exc}")
        raise
