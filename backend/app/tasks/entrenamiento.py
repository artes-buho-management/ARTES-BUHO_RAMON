"""Entrenamiento de Ramon sobre el historico real de RUBEN.

Lee correos ENVIADOS por Ruben en sus dos cuentas, los analiza con Gemini y
extrae:
- Tono habitual por tipo de destinatario
- Frases recurrentes (saludos, cierres, expresiones favoritas)
- Preferencias concretas (desayuno incluido en hotel, traslados, plantillas VIP...)
- Palabras que usa / evita

Guarda el resultado en Aprendizaje_Ramon.md (Drive/01_Aprendizaje) bajo la
seccion "Diccionario RUBEN" y "Preferencias detectadas".

Se ejecuta manualmente via POST /entrenamiento/ejecutar o en rearranques.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod
from app.integrations import drive as drive_mod
from app.integrations.gemini_brain import _call_gemini, GeminiBrainError, QuotaExceeded


_PROMPT = """Eres un analista entrenando a RAMON (asistente de ARTES BUHO, DJ).
Voy a darte una muestra de correos ENVIADOS por RUBEN. Analizalos y extrae un
perfil operativo para que Ramon imite su estilo al redactar.

Devuelve JSON con esta estructura exacta (nada mas):
{
  "tono_general": "descripcion (<200 chars)",
  "saludos_favoritos": ["...", "..."],
  "cierres_favoritos": ["...", "..."],
  "frases_recurrentes": ["...", "..."],
  "palabras_que_usa": ["...", "..."],
  "palabras_que_evita": ["...", "..."],
  "preferencias_detectadas": [
    "Pide desayuno incluido en hoteles",
    "Adjunta billetes AVE",
    "..."
  ],
  "tono_por_tipo": {
    "after_you": "...",
    "ayuntamientos": "...",
    "bodas": "...",
    "agencias": "...",
    "personales": "..."
  },
  "plantillas_detectadas": [
    {"nombre": "logistica After You", "patron": "..."}
  ],
  "instrucciones_para_ramon": [
    "Cuando escribas a After You, di 'Mil gracias' y 'Un abrazo fuerte'.",
    "..."
  ]
}
"""


def _recopilar_enviados(account: str, max_msgs: int = 80, after: str = "") -> list[str]:
    """Saca el texto de los N correos enviados mas recientes (opcionalmente tras fecha after=YYYY/MM/DD)."""
    query = "in:sent"
    if after:
        query += f" after:{after}"
    try:
        msgs = gmail_mod.list_messages(account, query=query, max_results=max_msgs)
    except Exception:
        return []
    muestras: list[str] = []
    for m in msgs:
        try:
            info = gmail_mod.get_message(account, m["id"])
            fecha = info.get("date", "")
            to = info.get("to", "")
            subj = info.get("subject", "")
            body = (info.get("body_text") or "")[:2500]
            muestras.append(
                f"--- FECHA: {fecha} | PARA: {to} | ASUNTO: {subj}\n{body}"
            )
        except Exception:
            continue
    return muestras


def entrenar_profundo(
    max_msgs_por_cuenta: int = 200,
    chunk_size: int = 25,
    pausa_s: int = 5,
) -> dict[str, Any]:
    """Entrenamiento profundo por chunks para evitar rate limit Gemini.

    Procesa por lotes de chunk_size correos, pausa entre llamadas y consolida al final.
    Seguro para correr en background 24h.
    """
    settings = get_settings()
    import time as _time
    combinado: list[str] = []
    stats: dict[str, Any] = {"cuentas": {}}

    for acc in [settings.gmail_user, settings.gmail_personal]:
        muestras = _recopilar_enviados(acc, max_msgs=max_msgs_por_cuenta)
        stats["cuentas"][acc] = {"muestras": len(muestras)}
        combinado.extend(muestras)

    if not combinado:
        return {"error": "sin historico accesible", "stats": stats}

    # Analizar por chunks, acumulando observaciones
    resumenes_parciales: list[dict[str, Any]] = []
    chunks = [combinado[i:i + chunk_size] for i in range(0, len(combinado), chunk_size)]
    stats["chunks"] = len(chunks)

    for idx, chunk in enumerate(chunks):
        try:
            r = _analizar_batch(chunk)
            resumenes_parciales.append(r)
        except QuotaExceeded as exc:
            stats[f"chunk_{idx}_error"] = f"quota: {exc}"
            _time.sleep(60)  # esperar minuto completo
            continue
        except Exception as exc:
            stats[f"chunk_{idx}_error"] = str(exc)[:200]
            continue
        _time.sleep(pausa_s)  # respetar rate limit

    if not resumenes_parciales:
        return {"error": "ningun chunk proceso correctamente", "stats": stats}

    # Fusionar resumenes: union de listas, mayoria tono
    fusion = _fusionar_resumenes(resumenes_parciales)

    # Persistir en Aprendizaje_Ramon.md
    actual = drive_mod.leer_aprendizaje_ramon()
    if not actual.strip():
        actual = "# Aprendizaje_Ramon.md\n\nArchivo maestro.\n"
    seccion = _render_seccion_aprendizaje(fusion)
    marcador = "## Perfil operativo de RUBEN"
    if marcador in actual:
        antes = actual.split(marcador)[0]
        nuevo = antes + seccion.lstrip("\n")
    else:
        nuevo = actual + "\n" + seccion
    drive_mod.escribir_aprendizaje_ramon(nuevo)

    return {
        "ok": True,
        "stats": stats,
        "chunks_procesados": len(resumenes_parciales),
        "analisis_fusionado": fusion,
        "guardado_en": "Drive/Ramon/01_Aprendizaje/Aprendizaje_Ramon.md",
    }


def _fusionar_resumenes(resumenes: list[dict[str, Any]]) -> dict[str, Any]:
    """Fusiona multiples analisis parciales en uno consolidado."""
    if not resumenes:
        return {}
    # Tono general: coger el primero (representativo)
    fusion = dict(resumenes[0])
    listas_claves = [
        "saludos_favoritos", "cierres_favoritos", "frases_recurrentes",
        "palabras_que_usa", "palabras_que_evita",
        "preferencias_detectadas", "instrucciones_para_ramon",
    ]
    for k in listas_claves:
        vistos = set()
        unificado: list[str] = []
        for r in resumenes:
            for item in (r.get(k) or []):
                key = str(item).strip().lower()[:100]
                if key and key not in vistos:
                    vistos.add(key)
                    unificado.append(item)
        fusion[k] = unificado[:20]
    # Plantillas y contactos agregados
    for k in ("plantillas_detectadas",):
        agg = []
        seen = set()
        for r in resumenes:
            for item in (r.get(k) or []):
                key = json.dumps(item, ensure_ascii=False, sort_keys=True)[:200]
                if key not in seen:
                    seen.add(key)
                    agg.append(item)
        fusion[k] = agg[:15]
    # tono_por_tipo: merge
    tono_agg: dict[str, str] = {}
    for r in resumenes:
        for k, v in (r.get("tono_por_tipo") or {}).items():
            if k not in tono_agg or len(str(v)) > len(str(tono_agg.get(k, ""))):
                tono_agg[k] = v
    fusion["tono_por_tipo"] = tono_agg
    return fusion


def _analizar_batch(muestras: list[str]) -> dict[str, Any]:
    texto = "\n\n".join(muestras)[:60000]
    raw = _call_gemini(_PROMPT, texto, response_json=True, max_tokens=8000, is_email_call=False)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    s, e = raw.find("{"), raw.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(raw[s:e + 1])
        except json.JSONDecodeError:
            pass
    # Intento 3: balancear llaves y cerrar strings abiertos
    if s >= 0:
        candidate = raw[s:].rstrip()
        # Cerrar string abierto si queda un comienzo de cadena sin cerrar
        if candidate.count('"') % 2 == 1:
            candidate += '"'
        opens = candidate.count("{") - candidate.count("}")
        opens_a = candidate.count("[") - candidate.count("]")
        candidate = candidate.rstrip(",") + ("]" * max(0, opens_a)) + ("}" * max(0, opens))
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON truncado irrecuperable: {exc}") from exc
    raise ValueError("respuesta vacia")


def _render_seccion_aprendizaje(analisis: dict[str, Any]) -> str:
    def _b(xs):
        return "\n".join(f"  - {x}" for x in xs) if xs else "  (vacio)"

    def _b_dicts(xs):
        lines = []
        for x in xs or []:
            if isinstance(x, dict):
                lines.append(f"  - {json.dumps(x, ensure_ascii=False)}")
            else:
                lines.append(f"  - {x}")
        return "\n".join(lines) if lines else "  (vacio)"

    tono_por_tipo = analisis.get("tono_por_tipo") or {}
    tono_lines = "\n".join(f"  - {k}: {v}" for k, v in tono_por_tipo.items())

    import datetime as _dt
    return (
        "\n## Perfil operativo de RUBEN (entrenado automaticamente)\n"
        f"Actualizado: {_dt.date.today().isoformat()}\n\n"
        f"**Tono general:** {analisis.get('tono_general', '')}\n\n"
        "**Saludos favoritos:**\n"
        f"{_b(analisis.get('saludos_favoritos', []))}\n\n"
        "**Cierres favoritos:**\n"
        f"{_b(analisis.get('cierres_favoritos', []))}\n\n"
        "**Frases recurrentes:**\n"
        f"{_b(analisis.get('frases_recurrentes', []))}\n\n"
        "**Palabras que USA:**\n"
        f"{_b(analisis.get('palabras_que_usa', []))}\n\n"
        "**Palabras que EVITA:**\n"
        f"{_b(analisis.get('palabras_que_evita', []))}\n\n"
        "**Preferencias detectadas:**\n"
        f"{_b(analisis.get('preferencias_detectadas', []))}\n\n"
        "**Tono por tipo de interlocutor:**\n"
        f"{tono_lines or '  (vacio)'}\n\n"
        "**Plantillas detectadas:**\n"
        f"{_b_dicts(analisis.get('plantillas_detectadas', []))}\n\n"
        "**Instrucciones clave para Ramon:**\n"
        f"{_b(analisis.get('instrucciones_para_ramon', []))}\n"
    )


def entrenar(max_msgs_por_cuenta: int = 80) -> dict[str, Any]:
    settings = get_settings()
    resultado: dict[str, Any] = {"cuentas": {}}

    combinado: list[str] = []
    for acc in [settings.gmail_user, settings.gmail_personal]:
        muestras = _recopilar_enviados(acc, max_msgs=max_msgs_por_cuenta)
        resultado["cuentas"][acc] = {"muestras": len(muestras)}
        combinado.extend(muestras)

    if not combinado:
        resultado["error"] = "no hay enviados o no hay acceso"
        return resultado

    try:
        analisis = _analizar_batch(combinado)
    except QuotaExceeded as exc:
        return {"error": f"quota: {exc}"}
    except GeminiBrainError as exc:
        return {"error": f"gemini: {exc}"}
    except Exception as exc:
        return {"error": f"parse: {exc}"}

    # Merge con Aprendizaje_Ramon.md existente
    actual = drive_mod.leer_aprendizaje_ramon()
    if not actual.strip():
        actual = "# Aprendizaje_Ramon.md\n\nArchivo maestro. Se actualiza con el historico.\n"
    seccion = _render_seccion_aprendizaje(analisis)
    # Reemplazar seccion previa si existe
    marcador = "## Perfil operativo de RUBEN"
    if marcador in actual:
        antes = actual.split(marcador)[0]
        nuevo = antes + seccion.lstrip("\n")
    else:
        nuevo = actual + "\n" + seccion
    drive_mod.escribir_aprendizaje_ramon(nuevo)

    resultado["analisis"] = analisis
    resultado["guardado_en"] = "Drive/Ramon/01_Aprendizaje/Aprendizaje_Ramon.md"
    return resultado


def asegurar_etiqueta_archivo() -> dict[str, Any]:
    """Garantiza la etiqueta RAMON/ARCHIVADO (distinta de ESTADO/ARCHIVADO)."""
    settings = get_settings()
    out = {}
    for acc in [settings.gmail_user, settings.gmail_personal]:
        try:
            lid = gmail_mod.ensure_label(acc, "RAMON/ARCHIVADO")
            out[acc] = {"label_id": lid}
        except Exception as exc:
            out[acc] = {"error": str(exc)}
    return out
