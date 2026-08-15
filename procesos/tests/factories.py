import factory

from core.tests.factories import EntidadFactory
from procesos.models import Proceso, Requisito, VersionDocumental


class ProcesoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Proceso

    numero_proceso = factory.Sequence(lambda n: f"PROC-{n:04d}")
    entidad = factory.SubFactory(EntidadFactory)
    objeto = factory.Sequence(lambda n: f"Objeto del proceso {n}")
    modalidad = Proceso.Modalidad.LICITACION


class VersionDocumentalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VersionDocumental

    proceso = factory.SubFactory(ProcesoFactory)
    tipo = VersionDocumental.Tipo.DEFINITIVO
    secuencia = factory.Sequence(lambda n: n)


class RequisitoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Requisito

    proceso = factory.SelfAttribute("version_origen.proceso")
    version_origen = factory.SubFactory(VersionDocumentalFactory)
    tipo = Requisito.Tipo.JURIDICO
    numeral = factory.Sequence(lambda n: f"3.{n}")
    descripcion = factory.Sequence(lambda n: f"Requisito de prueba {n}")
