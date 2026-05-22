"""Rescate de correos históricos pendientes de respuesta.

Objetivo: procesar hilos que han quedado "obsoletos" (sin respuesta de Rubén)
y decidir si responde Ramón directamente, deja borrador en amarillo, o ignora.

Se ejecuta:
 - Manual vía endpoint /rescate/ejecutar
 - Programado: diariamente a las 10:30 L-V, lotes pequeños

Estrategia:
 1. Busca en ambas cuentas hilos de los últimos N días sin respuesta nuestra.
 2. Por cada hilo, aplica el orquestador (`procesar_email`) que ya decide
    con el protocolo v4 si responder, dejar borrador o archivar.
 3. Limita por lote para no saturar (7 hilos por ejecución por defecto).
 4. Evita reprocesar con tabla EmailProcessed.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod
from app.tasks.orquestador import procesar_email, _ya_procesado
from app.learning import aprendizaje as apr


log = logging.getLogger("ramon.rescate")


def _hilos_pendientes(account: str, dias: int, max_msgs: int = 100) -> list[dict]:
    """Lista mensajes recibidos en los últimos `dias` donde aún no hemos respondido."""
    since = (_dt.date.today() - _dt.timedelta(days=dias)).strftime("%Y/%m/%d")
    # Trucos Gmail: -from:(yo) in:inbox has:nouserlabels no sirven,
    # así que tiramos de in:inbox + filtrar.
    query = f"in:inbox after:{since}"
    try:
        msgs = gmail_mod.list_messages(account, query=query, max_results=max_msgs)
    except Exception as exc:
        log.warning(f"list_messages {account}: {exc}")
        return []
    pendientes: list[dict] = []
    for m in msgs:
        try:
            info = gmail_mod.get_message(account, m["id"])
        except Exception:
            continue
        # ya procesado -> skip
        if _ya_procesado(info["id"]):
            continue
        # heurística sencilla: si UNREAD o si el from no es la propia cuenta
        sender = (info.get("from") or "").lower()
        if account.lower() in sender:
            continue
        pendientes.append(info)
    return pendientes


def rescatar_lote(max_hilos: int = 7, dias: int = 90) -> dict[str, Any]:
    settings = get_settings()
    try:
        ctx = apr.construir_contexto_para_gemini()
    except Exception:
        ctx = ""

    resultados: dict[str, Any] = {"procesados": 0, "por_cuenta": {}}
    restantes = max_hilos

    for account in [settings.gmail_user, settings.gmail_personal]:
        if restantes <= 0:
            break
        pendientes = _hilos_pendientes(account, dias=dias, max_msgs=80)
        procesados_cuenta = []
        for info in pendientes[: restantes]:
            try:
                r = procesar_email(account, info["id"], aprendizaje_ctx=ctx)
                procesados_cuenta.append({
                    "id": info["id"],
                    "subject": (info.get("subject") or "")[:80],
                    "from": info.get("from"),
                    "accion": r.get("accion"),
                })
                restantes -= 1
                if restantes <= 0:
                    break
            except Exception as exc:
                log.warning(f"rescate fallo en {info.get('id')}: {exc}")
        resultados["por_cuenta"][account] = {
            "candidatos": len(pendientes),
            "procesados": procesados_cuenta,
        }
        resultados["procesados"] += len(procesados_cuenta)

    log.info(
        "Rescate correos: procesados=%d restantes_del_lote=%d",
        resultados["procesados"], max(0, restantes),
    )
    return resultados
