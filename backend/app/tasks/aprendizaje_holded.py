"""Aprendizaje histórico y continuo de Holded.

Objetivo: Ramón aprende del histórico de facturación de ARTES BUHO para:
 - Entender patrones de facturación (clientes recurrentes, importes medios, cadencia)
 - Saber qué facturas envía habitualmente (conceptos, series, textos)
 - Cruzar Gmail ↔ Holded ↔ CRM al procesar correos
 - Detectar facturas pendientes de cobro y redactar recordatorios adecuados

Este módulo se ejecuta:
 - **Una vez (histórico)**: escanea todas las facturas/contactos y genera perfil
 - **Continuo**: cada 6h refresca con facturas nuevas y actualiza patrones

Se guarda un JSON en disco (`app/data/perfil_holded.json`) que se inyecta en el
prompt de Ramón como contexto siempre disponible.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.integrations import holded


log = logging.getLogger("ramon.aprendizaje_holded")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PERFIL_PATH = DATA_DIR / "perfil_holded.json"


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        log.warning(f"holded safe fail: {exc}")
        return default


def _cargar_todas_facturas(max_paginas: int = 20, por_pagina: int = 100) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_paginas + 1):
        try:
            rows = holded.list_invoices(limit=por_pagina, page=page)
        except Exception as exc:
            log.warning(f"list_invoices page {page} fail: {exc}")
            break
        if not rows:
            break
        out.extend(rows)
        if len(rows) < por_pagina:
            break
    return out


def _cargar_todos_contactos(max_offset: int = 3000, por_pagina: int = 500) -> list[dict]:
    out: list[dict] = []
    for offset in range(0, max_offset, por_pagina):
        try:
            rows = holded.list_contacts(limit=por_pagina, offset=offset)
        except Exception as exc:
            log.warning(f"list_contacts offset {offset} fail: {exc}")
            break
        if not rows:
            break
        out.extend(rows)
        if len(rows) < por_pagina:
            break
    return out


def _analizar(facturas: list[dict], contactos: list[dict]) -> dict[str, Any]:
    # Importe medio, cliente top, status, cadencia mensual
    totales = [float(f.get("total") or 0) for f in facturas if f.get("total")]
    importe_medio = sum(totales) / len(totales) if totales else 0
    importe_max = max(totales) if totales else 0

    clientes_cnt = Counter()
    for f in facturas:
        key = f.get("contactName") or f.get("contact") or f.get("contactId") or "?"
        clientes_cnt[key] += 1
    top_clientes = clientes_cnt.most_common(10)

    pendientes = [f for f in facturas if (f.get("pending") or 0) > 0 or f.get("status") in {"unpaid", "overdue"}]
    pendientes_total = sum(float(f.get("pending") or f.get("total") or 0) for f in pendientes)

    # Cadencia mensual (últimos 12 meses)
    meses = Counter()
    for f in facturas:
        ts = f.get("date")
        if isinstance(ts, (int, float)) and ts > 0:
            try:
                d = datetime.fromtimestamp(ts)
                meses[d.strftime("%Y-%m")] += 1
            except Exception:
                pass
    cadencia = dict(sorted(meses.items())[-12:])

    # Conceptos típicos: si el listado no trae items, vamos a get_invoice por
    # cada factura (solo las primeras 30, para limitar coste).
    conceptos = Counter()
    for f in facturas:
        items = f.get("items") or []
        if not items and f.get("id"):
            try:
                detalle = holded.get_invoice(f["id"])
                items = detalle.get("products") or detalle.get("items") or []
            except Exception:
                items = []
        if items and isinstance(items, list):
            for it in items[:2]:  # top-2 items por factura
                nombre = (it.get("name") or it.get("desc") or it.get("concept") or "").strip()
                if nombre:
                    conceptos[nombre[:80]] += 1
        # límite para no tirar de la API en histórico masivo
        if sum(conceptos.values()) > 60:
            break
    conceptos_top = conceptos.most_common(15)

    # Estadísticas contactos
    tipos = Counter(c.get("type") or "?" for c in contactos)

    return {
        "ultima_actualizacion": datetime.now().isoformat(timespec="seconds"),
        "totales": {
            "facturas_analizadas": len(facturas),
            "contactos": len(contactos),
            "importe_medio_eur": round(importe_medio, 2),
            "importe_max_eur": round(importe_max, 2),
        },
        "clientes_top": [{"cliente": k, "facturas": v} for k, v in top_clientes],
        "conceptos_frecuentes": [{"concepto": k, "veces": v} for k, v in conceptos_top],
        "cadencia_mensual_facturas": cadencia,
        "cobros_pendientes": {
            "num_facturas": len(pendientes),
            "importe_total_eur": round(pendientes_total, 2),
            "ejemplos": [
                {
                    "cliente": f.get("contactName") or f.get("contact"),
                    "num": f.get("docNumber"),
                    "total": f.get("total"),
                    "pending": f.get("pending"),
                    "fecha": f.get("date"),
                }
                for f in pendientes[:10]
            ],
        },
        "tipos_contacto": dict(tipos),
    }


def ejecutar_historico() -> dict[str, Any]:
    """Aprendizaje completo desde cero. Lento pero solo se hace una vez / semanal."""
    log.info("Aprendizaje histórico Holded: iniciando...")
    if not holded.available():
        log.warning("Holded no disponible (¿HOLDED_API_KEY?)")
        return {"ok": False, "error": "holded no disponible"}
    facturas = _safe(_cargar_todas_facturas, [])
    contactos = _safe(_cargar_todos_contactos, [])
    perfil = _analizar(facturas, contactos)
    PERFIL_PATH.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(
        "Histórico OK: %d facturas, %d contactos, pendientes %.2f€",
        perfil["totales"]["facturas_analizadas"],
        perfil["totales"]["contactos"],
        perfil["cobros_pendientes"]["importe_total_eur"],
    )
    return {"ok": True, "perfil": perfil}


def ejecutar_refresh() -> dict[str, Any]:
    """Refresh rápido: últimas 2 páginas de facturas + perfil actualizado."""
    if not holded.available():
        return {"ok": False, "error": "holded no disponible"}
    try:
        facturas = holded.list_invoices(limit=100, page=1) + holded.list_invoices(limit=100, page=2)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        contactos = holded.list_contacts(limit=500, offset=0)
    except Exception:
        contactos = []
    perfil = _analizar(facturas, contactos)
    # Si ya hay histórico previo, mantener los totales mayores
    if PERFIL_PATH.exists():
        try:
            prev = json.loads(PERFIL_PATH.read_text(encoding="utf-8"))
            # preservar top_clientes histórico si el refresh es reducido
            if prev.get("totales", {}).get("facturas_analizadas", 0) > perfil["totales"]["facturas_analizadas"]:
                perfil["clientes_top"] = prev.get("clientes_top", perfil["clientes_top"])
                perfil["conceptos_frecuentes"] = prev.get("conceptos_frecuentes", perfil["conceptos_frecuentes"])
        except Exception:
            pass
    PERFIL_PATH.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "perfil": perfil}


def cargar_perfil() -> dict[str, Any]:
    if not PERFIL_PATH.exists():
        return {}
    try:
        return json.loads(PERFIL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resumen_para_prompt() -> str:
    """Devuelve un bloque corto para inyectar en system prompt de Ramón."""
    p = cargar_perfil()
    if not p:
        return ""
    t = p.get("totales", {})
    pend = p.get("cobros_pendientes", {})
    top = ", ".join(c["cliente"] for c in (p.get("clientes_top") or [])[:5])
    conc = ", ".join(c["concepto"] for c in (p.get("conceptos_frecuentes") or [])[:5])
    return (
        f"[HOLDED] {t.get('facturas_analizadas', 0)} facturas analizadas, "
        f"importe medio {t.get('importe_medio_eur', 0)}€. "
        f"Cobros pendientes: {pend.get('num_facturas', 0)} por {pend.get('importe_total_eur', 0)}€. "
        f"Clientes top: {top}. Conceptos típicos: {conc}."
    )
