"""Escaneo historico de Gmail (protocolo v4 seccion 23).

Capa 1 — Escaneo inicial: una unica vez, revisa todo el historico.
Capa 2 — Revision profunda: lunes 08:05, ultimos 30 dias.
Capa 3 — Revision ligera: durante el dia (gestionada por orquestador).
"""
from __future__ import annotations

import datetime as _dt
import io
import logging
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod
from app.integrations import drive as drive_mod
from app.integrations.telegram_bot import send_message


log = logging.getLogger("ramon.escaneo")


def _buckets_por_remitente(messages: list[dict], account: str) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {}
    for m in messages[:500]:  # limitar por seguridad en capa 1
        try:
            info = gmail_mod.get_message(account, m["id"])
        except Exception:
            continue
        email = gmail_mod.extract_email_address(info["from"])
        if not email:
            continue
        buckets.setdefault(email, []).append(info["subject"] or "(sin asunto)")
    return buckets


def _hilos_sin_respuesta(account: str, dias: int) -> list[dict]:
    """Busca hilos donde el ultimo en escribir NO sea Ruben."""
    since = (_dt.date.today() - _dt.timedelta(days=dias)).strftime("%Y/%m/%d")
    query = f"in:inbox after:{since}"
    try:
        messages = gmail_mod.list_messages(account, query=query, max_results=200)
    except Exception as exc:
        log.warning(f"list_messages {account}: {exc}")
        return []
    sin_respuesta = []
    for m in messages:
        try:
            info = gmail_mod.get_message(account, m["id"])
        except Exception:
            continue
        if "UNREAD" in info.get("label_ids", []):
            sin_respuesta.append({
                "from": info["from"], "subject": info["subject"], "date": info["date"],
            })
    return sin_respuesta


def escaneo_capa_1() -> dict[str, Any]:
    """Escaneo inicial completo. Solo debe ejecutarse UNA VEZ."""
    settings = get_settings()
    resultados: dict[str, Any] = {"fecha": _dt.date.today().isoformat(), "cuentas": {}}

    for account in [settings.gmail_user, settings.gmail_personal]:
        try:
            # Barrido paginado hasta 2000 mensajes (primera pasada)
            svc = gmail_mod._service(account)  # type: ignore[attr-defined]
            all_msgs: list[dict] = []
            page_token: str | None = None
            while len(all_msgs) < 2000:
                resp = svc.users().messages().list(
                    userId="me", q="in:anywhere", maxResults=500, pageToken=page_token,
                ).execute()
                all_msgs.extend(resp.get("messages", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

            buckets = _buckets_por_remitente(all_msgs, account)
            resultados["cuentas"][account] = {
                "total_mensajes_listados": len(all_msgs),
                "remitentes_unicos": len(buckets),
                "top_remitentes": sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:20],
            }
        except Exception as exc:
            resultados["cuentas"][account] = {"error": str(exc)}

    # Informe PDF/MD a Drive
    pdf_bytes = _informe_escaneo_pdf(resultados)
    drive_mod.guardar_escaneo_inicial(pdf_bytes)

    try:
        send_message(
            "<b>✅ Escaneo Capa 1 completado</b>\n"
            f"PDF en Drive/Ramon/04_Escaneo/Informe_Escaneo_Inicial.pdf"
        )
    except Exception:
        pass

    return resultados


def escaneo_capa_2() -> dict[str, Any]:
    """Revision profunda semanal: ultimos 30 dias."""
    settings = get_settings()
    out: dict[str, Any] = {"fecha": _dt.date.today().isoformat()}
    alertas: list[str] = []
    for account in [settings.gmail_user, settings.gmail_personal]:
        pendientes = _hilos_sin_respuesta(account, dias=30)
        out[account] = {"pendientes": len(pendientes), "ejemplos": pendientes[:5]}
        if pendientes:
            alertas.append(f"{account}: {len(pendientes)} hilos sin respuesta (30d)")

    if alertas:
        try:
            send_message("<b>📬 Escaneo semanal</b>\n" + "\n".join(f"• {a}" for a in alertas))
        except Exception:
            pass
    return out


def _informe_escaneo_pdf(resultados: dict) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        return str(resultados).encode("utf-8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Informe Escaneo Inicial")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Informe de Escaneo Inicial — Ramon", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Fecha: {resultados.get('fecha', '')}", styles["BodyText"]),
        Spacer(1, 12),
    ]
    for cuenta, data in resultados.get("cuentas", {}).items():
        story.append(Paragraph(f"<b>{cuenta}</b>", styles["Heading2"]))
        if "error" in data:
            story.append(Paragraph(f"Error: {data['error']}", styles["BodyText"]))
            continue
        story.append(Paragraph(f"Total listados: {data.get('total_mensajes_listados', 0)}", styles["BodyText"]))
        story.append(Paragraph(f"Remitentes unicos: {data.get('remitentes_unicos', 0)}", styles["BodyText"]))
        story.append(Paragraph("<b>Top remitentes:</b>", styles["BodyText"]))
        for email, asuntos in data.get("top_remitentes", []):
            story.append(Paragraph(f"• {email} ({len(asuntos)})", styles["BodyText"]))
        story.append(Spacer(1, 12))
    doc.build(story)
    return buf.getvalue()
