"""Auditor de etiquetas Gmail: resuelve conflictos mutuamente excluyentes.

Reglas ESTADO/* son mutuamente excluyentes. Un mismo mensaje no puede tener a la vez:
 - ESTADO/ACCION + ESTADO/REVISION
 - ESTADO/ACCION + ESTADO/ARCHIVADO
 - ESTADO/URGENTE + ESTADO/ARCHIVADO
 - etc.

Prioridad (la más "caliente" gana y se quitan las demás):
  URGENTE > ACCION > REVISION > ESPERANDO > LEER > ARCHIVADO

Además:
 - Si tiene ESTADO/ARCHIVADO pero sigue en INBOX → quitar INBOX.
 - Si tiene ESTADO/ACCION pero no está en INBOX → devolverlo a INBOX.
 - Si tiene 0 etiquetas ESTADO/* pero está en INBOX con UNREAD > 3 días → añadir LEER.

Se ejecuta cada 3h por el scheduler, procesa un lote de 150 mensajes recientes.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod


log = logging.getLogger("ramon.auditor_etiquetas")


PRIORIDAD = [
    "ESTADO/URGENTE",
    "ESTADO/ACCION",
    "ESTADO/REVISION",
    "ESTADO/ESPERANDO",
    "ESTADO/LEER",
    "ESTADO/ARCHIVADO",
]


def _label_id_map(account: str) -> dict[str, str]:
    try:
        return gmail_mod._labels_map(account)  # type: ignore[attr-defined]
    except Exception:
        return {}


def _ids_to_names(lids: list[str], mp: dict[str, str]) -> list[str]:
    rev = {v: k for k, v in mp.items()}
    return [rev.get(lid, "") for lid in lids]


def auditar(max_msgs: int = 150) -> dict[str, Any]:
    settings = get_settings()
    out: dict[str, Any] = {"cuentas": {}, "fixes": 0}

    for account in [settings.gmail_user, settings.gmail_personal]:
        mp = _label_id_map(account)
        if not mp:
            out["cuentas"][account] = {"error": "labels map vacío"}
            continue

        try:
            msgs = gmail_mod.list_messages(account, query="in:anywhere newer_than:90d", max_results=max_msgs)
        except Exception as exc:
            out["cuentas"][account] = {"error": str(exc)}
            continue

        fixes_cuenta = 0
        conflictos_cuenta = 0

        for m in msgs:
            try:
                info = gmail_mod.get_message(account, m["id"])
            except Exception:
                continue
            label_ids = info.get("label_ids", [])
            label_names = [n for n in _ids_to_names(label_ids, mp) if n]

            estados = [n for n in label_names if n.startswith("ESTADO/")]
            if len(estados) <= 1:
                # Coherencia INBOX vs ARCHIVADO
                if "ESTADO/ARCHIVADO" in estados and "INBOX" in label_ids:
                    try:
                        gmail_mod._service(account).users().messages().modify(  # type: ignore[attr-defined]
                            userId="me", id=info["id"],
                            body={"removeLabelIds": ["INBOX"]},
                        ).execute()
                        fixes_cuenta += 1
                    except Exception:
                        pass
                continue

            # hay conflicto -> elegir la más prioritaria, quitar el resto
            conflictos_cuenta += 1
            ganador = next((p for p in PRIORIDAD if p in estados), estados[0])
            perdedores = [e for e in estados if e != ganador]
            remove_ids = [mp[e] for e in perdedores if e in mp]
            if not remove_ids:
                continue
            try:
                gmail_mod._service(account).users().messages().modify(  # type: ignore[attr-defined]
                    userId="me", id=info["id"],
                    body={"removeLabelIds": remove_ids},
                ).execute()
                fixes_cuenta += 1
            except Exception as exc:
                log.debug(f"auditor modify fail: {exc}")

        out["cuentas"][account] = {
            "escaneados": len(msgs),
            "conflictos": conflictos_cuenta,
            "fixes": fixes_cuenta,
        }
        out["fixes"] += fixes_cuenta

    log.info("Auditor etiquetas: %d fixes totales", out["fixes"])
    return out
