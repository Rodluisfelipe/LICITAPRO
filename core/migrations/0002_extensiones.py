from django.db import migrations

# run_before (no dependencies) a propósito: 0001_initial crea
# CodigoUNSPSC.embedding (VectorField) y el índice GIN trgm de Entidad, así
# que las extensiones deben existir antes de que corra. Si en vez de
# run_before hiciéramos que 0001 dependiera de esta migración, 0001 dejaría
# de ser la raíz ("__first__") del app core, y swappable_dependency(
# AUTH_USER_MODEL) —usado por allauth, guardian, etc.— resolvería a esta
# migración en lugar de a la que realmente crea Usuario.

EXTENSIONES_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
"""

CONFIGURACION_BUSQUEDA_SQL = """
CREATE TEXT SEARCH CONFIGURATION es_unaccent ( COPY = spanish );

ALTER TEXT SEARCH CONFIGURATION es_unaccent
    ALTER MAPPING FOR hword, hword_part, word
    WITH unaccent, spanish_stem;
"""

CONFIGURACION_BUSQUEDA_REVERSE_SQL = """
DROP TEXT SEARCH CONFIGURATION IF EXISTS es_unaccent;
"""


class Migration(migrations.Migration):

    dependencies = []

    run_before = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=EXTENSIONES_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=CONFIGURACION_BUSQUEDA_SQL,
            reverse_sql=CONFIGURACION_BUSQUEDA_REVERSE_SQL,
        ),
    ]
