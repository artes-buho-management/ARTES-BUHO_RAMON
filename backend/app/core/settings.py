"""Configuracion centralizada de Ramon."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    # Entorno
    env: str = os.getenv("RAMON_ENV", "production")

    # URLs
    ui_url: str = os.getenv("UI_URL", "https://ramon.artesbuhomanagement.com")
    api_url: str = os.getenv("API_URL", "https://api.ramon.artesbuhomanagement.com")

    # Google (reutiliza hub ARTES-BUHO_API-GOOGLE)
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_refresh_token: str = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    gmail_user: str = os.getenv("GMAIL_USER", "booking@artesbuhomanagement.com")
    gmail_personal: str = os.getenv("GMAIL_PERSONAL", "booking@artesbuhomanagement.com")
    google_calendar_id: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    # IDs de recursos de Ramon (desde Protocolo v3.0)
    drive_folder_ramon: str = os.getenv("DRIVE_FOLDER_RAMON", "1EtY1MuTXOmoeDNHVMYraC3fFfhznX2UU")
    crm_sheet_id: str = os.getenv("CRM_SHEET_ID", "REPLACE_WITH_SHEET_ID")

    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # DB
    database_url: str = os.getenv("DATABASE_URL", "")

    # Modo de operacion
    draft_only: bool = os.getenv("RAMON_DRAFT_ONLY", "true").lower() in {"1", "true", "yes"}
    # En modo draft_only Ramon NUNCA envia respuestas auto, solo crea borradores.
    # Se activa la primera semana para que Ruben revise.

    # Zona horaria operativa (Coslada, Madrid)
    timezone: str = os.getenv("TIMEZONE", "Europe/Madrid")

    # Horario arranque
    morning_hour: int = int(os.getenv("MORNING_HOUR", "8"))
    morning_minute: int = int(os.getenv("MORNING_MINUTE", "0"))
    report_hour: int = int(os.getenv("REPORT_HOUR", "8"))
    report_minute: int = int(os.getenv("REPORT_MINUTE", "15"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
