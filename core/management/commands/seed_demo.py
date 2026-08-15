import random
from datetime import timedelta
from decimal import Decimal

from auditlog.context import set_actor
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from core.models import Entidad, Usuario
from procesos import services as proc_services
from procesos.models import Proceso, Requisito, VersionDocumental
from social import services as social_services
from social.models import Actividad, Alerta

# Todo lo que genera este comando queda marcado con estos prefijos. Un
# re-run borra por prefijo/NIT y recrea — nunca toca datos sin el marcador,
# así que un superusuario o entidades reales nunca se ven afectados.
PREFIJO_PROCESO = "DEMO-"
PREFIJO_USUARIO = "demo_"

ENTIDADES_DEMO = [
    {"nombre": "Alcaldía de Medellín", "nit": "890905211-1", "orden": Entidad.Orden.MUNICIPAL,
     "sector": "Gobierno territorial", "departamento": "Antioquia", "municipio": "Medellín"},
    {"nombre": "Alcaldía de Bucaramanga", "nit": "890208001-1", "orden": Entidad.Orden.MUNICIPAL,
     "sector": "Gobierno territorial", "departamento": "Santander", "municipio": "Bucaramanga"},
    {"nombre": "Alcaldía de Santiago de Cali", "nit": "890399011-1", "orden": Entidad.Orden.MUNICIPAL,
     "sector": "Gobierno territorial", "departamento": "Valle del Cauca", "municipio": "Cali"},
    {"nombre": "Alcaldía de Pasto", "nit": "800103741-9", "orden": Entidad.Orden.MUNICIPAL,
     "sector": "Gobierno territorial", "departamento": "Nariño", "municipio": "Pasto"},
    {"nombre": "Gobernación de Antioquia", "nit": "890980040-2", "orden": Entidad.Orden.DEPARTAMENTAL,
     "sector": "Gobierno territorial", "departamento": "Antioquia", "municipio": "Medellín"},
    {"nombre": "Gobernación del Valle del Cauca", "nit": "890399029-6",
     "orden": Entidad.Orden.DEPARTAMENTAL, "sector": "Gobierno territorial",
     "departamento": "Valle del Cauca", "municipio": "Cali"},
    {"nombre": "Gobernación de Cundinamarca", "nit": "899999114-2",
     "orden": Entidad.Orden.DEPARTAMENTAL, "sector": "Gobierno territorial",
     "departamento": "Cundinamarca", "municipio": "Bogotá D.C."},
    {"nombre": "Instituto Nacional de Vías - INVÍAS", "nit": "800215807-6",
     "orden": Entidad.Orden.NACIONAL, "sector": "Infraestructura y transporte",
     "departamento": "Cundinamarca", "municipio": "Bogotá D.C."},
    {"nombre": "Instituto Colombiano de Bienestar Familiar - ICBF", "nit": "899999239-1",
     "orden": Entidad.Orden.NACIONAL, "sector": "Protección social",
     "departamento": "Cundinamarca", "municipio": "Bogotá D.C."},
    {"nombre": "E.S.E. Hospital Universitario del Valle", "nit": "890399008-1",
     "orden": Entidad.Orden.DESCENTRALIZADA, "sector": "Salud",
     "departamento": "Valle del Cauca", "municipio": "Cali"},
    {"nombre": "E.S.E. Hospital Departamental de Nariño", "nit": "800100486-3",
     "orden": Entidad.Orden.DESCENTRALIZADA, "sector": "Salud",
     "departamento": "Nariño", "municipio": "Pasto"},
    {"nombre": "E.S.E. Hospital Universitario del Caribe", "nit": "806008394-2",
     "orden": Entidad.Orden.DESCENTRALIZADA, "sector": "Salud",
     "departamento": "Bolívar", "municipio": "Cartagena"},
]

USUARIOS_DEMO = [
    {"username": "demo_mgomez", "first_name": "María", "last_name": "Gómez",
     "email": "maria.gomez@licitapro.demo", "cargo": "Analista comercial"},
    {"username": "demo_jperez", "first_name": "Juan", "last_name": "Pérez",
     "email": "juan.perez@licitapro.demo", "cargo": "Coordinador de licitaciones"},
    {"username": "demo_lrodriguez", "first_name": "Laura", "last_name": "Rodríguez",
     "email": "laura.rodriguez@licitapro.demo", "cargo": "Analista jurídica"},
]

OBJETOS_POR_CATEGORIA = {
    "suministro": [
        "Suministro de equipos de cómputo y conectividad para las sedes administrativas",
        "Suministro de elementos de protección personal para el personal operativo",
        "Suministro de medicamentos e insumos médico-quirúrgicos para la red hospitalaria",
        "Suministro de mobiliario escolar para instituciones educativas oficiales",
    ],
    "mantenimiento": [
        "Mantenimiento preventivo y correctivo de la infraestructura vial urbana",
        "Mantenimiento de redes eléctricas y alumbrado público en el área urbana y rural",
        "Mantenimiento locativo de las sedes administrativas de la entidad",
        "Mantenimiento de la flota vehicular y maquinaria amarilla",
    ],
    "interventoria": [
        "Interventoría técnica, administrativa, financiera y ambiental al contrato de obra pública",
        "Interventoría al proyecto de mejoramiento de vivienda rural",
        "Interventoría integral al programa de alimentación escolar",
        "Interventoría a las obras de construcción de la red de acueducto y alcantarillado",
    ],
    "dotacion": [
        "Dotación de vestido y calzado de labor para los funcionarios de la entidad",
        "Dotación de equipos biomédicos para los centros de salud de la red pública",
        "Dotación de material pedagógico y didáctico para los centros de desarrollo infantil",
        "Dotación de menaje y elementos de bioseguridad para los hogares comunitarios",
    ],
}

MOTIVOS_DESCARTE = [
    "No cumplimos la experiencia específica mínima exigida.",
    "El plazo de ejecución es incompatible con la carga operativa actual.",
    "El presupuesto oficial está por debajo del punto de equilibrio para la empresa.",
    "Las condiciones del contrato incluyen riesgos jurídicos no asumibles.",
]

# (indicador, operador, valor_umbral, unidad) — se ciclan entre los
# requisitos financieros de cada proceso con historial completo.
INDICADORES_FINANCIEROS = [
    ("indice_liquidez", ">=", Decimal("1.20"), "veces"),
    ("razon_endeudamiento", "<=", Decimal("65.00"), "%"),
    ("razon_cobertura_intereses", ">=", Decimal("1.50"), "veces"),
]

DESCRIPCIONES_POR_TIPO = {
    Requisito.Tipo.JURIDICO: [
        "Certificado de existencia y representación legal con vigencia no mayor a 30 días.",
        "Certificado de antecedentes disciplinarios, fiscales y de responsabilidad fiscal vigente.",
        "Garantía de seriedad de la oferta por el 10% del valor del presupuesto oficial.",
        "Registro Único de Proponentes (RUP) vigente y en firme.",
    ],
    Requisito.Tipo.FINANCIERO: [
        "Índice de liquidez mínimo exigido según el pliego de condiciones.",
        "Razón de endeudamiento máxima permitida según el pliego de condiciones.",
        "Cobertura de intereses mínima exigida para acreditar capacidad financiera.",
    ],
    Requisito.Tipo.TECNICO: [
        "Disponibilidad del equipo mínimo requerido para la ejecución del contrato.",
        "Personal técnico mínimo con experiencia certificada en el objeto contractual.",
        "Certificación de calidad ISO 9001 vigente del proponente.",
        "Plan de manejo ambiental para las actividades objeto del contrato.",
    ],
    Requisito.Tipo.EXPERIENCIA: [
        "Acreditar mínimo 3 contratos ejecutados con objeto similar en los últimos 5 años.",
        "Experiencia específica cuya sumatoria sea igual o superior al 100% del presupuesto oficial.",
        "Experiencia general no inferior a 5 años en el sector.",
    ],
}

NUMERAL_POR_TIPO = {
    Requisito.Tipo.JURIDICO: "3",
    Requisito.Tipo.FINANCIERO: "4",
    Requisito.Tipo.TECNICO: "5",
    Requisito.Tipo.EXPERIENCIA: "6",
}

CUMPLIMIENTOS_POSIBLES = [
    Requisito.Cumplimiento.CUMPLE, Requisito.Cumplimiento.CUMPLE, Requisito.Cumplimiento.CUMPLE,
    Requisito.Cumplimiento.PARCIAL, Requisito.Cumplimiento.NO_CUMPLE,
    Requisito.Cumplimiento.SUBSANABLE, Requisito.Cumplimiento.NO_APLICA,
]

# Reparto de los 40 procesos por estado. Cubre todo Proceso.Estado.
PLAN_ESTADOS = (
    [Proceso.Estado.DETECTADO] * 5
    + [Proceso.Estado.EN_EVALUACION] * 5
    + [Proceso.Estado.DESCARTADO] * 4
    + [Proceso.Estado.APTO] * 4
    + [Proceso.Estado.EN_PREPARACION] * 4
    + [Proceso.Estado.PRESENTADO] * 5
    + [Proceso.Estado.ADJUDICADO] * 5
    + [Proceso.Estado.NO_ADJUDICADO] * 4
    + [Proceso.Estado.DESIERTO] * 2
    + [Proceso.Estado.SUSPENDIDO] * 2
)

ESTADOS_POST_CIERRE = {
    Proceso.Estado.PRESENTADO, Proceso.Estado.ADJUDICADO,
    Proceso.Estado.NO_ADJUDICADO, Proceso.Estado.DESIERTO,
}

COMENTARIOS_SIMPLES = [
    "Ya tenemos el RUP actualizado, quedamos pendientes de subirlo al proceso.",
    "Quedó pendiente verificar la garantía de seriedad antes del cierre.",
    "Reviso el pliego hoy y comparto observaciones mañana a más tardar.",
    "Excelente, avancemos con la preparación de la propuesta técnica.",
    "La entidad respondió las observaciones, no hubo cambios de fondo.",
]

COMENTARIOS_CON_MENCION = [
    "@{usuario} ¿puedes confirmar el presupuesto con el área financiera?",
    "@{usuario} necesito que revises los requisitos jurídicos antes del viernes.",
    "Dejo la tarea a @{usuario}, avísenme si ven algún riesgo grande.",
    "@{usuario} quedamos pendientes de tu visto bueno para presentar.",
]


class Command(BaseCommand):
    help = (
        "Genera datos demo idempotentes (entidades, usuarios comerciales y procesos con "
        "historial documental completo). Reemplaza solo lo marcado con los prefijos "
        f"'{PREFIJO_PROCESO}' / '{PREFIJO_USUARIO}' — nunca toca usuarios ni entidades reales."
    )

    def handle(self, *args, **options):
        fake = Faker("es_CO")
        contadores = {
            "requisitos": 0, "versiones": 0, "comentarios": 0, "actividades": 0, "alertas": 0,
        }

        with transaction.atomic():
            self._limpiar()
            entidades = self._crear_entidades()
            usuarios = self._crear_usuarios()
            procesos = self._crear_procesos(entidades, usuarios)
            procesos_con_historial = [
                p for p in procesos if p.estado != Proceso.Estado.DETECTADO
            ][:8]
            self._crear_historial_documental(procesos_con_historial, usuarios, fake, contadores)

        contadores["alertas"] = self._contar_alertas(procesos_con_historial)

        self.stdout.write(self.style.SUCCESS("Datos demo generados:"))
        self.stdout.write(f"  Entidades: {len(entidades)}")
        self.stdout.write(f"  Usuarios comerciales demo: {len(usuarios)}")
        self.stdout.write(f"  Procesos: {len(procesos)}")
        self.stdout.write(f"  Con historial documental completo: {len(procesos_con_historial)}")
        self.stdout.write(f"  Versiones documentales: {contadores['versiones']}")
        self.stdout.write(f"  Requisitos: {contadores['requisitos']}")
        self.stdout.write(f"  Comentarios: {contadores['comentarios']}")
        self.stdout.write(f"  Actividades pendientes: {contadores['actividades']}")
        self.stdout.write(f"  Alertas de mención generadas: {contadores['alertas']}")

    # ---- limpieza ------------------------------------------------------
    def _limpiar(self):
        # Orden importa: procesos primero (cascada comentarios/actividades/
        # alertas/versiones/requisitos), luego usuarios demo (ya no los
        # referencia nada PROTECT), luego entidades (ya no las referencia
        # ningún proceso PROTECT).
        Proceso.objects.filter(numero_proceso__startswith=PREFIJO_PROCESO).delete()
        Usuario.objects.filter(username__startswith=PREFIJO_USUARIO).delete()
        Entidad.objects.filter(nit__in=[e["nit"] for e in ENTIDADES_DEMO]).delete()

    # ---- entidades y usuarios -------------------------------------------
    def _crear_entidades(self):
        return [Entidad.objects.create(**datos) for datos in ENTIDADES_DEMO]

    def _crear_usuarios(self):
        usuarios = []
        for datos in USUARIOS_DEMO:
            usuario = Usuario(**datos, activo_comercial=True)
            usuario.set_password("demo1234")
            usuario.save()
            usuarios.append(usuario)
        return usuarios

    # ---- procesos --------------------------------------------------------
    def _crear_procesos(self, entidades, usuarios):
        plan = list(PLAN_ESTADOS)
        random.shuffle(plan)
        ahora = timezone.now()
        procesos = []

        for indice, estado_objetivo in enumerate(plan, start=1):
            actor = random.choice(usuarios)
            fecha_cierre = self._fecha_cierre_para(estado_objetivo, ahora)
            categoria = random.choice(list(OBJETOS_POR_CATEGORIA))
            proceso = Proceso.objects.create(
                numero_proceso=f"{PREFIJO_PROCESO}{indice:04d}",
                entidad=random.choice(entidades),
                objeto=random.choice(OBJETOS_POR_CATEGORIA[categoria]),
                modalidad=random.choice(list(Proceso.Modalidad.values)),
                url_secop=f"https://community.secop.gov.co/Public/Tendering/OpportunityDetail/"
                          f"Index?noticeUID=DEMO-{indice:04d}",
                presupuesto_oficial=Decimal(random.randrange(50_000_000, 3_000_000_001, 500_000)),
                plazo_ejecucion_dias=random.randint(30, 365),
                fecha_publicacion=(fecha_cierre - timedelta(days=random.randint(15, 45))).date(),
                fecha_limite_observaciones=fecha_cierre - timedelta(days=random.randint(2, 10)),
                fecha_cierre=fecha_cierre,
                responsable=actor,
            )
            self._avanzar_a_estado(proceso, actor, estado_objetivo)

            if estado_objetivo in {
                Proceso.Estado.ADJUDICADO, Proceso.Estado.NO_ADJUDICADO, Proceso.Estado.DESIERTO,
            }:
                proceso.fecha_adjudicacion = (
                    fecha_cierre + timedelta(days=random.randint(10, 45))
                ).date()
                with set_actor(actor):
                    proceso.save()

            procesos.append(proceso)

        # La mitad queda con fechas verificadas por un humano; la otra
        # mitad se deja "sin verificar" a propósito (invariante 3).
        random.shuffle(procesos)
        for proceso in procesos[: len(procesos) // 2]:
            proc_services.verificar_fechas(proceso, random.choice(usuarios))

        return sorted(procesos, key=lambda p: p.numero_proceso)

    def _fecha_cierre_para(self, estado, ahora):
        if estado in ESTADOS_POST_CIERRE:
            return ahora - timedelta(days=random.randint(3, 90))

        balde = random.choices(["vencido", "proximo", "lejano"], weights=[20, 35, 45])[0]
        if balde == "vencido":
            return ahora - timedelta(days=random.randint(1, 30))
        if balde == "proximo":
            return ahora + timedelta(hours=random.randint(2, 120))
        return ahora + timedelta(days=random.randint(6, 90))

    def _avanzar_a_estado(self, proceso, actor, estado_objetivo):
        Estado = Proceso.Estado

        if estado_objetivo == Estado.SUSPENDIDO:
            if random.random() < 0.5:
                proc_services.iniciar_evaluacion(proceso, actor)
            proc_services.suspender(proceso, actor)
            return

        if estado_objetivo == Estado.DETECTADO:
            return

        proc_services.iniciar_evaluacion(proceso, actor)
        if estado_objetivo == Estado.EN_EVALUACION:
            return

        if estado_objetivo == Estado.DESCARTADO:
            proc_services.descartar(proceso, actor, motivo=random.choice(MOTIVOS_DESCARTE))
            return

        proc_services.marcar_apto(proceso, actor)
        if estado_objetivo == Estado.APTO:
            return

        proc_services.iniciar_preparacion(proceso, actor)
        if estado_objetivo == Estado.EN_PREPARACION:
            return

        proc_services.presentar(proceso, actor)
        if estado_objetivo == Estado.PRESENTADO:
            return

        if estado_objetivo == Estado.ADJUDICADO:
            proc_services.adjudicar(proceso, actor)
        elif estado_objetivo == Estado.NO_ADJUDICADO:
            proc_services.perder(proceso, actor)
        elif estado_objetivo == Estado.DESIERTO:
            proc_services.declarar_desierto(proceso, actor)

    # ---- historial documental (requisitos, adendas, chatter) -----------
    def _crear_historial_documental(self, procesos, usuarios, fake, contadores):
        for proceso in procesos:
            v0 = proc_services.crear_version(
                proceso, tipo=VersionDocumental.Tipo.DEFINITIVO, fecha=proceso.fecha_publicacion,
            )
            v0.procesada = True
            v0.save()
            contadores["versiones"] += 1

            requisitos_v0 = self._crear_requisitos(proceso, v0, fake)
            contadores["requisitos"] += len(requisitos_v0)

            vigentes = list(requisitos_v0)
            for _ in range(random.randint(1, 2)):
                version_adenda = proc_services.crear_version(
                    proceso, tipo=VersionDocumental.Tipo.ADENDA,
                    fecha=proceso.fecha_publicacion + timedelta(days=random.randint(3, 12)),
                )
                contadores["versiones"] += 1
                a_derogar = random.sample(vigentes, k=min(2, len(vigentes)))
                for viejo in a_derogar:
                    nuevo = self._derogar_con_ajuste(viejo, version_adenda)
                    vigentes.remove(viejo)
                    vigentes.append(nuevo)
                    contadores["requisitos"] += 1

            self._verificar_algunos_requisitos(vigentes, usuarios, fake)
            contadores["comentarios"] += self._crear_comentarios(proceso, usuarios)

        # Un par de actividades pendientes repartidas entre los procesos
        # con historial, no una por proceso.
        for proceso in random.sample(procesos, k=min(3, len(procesos))):
            social_services.programar_actividad(
                proceso,
                asignado_a=random.choice(usuarios),
                tipo=random.choice(Actividad.Tipo.values),
                titulo=random.choice([
                    "Llamar a la entidad para confirmar cronograma",
                    "Revisar observaciones al pliego antes del cierre",
                    "Radicar la propuesta técnica y económica",
                    "Enviar RUP actualizado al área jurídica",
                ]),
                vence_en=timezone.now() + timedelta(days=random.randint(1, 10)),
                notas="Generado por seed_demo.",
            )
            contadores["actividades"] += 1

    def _crear_requisitos(self, proceso, version, fake):
        tipos_pool = (
            [Requisito.Tipo.JURIDICO] * 3 + [Requisito.Tipo.FINANCIERO] * 3
            + [Requisito.Tipo.TECNICO] * 3 + [Requisito.Tipo.EXPERIENCIA] * 3
        )
        cantidad = random.randint(10, 15)
        tipos = random.choices(tipos_pool, k=cantidad)
        # al menos dos financieros con indicador real, sin importar el azar
        if tipos.count(Requisito.Tipo.FINANCIERO) < 2:
            tipos[0], tipos[1] = Requisito.Tipo.FINANCIERO, Requisito.Tipo.FINANCIERO

        contadores_por_tipo = {}
        indice_financiero = 0
        requisitos = []
        for tipo in tipos:
            contadores_por_tipo[tipo] = contadores_por_tipo.get(tipo, 0) + 1
            numeral = f"{NUMERAL_POR_TIPO[tipo]}.{contadores_por_tipo[tipo]}"
            descripcion = random.choice(DESCRIPCIONES_POR_TIPO[tipo])

            datos = {
                "proceso": proceso, "version_origen": version, "tipo": tipo,
                "numeral": numeral, "descripcion": descripcion,
                "cita_pagina": random.randint(1, 40), "cita_texto": fake.sentence(nb_words=10),
                "confianza": round(random.uniform(0.75, 0.98), 2),
                "es_critico": random.random() < 0.3,
            }
            if tipo == Requisito.Tipo.FINANCIERO:
                indicador, operador, valor, unidad = INDICADORES_FINANCIEROS[
                    indice_financiero % len(INDICADORES_FINANCIEROS)
                ]
                indice_financiero += 1
                datos.update(
                    indicador=indicador, operador=operador, valor_umbral=valor,
                    unidad=unidad, es_critico=True,
                )
            requisitos.append(Requisito.objects.create(**datos))
        return requisitos

    def _derogar_con_ajuste(self, requisito_viejo, version_adenda):
        datos_nuevos = {
            "tipo": requisito_viejo.tipo,
            "numeral": requisito_viejo.numeral,
            "descripcion": f"(Adenda) {requisito_viejo.descripcion} Condición ajustada por la entidad.",
            "cita_pagina": requisito_viejo.cita_pagina,
            "cita_texto": requisito_viejo.cita_texto,
            "es_critico": requisito_viejo.es_critico,
        }
        if requisito_viejo.tipo == Requisito.Tipo.FINANCIERO and requisito_viejo.valor_umbral:
            factor = Decimal("0.9") if requisito_viejo.operador == ">=" else Decimal("1.1")
            datos_nuevos.update(
                indicador=requisito_viejo.indicador,
                operador=requisito_viejo.operador,
                valor_umbral=(requisito_viejo.valor_umbral * factor).quantize(Decimal("0.01")),
                unidad=requisito_viejo.unidad,
            )
        return proc_services.derogar_requisito(requisito_viejo, datos_nuevos, version_adenda)

    def _verificar_algunos_requisitos(self, vigentes, usuarios, fake):
        for requisito in vigentes:
            if random.random() >= 0.65:
                continue
            requisito.cumplimiento = random.choice(CUMPLIMIENTOS_POSIBLES)
            requisito.justificacion = fake.sentence(nb_words=12)
            requisito.verificado_por = random.choice(usuarios)
            requisito.verificado_en = timezone.now() - timedelta(days=random.randint(0, 15))
            requisito.save()

    def _crear_comentarios(self, proceso, usuarios):
        creados = 0
        for _ in range(random.randint(2, 4)):
            autor = random.choice(usuarios)
            if random.random() < 0.5 and len(usuarios) > 1:
                mencionado = random.choice([u for u in usuarios if u != autor])
                cuerpo = random.choice(COMENTARIOS_CON_MENCION).format(usuario=mencionado.username)
            else:
                cuerpo = random.choice(COMENTARIOS_SIMPLES)
            social_services.publicar_comentario(proceso, autor, cuerpo)
            creados += 1
        return creados

    def _contar_alertas(self, procesos):
        return Alerta.objects.filter(proceso__in=procesos, tipo=Alerta.Tipo.MENCION).count()
