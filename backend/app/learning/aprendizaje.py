"""Sistema de aprendizaje de Ramon (protocolo v4 seccion 20 + 25).

Tres archivos vivos en Drive/Ramon/01_Aprendizaje/:
- Aprendizaje_Ramon.md       → maestro consolidado (el que se inyecta en prompts)
- Aprendizaje_desde_Chat.md   → escribe la Ramon Consultora (Claude.ai)
- Aprendizaje_desde_VPS.md    → escribe la Ramon Ejecutiva (este VPS)

Al arrancar cada dia la Ejecutiva:
 1. Lee los 3 archivos.
 2. Construye el bloque APRENDIZAJE ACUMULADO para el prompt.
 3. Si Chat.md tiene entradas mas recientes que su ultima lectura, las
    marca como "aplicadas" en VPS.md.

Consolidacion mensual (dia 1):
 1. Fusiona Chat.md + VPS.md → Aprendizaje_Ramon.md.
 2. Limpia las entradas aplicadas.
 3. Detecta contradicciones y las reporta a Ruben por Telegram.
"""
from __future__ import annotations

import datetime as _dt
from typing import Literal

from app.integrations import drive as drive_mod


Categoria = Literal["REDACCION", "CLIENTES", "DECISIONES", "PROCESOS", "EXCEPCIONES", "ERRORES"]
Fuente = Literal["chat", "vps"]


def cargar_contexto_aprendizaje() -> str:
    """Devuelve el bloque APRENDIZAJE que se inyecta en el system prompt."""
    bloques: list[str] = []
    ramon_md = drive_mod.leer_aprendizaje_ramon()
    chat_md = drive_mod.leer_aprendizaje_chat()
    vps_md = drive_mod.leer_aprendizaje_vps()

    if ramon_md.strip():
        bloques.append("## Maestro (Aprendizaje_Ramon.md)\n\n" + ramon_md.strip())
    if chat_md.strip():
        bloques.append("## Reciente desde Chat\n\n" + chat_md.strip()[-4000:])
    if vps_md.strip():
        bloques.append("## Observaciones desde VPS\n\n" + vps_md.strip()[-2000:])

    return "\n\n".join(bloques)


def _formatear_entrada(
    *,
    categoria: Categoria,
    situacion: str,
    aprendizaje: str,
    afecta_a: str = "",
    fuente: Fuente = "vps",
    fecha: _dt.date | None = None,
) -> str:
    f = fecha or _dt.date.today()
    return (
        f"[{f.isoformat()}] - [{categoria}] - [{fuente.upper()}]\n"
        f"Situacion: {situacion.strip()}\n"
        f"Aprendizaje: {aprendizaje.strip()}\n"
        f"Afecta a: {afecta_a.strip() or 'general'}"
    )


def registrar_desde_vps(
    *,
    categoria: Categoria,
    situacion: str,
    aprendizaje: str,
    afecta_a: str = "",
) -> dict:
    """Anade una entrada al archivo VPS.md (lo crea si no existe)."""
    entry = _formatear_entrada(
        categoria=categoria,
        situacion=situacion,
        aprendizaje=aprendizaje,
        afecta_a=afecta_a,
        fuente="vps",
    )
    return drive_mod.append_aprendizaje_vps(entry)


def inicializar_archivos_si_vacios() -> dict:
    """Crea los archivos Chat/VPS/Ramon con plantilla minima si no existen."""
    folder = drive_mod.aprendizaje_folder_id()
    creados: dict[str, bool] = {}

    plantilla = {
        "Aprendizaje_Ramon.md": (
            "# Aprendizaje_Ramon.md\n\n"
            "Archivo maestro consolidado. Se regenera el dia 1 de cada mes.\n\n"
            "## Preferencias por cliente\n\n(vacio)\n\n"
            "## Reglas personalizadas\n\n(vacio)\n\n"
            "## Patrones detectados\n\n(vacio)\n\n"
            "## Lecciones aprendidas\n\n(vacio)\n\n"
            "## Diccionario RUBEN\n\n(vacio)\n"
        ),
        "Aprendizaje_desde_Chat.md": (
            "# Aprendizaje_desde_Chat.md\n\n"
            "Escribe la Ramon Consultora (Claude.ai).\n"
            "Formato: [YYYY-MM-DD] - [CATEGORIA] - [CHAT]\\nSituacion: ...\\nAprendizaje: ...\\nAfecta a: ...\n"
        ),
        "Aprendizaje_desde_VPS.md": (
            "# Aprendizaje_desde_VPS.md\n\n"
            "Escribe la Ramon Ejecutiva (este VPS).\n"
            "Formato: [YYYY-MM-DD] - [CATEGORIA] - [VPS]\\nSituacion: ...\\nAprendizaje: ...\\nAfecta a: ...\n"
        ),
    }

    for name, contenido in plantilla.items():
        existing = drive_mod.find_child(folder, name)
        if not existing:
            drive_mod.upload_text(folder, name=name, text=contenido)
            creados[name] = True
        else:
            creados[name] = False
    return creados


def consolidar_mensual() -> dict:
    """Consolidacion del dia 1 de mes (protocolo 25.8).

    Estrategia simple MVP:
    1. Concatena las entradas de Chat y VPS bajo secciones separadas en el maestro.
    2. Limpia Chat y VPS dejando solo la cabecera plantilla.
    3. Devuelve resumen de lo consolidado.
    """
    ramon_md = drive_mod.leer_aprendizaje_ramon()
    chat_md = drive_mod.leer_aprendizaje_chat()
    vps_md = drive_mod.leer_aprendizaje_vps()

    hoy = _dt.date.today().isoformat()
    bloques = [ramon_md.strip() or "# Aprendizaje_Ramon.md"]
    bloques.append(f"\n\n## Consolidacion {hoy}\n")
    if chat_md.strip():
        bloques.append("\n### Desde Chat\n\n" + chat_md.strip())
    if vps_md.strip():
        bloques.append("\n### Desde VPS\n\n" + vps_md.strip())

    drive_mod.escribir_aprendizaje_ramon("\n".join(bloques))

    # Resetear Chat y VPS a plantilla minima.
    plantilla_vps = (
        "# Aprendizaje_desde_VPS.md\n\n"
        f"(Consolidado el {hoy}. Archivo reiniciado.)\n"
    )
    drive_mod.escribir_aprendizaje_vps(plantilla_vps)
    return {
        "consolidated_at": hoy,
        "chat_entries_bytes": len(chat_md),
        "vps_entries_bytes": len(vps_md),
    }
