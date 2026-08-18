# LicitaPro

Sistema web interno para gestionar el ciclo completo de licitaciones públicas
(Colombia / SECOP II) desde el lado del **proponente**. Reemplaza un Excel.
~15 usuarios internos, un solo desarrollador.

Las convenciones y reglas de dominio no-negociables viven en
[`CLAUDE.md`](CLAUDE.md). El historial de decisiones de arquitectura, con el
porqué de cada una, vive en [`DECISIONES.md`](DECISIONES.md). Este archivo es
la puerta de entrada: qué es esto, cómo se levanta, y qué hay construido hoy.

---

## Estado actual — Primera entrega (base de la plataforma, 10 días)

| Día | Ítem | Estado |
| --- | --- | --- |
| 1 | Autenticación (Google Workspace, dominio restringido) | ✅ |
| 2-3 | Perfiles y permisos configurables desde la interfaz | ✅ |
| 4 | Procesos: creación manual, listado, filtros, flujo de etapas | ✅ |
| 5-8 | Importador de Excel | ⏸️ bloqueado en insumos de `_legado/` (fuera del repo) |
| 9 | Datos reales + prueba con usuarios | pendiente |
| 10 | Despliegue | pendiente |

Ver [Pendiente / conocido](#pendiente--conocido) para el detalle fino dentro
de cada ítem ya cerrado.

---

## Stack

Python 3.12 · Django 5.2 · PostgreSQL 16 (`pgvector`, `pg_trgm`, `unaccent`) ·
HTMX + Alpine.js · CSS propio sobre tokens (sin Tailwind) · Celery + Redis ·
`uv` para dependencias, `ruff` para lint/formato, `pytest-django` para tests.

---

## Puesta en marcha

```bash
cp .env.example .env        # completar credenciales locales
make up                     # levanta postgres + redis (docker compose)
uv run python manage.py migrate
uv run python manage.py crear_admins tucorreo@tuempresa.com otro@tuempresa.com
uv run python manage.py seed_demo   # opcional: datos demo realistas, ver abajo
make dev                    # runserver en http://127.0.0.1:8000/
```

El acceso es **solo con Google** (ver [Autenticación](#autenticación) abajo)
— no hay `createsuperuser` con contraseña local, por eso el paso de
`crear_admins`. Necesitas un cliente OAuth de Google Cloud Console
(`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` en `.env`) y `GOOGLE_WORKSPACE_DOMAIN`
apuntando al dominio real de correo de la empresa.

Ver [Comandos](#comandos) para el resto del ciclo de desarrollo.

---

## Qué hay construido

### Procesos — el núcleo

- **`/procesos/`** conmuta entre dos vistas con un control segmentado,
  recordando la última usada por usuario:
  - **Kanban** (vista principal por defecto): columnas por estado del FSM
    (Detectado → En evaluación → Apto → En preparación → Presentado),
    cabecera pegajosa con contador/presupuesto/distribución de urgencia por
    columna, **drag & drop** (SortableJS) que dispara la transición de
    estado correspondiente — si no es válida, la tarjeta vuelve a su lugar
    y se avisa. Adjudicado / No adjudicado / Descartado quedan fuera por
    defecto (`?todos=1` los muestra).
  - **Lista**: filtros (estado, entidad, modalidad, responsable, rango de
    cierre), búsqueda de texto, orden por columna, paginación — pensada
    para triar procesos, no para trabajarlos.
  - Ambas se resuelven con **una sola consulta anotada**
    (`procesos.services.procesos_con_metricas`): cumplimiento de
    requisitos y severidad máxima de riesgo, sin una query por fila/tarjeta.
- **Detalle de proceso** (`/procesos/<id>/`): statusbar con las transiciones
  de FSM realmente alcanzables (nunca todas), formulario editable en dos
  columnas, botón "Marcar como verificado" junto a los campos críticos
  (invariante 3), pestañas Requisitos / Documentos / Riesgos / Actividades,
  y un **chatter** al fondo con comentarios en vivo (HTMX, sin recargar),
  @menciones con autocompletado, y el log de auditoría intercalado
  cronológicamente con los comentarios.
- **Creación manual** (`/procesos/nuevo/`, gate `crear_procesos`, botón
  "Nuevo" en el panel de control de kanban y lista): entidad por
  autocompletado seleccionable, con opción de crear una entidad nueva en
  línea (gate `gestionar_entidades`). Todo lo creado a mano entra con
  `origen=manual`, `estado=detectado` y sin fechas verificadas. Filtros de
  lista visibles como facetas removibles, y estados vacíos distintos para
  "no hay procesos todavía" (con CTA) y "sin resultados para el filtro"
  (con "Limpiar filtros").
- **Historial documental**: `VersionDocumental` (proyecto → definitivo →
  adendas) y `Requisito` **inmutable** — una adenda nunca edita un
  requisito, crea uno nuevo que deroga al anterior vía
  `procesos.services.derogar_requisito`.
- **`Riesgo`** con taxonomía cerrada (invariante 5). El modelo existe y
  alimenta el semáforo del kanban; falta la UI/pipeline que los capture.

### Social — el chatter estilo Odoo

- `Comentario` (con @menciones), `Actividad` ("programar seguimiento"),
  `Alerta` (hoy solo se dispara por mención). Todo vía
  `social/services.py`, nunca asignación directa.

### Autenticación

- **Solo Google, solo del dominio de la empresa.** `django-allauth` con el
  proveedor Google; `core.adapters.SocialAccountAdapterDominio` rechaza en
  `pre_social_login` cualquier correo que no termine en
  `@{GOOGLE_WORKSPACE_DOMAIN}` — el parámetro `hd` de Google es solo UX,
  la verificación real es del lado del servidor (ver `DECISIONES.md`).
  El registro por formulario (correo + contraseña) está desactivado.
- **Todas las vistas requieren sesión**, sin excepción salvo login/logout/
  callback — vía `django.contrib.auth.middleware.LoginRequiredMiddleware`
  (nativo de Django, no hay que decorar cada vista nueva a mano).
- `manage.py crear_admins correo1 correo2`: crea o promueve dos cuentas a
  administrador general (`is_staff` + `is_superuser`). Idempotente —
  correrlo de nuevo no duplica ni rompe. Si la cuenta ya existía sin
  privilegios, los agrega; si no existía, la crea para que quede lista
  antes del primer login por Google (el adapter conecta esa cuenta
  pre-creada a la cuenta de Google en vez de crear un usuario duplicado).
- Página de login propia (`templates/account/login.html`) sobre
  `tokens.css` — un botón "Continuar con Google", sin la plantilla por
  defecto de allauth. Los rechazos (dominio ajeno, cuenta desactivada)
  muestran un mensaje ahí mismo, no en la página de error de allauth.

### Perfiles y permisos (`/configuracion/`)

- Permisos por modelo y acción (`django.contrib.auth.Group`/`Permission`,
  **no** `django-guardian` — ver `DECISIONES.md`). El catálogo completo
  vive en `procesos/permisos.py`, con etiqueta en español para cada uno:
  `ver_procesos`, `crear_procesos`, `editar_procesos`, `eliminar_procesos`,
  `mover_etapa`, `descartar_procesos`, `verificar_fechas`,
  `importar_procesos`, `gestionar_entidades`, `gestionar_usuarios`,
  `ver_todos`.
- Tres perfiles de arranque (creados por migración, editables pero no
  eliminables): **Administrador** (todo), **Comercial** (el día a día:
  crear/editar/mover/descartar/verificar/importar + ver todo el equipo),
  **Consulta** (solo ver, todo el equipo).
- **Crear un perfil nuevo**: `/configuracion/perfiles/nuevo/` → nombre,
  descripción, y una matriz de checkboxes agrupada por módulo ("Marcar/
  desmarcar todo" alterna el módulo completo).
- **Asignar usuarios a un perfil**: entra al perfil desde
  `/configuracion/perfiles/` → tabla de usuarios asignados con "Quitar", y
  un select para agregar uno nuevo. También se puede cambiar el perfil de
  un usuario directamente desde `/configuracion/usuarios/` (select inline,
  HTMX, sin recargar).
- Un perfil con usuarios asignados no se puede eliminar, ni los tres de
  arranque aunque estén vacíos. Un administrador no puede desactivarse a
  sí mismo ni quitarse su única fuente de `gestionar_usuarios`.
- Sin `ver_todos`, un usuario solo ve procesos donde es responsable o
  seguidor — filtrado en `procesos.services.procesos_con_metricas()`, así
  que kanban, lista y detalle heredan el alcance de una sola vez (un
  proceso ajeno da 404 en el detalle, no 403).
- Los botones/acciones que un usuario no puede ejecutar no se renderizan
  (`{% if perms.procesos.mover_etapa %}`, no CSS), y cada endpoint POST
  los vuelve a exigir del lado del servidor — el drag&drop del kanban se
  deshabilita sin `mover_etapa` y el endpoint igual lo rechaza si alguien
  le pega directo.
- `@permission_required(..., raise_exception=True)` en cada vista que lo
  necesita, con una página 403 propia (`templates/403.html`) sobre
  `tokens.css` en vez de la de Django por defecto.

### Cuenta y preferencias

- `Usuario` (extiende `AbstractUser`) con `tema` (claro/oscuro),
  `densidad` (compacta/normal/cómoda) y `vista_preferida`
  (kanban/lista) — se renderizan desde el servidor en `<html>` (cero
  parpadeo al cargar) y se guardan en segundo plano al cambiarlas.

### Sistema visual v3

- CSS propio construido sobre `static/css/tokens.css` (color, espaciado,
  radio, sombra, tipografía — nada literal en las plantillas), con modo
  oscuro y tres densidades. Reemplaza a Tailwind por CDN, que quedó
  bloqueado por el DNS del ISP del desarrollador (ver `DECISIONES.md`).
  Un canal de color violeta (`--ia`) está reservado exclusivamente para
  contenido generado por el modelo — invariante 4 hecha pixel.
- Especificación visual documentada como página viva en
  `referencia_ui_v3.html` (raíz del repo).

### Datos demo

- `core/management/commands/seed_demo.py`: comando **idempotente** (nunca
  toca usuarios ni entidades reales) que genera 12 entidades colombianas
  realistas, 3 usuarios comerciales, 40 procesos repartidos por todos los
  estados del FSM, y para 8 de ellos historial documental completo
  (requisitos, adendas que derogan, comentarios con menciones,
  actividades). Todas las transiciones de estado pasan por
  `procesos.services`, nunca por asignación directa.

  ```bash
  uv run python manage.py seed_demo
  ```

### Entidades

- `/entidades/`: autocompletado por similitud (`pg_trgm`) sobre nombre y NIT.

---

## Pendiente / conocido

- Pestaña "Documentos" del detalle: sin implementar (no hay app
  `documentos` construida todavía).
- Estado "analizando" del kanban (barrido + progreso + polling HTMX
  dirigido) y el botón "Analizar pendientes": diseñados en el CSS
  (`.tarjeta.analizando`) pero sin el endpoint/simulación de IA que los
  dispare.
- La vista Lista todavía no tiene la columna "Ajuste" (puntaje de IA) ni
  la densidad de 25-30 filas por pantalla — quedó con la densidad
  original de cuando solo existía la lista.
- Vista de eliminación de procesos: `eliminar_procesos` está declarado en
  el catálogo de permisos, sin uso todavía — no estaba en el alcance del
  ítem 3.
- Importador de Excel (ítem 5, días 5-8): sin empezar — espera los
  insumos de `_legado/` (código de referencia del importador anterior y
  un CSV real de licitaciones.info) que van fuera del repo.
- El chatter (comentarios, actividades) no tiene permiso propio en el
  catálogo — cualquier usuario autenticado puede comentar o programar
  seguimiento, sin importar su perfil. No estaba en el catálogo pedido
  para esta entrega.
- Falta crear el cliente OAuth real en Google Cloud Console y completar
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_WORKSPACE_DOMAIN` en
  `.env` — con los valores de plantilla el botón de login no funciona.
- `CLAUDE.md` § Stack todavía menciona Tailwind como parte del frontend;
  quedó desactualizado tras el cambio a CSS propio (pendiente de corregir
  junto con la sección "Diseño" que documentará la regla del violeta).

---

## Comandos

```bash
make up          # levanta postgres + redis
make dev         # runserver
make worker      # celery
make test        # pytest
make lint        # ruff check --fix && ruff format
make migrate     # makemigrations + migrate (con revisión manual)
make shell       # shell_plus
make reset       # borra la base y reconstruye desde cero
```

---

## Estructura

```
config/          settings/{base,dev,prod}.py, urls, celery
core/            Usuario, Entidad, CodigoUNSPSC, adapters de auth, preferencias, seed_demo
procesos/        Proceso, VersionDocumental, Requisito, Riesgo, permisos.py — el núcleo
configuracion/   PerfilInfo, vistas de /configuracion/perfiles/ y /configuracion/usuarios/
documentos/      (vacío todavía) Documento, FragmentoDocumento, ingesta
perfil/          (vacío todavía) PerfilEmpresa, ExperienciaContrato...
ia/              (vacío todavía) AnalisisIA, prompts/, clientes
social/          Comentario, Actividad, Alerta — el chatter
templates/       base.html, componentes/, {app}/
static/          css/tokens.css, css/app.css, js/
```
