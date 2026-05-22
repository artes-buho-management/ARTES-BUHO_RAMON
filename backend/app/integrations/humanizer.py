"""Humanizador de correos: detecta y corrige sonido de IA.

Antes de enviar un borrador, Ramón lo pasa por un filtro que:
1. Detecta palabras y patrones típicos de IA.
2. Si algo suena robotizado, reescribe el borrador en modo "persona real".
3. Devuelve el cuerpo humanizado.

Además provee ask_ruben() para cuando Ramón tiene dudas y necesita consultar
al humano antes de enviar algo sensible.
"""
from __future__ import annotations

import re
from typing import Any


# Frases/palabras típicas de IA que suelen disparar rechazo en clientes.
_PATRONES_IA = [
    r"\bpor supuesto\b", r"\bestimad[oa]\b", r"\bestoy a su disposición\b",
    r"\bpermítame\b", r"\bes un placer ayudarle\b", r"\bno dude en\b",
    r"\ba su\s+servicio\b", r"\bcomo asistente (virtual|de ia|ia)\b",
    r"\bsoy (una |un )?(?:ia|inteligencia artificial|bot)\b",
    r"\bpor favor,\s+si necesita",
    r"[📧📞📅📍📎✅❌⚠️🚨🎉🔥💰🎧📊🏆💯🟢🟡🔴🟠🟣⬛🗓️📆🔔🔵🟩🟥]",
]


def detectar_tufillo_ia(texto: str) -> list[str]:
    """Devuelve lista de patrones IA encontrados."""
    encontrados = []
    t = texto.lower()
    for p in _PATRONES_IA:
        if re.search(p, t, flags=re.IGNORECASE):
            encontrados.append(p)
    # Emojis Unicode
    if re.search(r"[\U0001F300-\U0001FAFF]", texto):
        encontrados.append("emoji")
    return encontrados


def humanizar(borrador: str, destinatario_tipo: str = "profesional") -> str:
    """Intenta humanizar el borrador:
    - Elimina emojis
    - Sustituye patrones IA comunes
    - Mantiene estructura general
    """
    t = borrador
    # Quitar emojis
    t = re.sub(r"[\U0001F300-\U0001FAFF]", "", t)
    t = re.sub(r"[✅❌⚠️🚨🎉🔥💰🎧📊🏆💯🟢🟡🔴🟠🟣⬛🗓️📆🔔🔵🟩🟥📧📞📅📍📎]", "", t)
    # Reemplazos típicos
    replacements = [
        (r"\bPor supuesto,?\s*", "Claro, "),
        (r"\bEstimado", "Hola"),
        (r"\bEstimada", "Hola"),
        (r"Estoy a su disposición", "Cualquier cosa me decís"),
        (r"No dude en contactar(me|nos)", "Me decís si necesitáis algo"),
        (r"Es un placer ayudarle", "Encantada"),
        (r"a su servicio", "a vuestra disposición"),
        (r"Permítame", "Deja que"),
    ]
    for pat, rep in replacements:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)
    # Dobles espacios producidos
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def revisar_borrador_con_ia(system_prompt: str, borrador: str) -> str:
    """Segunda pasada: pide a la IA que relea y devuelva una versión mas humana
    si detecta que suena a robot.
    """
    from app.integrations.brain_router import generate
    critic = (
        "Actúa como corrector de estilo. Voy a pasarte un correo redactado por Ramón, "
        "asistente de ARTES BUHO. Tu tarea: si detectas tono de IA (frases tipo "
        "'Estimado', 'Por supuesto', 'Estoy a su disposición', 'No dude en contactar', "
        "emojis, listas con emojis, exceso de cortesía artificial), reescríbelo como "
        "lo haría una persona real: frases cortas, naturales, sin emojis, directo. "
        "Mantén el contenido, solo cambia el tono. Si ya suena humano, devuélvelo tal cual. "
        "Devuelve SOLO el borrador corregido, sin comentarios."
    )
    out, _ = generate(critic, borrador, json_mode=False, max_tokens=2000)
    return out.strip() or borrador


def ask_ruben(pregunta: str, contexto: str = "") -> None:
    """Envía una pregunta a Ruben por Telegram cuando Ramón necesita clarificar.

    El mensaje queda en cola si es fuera de horario laboral.
    """
    from app.integrations.telegram_bot import send_message
    txt = (
        "<b>❓ Ramón pregunta</b>\n\n"
        f"{pregunta}"
    )
    if contexto:
        txt += f"\n\n<i>Contexto:</i> {contexto[:500]}"
    try:
        send_message(txt)
    except Exception:
        pass
