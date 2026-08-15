import pytest

from core.services import buscar_entidades
from core.tests.factories import EntidadFactory


@pytest.mark.django_db
def test_buscar_entidades_encuentra_por_similitud():
    chia = EntidadFactory(nombre="Alcaldía Municipal de Chía")
    EntidadFactory(nombre="Gobernación de Cundinamarca")
    EntidadFactory(nombre="Alcaldía de Bogotá D.C.")

    resultados = list(buscar_entidades("alcaldia chia"))

    assert chia in resultados
