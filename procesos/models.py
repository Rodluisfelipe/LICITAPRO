from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition

from core.models import CodigoUNSPSC, Entidad, Origen, TimeStamped
from procesos.permisos import CATALOGO_PERMISOS


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
    numero_proceso = models.CharField(
        max_length=120, db_index=True, help_text="Número SECOP o referencia interna.",
    )
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
    estado = FSMField(
        default=Estado.DETECTADO, choices=Estado.choices, protected=True, db_index=True,
    )
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

    # --- triage de IA (kanban/lista). origen=IA por definición: puntaje_ajuste
    # nunca se muestra como dato verificado por un humano (invariante 4).
    puntaje_ajuste = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0-100. Lo calcula un AnalisisIA de tipo TRIAGE.",
    )
    lectura_ia = models.TextField(blank=True, help_text="1-2 frases de lectura del modelo.")
    confianza_ia = models.FloatField(null=True, blank=True)
    analisis_en_curso = models.BooleanField(default=False)
    analisis_paginas = models.PositiveIntegerField(null=True, blank=True)
    analisis_pagina_actual = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha_cierre"]
        indexes = [
            models.Index(fields=["estado", "fecha_cierre"]),
            models.Index(fields=["entidad", "-creado_en"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["entidad", "numero_proceso"], name="uq_proceso_entidad_numero",
            ),
        ]
        # Catálogo en procesos/permisos.py — única fuente de verdad, la
        # interfaz de perfiles lee de ahí, no de acá.
        permissions = [
            (codename, etiqueta)
            for modulo in CATALOGO_PERMISOS.values()
            for app_label, codename, etiqueta in modulo
            if app_label == "procesos"
        ]

    def __str__(self):
        return f"{self.numero_proceso} — {self.entidad.nombre}"

    # ---- máquina de estados -------------------------------------------------
    @transition(field=estado, source=Estado.DETECTADO, target=Estado.EN_EVALUACION)
    def iniciar_evaluacion(self):
        pass

    @transition(
        field=estado,
        source=[Estado.DETECTADO, Estado.EN_EVALUACION, Estado.APTO],
        target=Estado.DESCARTADO,
    )
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

    @transition(field=estado, source=Estado.PRESENTADO, target=Estado.ADJUDICADO)
    def adjudicar(self):
        pass

    @transition(field=estado, source=Estado.PRESENTADO, target=Estado.NO_ADJUDICADO)
    def perder(self):
        pass

    @transition(field=estado, source=Estado.PRESENTADO, target=Estado.DESIERTO)
    def declarar_desierto(self):
        pass

    @transition(field=estado, source="*", target=Estado.SUSPENDIDO)
    def suspender(self):
        pass

    # ---- helpers ------------------------------------------------------------
    @property
    def requisitos_vigentes(self):
        """Solo los requisitos que ninguna adenda posterior derogó."""
        return self.requisitos.filter(reemplazado_por__isnull=True)

    COLOR_POR_ESTADO = {
        Estado.DETECTADO: "gris",
        Estado.EN_EVALUACION: "azul",
        Estado.DESCARTADO: "rojo",
        Estado.APTO: "verde",
        Estado.EN_PREPARACION: "azul",
        Estado.PRESENTADO: "amarillo",
        Estado.ADJUDICADO: "verde",
        Estado.NO_ADJUDICADO: "rojo",
        Estado.DESIERTO: "gris",
        Estado.SUSPENDIDO: "amarillo",
    }

    @property
    def color_estado(self) -> str:
        return self.COLOR_POR_ESTADO.get(self.estado, "gris")

    @property
    def dias_para_cierre(self) -> int | None:
        """Días hasta `fecha_cierre`. Negativo si ya pasó. None si no hay fecha."""
        if not self.fecha_cierre:
            return None
        return (self.fecha_cierre - timezone.now()).days

    @property
    def cierre_proximo(self) -> bool:
        dias = self.dias_para_cierre
        return dias is not None and 0 <= dias < 5

    # Camino "feliz" del proceso, para el statusbar. Los estados de salida
    # (descartado, no_adjudicado, desierto, suspendido) quedan fuera a
    # propósito: se muestran como acciones laterales, no como una etapa más.
    ETAPAS_PIPELINE = [
        Estado.DETECTADO, Estado.EN_EVALUACION, Estado.APTO,
        Estado.EN_PREPARACION, Estado.PRESENTADO, Estado.ADJUDICADO,
    ]


class VersionDocumental(TimeStamped):
    """
    Un pliego no es un documento: es una secuencia. Proyecto -> definitivo ->
    adenda 1 -> adenda 2. Cada adenda puede derogar requisitos ya extraídos
    de una versión anterior.
    """

    class Tipo(models.TextChoices):
        PROYECTO = "proyecto", "Proyecto de pliego"
        DEFINITIVO = "definitivo", "Pliego definitivo"
        ADENDA = "adenda", "Adenda"
        RESPUESTA_OBS = "respuesta_obs", "Respuesta a observaciones"
        ANEXO = "anexo", "Anexo técnico"
        CRONOGRAMA = "cronograma", "Modificación de cronograma"

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
            models.UniqueConstraint(
                fields=["proceso", "secuencia"], name="uq_version_proceso_secuencia",
            ),
        ]

    def __str__(self):
        return f"{self.proceso.numero_proceso} v{self.secuencia} ({self.get_tipo_display()})"


class Requisito(TimeStamped):
    """
    Requisito habilitante o de evaluación.

    INMUTABLE: una adenda no edita el requisito anterior, crea uno nuevo y
    apunta `reemplaza` al viejo. No hacer UPDATE sobre `descripcion` ni
    `valor_umbral` de un requisito ya publicado — usar
    `procesos.services.derogar_requisito`.
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
    version_origen = models.ForeignKey(
        VersionDocumental, on_delete=models.CASCADE, related_name="requisitos_introducidos",
    )
    reemplaza = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reemplazado_por",
        help_text="Requisito de una versión anterior que este deroga.",
    )

    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    numeral = models.CharField(
        max_length=40, blank=True, help_text="Ej: 3.2.1 — para trazabilidad al pliego.",
    )
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
    cita_texto = models.TextField(
        blank=True, help_text="Fragmento literal que sustenta el requisito.",
    )
    confianza = models.FloatField(null=True, blank=True)

    # --- evaluación contra el perfil de la empresa
    cumplimiento = models.CharField(
        max_length=20, choices=Cumplimiento.choices,
        default=Cumplimiento.POR_VERIFICAR, db_index=True,
    )
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


class Riesgo(TimeStamped):
    """
    Semáforo de riesgos con taxonomía CERRADA (invariante 5 de CLAUDE.md).

    No se le pregunta al modelo "¿qué riesgos ves?" — se le pide detectar y
    citar riesgos de esta lista. Un semáforo determinista es auditable; uno
    generativo es una opinión.
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
    version_origen = models.ForeignKey(
        VersionDocumental, null=True, blank=True, on_delete=models.SET_NULL, related_name="riesgos",
    )
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
