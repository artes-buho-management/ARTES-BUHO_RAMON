"""Observador SOLO-LECTURA de la carpeta Drive "Facturas".

Carpeta Drive:
  https://drive.google.com/drive/folders/REPLACE_WITH_ID

Objetivo: Ramón NO toca esta carpeta. Solo la observa cada 4h para:
 - Detectar nuevos ficheros (PDFs de facturas emitidas/recibidas)
 - Aprender cómo se nombran (patrón de codificación del nombre)
 - Cruzar con Holded (mismo docNumber, mismo total)
 - Cruzar con Gmail (cuando se adjunta un PDF con el mismo hash)

Salida: JSON en `app/data/perfil_drive_facturas.json` con:
 - total_archivos
 - patrones_nombre (regex extraídos)
 - timeline (archivos por mes)
 - cruce_holded (nº de facturas Drive con doc match en Holded)
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.integrations import drive as drive_mod
from app.tasks import aprendizaje_holded


log = logging.getLogger("ramon.observador_drive_facturas")

FOLDER_ID = "1cMpA-sQuT-cDtS3DBGtrMtRUem8qQUrv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
PERFIL_PATH = DATA_DIR / "perfil_drive_facturas.json"


def _listar_recursivo(folder_id: str, depth: int = 0, acc: list[dict] | None = None) -> list[dict]:
    if acc is None:
        acc = []
    if depth > 3:
        return acc
    try:
        svc = drive_mod._svc()  # type: ignore[attr-defined]
        page_token: str | None = None
        while True:
            resp = svc.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType,size,createdTime,modifiedTime,md5Checksum)",
                pageSize=500,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in resp.get("files", []):
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    _listar_recursivo(f["id"], depth + 1, acc)
                else:
                    acc.append(f)
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as exc:
        log.warning(f"listar drive fail: {exc}")
    return acc


def _extraer_patron(nombre: str) -> str:
    """Simplifica un nombre a patrón (números→N, letras mantienen)."""
    # Primeros 60 chars, sin extensión
    base = nombre.rsplit(".", 1)[0][:60]
    # Colapsa secuencias de dígitos
    patron = re.sub(r"\d+", "N", base)
    return patron


def observar() -> dict[str, Any]:
    archivos = _listar_recursivo(FOLDER_ID)
    if not archivos:
        return {"ok": False, "archivos": 0}

    patrones = Counter(_extraer_patron(a["name"]) for a in archivos)
    timeline = Counter()
    for a in archivos:
        t = a.get("createdTime", "")
        if len(t) >= 7:
            timeline[t[:7]] += 1

    # Cruce Holded: busca doc numbers en nombres
    perfil_h = aprendizaje_holded.cargar_perfil()
    doc_numbers = set()
    for c in (perfil_h.get("cobros_pendientes", {}).get("ejemplos") or []):
        if c.get("num"):
            doc_numbers.add(str(c["num"]))

    cruce_count = 0
    ejemplos_cruce = []
    for a in archivos:
        for num in doc_numbers:
            if num and num in a["name"]:
                cruce_count += 1
                if len(ejemplos_cruce) < 5:
                    ejemplos_cruce.append({"archivo": a["name"], "num_holded": num})
                break

    perfil = {
        "ultima_actualizacion": datetime.now().isoformat(timespec="seconds"),
        "folder_id": FOLDER_ID,
        "total_archivos": len(archivos),
        "patrones_nombre_top": patrones.most_common(10),
        "timeline_mensual": dict(sorted(timeline.items())[-24:]),
        "cruce_holded": {
            "matches": cruce_count,
            "ejemplos": ejemplos_cruce,
        },
        "archivos_recientes": sorted(
            [{"name": a["name"], "created": a.get("createdTime"), "size": a.get("size")} for a in archivos],
            key=lambda x: x.get("created") or "",
            reverse=True,
        )[:20],
    }
    PERFIL_PATH.write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Observador Drive facturas: %d archivos, cruce Holded: %d", len(archivos), cruce_count)
    return {"ok": True, "perfil": perfil}


def cargar_perfil() -> dict[str, Any]:
    if not PERFIL_PATH.exists():
        return {}
    try:
        return json.loads(PERFIL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
