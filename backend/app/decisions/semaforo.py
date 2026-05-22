"""Sistema semaforo de decisiones (protocolo v4 seccion 22).

Niveles:
- VERDE: Ramon ejecuta sola.
- AMARILLO: Ramon propone (borrador) y espera confirmacion de Ruben.
- ROJO: Ramon NUNCA ejecuta, escala siempre.

Persistencia:
- Tabla `decisions` en Postgres (modelo ya existente).
- Exportacion periodica a Decisiones_Ramon.xlsx en Drive/03_Decisiones.
"""
from __future__ import annotations

import datetime as _dt
import io
from typing import Any, Literal

from app.core.database import SessionLocal
from app.core.models import Decision
from app.integrations import drive as drive_mod


Nivel = Literal["verde", "amarillo", "rojo"]


# Palabras clave que fuerzan ROJO independientemente del clasificador
PALABRAS_ROJAS = {
    "contrato", "contratar", "firmar", "firma electronica",
    "iban", "bic", "cuenta bancaria", "transferencia",
    "factura con iva", "retencion",
    "colaboracion", "sponsor",
    "acuerdo legal", "demanda", "reclamacion judicial",
    "bajar tarifa", "subir tarifa", "modificar tarifa",
}

# Palabras clave que suelen ser AMARILLAS
PALABRAS_AMARILLAS = {
    "descuento", "precio especial", "negociar",
    "solape", "conflicto de fechas",
    "cancelar", "posponer", "aplazar",
    "urgente",
}


def ajustar_nivel(nivel_sugerido: Nivel, asunto: str, cuerpo: str) -> Nivel:
    """Eleva el nivel si aparecen palabras criticas."""
    texto = f"{asunto} {cuerpo}".lower()
    if any(p in texto for p in PALABRAS_ROJAS):
        return "rojo"
    if nivel_sugerido == "verde" and any(p in texto for p in PALABRAS_AMARILLAS):
        return "amarillo"
    return nivel_sugerido


def registrar(
    *,
    nivel: Nivel,
    tema: str,
    propuesta: str = "",
    decision_final: str = "",
    resultado: str = "",
) -> int | None:
    """Registra una decision en Postgres. Devuelve el id o None si no hay DB."""
    if SessionLocal is None:
        return None
    with SessionLocal() as db:
        d = Decision(
            level=nivel,
            topic=tema,
            proposal=propuesta,
            final_decision=decision_final,
            outcome=resultado,
        )
        db.add(d)
        db.commit()
        db.refresh(d)
        return d.id


def resolver(decision_id: int, final_decision: str, outcome: str = "") -> bool:
    if SessionLocal is None:
        return False
    with SessionLocal() as db:
        d = db.get(Decision, decision_id)
        if d is None:
            return False
        d.final_decision = final_decision
        d.outcome = outcome
        d.resolved_at = _dt.datetime.utcnow()
        db.commit()
        return True


def listar_pendientes(nivel: Nivel | None = None, limite: int = 50) -> list[dict[str, Any]]:
    """Decisiones sin resolver (resolved_at=NULL)."""
    if SessionLocal is None:
        return []
    with SessionLocal() as db:
        q = db.query(Decision).filter(Decision.resolved_at.is_(None))
        if nivel:
            q = q.filter(Decision.level == nivel)
        q = q.order_by(Decision.created_at.desc()).limit(limite)
        return [
            {
                "id": d.id,
                "level": d.level,
                "topic": d.topic,
                "proposal": d.proposal,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in q.all()
        ]


def exportar_a_xlsx() -> dict[str, Any]:
    """Exporta todas las decisiones a Decisiones_Ramon.xlsx en Drive."""
    try:
        from openpyxl import Workbook
    except ImportError:
        # Fallback: CSV si no hay openpyxl
        return _exportar_a_csv()

    if SessionLocal is None:
        return {"exported": 0, "reason": "sin DB"}

    wb = Workbook()
    ws = wb.active
    ws.title = "Decisiones"
    ws.append(["ID", "Nivel", "Tema", "Propuesta", "Decision final", "Resultado", "Creado", "Resuelto"])
    n = 0
    with SessionLocal() as db:
        for d in db.query(Decision).order_by(Decision.created_at.desc()).all():
            ws.append([
                d.id,
                d.level,
                d.topic or "",
                d.proposal or "",
                d.final_decision or "",
                d.outcome or "",
                d.created_at.isoformat() if d.created_at else "",
                d.resolved_at.isoformat() if d.resolved_at else "",
            ])
            n += 1

    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    folder = drive_mod.subfolder_id("03_Decisiones")
    result = drive_mod.upload_bytes(
        folder,
        name="Decisiones_Ramon.xlsx",
        data=data,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return {"exported": n, "file": result}


def _exportar_a_csv() -> dict[str, Any]:
    if SessionLocal is None:
        return {"exported": 0, "reason": "sin DB"}
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Nivel", "Tema", "Propuesta", "Decision final", "Resultado", "Creado", "Resuelto"])
    n = 0
    with SessionLocal() as db:
        for d in db.query(Decision).order_by(Decision.created_at.desc()).all():
            writer.writerow([
                d.id, d.level, d.topic or "", d.proposal or "",
                d.final_decision or "", d.outcome or "",
                d.created_at.isoformat() if d.created_at else "",
                d.resolved_at.isoformat() if d.resolved_at else "",
            ])
            n += 1
    folder = drive_mod.subfolder_id("03_Decisiones")
    drive_mod.upload_bytes(
        folder,
        name="Decisiones_Ramon.csv",
        data=buf.getvalue().encode("utf-8"),
        mime_type="text/csv",
    )
    return {"exported": n, "format": "csv"}
