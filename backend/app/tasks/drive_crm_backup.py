"""Copia de seguridad SEMANAL de los 7 CRMs de ARTES BUHO.

Portado de ARTES-BUHO_DRIVE-COPIA-SEGURIDAD/scripts/crm_backup_scheduler.ps1.
Corre desde el VPS de Ramon (no del PC de Ruben).

8 CRMs que se respaldan cada lunes a las 14:00 Europe/Madrid:
  1. MARKETING Y PROMOCION
  2. OTROS
  3. FESTIVALES
  4. MUNDO DISCOGRAFICO
  5. BELLA BESTIA
  6. VENTA-BOOKING
  7. SITUACION BANDAS
  8. AYUDAS Y SUBVENCIONES 2.0V  (version nueva; la 1.0V desactivada)

Formato nombre backup: "COPIA SEGURIDAD YYMMDD - [emoji] <NOMBRE>"
  ej: "COPIA SEGURIDAD 260427 - \U0001F680 MARKETING Y PROMOCION"

Si ya existe un backup con ese nombre de hoy, no duplica (salvo force=True).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.google_client import drive as _drive_service

log = logging.getLogger("ramon.crm_backup")

EMOJI = "\U0001F680"  # rocket

# Los 7 CRMs a respaldar (origen → destino)
CRMS: list[dict[str, str]] = [
    {
        "name": "MARKETING Y PROMOCION",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1rieAe4JZyF39-VQSCUN_3FG4VecRW6V5",
    },
    {
        "name": "OTROS",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1_D-6r-fMd3HeQj0cYwrmwyBQBOsct2eh",
    },
    {
        "name": "FESTIVALES",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1PM5IMGYhPgIBBSbvIW_M3R5vNy5_g844",
    },
    {
        "name": "MUNDO DISCOGRAFICO",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1QPV0ePkS6uQWYAAN63EjBCSnevT1wBuK",
    },
    {
        "name": "BELLA BESTIA",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1iggWmRpPhnJslYERSAGVdy5M9TuB0DHb",
    },
    {
        "name": "VENTA-BOOKING",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "14lLKdArBywo_g5_2GFeSB2GegndEx3uD",
    },
    {
        "name": "SITUACION BANDAS",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1c-wD3qO2KjkP_IaV76tHvreTgOIaYrVH",
    },
    {
        "name": "AYUDAS Y SUBVENCIONES",
        "source_id": "REPLACE_WITH_SHEET_ID",
        "target_folder": "1Eig2NaPWUxmAcji_Rv2pz76maSaCH2cB",
    },
]


def _backup_name(crm_name: str, date: datetime | None = None) -> str:
    """Formato: 'COPIA SEGURIDAD YYMMDD - [emoji] <NOMBRE>'."""
    d = date or datetime.now()
    ymd = d.strftime("%y%m%d")
    return f"COPIA SEGURIDAD {ymd} - {EMOJI} {crm_name}"


def _find_existing(target_folder: str, name: str) -> dict | None:
    drive = _drive_service()
    safe_name = name.replace("'", "\\'")
    q = f"'{target_folder}' in parents and trashed = false and name = '{safe_name}'"
    resp = drive.files().list(
        q=q, spaces='drive', fields='files(id,name,createdTime)', pageSize=5
    ).execute()
    files = resp.get('files', [])
    return files[0] if files else None


def _copy_one_crm(crm: dict, force: bool = False) -> dict[str, Any]:
    """Copia un CRM. Devuelve dict con resultado (skipped/ok/error)."""
    name = crm["name"]
    src = crm["source_id"]
    dst_folder = crm["target_folder"]
    backup_name = _backup_name(name)
    drive = _drive_service()

    try:
        source = drive.files().get(fileId=src, fields='id,name,mimeType').execute()
    except Exception as exc:
        return {"crm": name, "ok": False, "error": f"source_not_accessible: {exc}"}

    existing = _find_existing(dst_folder, backup_name)
    if existing and not force:
        return {
            "crm": name, "ok": True, "skipped": True,
            "reason": "already_backed_up_today",
            "backup_name": backup_name,
            "existing_id": existing['id'],
        }

    try:
        copy = drive.files().copy(
            fileId=src,
            body={"name": backup_name, "parents": [dst_folder]},
            fields='id,name,createdTime',
        ).execute()
    except Exception as exc:
        log.error(f"copy {name} fallo: {exc}")
        return {"crm": name, "ok": False, "error": f"copy_failed: {exc}"}

    log.info(f"CRM backup OK: {copy['name']}")
    return {
        "crm": name,
        "ok": True,
        "backup_name": backup_name,
        "new_id": copy['id'],
        "created_at": copy.get('createdTime'),
    }


def run_backup(force: bool = False) -> dict[str, Any]:
    """Copia de seguridad de los 7 CRMs. Corre los lunes 14:00 via scheduler.

    force=True fuerza nueva copia aunque ya exista hoy.
    """
    results = [_copy_one_crm(crm, force=force) for crm in CRMS]
    ok = [r for r in results if r.get("ok")]
    errors = [r for r in results if not r.get("ok")]
    return {
        "total": len(CRMS),
        "ok_count": len(ok),
        "errors_count": len(errors),
        "results": results,
    }


# Alias por retrocompat (aunque ya no se usa con argumentos viejos)
def run_single_backup(source_id: str, target_folder: str, name: str = "CRM",
                       force: bool = False) -> dict[str, Any]:
    """Copia de 1 CRM ad-hoc (no esta en la lista de los 7)."""
    return _copy_one_crm(
        {"name": name, "source_id": source_id, "target_folder": target_folder},
        force=force,
    )
