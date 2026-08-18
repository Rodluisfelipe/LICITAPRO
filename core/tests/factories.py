import factory

from core.models import Entidad, Usuario


class UsuarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Usuario

    username = factory.Sequence(lambda n: f"usuario{n}")
    email = factory.Sequence(lambda n: f"usuario{n}@licitapro.test")


def usuario_comercial(**kwargs) -> Usuario:
    """Usuario de pruebas con el perfil Comercial ya asignado (el grupo lo
    crea la data migration `procesos.0006_perfiles_de_arranque`, que
    pytest-django aplica igual que cualquier migración real). Úsalo en
    tests de vistas que exigen permisos de negocio en vez de UsuarioFactory
    a secas."""
    from django.contrib.auth.models import Group

    usuario = UsuarioFactory(**kwargs)
    usuario.groups.add(Group.objects.get(name="Comercial"))
    return usuario


class EntidadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entidad

    nombre = factory.Sequence(lambda n: f"Entidad de Prueba {n}")
    nit = factory.Sequence(lambda n: f"900{n:06d}-1")
    orden = Entidad.Orden.MUNICIPAL
    departamento = "Antioquia"
    municipio = "Medellín"
