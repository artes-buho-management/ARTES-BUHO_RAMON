"""Modelos SQLAlchemy para el operativo interno de Ramon.

IMPORTANTE: la "libreta viva" que ve Ruben esta en Drive.
Esto es solo operativo interno (queue, cache, logs, aprendizaje rapido).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailProcessed(Base):
    """Registro de cada email procesado por Ramon."""
    __tablename__ = "emails_processed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gmail_id = Column(String(64), nullable=False, unique=True, index=True)
    account = Column(String(64), nullable=False, index=True)  # manager / artesbuho
    thread_id = Column(String(64), nullable=True, index=True)
    sender = Column(String(256), nullable=True)
    subject = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)
    urgency = Column(String(16), nullable=True)
    decision_level = Column(String(16), nullable=True)  # verde/amarillo/rojo
    action_taken = Column(String(64), nullable=True)  # draft/auto_reply/archive/escalate
    claude_response = Column(JSON, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow, index=True)


class Decision(Base):
    """Registro de decisiones (para Decisiones_Ramon.xlsx)."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level = Column(String(16), nullable=False)  # verde/amarillo/rojo
    topic = Column(Text, nullable=False)
    proposal = Column(Text, nullable=True)
    final_decision = Column(Text, nullable=True)
    outcome = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class TelegramMessage(Base):
    """Historial Telegram bidireccional."""
    __tablename__ = "telegram_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction = Column(String(8), nullable=False)  # in / out
    chat_id = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SystemLog(Base):
    """Log de eventos del sistema."""
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level = Column(String(16), nullable=False)  # info/warn/error
    source = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
