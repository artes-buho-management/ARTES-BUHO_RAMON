"""Integración con Holded (programa de contabilidad).

MODO: solo LECTURA por ahora. Ramón consume datos para aprender y cruzar con
CRM + Gmail + Calendar. La escritura (crear facturas, etc.) se añadirá más
tarde cuando tengamos confianza.

API ref: https://developers.holded.com/reference
Auth: header `key: <api_key>` (env HOLDED_API_KEY).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx


BASE_URL = "https://api.holded.com/api"


def _key() -> str:
    k = os.getenv("HOLDED_API_KEY", "")
    if not k:
        raise RuntimeError("HOLDED_API_KEY no configurada")
    return k


def _headers() -> dict[str, str]:
    return {"key": _key(), "accept": "application/json"}


# ---------- CONTACTOS (clientes, proveedores) ----------

def list_contacts(limit: int = 100, offset: int = 0) -> list[dict]:
    r = httpx.get(
        f"{BASE_URL}/invoicing/v1/contacts",
        headers=_headers(),
        params={"limit": limit, "offset": offset},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json() if isinstance(r.json(), list) else []


def buscar_contacto_por_email(email: str) -> dict | None:
    """Busca un contacto por email exacto."""
    email = (email or "").strip().lower()
    if not email:
        return None
    for offset in range(0, 3000, 500):
        rows = list_contacts(limit=500, offset=offset)
        if not rows:
            break
        for c in rows:
            if (c.get("email") or "").strip().lower() == email:
                return c
        if len(rows) < 500:
            break
    return None


# ---------- FACTURAS ----------

def list_invoices(limit: int = 100, page: int = 1, **filters: Any) -> list[dict]:
    params = {"page": page, "limit": limit}
    params.update(filters)
    r = httpx.get(
        f"{BASE_URL}/invoicing/v1/documents/invoice",
        headers=_headers(),
        params=params,
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def get_invoice(invoice_id: str) -> dict:
    r = httpx.get(
        f"{BASE_URL}/invoicing/v1/documents/invoice/{invoice_id}",
        headers=_headers(),
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


# ---------- PRESUPUESTOS ----------

def list_estimates(limit: int = 100, page: int = 1) -> list[dict]:
    r = httpx.get(
        f"{BASE_URL}/invoicing/v1/documents/estimate",
        headers=_headers(),
        params={"limit": limit, "page": page},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


# ---------- RESUMEN / INTEGRACION ----------

@lru_cache(maxsize=1)
def available() -> bool:
    try:
        r = httpx.get(
            f"{BASE_URL}/invoicing/v1/contacts?limit=1",
            headers=_headers(),
            timeout=5.0,
        )
        return r.status_code == 200
    except Exception:
        return False


def contexto_cliente_para_email(email: str) -> dict[str, Any]:
    """Devuelve datos Holded del cliente + sus últimas facturas.

    Pensado para inyectarse en el prompt cuando Ramón procesa un correo.
    """
    contact = buscar_contacto_por_email(email)
    if not contact:
        return {"found": False}
    cid = contact.get("id")
    # Filtrar facturas por contactId si se puede
    try:
        facturas = [
            f for f in list_invoices(limit=50)
            if f.get("contactId") == cid or f.get("contact") == cid
        ][:10]
    except Exception:
        facturas = []
    return {
        "found": True,
        "contact": {
            "id": cid,
            "name": contact.get("name"),
            "email": contact.get("email"),
            "type": contact.get("type"),
            "balance": contact.get("balance"),
        },
        "facturas_recientes": [
            {
                "id": f.get("id"),
                "num": f.get("docNumber"),
                "fecha": f.get("date"),
                "total": f.get("total"),
                "status": f.get("status"),
                "pagado": f.get("paymentsTotal"),
            }
            for f in facturas
        ],
    }


def stats() -> dict[str, Any]:
    """Resumen rápido: contactos, facturas recientes, cobros pendientes."""
    try:
        contactos = len(list_contacts(limit=500))
    except Exception:
        contactos = -1
    try:
        facturas_pag = list_invoices(limit=100, page=1)
    except Exception:
        facturas_pag = []
    pendientes = [f for f in facturas_pag if (f.get("pending") or 0) > 0 or f.get("status") == "unpaid"]
    return {
        "contactos_min_500": contactos,
        "facturas_recientes": len(facturas_pag),
        "facturas_pendientes_cobro": len(pendientes),
        "ejemplos_pendientes": [
            {"num": f.get("docNumber"), "total": f.get("total"), "pending": f.get("pending")}
            for f in pendientes[:5]
        ],
    }
