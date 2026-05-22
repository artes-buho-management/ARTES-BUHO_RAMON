"""Carpeta de recursos comerciales para promotores.

Zonavit Promotores - ARTES BUHO:
https://drive.google.com/drive/folders/REPLACE_WITH_ID

Es la carpeta que Ruben comparte con promotores cuando hay interes comercial.
Contiene: logos, biografia, press kit, visuales, videos promocionales.

Ramon la usa para:
- Enviar el link correcto a promotores nuevos (en lugar de adjuntar PDFs pesados).
- Recoger logos/recursos si los necesita para componer firmas / adjuntos.
- Mantener actualizado Aprendizaje_Ramon.md con el inventario.
"""
from __future__ import annotations

import os
from functools import lru_cache

from app.integrations import drive as drive_mod


def folder_id() -> str:
    return os.getenv("PROMOTORES_FOLDER_ID", "1RLLG0n08oeRf6SjiF6prIFx5UKMho4sX")


def folder_url() -> str:
    return os.getenv(
        "PROMOTORES_FOLDER_URL",
        f"https://drive.google.com/drive/folders/{folder_id()}",
    )


@lru_cache(maxsize=1)
def listar_inventario() -> list[dict]:
    """Lista archivos y subcarpetas de la carpeta de promotores (recursivo 1 nivel)."""
    out: list[dict] = []
    svc = drive_mod._svc()  # type: ignore[attr-defined]

    def _visit(fid: str, path: str, depth: int = 0):
        for f in drive_mod.list_children(fid):
            item = {
                "id": f["id"],
                "name": f["name"],
                "mime": f.get("mimeType", ""),
                "path": f"{path}/{f['name']}",
                "link": f"https://drive.google.com/file/d/{f['id']}/view",
            }
            out.append(item)
            if f.get("mimeType") == "application/vnd.google-apps.folder" and depth < 2:
                _visit(f["id"], f"{path}/{f['name']}", depth + 1)

    _visit(folder_id(), "/promotores", 0)
    return out


def buscar(patron: str) -> list[dict]:
    """Busca archivos por nombre (insensible a mayusculas)."""
    p = (patron or "").lower().strip()
    if not p:
        return []
    return [x for x in listar_inventario() if p in x["name"].lower()]


def bloque_para_prompt() -> str:
    """Texto breve para inyectar en el system prompt de Gemini cuando clasifica
    emails de promotor/comercial."""
    return (
        "# RECURSOS COMERCIALES\n\n"
        f"Carpeta Drive con material oficial para promotores/clientes:\n{folder_url()}\n\n"
        "Contiene: logos, biografia, press kit, visuales, videos promocionales.\n"
        "Si el interlocutor necesita material comercial, compartele ESTE enlace "
        "(no adjuntes PDFs pesados). Menciona que dentro encuentra todo lo que pueda "
        "necesitar: logos en distintas versiones, biografia, press kit con rider tecnico, "
        "visuales y videos."
    )
