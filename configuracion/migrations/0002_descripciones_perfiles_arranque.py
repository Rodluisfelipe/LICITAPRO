from django.db import migrations

DESCRIPCIONES = {
    "Administrador": "Acceso total: procesos, entidades, importación y administración del sistema.",
    "Comercial": "Gestiona procesos y entidades del día a día: crea, edita, mueve etapas, importa.",
    "Consulta": "Solo puede ver procesos, sin crear ni editar nada.",
}


def sembrar_descripciones(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    PerfilInfo = apps.get_model("configuracion", "PerfilInfo")

    for nombre, descripcion in DESCRIPCIONES.items():
        try:
            grupo = Group.objects.get(name=nombre)
        except Group.DoesNotExist:
            continue
        PerfilInfo.objects.get_or_create(grupo=grupo, defaults={"descripcion": descripcion})


def eliminar_descripciones(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0001_initial"),
        ("procesos", "0006_perfiles_de_arranque"),
    ]

    operations = [
        migrations.RunPython(sembrar_descripciones, eliminar_descripciones),
    ]
