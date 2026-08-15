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

## 2026-08-14 — Vista de detalle del proceso: statusbar, chatter, social

- Se implementó `social` (`Comentario`, `Actividad`, `Alerta`) tal cual el
  esquema de `_referencia_models.py`. `Comentario`/`Actividad` cuelgan de
  `Proceso`; `social` depende de `procesos`, nunca al revés.
- El statusbar de `/procesos/<id>/` **no** muestra todo `ETAPAS_PIPELINE`
  (el "camino feliz": detectado → en_evaluación → apto → en_preparación →
  presentado → adjudicado) como clicable — solo la transición que
  `proceso.get_available_estado_transitions()` permite ahora mismo. La FSM
  avanza de a un paso; ofrecer un clic directo a una etapa lejana induciría
  a pensar que existe un atajo que el modelo no tiene. Los estados de
  salida (`descartado`, `no_adjudicado`, `suspendido`) se muestran como
  botones laterales, no como parte del pipeline — `procesos.services.
  estado_disponible()` calcula ambos grupos.
- `descartar` sigue siendo la única transición que pide un dato adicional
  (`motivo`), así que es la única con un mini-formulario propio en el
  statusbar en vez de un botón simple.
- `fechas_verificadas_por/en` verifica el proceso completo con una sola
  acción (invariante 3), no campo por campo — aunque el botón "Marcar como
  verificado" aparece junto a `fecha_cierre` y junto a `presupuesto_oficial`
  por separado, ambos pegan al mismo endpoint y confirman lo mismo. Reflejar
  eso con dos pares de campos habría sido más preciso pero es un cambio de
  modelo que nadie pidió todavía.
- El chatter combina `Comentario` con `auditlog.LogEntry` en una sola
  timeline ordenada por fecha (`social.services.linea_de_tiempo`). Al ser
  `Proceso.id` un UUID, el filtro es por `object_pk` (texto), no
  `object_id` — mismo detalle que ya quedó anotado arriba para `LogEntry`.
- Las @menciones se resuelven por `username` exacto vía regex
  (`@([\w.]+)`), no por búsqueda difusa — evita mencionar a alguien por
  error. El autocompletado mientras se escribe usa **fetch directo**, no
  HTMX declarativo: necesita la posición del cursor dentro del textarea
  para saber qué token reemplazar, algo que `hx-vals` no expone con
  suficiente naturalidad. Sigue devolviendo HTML renderizado por el
  servidor, no JSON — no es una excepción a "no hay SPA", es una llamada
  puntual a un endpoint que también podría haberse pedido con HTMX.
- Pestañas "Documentos" y "Riesgos" del detalle quedan como placeholder
  ("aún no implementado"): esos modelos no existen todavía y no se pidieron
  en esta slice. Se optó por no fabricarlos solo para llenar la pestaña.

## 2026-08-14 — Transición `declarar_desierto` y `seed_demo`

- `Proceso.Estado.DESIERTO` existía en el choices desde el principio pero
  no tenía ningún `@transition` que lo alcanzara — un vacío del modelo
  original. Se agregó `declarar_desierto` (`PRESENTADO -> DESIERTO`),
  espejo exacto de `adjudicar`/`perder`, más su función en
  `procesos/services.py` y su entrada en `TRANSICIONES_VALIDAS`. No
  requirió migración (los `@transition` son métodos, no columnas). Se hizo
  porque generar datos demo respetando "nunca asignación directa de
  estado" era imposible sin esta transición.
- `core/management/commands/seed_demo.py` es idempotente por convención de
  nombres, no por un campo nuevo en el modelo: procesos con
  `numero_proceso` que empieza en `DEMO-`, usuarios con `username` que
  empieza en `demo_`, entidades por una lista fija de NITs. Un re-run
  borra por esos marcadores (procesos primero, cascada arrastra
  comentarios/actividades/alertas/versiones/requisitos; usuarios después;
  entidades al final) y nunca toca nada sin el marcador — así el
  superusuario real y cualquier dato capturado a mano quedan intactos
  siempre.
- El seed corre las transiciones de estado exclusivamente vía
  `procesos.services`, nunca `proceso.estado = "x"` — igual para
  `verificar_fechas` y `derogar_requisito`. Los únicos campos que el
  comando toca por asignación directa son los que no tienen invariante
  ni service (`responsable`, `fecha_adjudicacion`, y `cumplimiento` /
  `verificado_por` / `verificado_en` en `Requisito`, que el propio admin
  ya trata como editables — ver la nota de arriba sobre `readonly_fields`).
