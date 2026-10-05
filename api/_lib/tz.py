"""Hora de España.

Vercel corre en UTC: con datetime.now() a las 00:30 en Madrid el servidor aún
cree que es ayer, y las horas de los gráficos salen dos horas corridas.
Todo lo que dependa de «hoy» o de la hora local pasa por aquí.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")


def ahora():
    """Hora local de Madrid, sin tzinfo (como devolvía datetime.now())."""
    return datetime.now(MADRID).replace(tzinfo=None)


def hoy():
    return ahora().date()
