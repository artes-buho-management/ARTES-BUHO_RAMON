"""Gestion del CRM 2026v (Google Sheets).

CRM_SHEET_ID = 193f6vQLpf_Ty7nvyKEx7iHgB5k0hAOtI2UnUOUaj-Ds

Protocolo v4 seccion 12:
- PERMITIDO: actualizar estado, marcar cobros, registrar comunicaciones,
  anadir clientes nuevos, actualizar contacto.
- PROHIBIDO: borrar filas (solo marcar Cancelado), modificar importes cobrados,
  cambiar estructura.
- Cruce automatico: cada email entrante se busca en el CRM y aplica contexto.
- Backup automatico antes de cada modificacion.
"""
from __future__ import annotations

import datetime as _dt
from functools import lru_cache
from typing import Any

from app.google_client import sheets as _sheets_client, drive as _drive_client
from app.core.settings import get_settings
from app.integrations import drive as drive_mod


def _svc():
    return _sheets_client()


def _sheet_id() -> str:
    return get_settings().crm_sheet_id


# --- Metadata ---

@lru_cache(maxsize=1)
def get_metadata() -> dict[str, Any]:
    return _svc().spreadsheets().get(spreadsheetId=_sheet_id()).execute()


def first_sheet_name() -> str:
    meta = get_metadata()
    sheets = meta.get("sheets", [])
    if not sheets:
        return "Hoja 1"
    return sheets[0]["properties"]["title"]


# --- Lectura ---

def read_range(a1_range: str) -> list[list[str]]:
    resp = _svc().spreadsheets().values().get(
        spreadsheetId=_sheet_id(), range=a1_range
    ).execute()
    return resp.get("values", [])


def read_all(sheet_name: str | None = None) -> list[dict[str, str]]:
    """Lee toda la hoja y la devuelve como lista de dicts (primera fila = cabeceras)."""
    sheet = sheet_name or first_sheet_name()
    values = read_range(f"'{sheet}'")
    if not values:
        return []
    headers = [h.strip() for h in values[0]]
    out: list[dict[str, str]] = []
    for row in values[1:]:
        padded = row + [""] * (len(headers) - len(row))
        out.append({headers[i]: padded[i] for i in range(len(headers))})
    return out


# --- Cruce ---

def buscar_por_email(email: str, sheet_name: str | None = None) -> dict[str, str] | None:
    """Busca la primera fila del CRM donde aparezca ese email en cualquier columna."""
    email_lower = (email or "").strip().lower()
    if not email_lower:
        return None
    for row in read_all(sheet_name):
        for value in row.values():
            if email_lower in (value or "").strip().lower():
                return row
    return None


def buscar_por_nombre(nombre: str, sheet_name: str | None = None) -> list[dict[str, str]]:
    nom = (nombre or "").strip().lower()
    if not nom:
        return []
    return [
        row for row in read_all(sheet_name)
        if any(nom in (v or "").strip().lower() for v in row.values())
    ]


# --- Escritura (con backup previo obligatorio) ---

def _timestamp_iso() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")


def backup_crm_now(motivo: str = "pre_modificacion") -> dict[str, Any]:
    """Exporta el CRM como XLSX y lo guarda en 05_Backups en Drive."""
    try:
        xlsx = _drive_client().files().export(
            fileId=_sheet_id(),
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ).execute()
    except Exception as exc:
        # Si falla el export binario, volcar JSON como plan B.
        data = str(read_all()).encode("utf-8")
        return drive_mod.upload_bytes(
            drive_mod.subfolder_id("05_Backups"),
            name=f"CRM_backup_{_timestamp_iso()}_{motivo}_fallback.json",
            data=data,
            mime_type="application/json",
        )
    data = xlsx if isinstance(xlsx, bytes) else bytes(xlsx)
    return drive_mod.guardar_backup_crm(
        f"CRM_backup_{_timestamp_iso()}_{motivo}.xlsx", data
    )


def append_row(values: list[str], sheet_name: str | None = None) -> dict[str, Any]:
    """Anade una fila al final. Hace backup antes."""
    backup_crm_now(motivo="append_row")
    sheet = sheet_name or first_sheet_name()
    return _svc().spreadsheets().values().append(
        spreadsheetId=_sheet_id(),
        range=f"'{sheet}'",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


def update_cell(a1: str, value: str) -> dict[str, Any]:
    """Actualiza una celda concreta. Backup previo."""
    backup_crm_now(motivo=f"update_{a1.replace('!','_').replace(':','_')}")
    return _svc().spreadsheets().values().update(
        spreadsheetId=_sheet_id(),
        range=a1,
        valueInputOption="USER_ENTERED",
        body={"values": [[value]]},
    ).execute()


def update_row_by_email(
    email: str,
    updates: dict[str, str],
    sheet_name: str | None = None,
) -> dict[str, Any]:
    """Busca la fila por email y actualiza columnas por nombre de cabecera.

    Hace backup previo. Devuelve {"updated": N, "row_index": i} o {"updated": 0} si no encuentra.
    """
    sheet = sheet_name or first_sheet_name()
    values = read_range(f"'{sheet}'")
    if not values:
        return {"updated": 0, "reason": "hoja vacia"}
    headers = [h.strip() for h in values[0]]
    email_lower = email.strip().lower()
    target_row = None
    for idx, row in enumerate(values[1:], start=2):  # row_index 1-based, fila 1 = headers
        if any(email_lower in (v or "").strip().lower() for v in row):
            target_row = idx
            break
    if target_row is None:
        return {"updated": 0, "reason": "email no encontrado"}

    backup_crm_now(motivo=f"update_row_{email_lower}")

    data: list[dict[str, Any]] = []
    for col_name, new_val in updates.items():
        if col_name not in headers:
            continue
        col_idx = headers.index(col_name)
        col_letter = _col_to_letter(col_idx)
        data.append({
            "range": f"'{sheet}'!{col_letter}{target_row}",
            "values": [[new_val]],
        })
    if not data:
        return {"updated": 0, "reason": "ninguna columna coincide"}
    resp = _svc().spreadsheets().values().batchUpdate(
        spreadsheetId=_sheet_id(),
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()
    return {"updated": len(data), "row_index": target_row, "response": resp}


def _col_to_letter(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, ..."""
    result = ""
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord("A") + rem) + result
    return result


# --- Cobros pendientes ---

def cobros_pendientes(sheet_name: str | None = None, dias_min: int = 7) -> list[dict[str, str]]:
    """Heuristica: filas donde haya columna 'cobro' o 'estado' que indique pendiente.

    Como la estructura exacta del CRM no esta fijada, buscamos palabras clave.
    """
    rows = read_all(sheet_name)
    pendientes = []
    palabras_pendiente = {"pendiente", "impagado", "deuda", "por cobrar"}
    for r in rows:
        for k, v in r.items():
            key = k.lower()
            val = (v or "").lower()
            if ("cobro" in key or "estado" in key or "pago" in key) and any(p in val for p in palabras_pendiente):
                pendientes.append(r)
                break
    return pendientes
