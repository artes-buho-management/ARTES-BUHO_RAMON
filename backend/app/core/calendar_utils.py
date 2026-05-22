"""Utilidades de calendario laboral para Coslada, Madrid.

Festivos considerados:
- Nacionales de Espana
- Autonomicos de Madrid
- Locales de Coslada: San Isidro (15 mayo), Virgen del Amor Hermoso (septiembre)
"""
from __future__ import annotations

from datetime import date, datetime

import holidays
import pytz

from app.core.settings import get_settings


# Festivos locales de Coslada que no siempre estan en la libreria holidays.
_COSLADA_LOCAL = [
    # Mes, dia. La fecha exacta puede variar; se mantiene lista simple.
    (5, 15),   # San Isidro
    (9, 8),    # Virgen del Amor Hermoso (aproximado, el usuario puede ajustar)
]


def _es_holidays():
    return holidays.country_holidays("ES", subdiv="MD", years=[datetime.now().year, datetime.now().year + 1])


def is_holiday(d: date | None = None) -> bool:
    """Devuelve True si d (o hoy) es festivo en Coslada/Madrid/Espana."""
    d = d or date.today()
    es = _es_holidays()
    if d in es:
        return True
    for m, day in _COSLADA_LOCAL:
        if d.month == m and d.day == day:
            return True
    return False


def is_workday(d: date | None = None) -> bool:
    """Dia laborable: lunes-viernes y no festivo."""
    d = d or date.today()
    if d.weekday() >= 5:  # sabado o domingo
        return False
    return not is_holiday(d)


def now_local() -> datetime:
    tz = pytz.timezone(get_settings().timezone)
    return datetime.now(tz)


def today_local() -> date:
    return now_local().date()
