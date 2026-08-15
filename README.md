# LicitaPro

Sistema web interno para gestionar el ciclo completo de licitaciones públicas
(Colombia / SECOP II) desde el lado del **proponente**. Reemplaza un Excel.
~15 usuarios internos, un solo desarrollador.

Las convenciones y reglas de dominio no-negociables viven en
[`CLAUDE.md`](CLAUDE.md). El historial de decisiones de arquitectura, con el
porqué de cada una, vive en [`DECISIONES.md`](DECISIONES.md). Este archivo es
la puerta de entrada: qué es esto, cómo se levanta, y qué hay construido hoy.

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
uv run python manage.py createsuperuser
uv run python manage.py seed_demo   # opcional: datos demo realistas, ver abajo
make dev                    # runserver en http://127.0.0.1:8000/
```

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
- No hay `login_required` en ninguna vista todavía — gap preexistente,
  el proyecto asume por ahora que solo el equipo interno tiene acceso a
  la red donde corre.
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
core/            Usuario, Entidad, CodigoUNSPSC, preferencias, seed_demo
procesos/        Proceso, VersionDocumental, Requisito, Riesgo — el núcleo
documentos/      (vacío todavía) Documento, FragmentoDocumento, ingesta
perfil/          (vacío todavía) PerfilEmpresa, ExperienciaContrato...
ia/              (vacío todavía) AnalisisIA, prompts/, clientes
social/          Comentario, Actividad, Alerta — el chatter
templates/       base.html, componentes/, {app}/
static/          css/tokens.css, css/app.css, js/
```
