# Plataforma de gestión de licitaciones

Sistema web interno para gestionar el ciclo completo de licitaciones públicas
(Colombia / SECOP II) desde el lado del **proponente**. Reemplaza un Excel.
~15 usuarios internos. Un solo desarrollador.

## Regla de oro

Este proyecto se optimiza para **poco código y mucha convención**, no para
sofisticación técnica. 15 usuarios no justifican complejidad. Si una propuesta
agrega un servicio, una capa de abstracción o una dependencia, la respuesta por
defecto es NO salvo justificación explícita.

---

## Stack

- Python 3.12, Django 5.2 LTS, Django REST Framework (solo donde haga falta API)
- PostgreSQL 16 con `pgvector`, `pg_trgm`, `unaccent`
- Frontend: plantillas Django + HTMX + Alpine.js + Tailwind. **No hay SPA.**
- Celery + Redis para trabajo asíncrono
- Almacenamiento: Cloudflare R2 vía django-storages
- Gestión de dependencias: `uv`. Lint y formato: `ruff`. Tests: `pytest-django`.

### Prohibido sin discusión previa
LangChain, React/Next, Mongo, Elasticsearch, Pinecone/Qdrant, GraphQL,
Kubernetes, microservicios, un servicio de IA separado.

Los SDK de LLM se usan **directo** (`anthropic` / `openai`) con `pydantic`
para salida estructurada. Nada de frameworks de orquestación.

---

## Estructura

```
config/          settings/{base,dev,prod}.py, urls, celery
core/            Usuario, Entidad, CodigoUNSPSC, mixins, TimeStamped
procesos/        Proceso, VersionDocumental, Requisito, Riesgo  <- núcleo
documentos/      Documento, FragmentoDocumento, ingesta
perfil/          PerfilEmpresa, ExperienciaContrato, Certificacion, PersonalClave
ia/              AnalisisIA, prompts/, clientes, extractores
social/          Comentario, Actividad, Alerta
templates/       base.html, componentes/, {app}/
static/
```

---

## Invariantes del dominio — NO NEGOCIABLES

1. **Los `Requisito` son inmutables.** Una adenda nunca edita un requisito
   existente: crea uno nuevo con `reemplaza` apuntando al anterior. Los vigentes
   se leen con `proceso.requisitos_vigentes`. Jamás hacer `UPDATE` sobre la
   descripción o el umbral de un requisito ya publicado.

2. **Todo dato extraído por IA lleva cita.** `cita_pagina` + `cita_texto` +
   `numeral`. Un requisito o riesgo sin cita es un bug, no un resultado parcial.

3. **Las fechas críticas las verifica un humano.** `fecha_cierre`,
   `presupuesto_oficial`, valores de garantía y causales de rechazo se muestran
   siempre marcados como "sin verificar" hasta que alguien llene
   `fechas_verificadas_por`. La UI debe hacer esto visualmente obvio.

4. **El campo `origen` nunca se omite.** Distingue `manual` / `importado` /
   `secop` / `ia` / `regla`. Confundir extracción automática con verificación
   humana es el peor bug posible en este dominio.

5. **La taxonomía de `Riesgo` es cerrada.** El modelo detecta y cita riesgos de
   la lista existente. No se le pide "¿qué riesgos ves?" ni se agregan tipos
   nuevos sin decidirlo explícitamente.

6. **Los códigos UNSPSC nunca se generan.** Se recuperan por similitud desde
   `CodigoUNSPSC` y el LLM solo elige entre los candidatos recuperados.

7. **Búsqueda siempre híbrida.** FTS en español (`es_unaccent`) + vector,
   fusionados con RRF vía la función `buscar_fragmentos`. Nunca solo vectorial:
   los pliegos están llenos de literales (numerales, NITs, códigos).

---

## Convenciones de código

- Modelos, campos, verbose_name y contenido de UI: **en español**.
- Nombres de variables locales y funciones internas: español también, por
  consistencia. Sin espanglish (`get_procesos` no, `obtener_procesos` sí).
- Lógica de negocio en `services.py` por app, no en vistas ni en modelos.
  Las vistas orquestan; los modelos definen datos y transiciones.
- Transiciones de estado solo vía `django-fsm-2`. Nunca `proceso.estado = "x"`.
- Los `Decimal` para dinero, jamás `float`.
- Toda tarea Celery es idempotente y recibe IDs, no objetos.
- Templates HTMX: fragmentos en `templates/{app}/partials/`, con
  `django-template-partials`.

---

## Cómo trabajamos

- **Slices verticales.** Una feature completa por sesión: modelo → migración →
  service → vista → template → test. Nunca "todos los modelos de golpe".
- **Tests con cada slice.** `pytest`. Factories con `factory-boy`. Un test de
  camino feliz y uno del caso borde que importe.
- **Las migraciones se revisan a mano SIEMPRE** antes de aplicar. Es el único
  lugar donde un error es destructivo. Nunca `--fake` sin explicación.
- Antes de agregar una dependencia, preguntar.
- Al cerrar una decisión de arquitectura, anotarla en `DECISIONES.md`.

---

## Comandos

```bash
make up          # levanta postgres + redis
make dev         # runserver
make worker      # celery
make test        # pytest
make lint        # ruff check --fix && ruff format
make migrate     # makemigrations + migrate
make shell       # shell_plus
```

---

## Estado actual

Fase 1 en curso. Ver `PLAN.md` para el alcance de cada semana.
