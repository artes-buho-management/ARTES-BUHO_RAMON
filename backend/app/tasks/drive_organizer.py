"""Organizador automatico de Drive (portado de ARTES-BUHO_DRIVE-COPIA-SEGURIDAD).

Ordena archivos sueltos de la cuenta booking@artesbuhomanagement.com en una
estructura de carpetas por categoria. Usa el cerebro de Ramon (cascada tier
TRIVIAL) para clasificar archivos no obvios.

Categorias: CONTRATOS, FACTURAS, CORREO, AUDIO, VIDEO, IMAGEN, HOJAS,
PRESENTACIONES, SCRIPTS, DOCUMENTOS, COMPRIMIDOS, OTROS.

Estructura en "Mi Unidad" de booking@:
    DRIVE_IA_ORGANIZADOR_BOOKING/
    ├── 01_CLASIFICADOS/
    │   ├── CONTRATOS/
    │   ├── FACTURAS/
    │   └── ...
    ├── 02_REVISION_MANUAL/
    ├── 03_ERRORES/
    └── 99_LOGS/

Flujo:
1. Bootstrap -> garantiza estructura de carpetas
2. Listar archivos sueltos en "Mi unidad" (nivel 0)
3. Para cada archivo:
   - Heuristica por mime/nombre -> si clara, mover directo
   - Si ambigua -> cerebro Ramon (tier TRIVIAL) clasifica
   - Mover a subcarpeta correspondiente
4. Log a 99_LOGS/run_YYYY-MM-DD.txt
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any

from app.google_client import drive as _drive_service
from app.integrations import brain_router

log = logging.getLogger("ramon.drive_organizer")

ROOT_FOLDER_NAME = "DRIVE_IA_ORGANIZADOR_BOOKING"
CLASIFICADOS_FOLDER = "01_CLASIFICADOS"
REVISION_FOLDER = "02_REVISION_MANUAL"
ERRORES_FOLDER = "03_ERRORES"
LOGS_FOLDER = "99_LOGS"
CATEGORIES = [
    "CONTRATOS", "FACTURAS", "CORREO", "AUDIO", "VIDEO", "IMAGEN",
    "HOJAS", "PRESENTACIONES", "SCRIPTS", "DOCUMENTOS", "COMPRIMIDOS", "OTROS",
]


# ---------- Drive helpers ----------

def _get_drive():
    return _drive_service()


def _get_or_create_folder(parent_id: str | None, name: str) -> str:
    """Devuelve folder_id. Crea si no existe."""
    drive = _get_drive()
    q = [f"name = '{name}'",
         "mimeType = 'application/vnd.google-apps.folder'",
         "trashed = false"]
    if parent_id:
        q.append(f"'{parent_id}' in parents")
    else:
        q.append("'root' in parents")
    query = " and ".join(q)
    resp = drive.files().list(
        q=query, spaces='drive', fields='files(id,name)', pageSize=10
    ).execute()
    files = resp.get('files', [])
    if files:
        return files[0]['id']
    # Crear
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    folder = drive.files().create(body=body, fields='id').execute()
    log.info(f"Creada carpeta '{name}' id={folder['id']}")
    return folder['id']


def bootstrap_structure() -> dict[str, Any]:
    """Crea/asegura toda la jerarqu\u00eda."""
    root_id = _get_or_create_folder(None, ROOT_FOLDER_NAME)
    clasif_id = _get_or_create_folder(root_id, CLASIFICADOS_FOLDER)
    revision_id = _get_or_create_folder(root_id, REVISION_FOLDER)
    errores_id = _get_or_create_folder(root_id, ERRORES_FOLDER)
    logs_id = _get_or_create_folder(root_id, LOGS_FOLDER)
    cat_ids: dict[str, str] = {}
    for cat in CATEGORIES:
        cat_ids[cat] = _get_or_create_folder(clasif_id, cat)
    return {
        "root_id": root_id,
        "clasificados_id": clasif_id,
        "revision_id": revision_id,
        "errores_id": errores_id,
        "logs_id": logs_id,
        "categorias": cat_ids,
    }


def list_loose_files(max_files: int = 50) -> list[dict]:
    """Lista archivos en la raiz de Mi Unidad (no carpetas, no trashed)."""
    drive = _get_drive()
    q = ("'root' in parents and trashed = false "
         "and mimeType != 'application/vnd.google-apps.folder'")
    resp = drive.files().list(
        q=q, spaces='drive',
        fields='files(id,name,mimeType,size,modifiedTime,parents)',
        pageSize=max_files, orderBy='modifiedTime desc',
    ).execute()
    return resp.get('files', [])


def move_file(file_id: str, dest_folder_id: str) -> None:
    drive = _get_drive()
    f = drive.files().get(fileId=file_id, fields='parents').execute()
    prev_parents = ",".join(f.get('parents', [])) or "root"
    drive.files().update(
        fileId=file_id,
        addParents=dest_folder_id,
        removeParents=prev_parents,
        fields='id,parents',
    ).execute()


# ---------- Clasificacion ----------

_HEURISTIC_KEYS = [
    (r"factura|invoice|recibo|albaran|pago|nomina",          "FACTURAS"),
    (r"contrato|contract|acuerdo|booking|anex",              "CONTRATOS"),
    (r"correo|email|gmail|router|newsletter",                "CORREO"),
    (r"\.(zip|rar|7z|tar|gz)$",                              "COMPRIMIDOS"),
]


def heuristic_category(name: str, mime: str) -> str:
    n = (name or "").lower()
    m = (mime or "").lower()
    for rx, cat in _HEURISTIC_KEYS:
        if re.search(rx, n):
            return cat
    if m.startswith("audio/"):
        return "AUDIO"
    if m.startswith("video/"):
        return "VIDEO"
    if m.startswith("image/"):
        return "IMAGEN"
    if m == "application/vnd.google-apps.spreadsheet":
        return "HOJAS"
    if m == "application/vnd.google-apps.presentation":
        return "PRESENTACIONES"
    if m == "application/vnd.google-apps.script":
        return "SCRIPTS"
    if "zip" in m or "compressed" in m:
        return "COMPRIMIDOS"
    if "pdf" in m or "document" in m or "word" in m or "text" in m:
        return "DOCUMENTOS"
    return "OTROS"


def _should_use_ai(mime: str, heuristic: str) -> bool:
    m = (mime or "").lower()
    if m.startswith(("audio/", "video/", "image/")):
        return False
    if heuristic in ("HOJAS", "PRESENTACIONES", "SCRIPTS", "COMPRIMIDOS"):
        return False
    return True


_AI_SYSTEM = (
    "Clasifica archivos de Google Drive en UNA categoria de esta lista exacta: "
    "CONTRATOS, FACTURAS, CORREO, AUDIO, VIDEO, IMAGEN, HOJAS, PRESENTACIONES, "
    "SCRIPTS, DOCUMENTOS, COMPRIMIDOS, OTROS. "
    "Devuelve SOLO JSON valido sin markdown: "
    '{"categoria":"<CATEGORIA>","confianza":0.0,"motivo":"<texto corto>"}'
)


def ai_classify(file: dict) -> tuple[str, float, str]:
    """Clasifica via cerebro Ramon tier TRIVIAL. Devuelve (categoria, confianza, motivo)."""
    user = (f"nombre: {file.get('name')}\n"
            f"mimeType: {file.get('mimeType')}\n"
            f"tamanoBytes: {file.get('size', '?')}")
    try:
        data, _cerebro = brain_router.classify_json(_AI_SYSTEM, user, max_tokens=200)
    except Exception as exc:
        log.warning(f"ai_classify fallo: {exc}")
        return "OTROS", 0.0, "fallback error IA"
    cat = str(data.get("categoria", "")).upper().strip()
    if cat not in CATEGORIES:
        cat = "OTROS"
    conf = float(data.get("confianza", 0.5) or 0.5)
    motivo = str(data.get("motivo", ""))[:120]
    return cat, conf, motivo


# ---------- Ciclo principal ----------

def process_one_cycle(max_files: int = 25) -> dict[str, Any]:
    """Procesa un ciclo completo. Devuelve estadisticas."""
    t0 = time.time()
    struct = bootstrap_structure()
    files = list_loose_files(max_files=max_files)
    results: dict[str, int] = {}
    actions: list[dict] = []

    for f in files:
        try:
            heur = heuristic_category(f.get('name', ''), f.get('mimeType', ''))
            if _should_use_ai(f.get('mimeType', ''), heur):
                cat, conf, motivo = ai_classify(f)
                source = "ai"
                if conf < 0.6:
                    # Baja confianza -> revision manual
                    move_file(f['id'], struct['revision_id'])
                    actions.append({"id": f['id'], "name": f.get('name'),
                                    "action": "to_revision", "source": source,
                                    "conf": conf, "motivo": motivo})
                    results['REVISION'] = results.get('REVISION', 0) + 1
                    continue
            else:
                cat, conf, motivo = heur, 1.0, "heuristica"
                source = "heuristic"

            dest_id = struct['categorias'].get(cat) or struct['categorias']['OTROS']
            move_file(f['id'], dest_id)
            actions.append({"id": f['id'], "name": f.get('name'),
                            "action": f"moved->{cat}", "source": source,
                            "conf": conf, "motivo": motivo})
            results[cat] = results.get(cat, 0) + 1
        except Exception as exc:
            log.warning(f"Error procesando {f.get('name')}: {exc}")
            try:
                move_file(f['id'], struct['errores_id'])
                actions.append({"id": f['id'], "name": f.get('name'),
                                "action": "to_errors", "error": str(exc)[:120]})
                results['ERRORES'] = results.get('ERRORES', 0) + 1
            except Exception:
                pass

    elapsed = round(time.time() - t0, 1)

    # Log a Drive
    try:
        log_content = _build_log(files, actions, elapsed, results)
        _save_log_to_drive(struct['logs_id'], log_content)
    except Exception as exc:
        log.warning(f"No se pudo guardar log en Drive: {exc}")

    return {
        "processed": len(files),
        "results": results,
        "elapsed_s": elapsed,
        "actions": actions[-50:],
    }


def _build_log(files, actions, elapsed, results) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"=== Ramon Drive Organizer run {ts} ==="]
    lines.append(f"Archivos procesados: {len(files)} | Elapsed: {elapsed}s")
    lines.append(f"Resumen: {json.dumps(results, ensure_ascii=False)}")
    lines.append("")
    for a in actions:
        lines.append(f"  {a.get('name'):<60s} -> {a.get('action')} "
                     f"[{a.get('source','?')} conf={a.get('conf','')}]")
    return "\n".join(lines)


def _save_log_to_drive(logs_folder_id: str, content: str) -> None:
    from googleapiclient.http import MediaInMemoryUpload
    drive = _get_drive()
    fname = f"run_{datetime.now().strftime('%Y-%m-%d_%H%M')}.log"
    media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
    drive.files().create(
        body={"name": fname, "parents": [logs_folder_id]},
        media_body=media,
        fields='id',
    ).execute()
