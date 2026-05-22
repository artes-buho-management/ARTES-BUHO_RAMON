"""Backup diario del cerebro de Ramon a Google Drive.

Exporta todas las tablas Postgres (memoria operativa de Ramon) a un JSON
comprimido y lo sube a Drive en /ARTES-BUHO/Ramon/05_Backups/.

Formato portable: aunque cambiemos de base de datos, de proveedor IA o de
estructura interna, el contenido sigue siendo legible (dict -> json -> gz).

Retencion:
- Dias 0-30: un backup por dia
- Meses 2-12: un backup por mes (el dia 1)
- Mas antiguos: borrados automaticamente

Nomenclatura: cerebro_ramon_YYYY-MM-DD.json.gz
"""
from __future__ import annotations

import gzip
import io
import json
import logging
from datetime import datetime
from typing import Any

from app.core.database import SessionLocal, engine
from app.core import models
from app.google_client import drive as _drive_service

log = logging.getLogger("ramon.backup_cerebro")

DRIVE_BACKUPS_FOLDER_NAME = "05_Backups"
DRIVE_RAMON_ROOT_ENV = "DRIVE_FOLDER_RAMON"

# Tablas SQLAlchemy que queremos backupear
_TABLES_TO_BACKUP = [
    models.EmailProcessed,
    models.Decision,
    models.TelegramMessage,
    models.SystemLog,
]


def _dump_table(model_cls) -> list[dict]:
    """Devuelve todas las filas de una tabla SQLAlchemy como list[dict]."""
    rows: list[dict] = []
    with SessionLocal() as sess:
        try:
            for r in sess.query(model_cls).all():
                d = {}
                for col in model_cls.__table__.columns:
                    v = getattr(r, col.name, None)
                    if isinstance(v, datetime):
                        v = v.isoformat()
                    d[col.name] = v
                rows.append(d)
        except Exception as exc:
            log.warning(f"dump {model_cls.__tablename__} fallo: {exc}")
    return rows


def _build_backup() -> dict[str, Any]:
    """Construye el JSON completo del cerebro."""
    ts = datetime.utcnow().isoformat() + "Z"
    payload: dict[str, Any] = {
        "_meta": {
            "generated_at_utc": ts,
            "ramon_version": "0.4.0",
            "source": "ramon-db",
        },
        "tables": {},
    }
    for model_cls in _TABLES_TO_BACKUP:
        tname = model_cls.__tablename__
        rows = _dump_table(model_cls)
        payload["tables"][tname] = {
            "count": len(rows),
            "rows": rows,
        }
    return payload


def _get_or_create_folder(parent_id: str, name: str) -> str:
    drive = _drive_service()
    q = (f"name = '{name}' and '{parent_id}' in parents "
         "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    resp = drive.files().list(q=q, fields='files(id)', pageSize=5).execute()
    files = resp.get('files', [])
    if files:
        return files[0]['id']
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    created = drive.files().create(body=body, fields='id').execute()
    return created['id']


def _list_existing_backups(folder_id: str) -> list[dict]:
    drive = _drive_service()
    q = (f"'{folder_id}' in parents and trashed = false "
         "and name contains 'cerebro_ramon_'")
    resp = drive.files().list(
        q=q, fields='files(id,name,createdTime)', orderBy='name desc', pageSize=100
    ).execute()
    return resp.get('files', [])


def _apply_retention(folder_id: str) -> dict[str, int]:
    """Mantiene: ultimos 30 dias + 1 por mes hasta 12 meses."""
    existing = _list_existing_backups(folder_id)
    drive = _drive_service()
    today = datetime.utcnow().date()
    keep_ids: set[str] = set()
    months_kept: set[str] = set()  # 'YYYY-MM' si ya guardamos uno

    for f in existing:
        name = f['name']  # cerebro_ramon_YYYY-MM-DD.json.gz
        try:
            date_part = name.split('_')[2].split('.')[0]  # YYYY-MM-DD
            d = datetime.strptime(date_part, "%Y-%m-%d").date()
        except Exception:
            continue
        age_days = (today - d).days
        if age_days <= 30:
            keep_ids.add(f['id'])  # ultimos 30 dias
        elif age_days <= 365:
            ym = d.strftime("%Y-%m")
            if ym not in months_kept:
                keep_ids.add(f['id'])
                months_kept.add(ym)

    deleted = 0
    for f in existing:
        if f['id'] not in keep_ids:
            try:
                drive.files().delete(fileId=f['id']).execute()
                deleted += 1
            except Exception as exc:
                log.warning(f"delete fallo {f['name']}: {exc}")
    return {"total": len(existing), "kept": len(keep_ids), "deleted": deleted}


def run_backup() -> dict[str, Any]:
    """Genera backup, lo sube a Drive y aplica retencion."""
    import os
    ramon_root = os.getenv(DRIVE_RAMON_ROOT_ENV, "").strip()
    if not ramon_root:
        return {"ok": False, "error": f"{DRIVE_RAMON_ROOT_ENV} no configurada"}

    # 1. Construir payload
    payload = _build_backup()
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=6)
    raw_size = len(raw)
    gz_size = len(gz)

    # 2. Carpeta destino
    backups_folder_id = _get_or_create_folder(ramon_root, DRIVE_BACKUPS_FOLDER_NAME)

    # 3. Subir
    from googleapiclient.http import MediaInMemoryUpload
    fname = f"cerebro_ramon_{datetime.utcnow().strftime('%Y-%m-%d')}.json.gz"
    drive = _drive_service()
    media = MediaInMemoryUpload(gz, mimetype="application/gzip")
    uploaded = drive.files().create(
        body={"name": fname, "parents": [backups_folder_id]},
        media_body=media,
        fields='id,name,size',
    ).execute()

    # 4. Retencion
    retention = _apply_retention(backups_folder_id)

    total_rows = sum(t["count"] for t in payload["tables"].values())
    log.info(f"backup cerebro OK: {fname} size={gz_size}B rows={total_rows}")

    return {
        "ok": True,
        "filename": fname,
        "drive_id": uploaded['id'],
        "raw_size_bytes": raw_size,
        "gz_size_bytes": gz_size,
        "compression": round(1 - gz_size / raw_size, 2) if raw_size else 0,
        "tables": {t: d["count"] for t, d in payload["tables"].items()},
        "total_rows": total_rows,
        "retention": retention,
    }
