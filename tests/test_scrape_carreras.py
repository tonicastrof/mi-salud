import sys
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("bs4")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "carreras"))
import scrape  # noqa: E402

CARRERA = date(2026, 11, 22)


@pytest.mark.parametrize("txt,esperado", [
    ("Inscricións\nata o 18/11/2026 ás 23:59\nSaída: 11:00", date(2026, 11, 18)),
    ("Prazo de inscrición: do 1 de outubro ao 19 de novembro", date(2026, 11, 19)),
    ("Data peche inscricións 20/11", date(2026, 11, 20)),
    ("Inscrición: 10€ hasta el 15-11-26", date(2026, 11, 15)),
    ("Recollida de dorsais o 22/11 presentando a inscrición", None),
    ("Inscricións abertas", None),
    ("Inscricións ata o 30/11/2026", None),       # despois da carreira: non vale
])
def test_plazo_inscripcion(txt, esperado):
    assert scrape.plazo_inscripcion(txt, CARRERA) == esperado


def test_plazo_sin_anio_de_una_carrera_de_enero():
    assert scrape.plazo_inscripcion("Inscricións ata o 28/12", date(2027, 1, 6)) == date(2026, 12, 28)


def test_consultas_al_mapa():
    assert scrape._consultas("Ordes - Oroso", "Galicia")[:2] == ["Ordes - Oroso, Galicia, España", "Ordes, Galicia, España"]
    assert scrape._consultas("Llanes", "Asturias") == ["Llanes, Asturias, España"]
    assert scrape._consultas("", "Galicia") == []
