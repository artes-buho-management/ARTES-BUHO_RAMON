"""Conexion a PostgreSQL con SQLAlchemy."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


_raw_url = os.getenv("DATABASE_URL", "")
# SQLAlchemy 2.x no acepta postgres://, necesita postgresql://
_url = _raw_url.replace("postgres://", "postgresql+psycopg2://", 1) if _raw_url else ""

engine = create_engine(_url, pool_pre_ping=True, pool_recycle=300) if _url else None
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False) if engine else None


class Base(DeclarativeBase):
    pass


def get_db():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL no configurada")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
