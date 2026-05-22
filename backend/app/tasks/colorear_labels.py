"""Asigna colores a las etiquetas Gmail que usa Ramon (visual TDAH).

Gmail API permite pintar cada label con (textColor, backgroundColor).
Los colores permitidos son un conjunto finito; usamos los más contrastados.
"""
from __future__ import annotations

from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod


# Paleta valida Gmail (Google la controla, son esos hex exactos).
# Map Ramon -> colores de marca ARTES BUHO (naranja) + semaforo.
PALETA = {
    "RAMON/BASURA":         {"textColor": "#ffffff", "backgroundColor": "#464646"},  # gris oscuro
    "RAMON/ARCHIVADO":      {"textColor": "#ffffff", "backgroundColor": "#653e9b"},  # morado
    "ESTADO/ACCION":        {"textColor": "#ffffff", "backgroundColor": "#cc3a21"},  # rojo
    "ESTADO/URGENTE":       {"textColor": "#ffffff", "backgroundColor": "#cc3a21"},  # rojo
    "ESTADO/REVISION":      {"textColor": "#000000", "backgroundColor": "#ffad47"},  # naranja (marca)
    "ESTADO/ESPERANDO":     {"textColor": "#000000", "backgroundColor": "#fad165"},  # amarillo
    "ESTADO/LEER":          {"textColor": "#000000", "backgroundColor": "#c2c2c2"},  # gris claro
    "ESTADO/ARCHIVADO":     {"textColor": "#ffffff", "backgroundColor": "#16a766"},  # verde
    "CONTEXTO/RUBEN_COTON": {"textColor": "#ffffff", "backgroundColor": "#ffad47"},  # naranja marca
    "CONTEXTO/PERSONAL":    {"textColor": "#ffffff", "backgroundColor": "#4986e7"},  # azul
    "CONTEXTO/TICKETS_BUHO":{"textColor": "#ffffff", "backgroundColor": "#8e63ce"},  # violeta
    "TEMA/FINANZAS":        {"textColor": "#ffffff", "backgroundColor": "#43d692"},  # verde lima
    "TEMA/SISTEMAS":        {"textColor": "#ffffff", "backgroundColor": "#4986e7"},  # azul
    "TEMA/SEGURIDAD":       {"textColor": "#ffffff", "backgroundColor": "#b65775"},  # rosa oscuro
    "TEMA/PLATAFORMAS":     {"textColor": "#ffffff", "backgroundColor": "#41236d"},  # violeta oscuro
}


def aplicar(account: str | None = None) -> dict[str, Any]:
    account = account or get_settings().gmail_user
    svc = gmail_mod._service(account)  # type: ignore[attr-defined]
    # Refrescar cache de labels
    gmail_mod._labels_map.cache_clear()  # type: ignore[attr-defined]
    mp = gmail_mod._labels_map(account)  # type: ignore[attr-defined]

    aplicados: list[dict] = []
    creados: list[str] = []
    errores: list[str] = []

    for name, colors in PALETA.items():
        try:
            if name not in mp:
                # Crear la label con color desde el principio
                resp = svc.users().labels().create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                        "color": colors,
                    },
                ).execute()
                creados.append(name)
                aplicados.append({"label": name, "id": resp.get("id"), "created": True})
            else:
                # Actualizar color existente
                lid = mp[name]
                resp = svc.users().labels().patch(
                    userId="me", id=lid, body={"color": colors},
                ).execute()
                aplicados.append({"label": name, "id": lid, "updated": True})
        except Exception as exc:
            errores.append(f"{name}: {exc}")

    return {"aplicados": len(aplicados), "creados": creados, "errores": errores}
