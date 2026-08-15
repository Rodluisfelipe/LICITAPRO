import factory

from core.models import Entidad, Usuario


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario

    username = factory.Sequence(lambda n: f"usuario{n}")
    email = factory.Sequence(lambda n: f"usuario{n}@licitapro.test")


class EntidadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entidad

    nombre = factory.Sequence(lambda n: f"Entidad de Prueba {n}")
    nit = factory.Sequence(lambda n: f"900{n:06d}-1")
    orden = Entidad.Orden.MUNICIPAL
    departamento = "Antioquia"
    municipio = "Medellín"
