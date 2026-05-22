"""Gmail Router para booking@artesbuhomanagement.com.

Componente integrado en Ramon. Vive en el VPS.

Que hace:
1. Escanea INBOX sin procesar (sin etiquetas RAMON_*).
2. Clasifica cada hilo en una de 4 categorias:
   - 00_RESPONDE        (humano real entrante - REQUIERE ACCION)
   - 01_AUTORESPUESTAS  (respuestas automaticas - ignorar)
   - 02_REBOTES         (error de entrega - ignorar)
   - 03_OTROS           (notificaciones, marketing, etc)
3. Si categoria es 00_RESPONDE, crea un BORRADOR de reenvio en Gmail
   (To: contratacion@artesbuho.com + booking@artesbuho.com;
    BCC: rubencoton1993@gmail.com). El usuario lo revisa y envia manual.
   NO se envia nada automaticamente - solo queda listo en Drafts.
4. Aplica etiqueta + archiva de INBOX (mantiene limpia la bandeja).

Clasificacion: usa el cerebro de Ramon con tier TRIVIAL (ahorra tokens).
"""
from __future__ import annotations

import base64
import logging
import re
from email.mime.text import MIMEText
from typing import Any

from app.google_client import gmail as _gmail_service
from app.integrations import brain_router

log = logging.getLogger("ramon.gmail_router")

# ----- Config -----
LABELS = {
    "responde":      "00_RESPONDE",
    "autorespuestas": "01_AUTORESPUESTAS",
    "rebotes":       "02_REBOTES",
    "otros":         "03_OTROS",
    "procesado":     "RAMON_PROCESADO",
}
FORWARD_TO = ["contratacion@artesbuho.com", "booking@artesbuho.com"]
FORWARD_BCC = ["rubencoton1993@gmail.com"]

# ----- Helpers Gmail -----

def _ensure_label(name: str) -> str:
    """Devuelve label_id de 'name'. Crea si no existe."""
    gm = _gmail_service()
    labels = gm.users().labels().list(userId='me').execute().get('labels', [])
    for l in labels:
        if l['name'] == name:
            return l['id']
    created = gm.users().labels().create(
        userId='me',
        body={"name": name, "labelListVisibility": "labelShow",
              "messageListVisibility": "show"},
    ).execute()
    log.info(f"Label creada: {name} id={created['id']}")
    return created['id']


def _ensure_all_labels() -> dict[str, str]:
    return {k: _ensure_label(v) for k, v in LABELS.items()}


def _list_unprocessed(max_threads: int = 20) -> list[dict]:
    """Lista threads de INBOX sin procesar por Ramon."""
    gm = _gmail_service()
    q = f"in:inbox -label:{LABELS['procesado']}"
    resp = gm.users().threads().list(
        userId='me', q=q, maxResults=max_threads
    ).execute()
    return resp.get('threads', [])


def _get_thread(thread_id: str) -> dict:
    gm = _gmail_service()
    return gm.users().threads().get(userId='me', id=thread_id, format='metadata',
                                    metadataHeaders=['From','To','Subject','Date',
                                                     'Auto-Submitted','X-Auto-Response-Suppress',
                                                     'Precedence','Return-Path']).execute()


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h['name'].lower() == name.lower():
            return h['value']
    return ""


# ----- Clasificacion heuristica + IA -----

def _heuristic_category(thread: dict) -> tuple[str, str]:
    """Heuristica rapida. Devuelve (category_key, motivo)."""
    msgs = thread.get('messages', [])
    if not msgs:
        return "otros", "thread sin mensajes"
    last = msgs[-1]
    headers = last.get('payload', {}).get('headers', [])
    subject = _header(headers, 'Subject')
    sender = _header(headers, 'From').lower()
    auto_submitted = _header(headers, 'Auto-Submitted').lower()
    auto_response = _header(headers, 'X-Auto-Response-Suppress')
    precedence = _header(headers, 'Precedence').lower()
    return_path = _header(headers, 'Return-Path').lower()

    # Rebotes
    if ('mailer-daemon' in sender or 'postmaster' in sender or
        'delivery status' in subject.lower() or
        'undeliverable' in subject.lower() or
        'failure notice' in subject.lower() or
        '<>' == return_path):
        return "rebotes", "header/from rebote"

    # Autorespuestas
    if (auto_submitted and auto_submitted != 'no' or
        auto_response or
        precedence in ('auto_reply', 'bulk', 'list') or
        'out of office' in subject.lower() or
        'fuera de la oficina' in subject.lower() or
        'auto-reply' in subject.lower() or
        'automatic reply' in subject.lower() or
        'respuesta automatica' in subject.lower()):
        return "autorespuestas", "auto-submitted header"

    # Notificaciones obvias -> otros
    noise_domains = ['noreply@', 'no-reply@', 'notifications@',
                     'newsletter@', 'mailchimp', 'sendgrid', 'mailgun']
    if any(d in sender for d in noise_domains):
        return "otros", "dominio de notificacion"

    return "", ""  # sin heuristica clara


_AI_SYSTEM = (
    "Clasificas emails de la bandeja de entrada de ARTES BUHO Management. "
    "Devuelve SOLO JSON valido sin markdown. "
    "Categorias validas: RESPONDE (humano real que necesita respuesta), "
    "AUTORESPUESTAS (respuesta automatica), REBOTES (error entrega), "
    "OTROS (notificaciones, marketing, newsletters). "
    'Formato: {"categoria":"RESPONDE|AUTORESPUESTAS|REBOTES|OTROS","motivo":"texto corto"}'
)


def _ai_classify(thread: dict) -> tuple[str, str]:
    msgs = thread.get('messages', [])
    if not msgs:
        return "otros", "sin mensajes"
    last = msgs[-1]
    headers = last.get('payload', {}).get('headers', [])
    prompt = (f"De: {_header(headers, 'From')}\n"
              f"Asunto: {_header(headers, 'Subject')}\n"
              f"Snippet: {(last.get('snippet') or '')[:300]}")
    try:
        data, _ = brain_router.classify_json(_AI_SYSTEM, prompt, max_tokens=120)
        cat = str(data.get('categoria', 'OTROS')).upper().strip()
        motivo = str(data.get('motivo', ''))[:80]
    except Exception as exc:
        log.warning(f"ai_classify fallo: {exc}")
        return "otros", "fallback IA"
    mapping = {
        "RESPONDE": "responde",
        "AUTORESPUESTAS": "autorespuestas",
        "REBOTES": "rebotes",
        "OTROS": "otros",
    }
    return mapping.get(cat, "otros"), motivo or "ia"


def _classify_thread(thread: dict) -> tuple[str, str, str]:
    """Devuelve (category_key, source, motivo). source=heuristic|ai."""
    cat, motivo = _heuristic_category(thread)
    if cat:
        return cat, "heuristic", motivo
    cat, motivo = _ai_classify(thread)
    return cat, "ai", motivo


# ----- Forward -----

def _create_forward_draft(thread_id: str) -> bool:
    """Crea BORRADOR de reenvio en Gmail. NO envia nada.

    El borrador queda en Drafts listo para que el usuario lo revise y envie
    manualmente. To/Bcc pre-rellenados a FORWARD_TO + FORWARD_BCC.
    """
    gm = _gmail_service()
    thread = gm.users().threads().get(userId='me', id=thread_id, format='full').execute()
    msgs = thread.get('messages', [])
    if not msgs:
        return False
    last = msgs[-1]
    headers = last.get('payload', {}).get('headers', [])
    subject = _header(headers, 'Subject')
    from_ = _header(headers, 'From')
    date_h = _header(headers, 'Date')

    # Cuerpo
    body_parts = _extract_body(last.get('payload', {}))
    body_text = body_parts.get('text') or last.get('snippet', '')

    fwd_subject = subject if subject.lower().startswith('fwd:') else f"Fwd: {subject}"
    fwd_body = (f"---------- Mensaje reenviado ----------\n"
                f"De: {from_}\n"
                f"Fecha: {date_h}\n"
                f"Asunto: {subject}\n\n"
                f"{body_text}")

    mime = MIMEText(fwd_body, "plain", "utf-8")
    mime['To'] = ", ".join(FORWARD_TO)
    mime['Bcc'] = ", ".join(FORWARD_BCC)
    mime['Subject'] = fwd_subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    try:
        # drafts().create en vez de messages().send -> queda en Drafts, NO envia
        gm.users().drafts().create(
            userId='me',
            body={
                "message": {
                    "raw": raw,
                    "threadId": thread_id,  # lo enlaza al hilo original
                }
            },
        ).execute()
        log.info(f"Borrador creado para thread={thread_id}")
        return True
    except Exception as exc:
        log.error(f"crear borrador fallo thread={thread_id}: {exc}")
        return False


def _extract_body(payload: dict) -> dict:
    """Recorre payload multipart y extrae texto."""
    text = ""
    if payload.get('body', {}).get('data'):
        try:
            text = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
        except Exception:
            pass
    for part in payload.get('parts', []) or []:
        if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
            try:
                text += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
            except Exception:
                pass
        elif part.get('parts'):
            nested = _extract_body(part)
            text += nested.get('text', '')
    return {"text": text[:5000]}


# ----- Ciclo -----

def process_cycle(max_threads: int = 20) -> dict[str, Any]:
    """Procesa N threads no procesados. Devuelve stats."""
    labels_map = _ensure_all_labels()
    threads_raw = _list_unprocessed(max_threads=max_threads)
    gm = _gmail_service()

    stats = {"processed": 0, "drafts_created": 0, "categories": {}, "errors": 0}
    actions: list[dict] = []

    for t_ref in threads_raw:
        tid = t_ref['id']
        try:
            thread = gm.users().threads().get(userId='me', id=tid, format='metadata',
                metadataHeaders=['From','Subject','Auto-Submitted','X-Auto-Response-Suppress',
                                 'Precedence','Return-Path']).execute()
            cat, source, motivo = _classify_thread(thread)
            label_key = cat
            label_id = labels_map.get(label_key)
            if not label_id:
                label_id = labels_map['otros']

            # Si RESPONDE -> crea BORRADOR (no envia). Usuario lo manda manual.
            draft_created = False
            if label_key == "responde":
                draft_created = _create_forward_draft(tid)
                if draft_created:
                    stats['drafts_created'] = stats.get('drafts_created', 0) + 1

            # Aplicar etiqueta + PROCESADO + quitar INBOX
            add_labels = [label_id, labels_map['procesado']]
            remove_labels = ['INBOX']
            gm.users().threads().modify(
                userId='me', id=tid,
                body={"addLabelIds": add_labels, "removeLabelIds": remove_labels},
            ).execute()

            stats['categories'][label_key] = stats['categories'].get(label_key, 0) + 1
            stats['processed'] += 1
            actions.append({
                "thread_id": tid, "category": label_key, "source": source,
                "motivo": motivo, "draft_created": draft_created,
            })
        except Exception as exc:
            log.warning(f"Error procesando thread {tid}: {exc}")
            stats['errors'] += 1

    return {"stats": stats, "actions": actions[-30:]}
