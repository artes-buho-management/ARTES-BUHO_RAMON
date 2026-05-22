"""Revisa la carpeta Spam de Gmail, reclasifica con Gemini y mueve a RAMON/BASURA lo que Ramon confirme como spam.

Flujo:
1. Lista mensajes en label SPAM.
2. Para cada uno, Ramon analiza (remitente + asunto + snippet).
3. Si confirma spam: aplica RAMON/BASURA y quita SPAM/INBOX (queda archivado en BASURA).
4. Si NO es spam: aplica etiqueta ESTADO/REVISION (Ruben lo valida).
5. Al final, Telegram con resumen.

Ramon no envia a papelera permanente: eso lo decide Ruben con /basura/purgar.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.settings import get_settings
from app.integrations import gmail as gmail_mod
from app.integrations.gemini_brain import _call_gemini, GeminiBrainError, QuotaExceeded
from app.integrations.telegram_bot import send_message


log = logging.getLogger("ramon.spam")


_PROMPT = """Eres Ramon. Analiza este correo de la carpeta SPAM de ARTES BUHO.
Decide si es spam real o un falso positivo (correo legitimo que Gmail marco por error).

Criterios de spam real:
- Publicidad masiva sin opt-in
- Phishing / suplantacion
- Estafas, loterias, inversiones dudosas
- Remitentes aleatorios
- Idiomas raros sin contexto con DJ/booking

Criterios de falso positivo:
- Promotores, salas, agencias de booking
- Clientes o leads de bodas/eventos
- Gestorias, bancos, proveedores profesionales
- Mencion explicita a ARTES BUHO, DJ, bolos, eventos
- Respuestas a emails que Ruben envio

Devuelve SOLO JSON: {"es_spam": true|false, "confianza": 0-100, "razon": "<80 chars"}
"""


def revisar(max_msgs: int = 30) -> dict[str, Any]:
    account = get_settings().gmail_user
    try:
        msgs = gmail_mod.list_messages(account, query="in:spam", max_results=max_msgs)
    except Exception as exc:
        return {"error": str(exc)}

    procesados = 0
    a_basura = 0
    falsos_positivos = 0
    errores: list[str] = []

    for m in msgs:
        try:
            info = gmail_mod.get_message(account, m["id"])
            contexto = (
                f"DE: {info.get('from','')}\n"
                f"ASUNTO: {info.get('subject','')}\n"
                f"SNIPPET: {info.get('snippet','')[:400]}\n"
                f"BODY: {(info.get('body_text') or '')[:600]}"
            )
            raw = _call_gemini(_PROMPT, contexto, response_json=True, max_tokens=200, is_email_call=True)
            try:
                r = json.loads(raw)
            except json.JSONDecodeError:
                s, e = raw.find("{"), raw.rfind("}")
                r = json.loads(raw[s:e + 1]) if s >= 0 else {}
            if not r:
                errores.append(f"{m['id']}: parse")
                continue

            if r.get("es_spam"):
                gmail_mod.apply_labels(account, m["id"], add=["RAMON/BASURA"])
                # Sacar de SPAM
                gmail_mod._service(account).users().messages().modify(  # type: ignore[attr-defined]
                    userId="me", id=m["id"],
                    body={"removeLabelIds": ["SPAM"]},
                ).execute()
                a_basura += 1
            else:
                gmail_mod.apply_labels(account, m["id"], add=["ESTADO/REVISION"])
                # Mover a inbox para que Ruben lo vea
                gmail_mod._service(account).users().messages().modify(  # type: ignore[attr-defined]
                    userId="me", id=m["id"],
                    body={"addLabelIds": ["INBOX"], "removeLabelIds": ["SPAM"]},
                ).execute()
                falsos_positivos += 1
            procesados += 1
        except QuotaExceeded as exc:
            errores.append(f"quota: {exc}")
            break
        except Exception as exc:
            errores.append(f"{m['id']}: {exc}")

    resumen = {
        "procesados": procesados,
        "a_basura": a_basura,
        "falsos_positivos": falsos_positivos,
        "errores": errores[-5:],
    }

    if procesados:
        try:
            send_message(
                f"<b>📬 Revisión Spam</b>\n"
                f"• Analizados: {procesados}\n"
                f"• A Basura: {a_basura}\n"
                f"• Falsos positivos rescatados: {falsos_positivos}",
                urgent=False,
            )
        except Exception:
            pass

    return resumen
