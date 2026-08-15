import pytest

from core.tests.factories import EntidadFactory


@pytest.mark.django_db
def test_nombre_normalizado_se_genera_al_guardar():
    entidad = EntidadFactory(nombre="Alcaldía de Medellín")

    assert entidad.nombre_normalizado == "alcaldia de medellin"


@pytest.mark.django_db
def test_nombre_normalizado_se_actualiza_si_cambia_el_nombre():
    entidad = EntidadFactory(nombre="Gobernación de Antioquia")

    entidad.nombre = "Alcaldía de Bogotá D.C."
    entidad.save()

    assert entidad.nombre_normalizado == "alcaldia de bogota d.c."
