"""Sistema de firmas HTML de Ramon (Protocolo v4.0 seccion 24).

Estructura REAL de la firma de ARTES BUHO (extraida de booking@artesbuhomanagement.com):
- Tabla de 2 columnas con separador vertical gris (#b7b7b7)
- Columna izquierda: logo ARTES BUHO 121x65 px
- Columna derecha: nombre + rol + email + telefono + iconos RRSS
- Tipografia: Roboto (fallback Arial)
- Links: #1155cc

Tres variantes:
- Firma A "Ramon" → uso habitual (Ramon / Asistente Ejecutivo / ARTES BUHO Management)
- Firma B "ARTES BUHO" → VIPs y negociaciones (Ruben Jimenez Gonzalez / ARTES BUHO Management)
- Firma After You → texto plano sin logo (protocolo 16.1)
"""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path


LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "LOGO_ARTES_BUHO.png"
LOGO_WIDTH = 100
LOGO_HEIGHT = 54

RAMON_AVATAR_PATH = Path(__file__).resolve().parent.parent / "assets" / "ramon_avatar.png"
AVATAR_SIZE = 80

# Colores corporativos ARTES BUHO: ROJO, AMARILLO, BLANCO
COLOR_BRAND = "#D02E2B"   # rojo ARTES BUHO (match del logo)
COLOR_ACCENT = "#F4C430"  # amarillo ARTES BUHO (borde del logo)
COLOR_TEXT = "#000000"
COLOR_LINK = COLOR_BRAND
COLOR_SEP = COLOR_BRAND
COLOR_BG = "#ffffff"
FONT = "Roboto, Arial, sans-serif"


@lru_cache(maxsize=1)
def _logo_base64() -> str:
    """Lee el logo y lo devuelve en base64 optimizado para email."""
    if not LOGO_PATH.exists():
        return ""
    raw = LOGO_PATH.read_bytes()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        # Redimensionar manteniendo ratio a ~121x65
        img.thumbnail((LOGO_WIDTH * 2, LOGO_HEIGHT * 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        raw = buf.getvalue()
    except ImportError:
        pass
    except Exception:
        pass
    return base64.b64encode(raw).decode("ascii")


def _logo_img_tag() -> str:
    b64 = _logo_base64()
    if not b64:
        return ""
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'alt="ARTES BUHO" '
        f'width="{LOGO_WIDTH}" height="{LOGO_HEIGHT}" '
        f'style="display:block;border:0;outline:none;text-decoration:none;" />'
    )


@lru_cache(maxsize=1)
def _avatar_ramon_base64() -> str:
    """Avatar circular de Ramón (foto IA)."""
    if not RAMON_AVATAR_PATH.exists():
        return ""
    raw = RAMON_AVATAR_PATH.read_bytes()
    try:
        from PIL import Image, ImageDraw
        import io as _io
        img = Image.open(_io.BytesIO(raw)).convert("RGBA")
        # Crop cuadrado
        short = min(img.size)
        left = (img.width - short) // 2
        top = (img.height - short) // 2
        img = img.crop((left, top, left + short, top + short))
        img = img.resize((AVATAR_SIZE * 2, AVATAR_SIZE * 2), Image.LANCZOS)
        # Mascara circular
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, *img.size), fill=255)
        out = Image.new("RGBA", img.size, (255, 255, 255, 0))
        out.paste(img, (0, 0), mask)
        out = out.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        buf = _io.BytesIO()
        out.save(buf, format="PNG", optimize=True)
        raw = buf.getvalue()
    except ImportError:
        pass
    except Exception:
        pass
    return base64.b64encode(raw).decode("ascii")


def _avatar_ramon_img_tag() -> str:
    b64 = _avatar_ramon_base64()
    if not b64:
        return ""
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'alt="Ramón" width="{AVATAR_SIZE}" height="{AVATAR_SIZE}" '
        f'style="display:block;border:0;outline:none;border-radius:50%;" />'
    )


# Icono RRSS generico en SVG base64 (32x32 circular). Mantenemos texto legible.
_RRSS = [
    ("Instagram", "https://www.instagram.com/artesbuho/"),
    ("TikTok", "https://www.tiktok.com/@artesbuho"),
    ("YouTube", "https://www.youtube.com/@artesbuho"),
    ("Facebook", "https://www.facebook.com/artesbuhoOficial/"),
    ("X", "https://x.com/artesbuho"),
    ("Threads", "https://www.threads.com/@artesbuho"),
    ("Pinterest", "https://es.pinterest.com/artesbuho/"),
]


def _rrss_inline() -> str:
    """Barra horizontal de enlaces RRSS."""
    parts = [
        f'<a href="{url}" target="_blank" style="color:{COLOR_LINK};text-decoration:none;font-family:{FONT};font-size:10pt;">{name}</a>'
        for name, url in _RRSS
    ]
    sep = f' <span style="color:{COLOR_SEP};">·</span> '
    return sep.join(parts)


def _firma_table(
    *,
    nombre_grande: str,
    nombre_pequeno: str,
    email: str = "booking@artesbuhomanagement.com",
    telefono: str | None = "(+34) 613 00 93 36",
    web: str = "www.artesbuho.com",
) -> str:
    """Renderiza la tabla 2 columnas al estilo de la firma original de Ruben.

    telefono=None → se omite la fila del telefono (p.ej. firma de Ramón:
    no tiene telefono, es una asistente digital).
    """
    logo = _logo_img_tag()
    telefono_html = (
        f'<div style="font-size:11pt;line-height:1.55;color:{COLOR_TEXT};">Telf: {telefono}</div>'
        if telefono else ""
    )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;font-family:{FONT};color:{COLOR_TEXT};">'
        '<tr>'
        # Columna izquierda: logo con borde derecho naranja
        f'<td width="140" valign="top" '
        f'style="padding:6pt 14pt 6pt 6pt;border-right:2px solid {COLOR_SEP};">'
        f'{logo}'
        '</td>'
        # Columna derecha: datos de contacto
        f'<td valign="top" style="padding:6pt 6pt 6pt 14pt;">'
        # Nombre grande
        f'<div style="font-size:14pt;font-weight:700;line-height:1.25;color:{COLOR_TEXT};">{nombre_grande}</div>'
        # Rol
        f'<div style="font-size:11pt;line-height:1.35;color:{COLOR_TEXT};">{nombre_pequeno}</div>'
        # Email
        f'<div style="font-size:11pt;line-height:1.55;color:{COLOR_TEXT};margin-top:4pt;">'
        f'<a href="mailto:{email}" style="color:{COLOR_LINK};text-decoration:none;">{email}</a>'
        '</div>'
        # Web
        f'<div style="font-size:11pt;line-height:1.55;">'
        f'<a href="https://{web}" target="_blank" style="color:{COLOR_LINK};text-decoration:none;">{web}</a>'
        '</div>'
        # Telefono (opcional)
        f'{telefono_html}'
        # RRSS
        f'<div style="margin-top:6pt;font-size:10pt;line-height:1.4;">'
        f'{_rrss_inline()}'
        '</div>'
        '</td>'
        '</tr>'
        '</table>'
    )


def _signature_ramon() -> str:
    """Firma Ramón: avatar circular + logo + datos en orden piramidal (web → email → RRSS)."""
    avatar = _avatar_ramon_img_tag()
    logo = _logo_img_tag()
    col_izq = (
        f'{avatar}'
        f'<div style="margin-top:10px;">{logo}</div>' if logo else f'{avatar}'
    )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;font-family:{FONT};color:{COLOR_TEXT};">'
        '<tr>'
        f'<td width="110" valign="top" '
        f'style="padding:6pt 14pt 6pt 6pt;border-right:2px solid {COLOR_SEP};">'
        f'{col_izq}'
        '</td>'
        f'<td valign="top" style="padding:6pt 6pt 6pt 14pt;">'
        # Nombre
        f'<div style="font-size:14pt;font-weight:700;line-height:1.25;color:{COLOR_TEXT};">Ramón</div>'
        # Rol completo en una línea
        f'<div style="font-size:11pt;line-height:1.35;color:{COLOR_TEXT};">Asistente Ejecutivo de <strong>ARTES B\u00daHO</strong></div>'
        f'<div style="font-size:11pt;line-height:1.35;color:{COLOR_TEXT};font-style:italic;">Management de artistas</div>'
        # Orden piramidal: WEB → EMAIL → RRSS
        f'<div style="margin-top:8pt;font-size:11pt;line-height:1.55;">'
        f'<a href="https://www.artesbuho.com" target="_blank" style="color:{COLOR_LINK};text-decoration:none;font-weight:600;">www.artesbuho.com</a>'
        '</div>'
        f'<div style="font-size:11pt;line-height:1.55;color:{COLOR_TEXT};">'
        f'<a href="mailto:booking@artesbuhomanagement.com" style="color:{COLOR_LINK};text-decoration:none;">booking@artesbuhomanagement.com</a>'
        '</div>'
        f'<div style="margin-top:6pt;font-size:10pt;line-height:1.4;">'
        f'{_rrss_inline()}'
        '</div>'
        '</td>'
        '</tr>'
        '</table>'
    )


def _signature_ruben() -> str:
    """Firma B — ARTES BUHO (uso manual de Ruben desde su Gmail).

    Incluye logo + datos piramidal (web → email → teléfono → RRSS).
    """
    logo = _logo_img_tag()
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;font-family:{FONT};color:{COLOR_TEXT};">'
        '<tr>'
        f'<td width="140" valign="top" '
        f'style="padding:6pt 14pt 6pt 6pt;border-right:2px solid {COLOR_SEP};">'
        f'{logo}'
        '</td>'
        f'<td valign="top" style="padding:6pt 6pt 6pt 14pt;">'
        f'<div style="font-size:15pt;font-weight:700;line-height:1.25;letter-spacing:0.5px;color:{COLOR_TEXT};">ARTES BUHO</div>'
        f'<div style="font-size:11pt;line-height:1.35;color:{COLOR_TEXT};font-style:italic;">DJ profesional</div>'
        # Piramidal: WEB → EMAIL → TELEFONO → RRSS
        f'<div style="margin-top:8pt;font-size:11pt;line-height:1.55;">'
        f'<a href="https://www.artesbuho.com" target="_blank" style="color:{COLOR_LINK};text-decoration:none;font-weight:600;">www.artesbuho.com</a>'
        '</div>'
        f'<div style="font-size:11pt;line-height:1.55;color:{COLOR_TEXT};">'
        f'<a href="mailto:booking@artesbuhomanagement.com" style="color:{COLOR_LINK};text-decoration:none;">booking@artesbuhomanagement.com</a>'
        '</div>'
        f'<div style="font-size:11pt;line-height:1.55;color:{COLOR_TEXT};">Tel: (+34) 613 00 93 36</div>'
        f'<div style="margin-top:6pt;font-size:10pt;line-height:1.4;">'
        f'{_rrss_inline()}'
        '</div>'
        '</td>'
        '</tr>'
        '</table>'
    )


def _signature_after_you() -> str:
    """Firma especial After You: solo texto plano (protocolo 16.1)."""
    return (
        f'<div style="font-family:{FONT};font-size:11pt;color:{COLOR_TEXT};">'
        "Un abrazo fuerte,<br>"
        "<strong>ARTES BUHO</strong>"
        "</div>"
    )


def _body_to_html(body_text: str) -> str:
    """Convierte texto plano a HTML preservando saltos de linea."""
    import html as _html
    escaped = _html.escape(body_text.strip())
    paragraphs = escaped.split("\n\n")
    return "".join(f"<p style=\"margin:0 0 12px 0;line-height:1.5;\">{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)


def _base_wrapper(body_html: str, signature_html: str) -> str:
    """Envuelve cuerpo + firma en HTML email-safe."""
    return (
        f'<div style="font-family:{FONT};font-size:11pt;color:{COLOR_TEXT};line-height:1.5;">'
        f"{body_html}"
        '<br>'
        f"{signature_html}"
        '</div>'
    )


def render_email(*, body_text: str, signature: str = "ramon", closing: str = "Un abrazo,") -> str:
    """Renderiza el email completo en HTML con firma.

    Args:
        body_text: cuerpo limpio en texto plano (sin firma, sin cierre)
        signature: "ramon" | "ruben" | "after_you"
        closing: texto de cierre ("Un abrazo," / "Un abrazo fuerte," / "Mil gracias,")
    """
    sig = signature.lower().strip()
    if sig == "after_you":
        # En After You el cierre y la firma van integrados.
        body_html = _body_to_html(body_text)
        return _base_wrapper(body_html, _signature_after_you())

    closing_html = f'<p style="margin:0 0 12px 0;">{closing}</p>' if closing else ""
    body_html = _body_to_html(body_text) + closing_html
    sig_html = _signature_ruben() if sig == "ruben" else _signature_ramon()
    return _base_wrapper(body_html, sig_html)


def select_signature(*, categoria: str, account: str, firma_sugerida: str | None = None) -> str:
    """Ramón es una persona distinta de ARTES BUHO.

    Todo correo que Ramón redacta va firmado por Ramón.
    Las firmas "ruben" y "after_you" quedan como opciones manuales para
    cuando RUBEN pida expresamente firmar él desde su cuenta.
    """
    return "ramon"


def get_preview(signature: str = "ramon") -> str:
    """Renderiza una preview HTML completa para inspeccion manual."""
    html = render_email(
        body_text=(
            "Hola equipo, ¿qué tal?\n\n"
            "Esto es una previsualización de la firma de Ramón.\n\n"
            "Cualquier cosa me decís."
        ),
        signature=signature,
    )
    return f'<!DOCTYPE html><html><body style="background:#f5f5f5;padding:20px;">{html}</body></html>'


def install_in_gmail(account: str, signature: str = "ramon") -> dict:
    """Instala la firma indicada en la cuenta Gmail via API sendAs.

    Actualiza la firma del sendAs que coincide con `account`.
    """
    from app.google_client import gmail
    svc = gmail()
    sig_html = _signature_ramon() if signature == "ramon" else (
        _signature_ruben() if signature == "ruben" else _signature_after_you()
    )
    return svc.users().settings().sendAs().update(
        userId="me",
        sendAsEmail=account,
        body={"signature": sig_html},
    ).execute()
