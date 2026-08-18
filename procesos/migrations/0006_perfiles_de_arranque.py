from django.apps import apps as apps_reales
from django.contrib.auth.management import create_permissions
from django.db import migrations

from procesos.permisos import crear_perfiles_de_arranque


def crear_grupos(apps, schema_editor):
    # Los Permission de los Meta.permissions declarados en 0005 (y en la
    # migración de core) normalmente los crea el signal post_migrate — pero
    # ese signal solo se dispara al FINAL de todo el batch de `migrate`,
    # no incrementalmente entre migraciones. Como esta migración corre en
    # el MISMO batch cuando se migra desde cero (make reset, la base de
    # datos de test de pytest, un deploy nuevo...), sin esto
    # Permission.objects.filter(...) dentro de crear_perfiles_de_arranque()
    # no encontraría nada todavía y los tres grupos quedarían sin permisos.
    for app_label in ("procesos", "core"):
        create_permissions(apps_reales.get_app_config(app_label), apps=apps_reales, verbosity=0)
    crear_perfiles_de_arranque()


def eliminar_grupos(apps, schema_editor):
    # No-op a propósito: revertir esta migración no debe borrar grupos que
    # un administrador ya haya usado o editado desde la interfaz.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("procesos", "0005_alter_proceso_options"),
        ("core", "0003_alter_entidad_options_alter_usuario_options"),
    ]

    operations = [
        migrations.RunPython(crear_grupos, eliminar_grupos),
    ]
