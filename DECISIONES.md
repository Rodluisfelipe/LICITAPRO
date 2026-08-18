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

## 2026-08-15 — Sistema visual v3: tokens propios, kanban como vista principal

- Se retiró Tailwind por CDN (`cdn.tailwindcss.com`) de todo el proyecto.
  Motivo real: ese dominio específico está bloqueado a nivel de DNS del
  ISP del usuario (`Query refused` al resolverlo contra su resolver, pero
  resuelve bien contra 1.1.1.1/8.8.8.8) — htmx y Alpine, servidos desde
  `unpkg.com`, nunca estuvieron rotos. En vez de depender de un CDN
  externo (frágil incluso para quien no tenga ese bloqueo puntual), se
  construyó un sistema de tokens propio y CSS a mano sobre esos tokens.
- No existía `referencia_ui_v3.html` como insumo — se pidió construirlo
  desde cero "en base al proyecto". Se ancló en el vocabulario de color ya
  establecido (`gris/azul/verde/amarillo/rojo`, el mismo que
  `Proceso.COLOR_POR_ESTADO`) y se añadió un canal `--ia` (violeta)
  exclusivo para contenido generado por el modelo — nunca botones, nunca
  estados. `static/css/tokens.css` es el `:root` extraído literal de ese
  archivo; `static/css/app.css` es el CSS de componentes construido
  encima. Ambos archivos son ahora la única fuente de valores de
  color/espaciado/radio/sombra/tipografía — nada literal en las plantillas.
- `Usuario` gana `tema`/`densidad`/`vista_preferida`. Se renderizan como
  atributos `data-*` en `<html>` desde el servidor (nunca vía JS al
  cargar) para que no haya parpadeo; los botones de la navbar cambian el
  atributo en el DOM al instante y persisten con `htmx.ajax` en segundo
  plano contra `core:actualizar_preferencias`, que no hace nada si
  `request.user` no está autenticado (no hay `login_required` todavía en
  el proyecto — gap preexistente, no introducido aquí).
- El **kanban es ahora la vista por defecto** de `/procesos/` (antes era
  la lista). `procesos.views.lista_procesos` es un dispatcher: decide
  kanban vs. lista por `?vista=` o por `Usuario.vista_preferida`, nunca
  hay dos URLs distintas. Columnas del tablero = solo el camino activo
  (`detectado…presentado`); `descartado/adjudicado/no_adjudicado` quedan
  fuera por defecto, accesibles con `?todos=1`.
- Faltaba una transición de FSM: `Proceso.Estado.DESIERTO` existía en el
  choices pero ningún `@transition` lo alcanzaba. Se agregó
  `declarar_desierto` (`PRESENTADO -> DESIERTO`), espejo de
  `adjudicar`/`perder`. Sin esto no había forma de sembrar/mover un
  proceso a ese estado sin asignación directa, que es exactamente lo que
  las transiciones vía service existen para evitar.
- Se implementó `procesos.models.Riesgo` (no existía; solo estaba en
  `_referencia_models.py`) porque el queryset anotado del tablero
  (`procesos.services.procesos_con_metricas`) necesita `proceso.riesgos`
  para el semáforo. Misma taxonomía cerrada que la referencia (invariante
  5). Sin UI de captura todavía — la pestaña "Riesgos" del detalle
  muestra lo que haya, vacío por ahora.
- `procesos_con_metricas()` resuelve tablero y lista con **una sola
  consulta anotada** (confirmado: 1 query para 40 procesos con
  `CaptureQueriesContext`, muy por debajo del presupuesto de 5). Un
  detalle importante que se corrigió del enunciado original: anotar
  `riesgo_max=Max("riesgos__severidad")` sobre un `CharField` ordena
  *alfabéticamente* ("media" > "alta" > "baja"), así que un proceso con
  un riesgo alto y uno medio habría reportado "media" como el peor. Se
  anota `riesgo_rango` con `Case/When` (alta=3, media=2, baja=1) y se
  traduce de vuelta con el filtro `rango_a_severidad` — mismo costo, sin
  el bug. Cubierto por test (`test_procesos_con_metricas_riesgo_rango_no_se_confunde_con_orden_alfabetico`).
- Bug real encontrado en QA visual (Playwright + captura): con
  `LANGUAGE_CODE = "es-co"`, Django renderiza floats con coma decimal
  (`42,86`), inválido en `width:…%` de CSS y en `stroke-dashoffset` de
  SVG. Los filtros `porcentaje`/`offset_anillo`/`a_porcentaje` en
  `core/templatetags/ui.py` devuelven strings formateados a mano
  (`f"{valor:.2f}"`, punto siempre) en vez de floats crudos — Django ya
  no tiene oportunidad de localizarlos.
- El drag&drop del kanban (SortableJS, única librería nueva agregada,
  autorizada explícitamente) nunca decide una transición del lado del
  cliente: cada tarjeta lleva un `data-transiciones` con el mapa
  `{estado_destino: nombre_transicion}` que ya calculó
  `procesos.services.transiciones_disponibles` en el servidor. Si el
  destino no está en ese mapa, la tarjeta vuelve a su columna sin
  siquiera pegarle al backend; si sí está, igual se confirma contra
  `procesos:mover_kanban` (puede haber cambiado de estado entre el
  render y el drop) y ese endpoint es la única fuente de verdad — nunca
  se inventa una transición en JS.
- Quedó pendiente (explícitamente, es la segunda mitad del pedido):
  estado "analizando" con polling HTMX dirigido, rehacer la vista lista
  con densidad de referencia + columna Ajuste, y la sección "Diseño" en
  CLAUDE.md con la regla del violeta.

## 2026-08-18 — Autenticación: Google Workspace, dominio en el adapter

- Primera entrega contractual, día 1. Hasta hoy no había **ninguna** vista
  protegida — se agregó `django.contrib.auth.middleware.LoginRequiredMiddleware`
  (nativo desde Django 5.1, no un paquete nuevo) en vez de decorar cada vista
  a mano: por defecto exige sesión en *todo*, y las únicas vistas públicas
  son las que allauth ya marca con `login_not_required` (login, logout,
  callback de Google) — exactamente el modelo "todo cerrado salvo
  excepción explícita" que pedía el contrato, sin tener que acordarse de
  decorar cada vista nueva que se agregue después.
- **La restricción de dominio va en `SocialAccountAdapterDominio.pre_social_login`
  (`core/adapters.py`), no solo en el parámetro `hd` de `AUTH_PARAMS`.**
  `hd` es una preferencia que Django le pasa a la pantalla de selección de
  cuenta de Google — es UX, no seguridad: un usuario puede editarlo a mano
  en la URL de autorización, o Google puede simplemente no respetarlo para
  cuentas personales. La única verificación que no se puede evadir desde
  el navegador es la que ocurre del lado del servidor, después de que
  Google ya devolvió el email real de la cuenta — por eso `pre_social_login`
  y no el parámetro de la URL. `hd` se deja igual, como atajo cosmético
  para que el selector de Google no muestre cuentas personales de entrada,
  pero el gate real es el del adapter.
- El mismo adapter resuelve un problema derivado: `crear_admins` pre-crea
  el `Usuario` de los dos administradores generales ANTES de su primer
  login (así el contrato "dos cuentas de administrador general" se cumple
  desde el día uno, no desde que alguien decide loguearse). Sin conectar
  esa cuenta pre-creada a su `SocialAccount` de Google, `SOCIALACCOUNT_AUTO_SIGNUP`
  habría creado un *segundo* Usuario duplicado en el primer login. `pre_social_login`
  busca por email antes de dejar que allauth cree nada, y si hay match usa
  `sociallogin.connect()` — y si ese usuario existente está `is_active=False`,
  lo rechaza ahí mismo (un admin desactivado no debería poder re-entrar
  solo porque su correo sigue siendo válido en Google).
- `ACCOUNT_ADAPTER` (signup por formulario) y `SOCIALACCOUNT_ADAPTER`
  (login social) son dos hooks *distintos* en allauth — desactivar el
  primero (`is_open_for_signup` → `False`) no toca el segundo. El alta
  automática por Google sigue funcionando exactamente igual;
  solo se cerró `/accounts/signup/`, el formulario de correo+contraseña.
- `templates/account/login.html` reemplaza la plantilla por defecto de
  allauth — sin ella, allauth muestra su propio formulario de login con
  usuario/contraseña visible aunque esté desactivado, lo cual confundiría
  al único camino de entrada real (el botón de Google).
- Pendiente cerrado del día 1: los rechazos del adapter (dominio ajeno,
  usuario desactivado) sí aterrizan en nuestra página de login con el
  mensaje visible, en claro y oscuro — confirmado con un test que
  reproduce el ciclo real (mismo request, misma sesión que sigue el
  cliente de pruebas) y con captura de pantalla. No hizo falta cambiar
  código: `messages.error()` + `ImmediateHttpResponse(redirect(...))` ya
  sobrevive el redirect porque `CookieStorage` (la primera de las dos
  storages de `FallbackStorage`) pone el mensaje en una cookie de la
  respuesta que sí vuelve al navegador.

## 2026-08-18 — Perfiles y permisos configurables desde la interfaz

- **`django.contrib.auth.Group`/`Permission`, no `django-guardian`.** Los
  permisos de esta entrega son por modelo y acción ("¿puede mover_etapa?"),
  nunca por objeto ("¿puede mover ESTE proceso puntual?"). `guardian` ya
  está instalado en el proyecto (se agregó pensando en un futuro "solo mis
  procesos" a nivel de fila), pero usarlo acá habría sido resolver con
  permisos por objeto un problema que es de rol — más superficie, cero
  beneficio real hoy. Si en el futuro hace falta permiso por objeto
  puntual, se decide esa vez; el alcance "ver todo el equipo vs. solo lo
  mío" ya quedó cubierto con un permiso de rol (`ver_todos`) más un filtro
  por `responsable`/`seguidores`, sin tocar guardian.
- El catálogo de permisos vive en `procesos/permisos.py` — una sola fuente
  de verdad de la que leen tanto los `Meta.permissions` de `Proceso` /
  `Entidad` / `Usuario` como la interfaz de `/configuracion/perfiles/`. Un
  administrador no técnico nunca ve un codename, solo la etiqueta en
  español del catálogo.
- `mover_etapa` y `descartar_procesos` son permisos DISTINTOS a propósito
  (así lo pide el catálogo del contrato). `procesos.permisos.
  permiso_requerido_para_transicion()` centraliza esa regla — "descartar"
  exige `descartar_procesos`, cualquier otra transición del flujo
  (incluida `suspender`, que no tiene permiso propio en el catálogo) exige
  `mover_etapa`. La usan tanto `transicionar_proceso` como `mover_kanban`
  (el drag&drop), así que el mapeo nunca se duplica ni se desincroniza
  entre el statusbar y el tablero.
- **`ver_todos` se filtra en `procesos.services.procesos_con_metricas()`,
  no en cada vista** — exactamente como pedía el enunciado. Eso significa
  que kanban, lista Y el detalle (que reutiliza el mismo queryset para el
  `get_object_or_404`) heredan el alcance de una sola vez. Sin
  `ver_todos`, un proceso ajeno da 404 en el detalle, no 403 — el ORM
  simplemente no lo encuentra en el queryset con alcance, así que no hay
  manera de que la vista "sepa" que existe para decidir entre 403 y 404.
- **Bug real encontrado corriendo los tests, no solo en teoría**: los
  `Permission` que declara `Meta.permissions` los crea el signal
  `post_migrate` de `django.contrib.auth`, que se dispara una sola vez al
  FINAL de todo el batch de `migrate` — no incrementalmente después de
  cada migración. La data migration `procesos.0006_perfiles_de_arranque`
  corre en el MISMO batch que la migración que declara esos permisos
  cuando se migra desde cero (base de datos de test de pytest, `make
  reset`, un deploy nuevo), así que `Permission.objects.filter(...)`
  dentro de ella no encontraba nada todavía y los tres grupos de arranque
  quedaban creados pero sin un solo permiso. Se corrigió llamando
  `django.contrib.auth.management.create_permissions` a mano dentro de la
  migración antes de consultar. Se detectó porque el test suite completo
  (que sí migra desde cero) fallaba con 403 en vistas que deberían
  funcionar — la base de datos de dev no lo mostró porque ahí las
  migraciones se habían aplicado en comandos `migrate` separados, dándole
  tiempo al signal de disparar entre una y otra por accidente.
- `PerfilInfo` (`configuracion/models.py`) es una tabla aparte 1:1 con
  `Group` — el contrato pide "nombre, descripción" por perfil pero `Group`
  no trae `descripcion` de fábrica y no se puede modificar directamente
  (es de `django.contrib.auth`). Es el patrón estándar de Django para
  extender un modelo de terceros sin tocarlo.
- Autoprotección: un administrador no puede desactivarse a sí mismo
  (`usuario_alternar_activo`) ni quitarse a sí mismo su única fuente de
  `gestionar_usuarios`, ya sea cambiando su propio perfil desde la lista
  de usuarios (`usuario_cambiar_perfil`) o quitándose a sí mismo de un
  grupo desde el detalle del perfil (`perfil_quitar_usuario`). Lo que NO
  se bloquea a propósito: editar la matriz de permisos de un grupo
  compartido de forma que indirectamente el propio admin pierda acceso —
  eso afecta a otros usuarios del mismo grupo, no es una acción
  "dirigida a uno mismo", y bloquearlo habría estorbado ediciones
  legítimas del perfil.
- El drag&drop respeta `mover_etapa` en dos capas: si el usuario no lo
  tiene, `kanban.js` ni siquiera inicializa SortableJS (las tarjetas no
  son arrastrables), y el endpoint `mover_kanban` lo vuelve a exigir del
  lado del servidor — un POST directo con curl sin el permiso da 403
  aunque nunca haya pasado por el navegador.

## 2026-08-18 — Creación manual de procesos (ítem 3, día 4 de la primera entrega)

- **Auditoría de las 9 transiciones del FSM contra la interfaz**: las nueve
  (`iniciar_evaluacion`, `descartar`, `marcar_apto`, `iniciar_preparacion`,
  `presentar`, `adjudicar`, `perder`, `declarar_desierto`, `suspender`) ya
  tenían un camino real desde el statusbar del detalle — el pipeline
  cubre las de avance, y `estado_ui.laterales` (calculado en
  `services.estado_disponible`) cubre TODAS las que no están en
  `ETAPAS_PIPELINE`, incluida `suspender` (que usa `source="*"` en el
  modelo, así que siempre aparece como lateral) y `declarar_desierto`. El
  kanban también llega a las nueve, pero las que aterrizan en un estado de
  salida (descartado/adjudicado/no_adjudicado/desierto) necesitan
  `?todos=1` para que la columna destino exista — diseño intencional, no
  un hueco: esos estados se tratan como desenlaces, no como una columna
  más del día a día.
- **Hueco real que sí se corrigió**: arrastrar una tarjeta a la columna
  "Descartado" no pedía motivo — `mover_kanban` lo rellenaba con un texto
  genérico. El statusbar sí exige el motivo (textarea `required`). Se
  corrigió en `kanban.js` con `window.prompt()` antes de llamar al
  endpoint: cancelar o dejarlo vacío revierte la tarjeta sin pegarle al
  servidor. No se construyó un modal Alpine para esto (ya existe uno en el
  statusbar para quien prefiera esa ruta) — un `prompt()` es la opción de
  menos código para un caso que ocurre poco.
- **Creación manual (`/procesos/nuevo/`)**: la entidad se resuelve con el
  mismo patrón de autocompletado seleccionable que las @menciones del
  chatter (un input de texto + un endpoint que devuelve botones clicables
  que rellenan un input oculto), no con el `<select>` gigante que ya usa
  el filtro de lista — con cientos de entidades un `<select>` no escala y
  ya existía el patrón de autocompletado en el proyecto. La opción "crear
  entidad nueva en línea" (gate `core.gestionar_entidades`) usa el
  `prefix` nativo de Django forms (`EntidadForm(prefix="nueva_entidad")`)
  para convivir con `ProcesoForm` en el mismo POST sin colisión de
  nombres — evita un segundo endpoint AJAX solo para crear la entidad. Si
  la entidad nueva no valida, se hace rollback de la transacción completa
  (no queda una `Entidad` huérfana si el `Proceso` después falla).
  `origen=Origen.MANUAL` se fija explícitamente en la vista aunque ya sea
  el default del modelo — la invariante 4 pide que el campo nunca se
  omita, no que se confíe en un default silencioso.
- **Facetas de filtro removibles**: los filtros de lista (estado, entidad,
  modalidad, responsable, rango de cierre, texto) ya eran combinables por
  `django_filters` — lo que faltaba era hacerlos *visibles* como chips
  independientes. Se calculan en `_facetas_activas` (vista, no template)
  porque construir "la querystring actual sin esta clave" es más claro en
  Python que en DTL. Viven dentro del fragmento que HTMX intercambia
  (`tabla-procesos-wrapper`) para que aparecer/desaparecer sea parte del
  mismo swap que ya disparan los filtros.
- **Estados vacíos**: se distingue "no hay procesos todavía" (banner con
  CTA "Crear el primero", gateado por `crear_procesos`) de "hay procesos
  pero ningún filtro los encuentra" (mensaje + botón "Limpiar filtros") —
  antes ambos casos mostraban el mismo texto genérico. La distinción se
  calcula con una segunda consulta `.exists()` sin filtrar
  (`hay_procesos_sin_filtrar` / `tablero_vacio`), aceptable porque es una
  sola query barata comparada con el resto de la vista.
