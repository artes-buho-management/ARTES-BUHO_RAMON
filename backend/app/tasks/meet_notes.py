"""Procesamiento automatico de notas y transcripciones de Google Meet.

Requiere Google Workspace Business Standard (o superior) con Gemini activo.
Google guarda automaticamente en Drive:
- Meet Recordings/     → grabaciones .mp4
- Notas de reunion de Gemini / Meet Recordings → transcripciones .txt/.docx
  y documentos de notas generados por Gemini.

Flujo de Ramon:
1. Escanea Drive buscando archivos nuevos con mime_type transcripcion o doc de reunion.
2. Descarga contenido del archivo (o export text si es Google Doc).
3. Pasa el texto a Gemini con un prompt estructurado.
4. Gemini devuelve JSON: resumen, decisiones, action_items, contactos, tarifas_mencionadas, next_steps, clasificacion.
5. Guarda resumen estructurado en Drive/Ramon/06_Reuniones/{fecha}_{titulo}.md
6. Actualiza CRM si detecta un contacto existente.
7. Envia resumen por Telegram.

La tarea se ejecuta cada hora (scheduler).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from typing import Any

from app.integrations import drive as drive_mod
from app.integrations import sheets_crm as crm
from app.integrations.gemini_brain import _call_gemini, GeminiBrainError, QuotaExceeded
from app.integrations.telegram_bot import send_message


# Carpeta Ramon para reuniones procesadas
REUNIONES_FOLDER_NAME = "06_Reuniones"

# Mime types relevantes en Drive
MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_TEXT_PLAIN = "text/plain"
MIME_VIDEO = "video/mp4"


_MEET_HINTS = (
    "meet recordings",
    "notas de reunion",
    "notas de la reunion",
    "meeting notes",
    "transcripcion",
    "gemini notes",
)


def _ensure_reuniones_folder() -> str:
    """Garantiza la carpeta 06_Reuniones dentro de la estructura Ramon."""
    struct = drive_mod.ensure_ramon_structure()
    root = struct["_ROOT"]
    return drive_mod.ensure_folder(root, REUNIONES_FOLDER_NAME)


def _buscar_archivos_recientes(horas: int = 24) -> list[dict]:
    """Busca archivos de Meet modificados en las ultimas N horas.

    Estrategia: listar archivos recientes del Drive del usuario y filtrar
    por nombre/parent que indique transcripcion de Meet.
    """
    svc = drive_mod._svc()  # type: ignore[attr-defined]
    since = (_dt.datetime.utcnow() - _dt.timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = (
        f"modifiedTime > '{since}' and trashed=false and "
        f"(mimeType='{MIME_GOOGLE_DOC}' or mimeType='{MIME_TEXT_PLAIN}' or mimeType='{MIME_VIDEO}')"
    )
    resp = svc.files().list(
        q=q,
        fields="files(id,name,mimeType,modifiedTime,parents,webViewLink)",
        pageSize=200,
        orderBy="modifiedTime desc",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    relevantes = []
    for f in files:
        name_lower = f["name"].lower()
        if any(h in name_lower for h in _MEET_HINTS):
            relevantes.append(f)
            continue
        # Tambien: archivos dentro de carpetas Meet Recordings / Notas
        for parent_id in f.get("parents", []):
            try:
                parent = svc.files().get(
                    fileId=parent_id, fields="name", supportsAllDrives=True,
                ).execute()
                pname = (parent.get("name") or "").lower()
                if any(h in pname for h in _MEET_HINTS):
                    relevantes.append(f)
                    break
            except Exception:
                pass
    return relevantes


def _extraer_texto(file: dict) -> str:
    """Extrae texto del archivo segun su mime type."""
    fid = file["id"]
    mime = file["mimeType"]
    if mime == MIME_GOOGLE_DOC:
        return drive_mod.export_google_file(fid, "text/plain").decode("utf-8", errors="replace")
    if mime == MIME_TEXT_PLAIN:
        return drive_mod.download_text(fid)
    if mime == MIME_VIDEO:
        # No procesamos video: se procesa la transcripcion asociada
        return ""
    # Fallback
    try:
        return drive_mod.download_text(fid)
    except Exception:
        return ""


_PROMPT_ANALISIS = """Eres RAMON, asistente de ARTES BUHO. Vas a analizar la transcripcion/notas
de una reunion de Google Meet. Extrae informacion estructurada util para la gestion.

Reglas:
- No inventes datos. Si algo no esta claro, usa null.
- Importes en EUR. Fechas en formato ISO (YYYY-MM-DD).
- Enfoque: booking de DJ, bodas, corporativos, ayuntamientos, colaboraciones.

Devuelve SOLO JSON valido con esta estructura:
{
  "titulo_reunion": "resumen breve (<80 chars)",
  "fecha": "YYYY-MM-DD o null",
  "asistentes": ["nombre1", "nombre2"],
  "categoria": "boda|corporativo|ayuntamiento|festival|agencia|personal|otro",
  "resumen": "3-5 frases con lo esencial",
  "decisiones": ["decision1", "decision2"],
  "action_items": [
    {"que": "accion concreta", "quien": "ruben|ramon|cliente|null", "fecha_limite": "YYYY-MM-DD o null"}
  ],
  "tarifas_mencionadas": ["Pack 4h 1000 EUR", "..."],
  "siguientes_pasos": ["proximo paso 1", "..."],
  "contactos_detectados": [
    {"nombre": "...", "email": "...", "telefono": "...", "empresa": "..."}
  ],
  "temas_administrativos": ["facturacion IVA", "contrato", "reserva 200 EUR"],
  "riesgos_alertas": ["alerta si aplica"],
  "nivel_decision": "verde|amarillo|rojo"
}
"""


def _analizar_con_gemini(texto: str) -> dict[str, Any]:
    if not texto.strip():
        return {"error": "texto vacio"}
    raw = _call_gemini(
        _PROMPT_ANALISIS,
        texto[:60000],
        response_json=True,
        max_tokens=3000,
        is_email_call=False,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        return {"error": "respuesta no-JSON", "raw": raw[:500]}


def _hash_contenido(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _ya_procesado(reuniones_folder_id: str, hash_id: str) -> bool:
    """Busca si ya existe un .md con ese hash en la carpeta."""
    for f in drive_mod.list_children(reuniones_folder_id):
        if hash_id in f["name"]:
            return True
    return False


def _render_markdown(analisis: dict[str, Any], origen: dict) -> str:
    def _list(xs):
        if not xs:
            return "- (ninguno)"
        return "\n".join(f"- {x}" if not isinstance(x, dict) else f"- {json.dumps(x, ensure_ascii=False)}" for x in xs)

    return (
        f"# {analisis.get('titulo_reunion', 'Reunion Meet')}\n\n"
        f"**Fecha:** {analisis.get('fecha', 'desconocida')}\n"
        f"**Categoria:** {analisis.get('categoria', '—')}\n"
        f"**Nivel decision:** {analisis.get('nivel_decision', '—')}\n"
        f"**Archivo origen:** [{origen.get('name')}]({origen.get('webViewLink', '')})\n\n"
        f"## Asistentes\n{_list(analisis.get('asistentes', []))}\n\n"
        f"## Resumen\n{analisis.get('resumen', '')}\n\n"
        f"## Decisiones\n{_list(analisis.get('decisiones', []))}\n\n"
        f"## Action items\n{_list(analisis.get('action_items', []))}\n\n"
        f"## Tarifas mencionadas\n{_list(analisis.get('tarifas_mencionadas', []))}\n\n"
        f"## Siguientes pasos\n{_list(analisis.get('siguientes_pasos', []))}\n\n"
        f"## Contactos detectados\n{_list(analisis.get('contactos_detectados', []))}\n\n"
        f"## Temas administrativos\n{_list(analisis.get('temas_administrativos', []))}\n\n"
        f"## Riesgos / alertas\n{_list(analisis.get('riesgos_alertas', []))}\n"
    )


def _actualizar_crm_si_procede(analisis: dict[str, Any]) -> list[dict]:
    """Si detectamos un contacto por email que ya este en CRM, dejamos nota con fecha."""
    actualizados = []
    fecha = analisis.get("fecha") or _dt.date.today().isoformat()
    nota = f"[{fecha}] Reunion Meet: {analisis.get('resumen', '')[:300]}"
    for c in analisis.get("contactos_detectados", []) or []:
        email = (c.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        try:
            r = crm.buscar_por_email(email)
            if not r:
                continue
            # Si el CRM tiene columna NOTAS, actualizamos (heuristica)
            actualizados.append({"email": email, "fila": r, "nota": nota})
            # El update por columna exacta depende de la estructura real, lo dejamos como borrador.
        except Exception:
            pass
    return actualizados


def _formatear_telegram(analisis: dict[str, Any]) -> str:
    lines = [
        f"<b>📋 Notas Meet — {analisis.get('titulo_reunion', '')}</b>",
        f"<i>{analisis.get('fecha', '')} · {analisis.get('categoria', '')}</i>",
        "",
        f"<b>Resumen:</b> {analisis.get('resumen', '')[:500]}",
    ]
    actions = analisis.get("action_items", []) or []
    if actions:
        lines.append("")
        lines.append("<b>Action items:</b>")
        for a in actions[:6]:
            if isinstance(a, dict):
                lines.append(f"• {a.get('que', '')} ({a.get('quien', '?')})")
            else:
                lines.append(f"• {a}")
    return "\n".join(lines)[:3900]


def procesar_pendientes(horas: int = 24, dry_run: bool = False) -> dict[str, Any]:
    """Busca archivos recientes de Meet, los analiza y guarda notas."""
    reuniones_folder_id = _ensure_reuniones_folder()
    archivos = _buscar_archivos_recientes(horas=horas)
    procesados: list[dict] = []
    errores: list[dict] = []

    for f in archivos:
        if f["mimeType"] == MIME_VIDEO:
            continue  # las grabaciones las ignoramos (no tiene sentido transcripciones de video aqui)
        try:
            texto = _extraer_texto(f)
            if len(texto) < 100:
                continue
            hash_id = _hash_contenido(texto)
            if _ya_procesado(reuniones_folder_id, hash_id):
                continue
            if dry_run:
                procesados.append({"file": f["name"], "hash": hash_id, "bytes": len(texto), "dry": True})
                continue
            analisis = _analizar_con_gemini(texto)
            if "error" in analisis:
                errores.append({"file": f["name"], "error": analisis["error"]})
                continue

            md = _render_markdown(analisis, f)
            fecha_prefix = analisis.get("fecha") or _dt.date.today().isoformat()
            safe_title = re.sub(r"[^a-zA-Z0-9\- ]", "", analisis.get("titulo_reunion", "Meet"))[:60].strip().replace(" ", "_")
            filename = f"{fecha_prefix}__{safe_title}__{hash_id}.md"
            drive_mod.upload_text(reuniones_folder_id, name=filename, text=md)

            _actualizar_crm_si_procede(analisis)

            try:
                send_message(_formatear_telegram(analisis))
            except Exception:
                pass

            procesados.append({
                "file": f["name"],
                "titulo": analisis.get("titulo_reunion"),
                "nota_md": filename,
                "action_items": len(analisis.get("action_items", []) or []),
            })
        except QuotaExceeded as exc:
            errores.append({"file": f["name"], "error": f"quota: {exc}"})
            break
        except GeminiBrainError as exc:
            errores.append({"file": f["name"], "error": f"gemini: {exc}"})
        except Exception as exc:
            errores.append({"file": f["name"], "error": str(exc)})

    return {
        "archivos_encontrados": len(archivos),
        "procesados": procesados,
        "errores": errores,
        "dry_run": dry_run,
    }
