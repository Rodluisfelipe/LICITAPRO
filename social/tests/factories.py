import factory
from django.utils import timezone

from core.tests.factories import UsuarioFactory
from procesos.tests.factories import ProcesoFactory
from social.models import Actividad, Comentario


class ComentarioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Comentario

    proceso = factory.SubFactory(ProcesoFactory)
    autor = factory.SubFactory(UsuarioFactory)
    cuerpo = factory.Sequence(lambda n: f"Comentario de prueba {n}")


class ActividadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Actividad

    proceso = factory.SubFactory(ProcesoFactory)
    asignado_a = factory.SubFactory(UsuarioFactory)
    titulo = factory.Sequence(lambda n: f"Actividad de prueba {n}")
    vence_en = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=3))
