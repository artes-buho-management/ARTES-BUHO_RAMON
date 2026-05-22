"""Operaciones Gmail para Ramon.

Soporta las 2 cuentas via refresh tokens independientes:
- booking@artesbuhomanagement.com  →  GOOGLE_REFRESH_TOKEN (principal, comparte hub)
- booking@artesbuhomanagement.com     →  GOOGLE_REFRESH_TOKEN_PERSONAL (pendiente OAuth)

Si la cuenta personal aun no tiene token, las operaciones sobre ella
lanzan GoogleAuthError controlada (no rompen el flujo del scheduler).
"""
from __future__ import annotations

import base64
import os
import re
from email.message import EmailMessage
from functools import lru_cache
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.google_client import GoogleAuthError, SCOPES
from app.core.settings import get_settings


# --- Credenciales por cuenta ---

def _creds_for(account: str) -> Credentials:
    """Devuelve credenciales para la cuenta indicada."""
    settings = get_settings()
    if account == settings.gmail_user:
        refresh = settings.google_refresh_token
    elif account == settings.gmail_personal:
        refresh = os.getenv("GOOGLE_REFRESH_TOKEN_PERSONAL", "")
    else:
        raise GoogleAuthError(f"Cuenta no soportada: {account}")
    if not refresh:
        raise GoogleAuthError(f"Falta refresh_token para {account}")
    return Credentials(
        token=None,
        refresh_token=refresh,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


@lru_cache(maxsize=4)
def _service(account: str):
    return build("gmail", "v1", credentials=_creds_for(account), cache_discovery=False)


# --- Labels ---

@lru_cache(maxsize=8)
def _labels_map(account: str) -> dict[str, str]:
    """Mapa nombre -> id de etiquetas. Cacheado para evitar reconsultar."""
    resp = _service(account).users().labels().list(userId="me").execute()
    return {lbl["name"]: lbl["id"] for lbl in resp.get("labels", [])}


def ensure_label(account: str, name: str) -> str:
    """Devuelve el id de una etiqueta, creandola si no existe."""
    mp = _labels_map(account)
    if name in mp:
        return mp[name]
    body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created = _service(account).users().labels().create(userId="me", body=body).execute()
    _labels_map.cache_clear()
    return created["id"]


def apply_labels(account: str, msg_id: str, add: list[str] | None = None, remove: list[str] | None = None) -> dict:
    """Aplica/quita etiquetas por NOMBRE (resuelve a id internamente)."""
    add_ids = [ensure_label(account, n) for n in (add or [])]
    remove_ids = [ensure_label(account, n) for n in (remove or [])]
    body = {"addLabelIds": add_ids, "removeLabelIds": remove_ids}
    return _service(account).users().messages().modify(userId="me", id=msg_id, body=body).execute()


def archive(account: str, msg_id: str) -> dict:
    """Archivar = quitar INBOX."""
    return _service(account).users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["INBOX"]}
    ).execute()


def mark_as_read(account: str, msg_id: str) -> dict:
    return _service(account).users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def mover_a_basura(account: str, msg_id: str) -> dict:
    """Papelera controlada de Ramon: etiqueta RAMON/BASURA + sale de INBOX.

    No es TRASH de Gmail (que se borra a los 30 dias). Es una etiqueta propia
    para que RUBEN pueda revisar y purgar manualmente si lo ve bien.
    """
    bid = ensure_label(account, "RAMON/BASURA")
    return _service(account).users().messages().modify(
        userId="me", id=msg_id,
        body={"addLabelIds": [bid], "removeLabelIds": ["INBOX"]},
    ).execute()


def purgar_basura(account: str, dry_run: bool = True) -> dict:
    """Envia a TRASH real todos los mensajes con etiqueta RAMON/BASURA.

    dry_run=True por defecto. Solo cuenta. Con dry_run=False los manda a Papelera.
    """
    mp = _labels_map(account)
    if "RAMON/BASURA" not in mp:
        return {"purged": 0, "reason": "sin etiqueta"}
    bid = mp["RAMON/BASURA"]
    resp = _service(account).users().messages().list(
        userId="me", labelIds=[bid], maxResults=500,
    ).execute()
    msgs = resp.get("messages", [])
    if dry_run:
        return {"would_purge": len(msgs), "dry_run": True}
    purged = 0
    svc = _service(account)
    for m in msgs:
        try:
            svc.users().messages().trash(userId="me", id=m["id"]).execute()
            purged += 1
        except Exception:
            pass
    return {"purged": purged, "dry_run": False}


# --- Lectura ---

def list_messages(account: str, query: str = "in:inbox is:unread", max_results: int = 50) -> list[dict]:
    """Lista IDs de mensajes que cumplen el query Gmail."""
    resp = _service(account).users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return resp.get("messages", [])


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    pad = 4 - (len(data) % 4)
    if pad and pad < 4:
        data += "=" * pad
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body(payload: dict) -> tuple[str, str]:
    """Extrae (text_plain, text_html) del payload Gmail."""
    plain, html = "", ""
    if not payload:
        return plain, html
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data", "")
    if mime == "text/plain" and data:
        plain = _decode_b64url(data)
    elif mime == "text/html" and data:
        html = _decode_b64url(data)
    for part in payload.get("parts", []) or []:
        p, h = _extract_body(part)
        plain = plain or p
        html = html or h
    return plain, html


def _headers_dict(headers: list[dict]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in headers or []}


def get_message(account: str, msg_id: str) -> dict[str, Any]:
    """Devuelve el mensaje normalizado: headers, body_text, body_html, etc."""
    msg = _service(account).users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = _headers_dict(msg.get("payload", {}).get("headers", []))
    plain, html = _extract_body(msg.get("payload", {}))
    if not plain and html:
        plain = _strip_html(html)
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "label_ids": msg.get("labelIds", []),
        "snippet": msg.get("snippet", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "message_id": headers.get("message-id", ""),
        "in_reply_to": headers.get("in-reply-to", ""),
        "references": headers.get("references", ""),
        "body_text": plain,
        "body_html": html,
        "internal_date": msg.get("internalDate"),
        "size_estimate": msg.get("sizeEstimate"),
    }


_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _HTML_TAG.sub("", html).strip()


def extract_email_address(from_header: str) -> str:
    """Extrae 'foo@bar.com' de 'Nombre <foo@bar.com>' o similar."""
    m = re.search(r"[\w\.\-+%]+@[\w\.\-]+\.\w+", from_header or "")
    return m.group(0).lower() if m else ""


# --- Escritura: borradores y envios ---

def _build_mime(
    *,
    to: str,
    subject: str,
    body_html: str,
    from_addr: str,
    in_reply_to: str = "",
    references: str = "",
    cc: str = "",
    attachments: list[dict] | None = None,
) -> dict[str, str]:
    """Construye MIME.

    attachments: lista de dicts con
      - path: ruta local del archivo (se lee bytes), o
      - data: bytes ya cargados
      - filename: nombre visible
      - mime: mimetype (default application/octet-stream)
    """
    import mimetypes
    from pathlib import Path

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = from_addr
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(body_html, subtype="html")

    for att in attachments or []:
        data: bytes
        if "data" in att and att["data"] is not None:
            data = att["data"]
        elif "path" in att and att["path"]:
            data = Path(att["path"]).read_bytes()
        else:
            continue
        filename = att.get("filename") or (Path(att["path"]).name if att.get("path") else "adjunto")
        mime = att.get("mime") or (mimetypes.guess_type(filename)[0] or "application/octet-stream")
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def create_draft(
    account: str,
    *,
    to: str,
    subject: str,
    body_html: str,
    thread_id: str | None = None,
    in_reply_to: str = "",
    references: str = "",
    cc: str = "",
    attachments: list[dict] | None = None,
) -> dict[str, Any]:
    """Crea un borrador en Gmail. Lo deja listo para que RUBEN lo revise y envie."""
    mime = _build_mime(
        to=to, subject=subject, body_html=body_html,
        from_addr=account, in_reply_to=in_reply_to, references=references, cc=cc,
        attachments=attachments,
    )
    body: dict[str, Any] = {"message": mime}
    if thread_id:
        body["message"]["threadId"] = thread_id
    return _service(account).users().drafts().create(userId="me", body=body).execute()


def send_message(
    account: str,
    *,
    to: str,
    subject: str,
    body_html: str,
    thread_id: str | None = None,
    in_reply_to: str = "",
    references: str = "",
    cc: str = "",
    attachments: list[dict] | None = None,
) -> dict[str, Any]:
    """FUSE DE SEGURIDAD: siempre crea BORRADOR en vez de enviar.

    Regla Ruben: Ramon nunca envia emails automaticamente. Solo deja borradores
    listos para que el usuario los revise y envie manualmente desde Gmail.
    Esto es INMUTABLE - no depende de env vars ni de flags.

    Tambien cuando esta activo el modo entrenamiento (training_mode), se fuerza
    borrador extra-seguro.
    """
    mime = _build_mime(
        to=to, subject=subject, body_html=body_html,
        from_addr=account, in_reply_to=in_reply_to, references=references, cc=cc,
        attachments=attachments,
    )
    body: dict[str, Any] = {"message": dict(mime)}
    if thread_id:
        body["message"]["threadId"] = thread_id
    # SIEMPRE drafts().create -- NUNCA messages().send
    draft = _service(account).users().drafts().create(userId="me", body=body).execute()
    return {
        "forced_to_draft": True,
        "reason": "regla_ruben_no_envios_automaticos",
        "draft_id": draft.get("id"),
        "message_id": draft.get("message", {}).get("id"),
    }


def list_threads(account: str, query: str, max_results: int = 50) -> list[dict]:
    resp = _service(account).users().threads().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    return resp.get("threads", [])


def get_thread(account: str, thread_id: str) -> dict[str, Any]:
    return _service(account).users().threads().get(userId="me", id=thread_id, format="metadata").execute()


# --- Helpers de alto nivel ---

def safe_list_unread(account: str, max_results: int = 50) -> list[dict]:
    """Lista mensajes no leidos tolerando cuentas sin token configurado."""
    try:
        return list_messages(account, "in:inbox is:unread", max_results=max_results)
    except GoogleAuthError:
        return []
    except HttpError:
        return []
