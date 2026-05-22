"""Operaciones Google Drive para Ramon.

Ramon mantiene su "libreta viva" en la carpeta:
DRIVE_FOLDER_RAMON = 1EtY1MuTXOmoeDNHVMYraC3fFfhznX2UU

Estructura mantenida (protocolo v4 seccion 15 + 25.3):
Ramon/
├── 00_Protocolo/
├── 01_Aprendizaje/
│   ├── Aprendizaje_Ramon.md       (maestro, consolidado)
│   ├── Aprendizaje_desde_Chat.md  (escribe Consultora, lee Ejecutiva)
│   └── Aprendizaje_desde_VPS.md   (escribe Ejecutiva, lee Consultora)
├── 02_Diario/                     (informes diarios en PDF)
├── 03_Decisiones/                 (Decisiones_Ramon.xlsx)
├── 04_Escaneo/                    (informes de escaneo historico)
├── 05_Backups/                    (snapshots CRM antes de modificar)
└── 99_Adjuntos/
"""
from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from app.google_client import drive as _drive_client
from app.core.settings import get_settings


RAMON_SUBFOLDERS = [
    "00_Protocolo",
    "01_Aprendizaje",
    "02_Diario",
    "03_Decisiones",
    "04_Escaneo",
    "05_Backups",
    "99_Adjuntos",
]


def _svc():
    return _drive_client()


def _root_id() -> str:
    return get_settings().drive_folder_ramon


# --- Folders ---

def list_children(folder_id: str, mime_type: str | None = None) -> list[dict]:
    """Lista archivos o carpetas dentro de folder_id."""
    q = f"'{folder_id}' in parents and trashed=false"
    if mime_type:
        q += f" and mimeType='{mime_type}'"
    resp = _svc().files().list(
        q=q,
        fields="files(id,name,mimeType,modifiedTime,size)",
        pageSize=1000,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    return resp.get("files", [])


def find_child(folder_id: str, name: str, mime_type: str | None = None) -> dict | None:
    """Busca un hijo por nombre exacto."""
    q = f"'{folder_id}' in parents and name='{name}' and trashed=false"
    if mime_type:
        q += f" and mimeType='{mime_type}'"
    resp = _svc().files().list(
        q=q,
        fields="files(id,name,mimeType)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    return files[0] if files else None


def ensure_folder(parent_id: str, name: str) -> str:
    """Devuelve el id de una carpeta, creandola si no existe."""
    existing = find_child(parent_id, name, mime_type="application/vnd.google-apps.folder")
    if existing:
        return existing["id"]
    created = _svc().files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return created["id"]


@lru_cache(maxsize=16)
def ensure_ramon_structure() -> dict[str, str]:
    """Garantiza la estructura estandar de Ramon. Devuelve {subfolder_name: id}."""
    root = _root_id()
    out = {"_ROOT": root}
    for name in RAMON_SUBFOLDERS:
        out[name] = ensure_folder(root, name)
    return out


def subfolder_id(name: str) -> str:
    return ensure_ramon_structure()[name]


# --- Files: upload / download / update ---

def upload_bytes(
    parent_id: str,
    *,
    name: str,
    data: bytes,
    mime_type: str,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Sube un archivo (o sobreescribe si existe)."""
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
    existing = find_child(parent_id, name)
    if existing and overwrite:
        return _svc().files().update(
            fileId=existing["id"],
            media_body=media,
            fields="id,name,modifiedTime",
            supportsAllDrives=True,
        ).execute()
    return _svc().files().create(
        body={"name": name, "parents": [parent_id]},
        media_body=media,
        fields="id,name,modifiedTime",
        supportsAllDrives=True,
    ).execute()


def upload_text(parent_id: str, *, name: str, text: str, mime_type: str = "text/markdown") -> dict[str, Any]:
    return upload_bytes(parent_id, name=name, data=text.encode("utf-8"), mime_type=mime_type)


def download_bytes(file_id: str) -> bytes:
    """Descarga el contenido binario de un archivo."""
    request = _svc().files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def download_text(file_id: str, encoding: str = "utf-8") -> str:
    return download_bytes(file_id).decode(encoding, errors="replace")


def read_text_by_name(parent_id: str, name: str) -> str:
    """Lee un archivo de texto por nombre. Devuelve string vacio si no existe."""
    f = find_child(parent_id, name)
    if not f:
        return ""
    return download_text(f["id"])


# --- Export de Google Docs/Sheets ---

def export_google_file(file_id: str, mime_type: str) -> bytes:
    """Exporta un Google Doc/Sheet a formato binario (pdf, xlsx, etc.)."""
    data = _svc().files().export(fileId=file_id, mimeType=mime_type).execute()
    return data if isinstance(data, bytes) else bytes(data)


# --- Aprendizaje helpers ---

def aprendizaje_folder_id() -> str:
    return subfolder_id("01_Aprendizaje")


def leer_aprendizaje_ramon() -> str:
    return read_text_by_name(aprendizaje_folder_id(), "Aprendizaje_Ramon.md")


def leer_aprendizaje_chat() -> str:
    return read_text_by_name(aprendizaje_folder_id(), "Aprendizaje_desde_Chat.md")


def leer_aprendizaje_vps() -> str:
    return read_text_by_name(aprendizaje_folder_id(), "Aprendizaje_desde_VPS.md")


def escribir_aprendizaje_vps(text: str) -> dict[str, Any]:
    return upload_text(aprendizaje_folder_id(), name="Aprendizaje_desde_VPS.md", text=text)


def append_aprendizaje_vps(entry: str) -> dict[str, Any]:
    """Anade una entrada al final del archivo VPS (creandolo si no existe)."""
    existing = leer_aprendizaje_vps()
    sep = "\n\n---\n\n" if existing.strip() else ""
    nuevo = existing + sep + entry.strip()
    return escribir_aprendizaje_vps(nuevo)


def escribir_aprendizaje_ramon(text: str) -> dict[str, Any]:
    return upload_text(aprendizaje_folder_id(), name="Aprendizaje_Ramon.md", text=text)


# --- Backups CRM ---

def guardar_backup_crm(nombre: str, data: bytes) -> dict[str, Any]:
    """Guarda snapshot del CRM en 05_Backups antes de modificar."""
    return upload_bytes(
        subfolder_id("05_Backups"),
        name=nombre,
        data=data,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# --- Informes ---

def guardar_informe_diario(fecha_iso: str, pdf_bytes: bytes) -> dict[str, Any]:
    return upload_bytes(
        subfolder_id("02_Diario"),
        name=f"Informe_{fecha_iso}.pdf",
        data=pdf_bytes,
        mime_type="application/pdf",
    )


def guardar_escaneo_inicial(pdf_bytes: bytes) -> dict[str, Any]:
    return upload_bytes(
        subfolder_id("04_Escaneo"),
        name="Informe_Escaneo_Inicial.pdf",
        data=pdf_bytes,
        mime_type="application/pdf",
    )
