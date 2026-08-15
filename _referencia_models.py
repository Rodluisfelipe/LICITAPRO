"""
Esquema de datos — Plataforma de gestión de licitaciones
Django 5.x + PostgreSQL 16 (pgvector, pg_trgm, FTS español)

Organización sugerida en apps:
    core/         -> Usuario, Entidad, CodigoUNSPSC
    procesos/     -> Proceso, Requisito, VersionDocumental, Riesgo
    documentos/   -> Documento, FragmentoDocumento
    perfil/       -> PerfilEmpresa, ExperienciaContrato, Certificacion, PersonalClave
    ia/           -> AnalisisIA
    social/       -> Comentario, Actividad, Alerta

Este archivo los presenta juntos para que se lea el modelo completo de un vistazo.
"""

import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django_fsm import FSMField, transition
from pgvector.django import HnswIndex, VectorField

EMBEDDING_DIMS = 1024  # BGE-M3 / Qwen3-Embedding-0.6B


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class TimeStamped(models.Model):
    """Auditoría mínima en todas las tablas. django-auditlog cubre el detalle."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


class Origen(models.TextChoices):
    """Quién produjo el dato. Crítico: nunca confundir extracción de IA con
    verificación humana."""
    MANUAL = "manual", "Capturado manualmente"
    IMPORTADO = "importado", "Importado de Excel"
    SECOP = "secop", "API SECOP II"
    IA = "ia", "Extraído por IA"
    REGLA = "regla", "Regla determinista"


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------

class Entidad(TimeStamped):
    """Entidad contratante. Autocompletado vía pg_trgm sobre nombre y NIT."""

    class Orden(models.TextChoices):
        NACIONAL = "nacional", "Nacional"
        DEPARTAMENTAL = "departamental", "Departamental"
        MUNICIPAL = "municipal", "Municipal"
        DESCENTRALIZADA = "descentralizada", "Descentralizada"
        MIXTA = "mixta", "Economía mixta"

    nombre = models.CharField(max_length=300)
    nombre_normalizado = models.CharField(
        max_length=300, db_index=True,
        help_text="Minúsculas, sin tildes. Para deduplicar en el importador.",
    )
    nit = models.CharField(max_length=20, blank=True, db_index=True)
    orden = models.CharField(max_length=20, choices=Orden.choices, blank=True)
    sector = models.CharField(max_length=120, blank=True)
    departamento = models.CharField(max_length=80, blank=True)
    municipio = models.CharField(max_length=120, blank=True)
    sitio_web = models.URLField(blank=True)
    notas = models.TextField(blank=True, help_text="Historial de relación con la entidad.")

    class Meta:
        verbose_name_plural = "Entidades"
        indexes = [
            GinIndex(fields=["nombre_normalizado"], name="idx_entidad_trgm",
                     opclasses=["gin_trgm_ops"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["nit"], condition=~Q(nit=""), name="uq_entidad_nit",
            ),
        ]

    def __str__(self):
        return self.nombre


class CodigoUNSPSC(models.Model):
    """Catálogo UNSPSC embebido una sola vez. El LLM elige entre candidatos
    recuperados por similitud — nunca genera códigos de memoria."""

    codigo = models.CharField(max_length=10, primary_key=True)
    nombre = models.CharField(max_length=300)
    nivel = models.PositiveSmallIntegerField(help_text="1=Segmento 2=Familia 3=Clase 4=Producto")
    padre = models.ForeignKey("self", null=True, blank=True,
                              on_delete=models.PROTECT, related_name="hijos")
    embedding = VectorField(dimensions=EMBEDDING_DIMS, null=True)
    es_habitual = models.BooleanField(
        default=False, help_text="Marcado por el equipo: códigos en los que la empresa compite.",
    )

    class Meta:
        verbose_name = "Código UNSPSC"
        verbose_name_plural = "Códigos UNSPSC"
        indexes = [
            HnswIndex(name="idx_unspsc_emb", fields=["embedding"],
                      m=16, ef_construction=64, opclasses=["vector_cosine_ops"]),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


# ---------------------------------------------------------------------------
# procesos
# ---------------------------------------------------------------------------

class Proceso(TimeStamped):
    """Entidad central del sistema. Todo cuelga de aquí."""

    class Modalidad(models.TextChoices):
        LICITACION = "licitacion", "Licitación pública"
        SELECCION_ABREVIADA = "seleccion_abreviada", "Selección abreviada"
        CONCURSO_MERITOS = "concurso_meritos", "Concurso de méritos"
        MINIMA_CUANTIA = "minima_cuantia", "Mínima cuantía"
        CONTRATACION_DIRECTA = "contratacion_directa", "Contratación directa"
        SUBASTA_INVERSA = "subasta_inversa", "Subasta inversa"
        PRIVADA = "privada", "Invitación privada"
        OTRA = "otra", "Otra"

    class Estado(models.TextChoices):
        DETECTADO = "detectado", "Detectado"
        EN_EVALUACION = "en_evaluacion", "En evaluación"
        DESCARTADO = "descartado", "Descartado"
        APTO = "apto", "Apto — decisión de participar"
        EN_PREPARACION = "en_preparacion", "En preparación"
        PRESENTADO = "presentado", "Presentado"
        ADJUDICADO = "adjudicado", "Adjudicado"
        NO_ADJUDICADO = "no_adjudicado", "No adjudicado"
        DESIERTO = "desierto", "Declarado desierto"
        SUSPENDIDO = "suspendido", "Suspendido"

    # --- identificación
    numero_proceso = models.CharField(max_length=120, db_index=True,
                                      help_text="Número SECOP o referencia interna.")
    entidad = models.ForeignKey(Entidad, on_delete=models.PROTECT, related_name="procesos")
    objeto = models.TextField()
    modalidad = models.CharField(max_length=30, choices=Modalidad.choices, blank=True)
    url_secop = models.URLField(blank=True)
    origen = models.CharField(max_length=20, choices=Origen.choices, default=Origen.MANUAL)

    # --- cifras. Se anotan como "declaradas" y deben verificarse a mano.
    presupuesto_oficial = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    moneda = models.CharField(max_length=3, default="COP")
    plazo_ejecucion_dias = models.PositiveIntegerField(null=True, blank=True)

    # --- fechas críticas. NUNCA fuente-de-verdad de IA sin verificación humana.
    fecha_publicacion = models.DateField(null=True, blank=True)
    fecha_limite_observaciones = models.DateTimeField(null=True, blank=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True, db_index=True)
    fecha_adjudicacion = models.DateField(null=True, blank=True)
    fechas_verificadas_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="procesos_fechas_verificadas",
    )
    fechas_verificadas_en = models.DateTimeField(null=True, blank=True)

    # --- gestión
    estado = FSMField(default=Estado.DETECTADO, choices=Estado.choices,
                      protected=True, db_index=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="procesos_a_cargo",
    )
    seguidores = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="procesos_seguidos",
        help_text="Chatter: reciben notificaciones del proceso.",
    )
    codigos_unspsc = models.ManyToManyField(CodigoUNSPSC, blank=True, related_name="procesos")
    motivo_descarte = models.TextField(blank=True)

    # --- resultado de IA (caché; el detalle vive en AnalisisIA)
    resumen_ejecutivo = models.TextField(blank=True)
    semaforo = models.CharField(
        max_length=10, blank=True,
        choices=[("verde", "Verde"), ("amarillo", "Amarillo"), ("rojo", "Rojo")],
    )

    class Meta:
        ordering = ["-fecha_cierre"]
        indexes = [
            models.Index(fields=["estado", "fecha_cierre"]),
            models.Index(fields=["entidad", "-creado_en"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["entidad", "numero_proceso"],
                                    name="uq_proceso_entidad_numero"),
        ]

    def __str__(self):
        return f"{self.numero_proceso} — {self.entidad.nombre}"

    # ---- máquina de estados -------------------------------------------------
    @transition(field=estado, source=Estado.DETECTADO, target=Estado.EN_EVALUACION)
    def iniciar_evaluacion(self):
        pass

    @transition(field=estado,
                source=[Estado.DETECTADO, Estado.EN_EVALUACION, Estado.APTO],
                target=Estado.DESCARTADO)
    def descartar(self, motivo: str):
        self.motivo_descarte = motivo

    @transition(field=estado, source=Estado.EN_EVALUACION, target=Estado.APTO)
    def marcar_apto(self):
        pass

    @transition(field=estado, source=Estado.APTO, target=Estado.EN_PREPARACION)
    def iniciar_preparacion(self):
        pass

    @transition(field=estado, source=Estado.EN_PREPARACION, target=Estado.PRESENTADO)
    def presentar(self):
        pass

    @transition(field=estado, source=Estado.PRESENTADO,
                target=Estado.ADJUDICADO)
    def adjudicar(self):
        pass

    @transition(field=estado, source=Estado.PRESENTADO, target=Estado.NO_ADJUDICADO)
    def perder(self):
        pass

    @transition(field=estado, source="*", target=Estado.SUSPENDIDO)
    def suspender(self):
        pass

    # ---- helpers ------------------------------------------------------------
    @property
    def requisitos_vigentes(self):
        """Solo los requisitos que ninguna adenda posterior derogó."""
        return self.requisitos.filter(reemplazado_por__isnull=True)


class VersionDocumental(TimeStamped):
    """
    PIEZA CLAVE DEL ESQUEMA.

    Un pliego no es un documento: es una secuencia. Borrador -> definitivo ->
    adenda 1 -> adenda 2. Cada adenda puede cambiar fechas y requisitos ya
    extraídos. Modelar esto desde el día uno evita una migración dolorosa
    cuando el primer proceso reciba su tercera adenda.
    """

    class Tipo(models.TextChoices):
        PROYECTO = "proyecto", "Proyecto de pliego"
        DEFINITIVO = "definitivo", "Pliego definitivo"
        ADENDA = "adenda", "Adenda"
        RESPUESTA_OBS = "respuesta_obs", "Respuesta a observaciones"
        ANEXO = "anexo", "Anexo técnico"
        ADDENDUM_CRONOGRAMA = "cronograma", "Modificación de cronograma"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="versiones")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    secuencia = models.PositiveSmallIntegerField(
        help_text="Orden cronológico dentro del proceso. 0 = documento inicial.",
    )
    numero_adenda = models.PositiveSmallIntegerField(null=True, blank=True)
    fecha_publicacion = models.DateField(null=True, blank=True)
    resumen_cambios = models.TextField(
        blank=True, help_text="Qué modificó respecto a la versión anterior.",
    )
    procesada = models.BooleanField(default=False)

    class Meta:
        ordering = ["proceso", "secuencia"]
        verbose_name = "Versión documental"
        verbose_name_plural = "Versiones documentales"
        constraints = [
            models.UniqueConstraint(fields=["proceso", "secuencia"],
                                    name="uq_version_proceso_secuencia"),
        ]

    def __str__(self):
        return f"{self.proceso.numero_proceso} v{self.secuencia} ({self.get_tipo_display()})"


class Requisito(TimeStamped):
    """
    Requisito habilitante o de evaluación.

    Los registros son INMUTABLES: una adenda no edita el requisito anterior,
    crea uno nuevo y apunta `reemplaza` al viejo. Así queda historial auditable
    de qué exigía el pliego en cada momento.
    """

    class Tipo(models.TextChoices):
        JURIDICO = "juridico", "Jurídico"
        FINANCIERO = "financiero", "Financiero"
        TECNICO = "tecnico", "Técnico"
        EXPERIENCIA = "experiencia", "Experiencia"
        ORGANIZACIONAL = "organizacional", "Capacidad organizacional"
        PUNTUABLE = "puntuable", "Factor de puntuación"

    class Cumplimiento(models.TextChoices):
        POR_VERIFICAR = "por_verificar", "Por verificar"
        CUMPLE = "cumple", "Cumple"
        NO_CUMPLE = "no_cumple", "No cumple"
        PARCIAL = "parcial", "Cumple parcialmente"
        SUBSANABLE = "subsanable", "No cumple pero es subsanable"
        NO_APLICA = "no_aplica", "No aplica"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="requisitos")
    version_origen = models.ForeignKey(VersionDocumental, on_delete=models.CASCADE,
                                       related_name="requisitos_introducidos")
    reemplaza = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reemplazado_por",
        help_text="Requisito de una versión anterior que este deroga.",
    )

    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    numeral = models.CharField(max_length=40, blank=True,
                               help_text="Ej: 3.2.1 — para trazabilidad al pliego.")
    descripcion = models.TextField()

    # --- parametrización: permite evaluar sin LLM cuando el requisito es numérico
    indicador = models.CharField(
        max_length=60, blank=True,
        help_text="Ej: indice_liquidez, razon_endeudamiento, capacidad_residual.",
    )
    operador = models.CharField(
        max_length=4, blank=True,
        choices=[(">=", "≥"), ("<=", "≤"), ("=", "="), (">", ">"), ("<", "<")],
    )
    valor_umbral = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unidad = models.CharField(max_length=20, blank=True, help_text="COP, SMMLV, años, veces…")

    # --- trazabilidad de la extracción
    origen = models.CharField(max_length=20, choices=Origen.choices, default=Origen.IA)
    cita_pagina = models.PositiveIntegerField(null=True, blank=True)
    cita_texto = models.TextField(blank=True, help_text="Fragmento literal que sustenta el requisito.")
    confianza = models.FloatField(null=True, blank=True)

    # --- evaluación contra el perfil de la empresa
    cumplimiento = models.CharField(max_length=20, choices=Cumplimiento.choices,
                                    default=Cumplimiento.POR_VERIFICAR, db_index=True)
    justificacion = models.TextField(blank=True)
    es_critico = models.BooleanField(default=False, help_text="Su incumplimiento causa rechazo.")
    verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="requisitos_verificados",
    )
    verificado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["tipo", "numeral"]
        indexes = [models.Index(fields=["proceso", "tipo", "cumplimiento"])]

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.numeral} {self.descripcion[:60]}"

    @property
    def vigente(self) -> bool:
        return not hasattr(self, "reemplazado_por")

    @property
    def evaluable_automaticamente(self) -> bool:
        return bool(self.indicador and self.operador and self.valor_umbral is not None)


class Riesgo(TimeStamped):
    """
    Semáforo de riesgos con taxonomía CERRADA.

    No se le pregunta al modelo "¿qué riesgos ves?" — se le pide detectar y citar
    riesgos de esta lista. Un semáforo determinista es auditable; uno generativo
    es una opinión.
    """

    class Tipo(models.TextChoices):
        EXPERIENCIA_DIRECCIONADA = "exp_direccionada", "Experiencia posiblemente direccionada"
        SPECS_MARCA = "specs_marca", "Especificaciones atadas a marca"
        PLAZO_IRREAL = "plazo_irreal", "Plazo de ejecución irreal"
        GARANTIA_DESPROPORCIONADA = "garantia_despro", "Garantías desproporcionadas"
        INDICADORES_RESTRICTIVOS = "indic_restrictivos", "Indicadores financieros restrictivos"
        ANTICIPO_SIN_CLARIDAD = "anticipo", "Anticipo sin amortización clara"
        MULTAS_AGRESIVAS = "multas", "Régimen sancionatorio agresivo"
        CRONOGRAMA_CORTO = "cronograma_corto", "Tiempo insuficiente para preparar"
        PRESUPUESTO_BAJO = "presupuesto_bajo", "Presupuesto por debajo de mercado"
        PAGO_DIFERIDO = "pago_diferido", "Condiciones de pago desfavorables"

    class Severidad(models.TextChoices):
        BAJA = "baja", "Baja"
        MEDIA = "media", "Media"
        ALTA = "alta", "Alta"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="riesgos")
    version_origen = models.ForeignKey(VersionDocumental, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="riesgos")
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    severidad = models.CharField(max_length=10, choices=Severidad.choices)
    descripcion = models.TextField()
    cita_numeral = models.CharField(max_length=40, blank=True)
    cita_pagina = models.PositiveIntegerField(null=True, blank=True)
    origen = models.CharField(max_length=20, choices=Origen.choices, default=Origen.IA)
    descartado_por_usuario = models.BooleanField(default=False)

    class Meta:
        ordering = ["-severidad"]

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.get_severidad_display()})"


# ---------------------------------------------------------------------------
# documentos
# ---------------------------------------------------------------------------

class Documento(TimeStamped):
    """Archivo físico. El hash evita reprocesar el mismo PDF dos veces."""

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PROCESANDO = "procesando", "Procesando"
        LISTO = "listo", "Listo"
        ERROR = "error", "Error"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="documentos")
    version = models.ForeignKey(VersionDocumental, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="documentos")
    archivo = models.FileField(upload_to="procesos/%Y/%m/")
    nombre_original = models.CharField(max_length=300)
    mime = models.CharField(max_length=100, blank=True)
    tamano_bytes = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    paginas = models.PositiveIntegerField(null=True, blank=True)

    texto_extraido = models.TextField(blank=True)
    markdown = models.TextField(blank=True, help_text="Salida con layout preservado (Docling).")
    estado_procesamiento = models.CharField(max_length=15, choices=Estado.choices,
                                            default=Estado.PENDIENTE, db_index=True)
    error_procesamiento = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["proceso", "sha256"], name="uq_doc_proceso_hash"),
        ]

    def __str__(self):
        return self.nombre_original


class FragmentoDocumento(models.Model):
    """
    Chunk para búsqueda híbrida: FTS en español (BM25-like) + vector denso.
    Los pliegos están llenos de literales — códigos, numerales, NITs — que un
    embedding denso pierde. El híbrido no es opcional.
    """

    id = models.BigAutoField(primary_key=True)
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name="fragmentos")
    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="fragmentos")
    orden = models.PositiveIntegerField()
    pagina = models.PositiveIntegerField(null=True, blank=True)
    numeral = models.CharField(max_length=40, blank=True)
    titulo_seccion = models.CharField(max_length=300, blank=True)
    texto = models.TextField()
    tokens = models.PositiveIntegerField(null=True, blank=True)

    search_vector = SearchVectorField(null=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMS, null=True)

    class Meta:
        ordering = ["documento", "orden"]
        indexes = [
            GinIndex(fields=["search_vector"], name="idx_frag_fts"),
            HnswIndex(name="idx_frag_emb", fields=["embedding"],
                      m=16, ef_construction=64, opclasses=["vector_cosine_ops"]),
            models.Index(fields=["proceso", "pagina"]),
        ]


# ---------------------------------------------------------------------------
# perfil de la empresa — el activo que abarata todo lo demás
# ---------------------------------------------------------------------------

class PerfilEmpresa(TimeStamped):
    """Indicadores por año fiscal. Se captura una vez al año y hace que la
    verificación de habilitantes financieros sea determinista, sin LLM."""

    anio = models.PositiveSmallIntegerField(unique=True)
    indice_liquidez = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    razon_endeudamiento = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    razon_cobertura_intereses = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rentabilidad_patrimonio = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    rentabilidad_activo = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    capital_trabajo = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    patrimonio = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    capacidad_residual = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    smmlv_del_anio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Perfil de empresa"
        verbose_name_plural = "Perfiles de empresa"
        ordering = ["-anio"]

    def __str__(self):
        return f"Perfil {self.anio}"


class ExperienciaContrato(TimeStamped):
    """Contratos ejecutados acreditables. Se compara contra los requisitos de
    experiencia sin necesidad de razonamiento generativo."""

    entidad_contratante = models.CharField(max_length=300)
    numero_contrato = models.CharField(max_length=120, blank=True)
    objeto = models.TextField()
    valor = models.DecimalField(max_digits=18, decimal_places=2)
    valor_smmlv = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fecha_inicio = models.DateField()
    fecha_terminacion = models.DateField(null=True, blank=True)
    codigos_unspsc = models.ManyToManyField(CodigoUNSPSC, blank=True,
                                            related_name="experiencias")
    acta_liquidacion = models.FileField(upload_to="perfil/experiencia/", blank=True)
    inscrito_en_rup = models.BooleanField(default=False)
    embedding = VectorField(dimensions=EMBEDDING_DIMS, null=True)

    class Meta:
        verbose_name = "Experiencia — contrato"
        verbose_name_plural = "Experiencia — contratos"
        ordering = ["-fecha_terminacion"]

    def __str__(self):
        return f"{self.entidad_contratante} — {self.objeto[:60]}"


class Certificacion(TimeStamped):
    nombre = models.CharField(max_length=200)
    entidad_emisora = models.CharField(max_length=200, blank=True)
    numero = models.CharField(max_length=120, blank=True)
    fecha_emision = models.DateField(null=True, blank=True)
    fecha_vencimiento = models.DateField(null=True, blank=True, db_index=True)
    archivo = models.FileField(upload_to="perfil/certificaciones/", blank=True)

    class Meta:
        verbose_name_plural = "Certificaciones"

    def __str__(self):
        return self.nombre


class PersonalClave(TimeStamped):
    nombre = models.CharField(max_length=200)
    profesion = models.CharField(max_length=200)
    tarjeta_profesional = models.CharField(max_length=60, blank=True)
    anios_experiencia = models.PositiveSmallIntegerField(null=True, blank=True)
    hoja_de_vida = models.FileField(upload_to="perfil/personal/", blank=True)
    disponible = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Personal clave"
        verbose_name_plural = "Personal clave"

    def __str__(self):
        return f"{self.nombre} — {self.profesion}"


# ---------------------------------------------------------------------------
# ia — trazabilidad y costo
# ---------------------------------------------------------------------------

class AnalisisIA(TimeStamped):
    """
    Registro de cada corrida. Sin esto no puedes reproducir un resultado,
    comparar versiones de prompt, ni saber cuánto te cuesta cada proceso.
    """

    class Tipo(models.TextChoices):
        TRIAGE = "triage", "Triage rápido"
        RESUMEN = "resumen", "Resumen ejecutivo"
        HABILITANTES = "habilitantes", "Verificación de habilitantes"
        RIESGOS = "riesgos", "Semáforo de riesgos"
        UNSPSC = "unspsc", "Clasificación UNSPSC"
        ADENDA_DIFF = "adenda_diff", "Impacto de adenda"
        SPECS = "specs", "Match de marcas y equipos"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EJECUTANDO = "ejecutando", "Ejecutando"
        OK = "ok", "Completado"
        ERROR = "error", "Error"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="analisis")
    version = models.ForeignKey(VersionDocumental, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="analisis")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)

    modelo = models.CharField(max_length=80, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True,
                                      help_text="Versiona los prompts como versionas el código.")
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_entrada_cache = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    costo_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latencia_ms = models.PositiveIntegerField(null=True, blank=True)
    trace_id = models.CharField(max_length=100, blank=True, help_text="ID en Langfuse.")

    resultado = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Análisis IA"
        verbose_name_plural = "Análisis IA"
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["proceso", "tipo", "-creado_en"])]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.proceso.numero_proceso}"


# ---------------------------------------------------------------------------
# social — el "chatter" estilo Odoo
# ---------------------------------------------------------------------------

class Comentario(TimeStamped):
    """Comentario contextual al proceso. Reemplaza el chat interno: es lo que
    hace que Odoo se sienta ordenado."""

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name="comentarios")
    cuerpo = models.TextField()
    menciones = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                       related_name="comentarios_mencionado")
    responde_a = models.ForeignKey("self", null=True, blank=True,
                                   on_delete=models.CASCADE, related_name="respuestas")
    adjunto = models.FileField(upload_to="comentarios/%Y/%m/", blank=True)

    class Meta:
        ordering = ["creado_en"]

    def __str__(self):
        return f"{self.autor} — {self.cuerpo[:50]}"


class Actividad(TimeStamped):
    """'Programar seguimiento' de Odoo. Alimenta las alertas."""

    class Tipo(models.TextChoices):
        LLAMADA = "llamada", "Llamada"
        REUNION = "reunion", "Reunión"
        TAREA = "tarea", "Tarea"
        REVISION = "revision", "Revisión de documentos"
        ENVIO = "envio", "Envío / radicación"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="actividades")
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.TAREA)
    titulo = models.CharField(max_length=200)
    notas = models.TextField(blank=True)
    asignado_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="actividades")
    vence_en = models.DateTimeField(db_index=True)
    completada_en = models.DateTimeField(null=True, blank=True)
    evento_calendar_id = models.CharField(max_length=200, blank=True,
                                          help_text="ID en Google Calendar si se sincroniza.")

    class Meta:
        verbose_name_plural = "Actividades"
        ordering = ["vence_en"]


class Alerta(TimeStamped):
    class Tipo(models.TextChoices):
        CIERRE_PROXIMO = "cierre_proximo", "Cierre próximo"
        NUEVA_ADENDA = "nueva_adenda", "Nueva adenda publicada"
        ANALISIS_LISTO = "analisis_listo", "Análisis de IA listo"
        RIESGO_ALTO = "riesgo_alto", "Riesgo alto detectado"
        MENCION = "mencion", "Te mencionaron"
        ASIGNACION = "asignacion", "Proceso asignado"
        NO_CUMPLE = "no_cumple", "Requisito crítico no cumplido"

    proceso = models.ForeignKey(Proceso, on_delete=models.CASCADE, related_name="alertas")
    destinatario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="alertas")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    titulo = models.CharField(max_length=200)
    cuerpo = models.TextField(blank=True)
    leida_en = models.DateTimeField(null=True, blank=True)
    email_enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["destinatario", "leida_en"])]
