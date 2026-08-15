# Decisiones de arquitectura

## 2026-08-13 — Capa de settings

- `config/settings.py` se dividió en `config/settings/{base,dev,prod}.py`.
  `DJANGO_SETTINGS_MODULE` apunta siempre a `dev` o `prod` explícitamente
  (nunca al paquete `config.settings` a secas). `manage.py`, `wsgi.py` y
  `asgi.py` por defecto usan `config.settings.dev`; en prod se sobreescribe
  la variable de entorno al desplegar.
- Se agregaron `sentry-sdk` y `whitenoise` a las dependencias (no estaban en
  `pyproject.toml`) para cubrir observabilidad y estáticos en prod.
- Storage en prod usa `storages.backends.s3boto3.S3Boto3Storage` apuntando a
  R2 vía `AWS_S3_ENDPOINT_URL`. Estáticos en prod: WhiteNoise con
  `CompressedManifestStaticFilesStorage`. En dev, disco local.
- Login con Google restringido al dominio de Workspace vía el parámetro
  `hd` en `SOCIALACCOUNT_PROVIDERS["google"]["AUTH_PARAMS"]`, usando
  `GOOGLE_WORKSPACE_DOMAIN` de `.env`.
- `AUTH_USER_MODEL = "core.Usuario"` queda seteado aunque el modelo no
  existe todavía — `manage.py check` falla ahí a propósito hasta que se
  cree el modelo.
- Se quitó `--nomigrations` de `addopts` en `pyproject.toml`: pytest-django
  corre las migraciones reales contra `test_licitaciones`, así las
  extensiones de Postgres (`vector`, `pg_trgm`, `unaccent`) quedan creadas
  antes de que se creen las tablas con `VectorField`/índices GIN trgm.
  Costo aceptado: la suite corre más lento que con `--nomigrations`.
- `[tool.ruff]` usa `extend-exclude` en vez de `exclude` — `exclude` a secas
  reemplaza las exclusiones por defecto de ruff (que incluyen `.venv`) en
  vez de sumarse a ellas.

## 2026-08-14 — Proceso: máquina de estados y auditoría

- `Proceso.estado` es un `FSMField(protected=True)` (`django-fsm-2`). Las
  vistas nunca llaman a los métodos de transición directamente: siempre
  pasan por una función de `procesos/services.py` (`iniciar_evaluacion`,
  `descartar`, `marcar_apto`, ...), una por transición, que ejecuta el
  método, guarda y sale.
- Cada función de `services.py` envuelve el `save()` en
  `auditlog.context.set_actor(usuario)`. Es necesario porque
  `AuditlogMiddleware` solo fija el actor cuando el cambio ocurre dentro
  del ciclo request/response; los services se seguirán llamando desde
  Celery y comandos de management donde no hay request, así que el actor
  se pasa explícito como parámetro de cada función.
- Nota para pruebas: `FSMField(protected=True)` rompe
  `instance.refresh_from_db()` (su descriptor bloquea el `setattr` interno
  que usa `refresh_from_db`). Para releer un `Proceso` en un test hay que
  pedir una instancia nueva (`Proceso.objects.get(pk=...)`), no refrescar
  la existente.
- `auditlog.models.LogEntry` guarda la PK del objeto en `object_pk` (texto)
  cuando el modelo no usa PK entera — no en `object_id`
  (`BigIntegerField`). Como `Proceso.id` es UUID, cualquier consulta a
  `LogEntry` para un `Proceso` debe filtrar por `object_pk`.

## 2026-08-14 — VersionDocumental y Requisito: inmutabilidad y reconstrucción histórica

- `Requisito` nunca se edita tras publicarse (invariante 1 de CLAUDE.md). Una
  adenda pasa por `procesos.services.derogar_requisito`, que crea un
  `Requisito` nuevo con `reemplaza` (OneToOneField a `self`) apuntando al
  viejo. `reemplazado_por` es el related_name inverso; `proceso.
  requisitos_vigentes` filtra `reemplazado_por__isnull=True`.
- `VersionDocumental.secuencia` es la única fuente de orden temporal (0 =
  documento inicial). `procesos.services.crear_version` la calcula sola con
  `Max("secuencia") + 1` — nunca se asigna a mano.
- `requisitos_vigentes_en(proceso, version)` recibe una instancia de
  `VersionDocumental`, no un entero: reconstruye el estado del pliego a esa
  versión filtrando `version_origen__secuencia__lte` y excluyendo los que un
  requisito con `version_origen__secuencia__lte` ese mismo límite ya derogó.
  Se eligió instancia sobre entero suelto para no depender de qué signifique
  "versión 1" en lenguaje natural — la ambigüedad entre "primera versión
  creada" y "secuencia == 1" es real porque `secuencia` arranca en 0.
- Los `readonly_fields` del inline de `Requisito` en `VersionDocumentalAdmin`
  cubren `descripcion` y `valor_umbral` — son los dos campos que un
  invariante prohíbe tocar tras publicarse. El resto de campos operativos
  (`cumplimiento`, `origen`, etc.) sí se pueden editar desde ahí porque no
  reescriben lo que decía el pliego.
