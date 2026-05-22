"""Generacion del informe diario en PDF + guardado en Drive."""
from __future__ import annotations

import datetime as _dt
import io
from typing import Any

from app.integrations import drive as drive_mod


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Informe diario — {payload.get('fecha', _dt.date.today().isoformat())}\n"]

    def _section(titulo: str, items: list):
        if not items:
            return
        lines.append(f"## {titulo}\n")
        for it in items:
            lines.append(f"- {it}")
        lines.append("")

    _section("URGENTE HOY", payload.get("urgente", []))
    _section("AGENDA DEL DIA", payload.get("agenda", []))
    _section("EMAILS PENDIENTES", payload.get("emails_pendientes", []))
    _section("BUZON PERSONAL", payload.get("personal", []))
    _section("COBROS PENDIENTES (>7 dias)", payload.get("cobros", []))
    _section("BOLOS PROXIMOS (14 dias)", payload.get("bolos", []))
    _section("ALERTAS", payload.get("alertas", []))

    if payload.get("modo_solo_borradores"):
        lines.append("\n> Modo: solo borradores (primera semana).")
    return "\n".join(lines)


def generar_pdf(payload: dict[str, Any]) -> bytes:
    """Render PDF con reportlab. Fallback: texto plano bytes si reportlab no disponible."""
    md = _render_markdown(payload)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        return md.encode("utf-8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Ramon - Informe {payload.get('fecha', '')}")
    styles = getSampleStyleSheet()
    story = []
    for line in md.split("\n"):
        if not line.strip():
            story.append(Spacer(1, 6))
            continue
        if line.startswith("# "):
            story.append(Paragraph(line[2:], styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], styles["Heading2"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + line[2:].replace("<", "&lt;").replace(">", "&gt;"), styles["BodyText"]))
        else:
            story.append(Paragraph(line.replace("<", "&lt;").replace(">", "&gt;"), styles["BodyText"]))
    doc.build(story)
    return buf.getvalue()


def generar_y_guardar_pdf(payload: dict[str, Any]) -> dict[str, Any]:
    pdf_bytes = generar_pdf(payload)
    fecha = payload.get("fecha", _dt.date.today().isoformat())
    return drive_mod.guardar_informe_diario(fecha, pdf_bytes)
