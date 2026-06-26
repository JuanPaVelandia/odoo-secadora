# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - RETENCIONES EN LA FUENTE
=============================================

Implementación del cálculo de retención en la fuente según normatividad colombiana.

Base Legal:
- Art. 383 ET: Tabla de tarifas marginales
- Art. 385 ET: Procedimiento 1 (Cálculo mensual)
- Art. 386 ET: Procedimiento 2 (Porcentaje fijo semestral)
- Art. 387 ET: Deducciones permitidas
- Art. 206 Num. 10 ET: Renta exenta laboral 25%
- Art. 336 ET: Límite global 40%
- Art. 126-1 y 126-4 ET: AFC/AVC
- Ley 2277 de 2022: Reforma tributaria
"""

from odoo import models, api
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import TABLA_RETENCION
from .config_reglas import crear_log_data, crear_resultado_regla, crear_resultado_vacio


# ═══════════════════════════════════════════════════════════════════════════════
# ESTRUCTURA NORMATIVA - CONSTANTES Y TOPES LEGALES
# ═══════════════════════════════════════════════════════════════════════════════

NORMATIVA_RETENCION = {
    # ─────────────────────────────────────────────────────────────────────────
    # PASO 1: INGRESOS BRUTOS
    # ─────────────────────────────────────────────────────────────────────────
    'paso_1_ingresos': {
        'nombre': 'Ingresos Laborales Brutos',
        'base_legal': 'Art. 103 ET - Definición de rentas de trabajo',
        'elemento_ley': 'Se consideran rentas de trabajo las obtenidas por personas naturales por concepto de salarios, comisiones, prestaciones sociales, viáticos, gastos de representación, honorarios, emolumentos eclesiásticos, compensaciones recibidas por el trabajo asociado cooperativo y, en general, las compensaciones por servicios personales.',
        'categorias_incluir': ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL', 'COMISIONES', 'HEYREC'],
        'categorias_excluir': ['CESANTIAS', 'INT_CESANTIAS'],
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 2: INGRESOS NO CONSTITUTIVOS DE RENTA (INCR)
    # ─────────────────────────────────────────────────────────────────────────
    'paso_2_incr': {
        'nombre': 'Ingresos No Constitutivos de Renta',
        'base_legal': 'Art. 55 y 56 ET',
        'elemento_ley': 'Los aportes obligatorios que efectúen los trabajadores a los fondos de pensiones y los aportes al sistema de seguridad social en salud no hacen parte de la base para aplicar la retención en la fuente.',
        'componentes': {
            'salud': {
                'codigo': 'SSOCIAL001',
                'nombre': 'Aporte Salud Empleado',
                'base_legal': 'Art. 56 ET',
                'porcentaje': 4.0,
            },
            'pension': {
                'codigo': 'SSOCIAL002',
                'nombre': 'Aporte Pensión Obligatoria Empleado',
                'base_legal': 'Art. 55 ET',
                'porcentaje': 4.0,
            },
            'solidaridad': {
                'codigo': 'SSOCIAL003',
                'nombre': 'Fondo de Solidaridad Pensional',
                'base_legal': 'Art. 55 ET, Ley 797/2003 Art. 7',
                'porcentaje': 'variable (1% a 2%)',
                'aplica_desde': '4 SMMLV',
            },
            'subsistencia': {
                'codigo': 'SSOCIAL004',
                'nombre': 'Fondo de Subsistencia',
                'base_legal': 'Art. 55 ET, Ley 797/2003 Art. 7',
                'porcentaje': 'variable (0.2% a 1%)',
                'aplica_desde': '16 SMMLV',
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 3: DEDUCCIONES TRIBUTARIAS
    # ─────────────────────────────────────────────────────────────────────────
    'paso_3_deducciones': {
        'nombre': 'Deducciones Tributarias',
        'base_legal': 'Art. 387 ET',
        'elemento_ley': 'Los pagos efectuados por los siguientes conceptos son deducibles de la base de retención: intereses en préstamos para adquisición de vivienda, pagos de salud prepagada y dependientes económicos.',
        'deducciones': {
            'dependientes': {
                'codigo': 'DED_DEPENDIENTES',
                'nombre': 'Deducción por Dependientes',
                'base_legal': 'Art. 387 Num. 1 ET',
                'elemento_ley': 'Se permite la deducción del 10% del total de ingresos brutos, hasta un máximo de 32 UVT mensuales, por concepto de dependientes.',
                'calculo': 'porcentaje',
                'porcentaje_base': 10,
                'tope_uvt_mensual': 32,
                'tope_uvt_anual': 384,
                'requisitos': [
                    'Hijos menores de edad',
                    'Hijos entre 18 y 23 años por dependencia económica o estudiando',
                    'Hijos mayores de 23 años en situación de discapacidad',
                    'Cónyuge o compañero permanente en situación de dependencia',
                    'Padres o hermanos en situación de dependencia económica',
                ],
            },
            'prepagada': {
                'codigo': 'DED_PREPAGADA',
                'nombre': 'Medicina Prepagada y Seguros de Salud',
                'base_legal': 'Art. 387 Num. 2 ET',
                'elemento_ley': 'Los pagos por seguros de salud y planes complementarios de salud son deducibles hasta un máximo de 16 UVT mensuales.',
                'calculo': 'valor_pagado',
                'tope_uvt_mensual': 16,
                'tope_uvt_anual': 192,
            },
            'vivienda': {
                'codigo': 'DED_VIVIENDA',
                'nombre': 'Intereses de Vivienda',
                'base_legal': 'Art. 119 ET y Art. 387 Num. 3 ET',
                'elemento_ley': 'Los intereses o corrección monetaria en virtud de préstamos para adquisición de vivienda son deducibles hasta 100 UVT mensuales.',
                'calculo': 'valor_certificado',
                'tope_uvt_mensual': 100,
                'tope_uvt_anual': 1200,
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 4: RENTAS EXENTAS (AFC/AVC)
    # ─────────────────────────────────────────────────────────────────────────
    'paso_4_rentas_exentas': {
        'nombre': 'Rentas Exentas - Aportes Voluntarios',
        'base_legal': 'Art. 126-1 y 126-4 ET',
        'elemento_ley': 'Los aportes voluntarios a fondos de pensiones y cuentas AFC que realice el trabajador, el empleador o ambos, no harán parte de la base para aplicar retención en la fuente, siempre que sumados no excedan el 30% del ingreso laboral o tributario del año y hasta 3.800 UVT anuales.',
        'rentas': {
            'afc': {
                'codigo': 'AFC',
                'nombre': 'Aportes a Cuentas AFC',
                'base_legal': 'Art. 126-4 ET',
                'elemento_ley': 'Los retiros de las cuentas de Ahorro para el Fomento de la Construcción (AFC) mantendrán el tratamiento de renta exenta siempre que se destinen a la adquisición de vivienda.',
                'limite_porcentaje': 30,
                'limite_base': 'Ingreso Tributario (Subtotal 1)',
                'tope_uvt_anual': 3800,
            },
            'avc': {
                'codigo': 'AVC',
                'nombre': 'Aportes Voluntarios a Pensión',
                'base_legal': 'Art. 126-1 ET',
                'elemento_ley': 'Los aportes voluntarios a fondos de pensiones obligatorias son renta exenta hasta el límite del 30% del ingreso laboral o tributario del año.',
                'limite_porcentaje': 30,
                'limite_base': 'Ingreso Tributario (Subtotal 1)',
                'tope_uvt_anual': 3800,
                'nota': 'AFC + AVC comparten el mismo límite global',
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 5: RENTA EXENTA LABORAL 25%
    # ─────────────────────────────────────────────────────────────────────────
    'paso_5_renta_exenta_25': {
        'nombre': 'Renta Exenta Laboral del 25%',
        'base_legal': 'Art. 206 Numeral 10 ET (Ley 2277/2022)',
        'elemento_ley': 'El veinticinco por ciento (25%) del valor total de los pagos laborales, limitado anualmente a setecientos noventa (790) UVT. El cálculo de esta renta exenta se efectuará una vez se detraigan del valor total de los pagos laborales recibidos por el trabajador, los ingresos no constitutivos de renta, las deducciones y las demás rentas exentas diferentes al 25%.',
        'porcentaje': 25,
        'tope_uvt_mensual': 65.83,  # 790 / 12
        'tope_uvt_anual': 790,
        'orden_calculo': 'Aplicar DESPUÉS de deducciones y otras rentas exentas',
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 6: LÍMITE GLOBAL DEL 40%
    # ─────────────────────────────────────────────────────────────────────────
    'paso_6_limite_global': {
        'nombre': 'Límite Global a Deducciones y Rentas Exentas',
        'base_legal': 'Art. 336 ET (Ley 2277/2022)',
        'elemento_ley': 'La suma de todas las rentas exentas y deducciones imputables a las rentas de trabajo no podrá superar el cuarenta por ciento (40%) del resultado de restar del monto del pago o abono en cuenta los ingresos no constitutivos de renta, ni podrá superar 1.340 UVT anuales.',
        'componentes_sujetos': [
            'Deducciones (dependientes, prepagada, vivienda)',
            'Rentas exentas (AFC, AVC)',
            'Renta exenta 25%',
        ],
        'limite_porcentaje': 40,
        'limite_base': 'Subtotal 1 (Ingresos - INCR)',
        'tope_uvt_anual': 1340,
        'tope_uvt_mensual': 111.67,  # 1340/12
    },

    # ─────────────────────────────────────────────────────────────────────────
    # PASO 7: TABLA DE RETENCIÓN
    # ─────────────────────────────────────────────────────────────────────────
    'paso_7_tabla_retencion': {
        'nombre': 'Aplicación de Tarifa de Retención',
        'base_legal': 'Art. 383 ET',
        'elemento_ley': 'La retención en la fuente aplicable a los pagos gravables efectuados por las personas naturales o jurídicas, las sociedades de hecho y las comunidades organizadas, originados en la relación laboral, o legal y reglamentaria, será la que resulte de aplicar a dichos pagos la tabla de retención.',
        'tabla': [
            {'desde': 0, 'hasta': 95, 'tarifa': 0, 'resta_uvt': 0, 'suma_uvt': 0},
            {'desde': 95, 'hasta': 150, 'tarifa': 19, 'resta_uvt': 95, 'suma_uvt': 0},
            {'desde': 150, 'hasta': 360, 'tarifa': 28, 'resta_uvt': 150, 'suma_uvt': 10},
            {'desde': 360, 'hasta': 640, 'tarifa': 33, 'resta_uvt': 360, 'suma_uvt': 69},
            {'desde': 640, 'hasta': 945, 'tarifa': 35, 'resta_uvt': 640, 'suma_uvt': 162},
            {'desde': 945, 'hasta': 2300, 'tarifa': 37, 'resta_uvt': 945, 'suma_uvt': 268},
            {'desde': 2300, 'hasta': float('inf'), 'tarifa': 39, 'resta_uvt': 2300, 'suma_uvt': 770},
        ],
        'formula': '((Base_UVT - Resta_UVT) * Tarifa%) + Suma_UVT) * Valor_UVT',
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CASOS ESPECIALES
    # ─────────────────────────────────────────────────────────────────────────
    'casos_especiales': {
        'aprendices': {
            'nombre': 'Contrato de Aprendizaje',
            'base_legal': 'Ley 789/2002 Art. 30',
            'elemento_ley': 'Durante la fase práctica el aprendiz estará afiliado como independiente y la cotización será cubierta plenamente por la empresa patrocinadora. El apoyo de sostenimiento no constituye salario.',
            'aplica_retencion': False,
        },
        'extranjero_no_residente': {
            'nombre': 'Extranjero No Residente',
            'base_legal': 'Art. 408 ET',
            'elemento_ley': 'Los pagos o abonos en cuenta por concepto de rentas de trabajo realizados a personas naturales no residentes en el país están sometidos a una tarifa del 20% a título de retención en la fuente.',
            'tarifa_fija': 20,
        },
        'salario_integral': {
            'nombre': 'Salario Integral',
            'base_legal': 'Art. 132 CST, Art. 206 Par. 2 ET',
            'elemento_ley': 'En el caso del salario integral, el 25% de renta exenta se aplica sobre el 70% que constituye factor salarial.',
            'factor_salarial': 70,
            'factor_prestacional': 30,
        },
        'prima_servicios': {
            'nombre': 'Prima de Servicios',
            'base_legal': 'Art. 385 Parágrafo ET',
            'elemento_ley': 'La prima de servicios tiene su propia depuración independiente para efectos de retención en la fuente.',
            'calculo_independiente': True,
        },
    },
}


class HrSalaryRuleRetenciones(models.AbstractModel):
    """
    Mixin para reglas de retenciones en la fuente.

    Implementa el cálculo de retención según la normatividad colombiana
    con trazabilidad de base legal en cada paso.
    """

    _name = 'hr.salary.rule.retenciones'
    _description = 'Métodos para Retenciones en la Fuente'

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODO PRINCIPAL - ORQUESTADOR
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_retention_generic(self, localdict, tipo='nomina'):
        """
        Método genérico para retención en la fuente.

        Soporta procedimientos:
        - '100': Procedimiento 1 - Cálculo mensual (Art. 385 ET)
        - '102': Procedimiento 2 - Porcentaje fijo (Art. 386 ET)
        - 'fixed': Monto fijo definido en contrato
        - 'extranjero_no_residente': 20% sobre ingresos (Art. 408 ET)

        Args:
            localdict: Diccionario de contexto de nómina
            tipo: Tipo de retención ('nomina', 'prima', etc.)

        Returns:
            Tuple: (rate, quantity, percentage, name, log_data_dict, extra_data_dict)
        """
        contract = localdict['contract']
        slip = localdict['slip']
        employee = localdict['employee']
        annual_parameters = localdict.get('annual_parameters')

        # Inicializar diccionario de datos con trazabilidad normativa
        retention_data = {
            'tipo': tipo,
            'year': slip.date_to.year,
            'month': slip.date_to.month,
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'document': employee.identification_id or ''
            },
            'normativa': NORMATIVA_RETENCION,  # Incluir estructura normativa
            'pasos_aplicados': [],
        }

        # ═══════════════════════════════════════════════════════════════════
        # CASO ESPECIAL: Aprendices SENA - No aplica retencion
        # Base Legal: Ley 789/2002 Art. 30
        # ═══════════════════════════════════════════════════════════════════
        contract_category = contract.contract_type_id.contract_category if contract.contract_type_id else ''
        if contract_category == 'aprendizaje':
            retention_data['status'] = 'no_applicable'
            retention_data['reason'] = 'contract_type_apprentice'
            retention_data['base_legal'] = NORMATIVA_RETENCION['casos_especiales']['aprendices']['base_legal']
            retention_data['elemento_ley'] = NORMATIVA_RETENCION['casos_especiales']['aprendices']['elemento_ley']
            localdict['retention_data'] = retention_data
            return 0, 0, 0, 'No aplica para aprendices (Ley 789/2002)', retention_data, {}

        # Determinar método según procedimiento configurado en contrato
        resultado = None
        if contract.retention_procedure:
            if contract.retention_procedure == 'extranjero_no_residente':
                resultado = self._calculate_retention_foreigner(localdict, retention_data)
            elif contract.retention_procedure == 'fixed':
                resultado = self._calculate_retention_fixed(localdict, retention_data)

        if not resultado:
            resultado = self._calculate_retention_ordinary(localdict, retention_data, tipo)

        # Crear registro de reporte
        if resultado and len(resultado) >= 6 and resultado[5]:
            try:
                retention_kpi = localdict.get('retention_kpi', resultado[5])
                retention_data_final = localdict.get('retention_data', resultado[4])
                self._crear_registro_retencion(localdict, retention_kpi, retention_data_final)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Error creando registro retención: {e}")

        return resultado

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS AUXILIARES CON BASE LEGAL
    # ═══════════════════════════════════════════════════════════════════════════

    def _calcular_dias_trabajados_ret(self, localdict):
        """Calcula los días trabajados en el período."""
        dias_trabajados = 30
        worked_days = localdict.get('worked_days', {})
        work100 = worked_days.get('WORK100')
        if work100:
            dias_trabajados = work100.number_of_days
        return dias_trabajados

    def _verificar_proyeccion_ret(self, contract, slip):
        """
        Verifica si debe proyectar la retención (nóminas quincenales).
        Solo proyecta si:
        1. Contrato tiene proyectar_ret=True
        2. El período es quincenal (≤ 16 días)
        3. Es la primera quincena (date_from.day <= 15)
        """
        if not contract.proyectar_ret:
            return False

        # Verificar duración del período
        dias_periodo = (slip.date_to - slip.date_from).days + 1

        # Solo proyectar si es período quincenal (hasta 16 días) y es primera quincena
        return dias_periodo <= 16 and slip.date_from.day <= 15

    def _obtener_lineas_detalle(self, localdict, categorias=None, codigos=None, excluir_codigos=None, incluir_ceros=False):
        """
        Obtiene el detalle de líneas de nómina con ID, código, nombre y valor.

        Args:
            localdict: Diccionario de contexto de nómina
            categorias: Lista de categorías a incluir (ej: ['BASIC', 'DEV_SALARIAL'])
            codigos: Lista de códigos específicos a incluir
            excluir_codigos: Lista de códigos a excluir (ej: ['CESANTIAS', 'INT_CESANTIAS'])
            incluir_ceros: Si True, incluye líneas con valor 0

        Returns:
            list: Lista de diccionarios con detalle de cada línea
        """
        excluir_codigos = excluir_codigos or []
        lineas_detalle = []

        rules = localdict.get('rules', {})

        for code, rule_data in rules.items():
            if code in excluir_codigos:
                continue

            rule_obj = rule_data.rule if rule_data else None
            if not rule_obj:
                continue

            # Excluir si tiene excluir_ret marcado
            if rule_obj.excluir_ret:
                continue

            # Filtrar por categorías si se especifican
            if categorias:
                cat_code = rule_obj.category_id.code if rule_obj.category_id else ''
                parent_cat_code = rule_obj.category_id.parent_id.code if rule_obj.category_id and rule_obj.category_id.parent_id else ''
                if cat_code not in categorias and parent_cat_code not in categorias:
                    continue

            # Filtrar por códigos específicos si se especifican
            if codigos and code not in codigos:
                continue

            valor = rule_data.total or 0
            # Incluir línea si tiene valor o si incluir_ceros=True
            if valor != 0 or incluir_ceros:
                lineas_detalle.append({
                    'id': rule_obj.id,
                    'code': code,
                    'name': rule_obj.name,
                    'category_id': rule_obj.category_id.id if rule_obj.category_id else False,
                    'category_code': rule_obj.category_id.code if rule_obj.category_id else '',
                    'category_name': rule_obj.category_id.name if rule_obj.category_id else '',
                    'quantity': rule_data.quantity or 0,
                    'amount': rule_data.amount or 0,
                    'total': valor,
                })

        return lineas_detalle

    def _calcular_ingresos_ret(self, localdict, tipo_especial=None):
        """
        PASO 1: Calcular Ingresos Laborales Brutos
        Base Legal: Art. 103 ET

        Estructura de depuración:
        - Sueldo básico
        - Auxilio de transporte
        - Comisiones
        - Horas extras y recargos
        - Bonificaciones
        - Viáticos
        - Vacaciones
        - Otros ingresos laborales

        EXCLUYE: Cesantías, Intereses de cesantías, Prima legal (se calcula independiente)
        """
        normativa = NORMATIVA_RETENCION['paso_1_ingresos']

        # Códigos a excluir según normativa
        codigos_excluir = ['CESANTIAS', 'INT_CESANTIAS', 'PRIMA', 'PRIMA_SERVICIOS']

        if tipo_especial == 'prima':
            # Prima se calcula independiente
            lineas_prima = self._obtener_lineas_detalle(localdict, codigos=['PRIMA', 'PRIMA_SERVICIOS'])
            total_prima = sum(l['total'] for l in lineas_prima)
            return {
                'total': total_prima,
                'salario': 0,
                'devengados': total_prima,
                'dev_no_salarial': 0,
                'lineas_detalle': lineas_prima,
                'base_legal': normativa['base_legal'],
                'elemento_ley': normativa['elemento_ley'],
            }

        # ─────────────────────────────────────────────────────────────────
        # OBTENER DETALLE DE CADA CONCEPTO CON ID DE LÍNEA
        # Usamos un set de códigos procesados para evitar duplicados
        # Incluimos líneas con valor cero para mostrar todos los conceptos
        # ─────────────────────────────────────────────────────────────────
        codigos_procesados = set(codigos_excluir)

        # 1. Salario básico (incluir ceros para mostrar conceptos disponibles)
        lineas_basico = self._obtener_lineas_detalle(
            localdict, categorias=['BASIC'],
            excluir_codigos=list(codigos_procesados),
            incluir_ceros=True
        )
        total_basico = sum(l['total'] for l in lineas_basico)
        # Agregar códigos procesados para evitar duplicados en siguientes categorías
        codigos_procesados.update(l['code'] for l in lineas_basico)

        # 2. Devengos salariales (comisiones, horas extras, recargos, bonificaciones, etc.)
        lineas_dev_salarial = self._obtener_lineas_detalle(
            localdict,
            categorias=['DEV_SALARIAL', 'COMISIONES', 'HEYREC'],
            excluir_codigos=list(codigos_procesados),
            incluir_ceros=True
        )
        total_dev_salarial = sum(l['total'] for l in lineas_dev_salarial)
        # Agregar códigos procesados
        codigos_procesados.update(l['code'] for l in lineas_dev_salarial)

        # 3. Devengos no salariales (auxilios, viáticos, etc.)
        lineas_dev_no_salarial = self._obtener_lineas_detalle(
            localdict,
            categorias=['DEV_NO_SALARIAL', 'COMPLEMENTARIOS'],
            excluir_codigos=list(codigos_procesados),
            incluir_ceros=True
        )
        total_dev_no_salarial = sum(l['total'] for l in lineas_dev_no_salarial)

        # Consolidar todas las líneas (sin duplicados, incluyendo ceros para visualización)
        todas_lineas = lineas_basico + lineas_dev_salarial + lineas_dev_no_salarial
        total_ingresos = total_basico + total_dev_salarial + total_dev_no_salarial

        # ─────────────────────────────────────────────────────────────────
        # CONCEPTOS PROYECTADOS DE CONTRATO
        # Obtener conceptos de hr.contract.concepts con proyectar_retencion=True
        # ─────────────────────────────────────────────────────────────────
        contract = localdict.get('contract')
        slip = localdict.get('slip')
        lineas_proyectadas = []
        total_proyectado = 0

        if contract and slip:
            ConceptModel = self.env['hr.contract.concepts']
            proyectados = ConceptModel.get_contract_projected_concepts(
                contract.id,
                'retencion',
                slip.date_from,
                slip.date_to,
                localdict
            )
            total_proyectado = proyectados.get('total', 0)

            # Agregar lineas de conceptos proyectados al detalle
            for concept in proyectados.get('concepts', []):
                lineas_proyectadas.append({
                    'id': concept['id'],
                    'code': concept.get('code', 'PROY_RET'),
                    'name': f"[PROY] {concept['name']}",
                    'category_id': False,
                    'category_code': 'PROYECTADO',
                    'category_name': 'Conceptos Proyectados',
                    'quantity': 1,
                    'amount': concept['amount'],
                    'total': concept['projected'],
                    'factor': concept.get('factor', 1),
                })

        todas_lineas = lineas_basico + lineas_dev_salarial + lineas_dev_no_salarial + lineas_proyectadas
        total_ingresos = total_basico + total_dev_salarial + total_dev_no_salarial + total_proyectado

        return {
            'salario': total_basico,
            'devengados': total_dev_salarial,
            'dev_no_salarial': total_dev_no_salarial,
            'proyectados': total_proyectado,
            'total': total_ingresos,
            'lineas_detalle': todas_lineas,
            'lineas_proyectadas': lineas_proyectadas,
            'resumen_por_categoria': {
                'BASIC': {'total': total_basico, 'lineas': lineas_basico},
                'DEV_SALARIAL': {'total': total_dev_salarial, 'lineas': lineas_dev_salarial},
                'DEV_NO_SALARIAL': {'total': total_dev_no_salarial, 'lineas': lineas_dev_no_salarial},
                'PROYECTADO': {'total': total_proyectado, 'lineas': lineas_proyectadas},
            },
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
        }

    def _aplicar_proyeccion_ret(self, ingresos, dias_trabajados):
        """Aplica proyección a 30 días para nóminas quincenales."""
        if dias_trabajados > 0:
            factor = 30.0 / dias_trabajados
            resultado = {k: v * factor if isinstance(v, (int, float)) else v
                        for k, v in ingresos.items()}
            return resultado
        return ingresos

    def _calcular_aportes_ret(self, localdict):
        """
        PASO 2: Calcular INCR - Ingresos No Constitutivos de Renta
        Base Legal: Art. 55 y 56 ET

        Componentes:
        - Aportes obligatorios a Fondos de Pensiones (Art. 55 ET)
        - Fondo de Solidaridad Pensional
        - Aportes obligatorios al sistema de salud (Art. 56 ET)
        """
        normativa = NORMATIVA_RETENCION['paso_2_incr']

        # Obtener detalle de cada componente con ID de línea
        codigos_incr = ['SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']
        lineas_incr = self._obtener_lineas_detalle(localdict, codigos=codigos_incr)

        # Extraer valores individuales
        salud = 0
        pension = 0
        solidaridad = 0
        subsistencia = 0

        lineas_detalle = []
        for linea in lineas_incr:
            valor = abs(linea['total'])
            linea_detalle = {
                'id': linea['id'],
                'code': linea['code'],
                'name': linea['name'],
                'total': valor,
            }

            if linea['code'] == 'SSOCIAL001':
                salud = valor
                linea_detalle['concepto'] = 'Aporte Salud Empleado'
                linea_detalle['base_legal'] = 'Art. 56 ET'
            elif linea['code'] == 'SSOCIAL002':
                pension = valor
                linea_detalle['concepto'] = 'Aporte Pensión Obligatoria'
                linea_detalle['base_legal'] = 'Art. 55 ET'
            elif linea['code'] == 'SSOCIAL003':
                solidaridad = valor
                linea_detalle['concepto'] = 'Fondo de Solidaridad Pensional'
                linea_detalle['base_legal'] = 'Art. 55 ET, Ley 797/2003'
            elif linea['code'] == 'SSOCIAL004':
                subsistencia = valor
                linea_detalle['concepto'] = 'Fondo de Subsistencia'
                linea_detalle['base_legal'] = 'Art. 55 ET, Ley 797/2003'

            lineas_detalle.append(linea_detalle)

        return {
            'salud': salud,
            'pension': pension,
            'solidaridad': solidaridad,
            'subsistencia': subsistencia,
            'total_pension': pension + solidaridad + subsistencia,
            'total': salud + pension + solidaridad + subsistencia,
            'lineas_detalle': lineas_detalle,
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
            'detalle_componentes': normativa['componentes'],
        }

    def _calcular_deducciones_ret(self, localdict, ingresos_total, subtotal_1, annual_parameters):
        """
        PASO 3: Calcular Deducciones Tributarias
        Base Legal: Art. 387 ET
        """
        normativa = NORMATIVA_RETENCION['paso_3_deducciones']
        contract = localdict['contract']
        slip = localdict['slip']
        uvt = annual_parameters.value_uvt
        fecha_nomina = slip.date_to  # Fecha de referencia para validar vigencia

        deducciones = {
            'dependientes': 0,
            'prepagada': 0,
            'vivienda': 0,
            'total': 0,
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
            'detalle': [],
        }

        # ─────────────────────────────────────────────────────────────────
        # DEDUCCIÓN POR DEPENDIENTES
        # Base Legal: Art. 387 Num. 1 ET
        # Tope: 10% ingreso bruto, máximo 32 UVT mensuales
        # ─────────────────────────────────────────────────────────────────
        norm_dep = normativa['deducciones']['dependientes']
        if contract.ded_dependents:
            base_dependientes = ingresos_total * (norm_dep['porcentaje_base'] / 100.0)
            tope_dependientes = norm_dep['tope_uvt_mensual'] * uvt
            ded_dependientes = min(base_dependientes, tope_dependientes)
            deducciones['dependientes'] = ded_dependientes
            deducciones['detalle'].append({
                'concepto': norm_dep['nombre'],
                'base_legal': norm_dep['base_legal'],
                'elemento_ley': norm_dep['elemento_ley'],
                'base_calculo': ingresos_total,
                'porcentaje': norm_dep['porcentaje_base'],
                'tope_uvt': norm_dep['tope_uvt_mensual'],
                'tope_pesos': tope_dependientes,
                'valor_calculado': base_dependientes,
                'valor_aplicado': ded_dependientes,
            })

        # ─────────────────────────────────────────────────────────────────
        # DEDUCCIÓN MEDICINA PREPAGADA
        # Base Legal: Art. 387 Num. 2 ET
        # Tope: 16 UVT mensuales
        # ─────────────────────────────────────────────────────────────────
        norm_prep = normativa['deducciones']['prepagada']
        detalle_prepagada = self._obtener_deduccion_contrato(contract, 'MEDPRE', fecha_nomina, retornar_detalle=True)
        if detalle_prepagada['value'] > 0:
            tope_prepagada = norm_prep['tope_uvt_mensual'] * uvt
            ded_prepagada = min(detalle_prepagada['value'], tope_prepagada)
            deducciones['prepagada'] = ded_prepagada
            deducciones['detalle'].append({
                'id': detalle_prepagada['id'],
                'code': detalle_prepagada['code'],
                'concepto': norm_prep['nombre'],
                'base_legal': norm_prep['base_legal'],
                'elemento_ley': norm_prep['elemento_ley'],
                'valor_reportado': detalle_prepagada['value'],
                'valor_total_certificado': detalle_prepagada['value_total'],
                'fecha_inicio': detalle_prepagada['date_start'],
                'fecha_fin': detalle_prepagada['date_end'],
                'tope_uvt': norm_prep['tope_uvt_mensual'],
                'tope_pesos': tope_prepagada,
                'valor_aplicado': ded_prepagada,
            })

        # ─────────────────────────────────────────────────────────────────
        # DEDUCCIÓN INTERESES VIVIENDA
        # Base Legal: Art. 119 ET, Art. 387 Num. 3 ET
        # Tope: 100 UVT mensuales
        # ─────────────────────────────────────────────────────────────────
        norm_viv = normativa['deducciones']['vivienda']
        detalle_vivienda = self._obtener_deduccion_contrato(contract, 'INTVIV', fecha_nomina, retornar_detalle=True)
        if detalle_vivienda['value'] > 0:
            tope_vivienda = norm_viv['tope_uvt_mensual'] * uvt
            ded_vivienda = min(detalle_vivienda['value'], tope_vivienda)
            deducciones['vivienda'] = ded_vivienda
            deducciones['detalle'].append({
                'id': detalle_vivienda['id'],
                'code': detalle_vivienda['code'],
                'concepto': norm_viv['nombre'],
                'base_legal': norm_viv['base_legal'],
                'elemento_ley': norm_viv['elemento_ley'],
                'valor_certificado': detalle_vivienda['value'],
                'valor_total_certificado': detalle_vivienda['value_total'],
                'fecha_inicio': detalle_vivienda['date_start'],
                'fecha_fin': detalle_vivienda['date_end'],
                'tope_uvt': norm_viv['tope_uvt_mensual'],
                'tope_pesos': tope_vivienda,
                'valor_aplicado': ded_vivienda,
            })

        deducciones['total'] = (deducciones['dependientes'] +
                               deducciones['prepagada'] +
                               deducciones['vivienda'])

        return deducciones

    def _calcular_rentas_exentas_ret(self, localdict, subtotal_1, annual_parameters):
        """
        PASO 4: Calcular Rentas Exentas (AFC/AVC)
        Base Legal: Art. 126-1 y 126-4 ET

        Obtiene valores de dos fuentes:
        1. Líneas de nómina (reglas AFC/AVC calculadas)
        2. Modelo hr.contract.deductions.rtf (valores fijos del contrato)
        """
        normativa = NORMATIVA_RETENCION['paso_4_rentas_exentas']
        contract = localdict['contract']
        slip = localdict['slip']
        uvt = annual_parameters.value_uvt
        fecha_nomina = slip.date_to

        lineas_detalle = []

        # ─────────────────────────────────────────────────────────────────
        # FUENTE 1: Obtener valores AFC y AVC de las líneas de nómina
        # ─────────────────────────────────────────────────────────────────
        lineas_afc_nomina = self._obtener_lineas_detalle(localdict, codigos=['AFC'])
        lineas_avc_nomina = self._obtener_lineas_detalle(localdict, codigos=['AVC'])

        afc_nomina = sum(abs(l['total']) for l in lineas_afc_nomina)
        avc_nomina = sum(abs(l['total']) for l in lineas_avc_nomina)

        for linea in lineas_afc_nomina:
            lineas_detalle.append({
                'id': linea['id'],
                'code': linea['code'],
                'name': linea['name'],
                'fuente': 'nomina',
                'tipo': 'AFC',
                'base_legal': 'Art. 126-4 ET',
                'total': abs(linea['total']),
            })

        for linea in lineas_avc_nomina:
            lineas_detalle.append({
                'id': linea['id'],
                'code': linea['code'],
                'name': linea['name'],
                'fuente': 'nomina',
                'tipo': 'AVC',
                'base_legal': 'Art. 126-1 ET',
                'total': abs(linea['total']),
            })

        # ─────────────────────────────────────────────────────────────────
        # FUENTE 2: Obtener valores AFC y AVC del modelo de deducciones RTF
        # ─────────────────────────────────────────────────────────────────
        detalle_afc_contrato = self._obtener_deduccion_contrato(contract, 'AFC', fecha_nomina, retornar_detalle=True)
        detalle_avc_contrato = self._obtener_deduccion_contrato(contract, 'AVC', fecha_nomina, retornar_detalle=True)

        afc_contrato = detalle_afc_contrato['value']
        avc_contrato = detalle_avc_contrato['value']

        if afc_contrato > 0:
            lineas_detalle.append({
                'id': detalle_afc_contrato['id'],
                'code': detalle_afc_contrato['code'],
                'name': detalle_afc_contrato['name'],
                'fuente': 'contrato',
                'tipo': 'AFC',
                'base_legal': 'Art. 126-4 ET',
                'total': afc_contrato,
                'fecha_inicio': detalle_afc_contrato['date_start'],
                'fecha_fin': detalle_afc_contrato['date_end'],
            })

        if avc_contrato > 0:
            lineas_detalle.append({
                'id': detalle_avc_contrato['id'],
                'code': detalle_avc_contrato['code'],
                'name': detalle_avc_contrato['name'],
                'fuente': 'contrato',
                'tipo': 'AVC',
                'base_legal': 'Art. 126-1 ET',
                'total': avc_contrato,
                'fecha_inicio': detalle_avc_contrato['date_start'],
                'fecha_fin': detalle_avc_contrato['date_end'],
            })

        # Consolidar valores (usar el mayor de cada fuente para evitar duplicados)
        valor_afc = max(afc_nomina, afc_contrato)
        valor_avc = max(avc_nomina, avc_contrato)

        # ─────────────────────────────────────────────────────────────────
        # LÍMITES COMBINADOS PARA AFC + AVC
        # Art. 126-1 y 126-4 ET: 30% del ingreso + tope 3800 UVT anual
        # ─────────────────────────────────────────────────────────────────
        limite_30_pct = subtotal_1 * 0.30
        limite_uvt_mensual = (normativa['rentas']['afc']['tope_uvt_anual'] / 12) * uvt
        limite_total = min(limite_30_pct, limite_uvt_mensual)

        # Aplicar límites
        total_afc_avc = valor_afc + valor_avc
        afc_avc_limitado = min(total_afc_avc, limite_total)

        return {
            'afc_nomina': afc_nomina,
            'afc_contrato': afc_contrato,
            'afc_reportado': valor_afc,
            'avc_nomina': avc_nomina,
            'avc_contrato': avc_contrato,
            'avc_reportado': valor_avc,
            'total_reportado': total_afc_avc,
            'limite_30_pct': limite_30_pct,
            'limite_uvt': limite_uvt_mensual,
            'limite_aplicado': limite_total,
            'total_aceptado': afc_avc_limitado,
            'lineas_detalle': lineas_detalle,
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
            'detalle_afc': normativa['rentas']['afc'],
            'detalle_avc': normativa['rentas']['avc'],
        }

    def _calcular_renta_exenta_25_ret(self, subtotal_2, annual_parameters):
        """
        PASO 5: Calcular Renta Exenta Laboral del 25%
        Base Legal: Art. 206 Numeral 10 ET
        Tope: 240 UVT mensuales
        """
        normativa = NORMATIVA_RETENCION['paso_5_renta_exenta_25']
        uvt = annual_parameters.value_uvt

        valor_25_pct = subtotal_2 * (normativa['porcentaje'] / 100.0)
        tope_uvt = normativa['tope_uvt_mensual'] * uvt
        renta_exenta_25 = min(valor_25_pct, tope_uvt)

        return {
            'base_calculo': subtotal_2,
            'porcentaje': normativa['porcentaje'],
            'valor_calculado': valor_25_pct,
            'tope_uvt': normativa['tope_uvt_mensual'],
            'tope_pesos': tope_uvt,
            'valor_aplicado': renta_exenta_25,
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
        }

    def _aplicar_limite_global_ret(self, subtotal_1, deducciones, rentas_exentas, renta_25, annual_parameters):
        """
        PASO 6: Aplicar Límite Global del 40%
        Base Legal: Art. 336 ET (Ley 2277/2022)
        Tope: min(40% del subtotal_1, 1340 UVT anuales)
        """
        normativa = NORMATIVA_RETENCION['paso_6_limite_global']
        uvt = annual_parameters.value_uvt

        # Sumar todos los beneficios
        total_beneficios = (deducciones['total'] +
                          rentas_exentas['total_aceptado'] +
                          renta_25['valor_aplicado'])

        # Calcular límites
        limite_40_pct = subtotal_1 * (normativa['limite_porcentaje'] / 100.0)
        limite_uvt_mensual = (normativa['tope_uvt_anual'] / 12) * uvt
        limite_aplicable = min(limite_40_pct, limite_uvt_mensual)

        # Aplicar límite
        beneficios_aceptados = min(total_beneficios, limite_aplicable)

        # Si hay exceso, calcular proporción de recorte
        exceso = total_beneficios - beneficios_aceptados
        factor_ajuste = beneficios_aceptados / total_beneficios if total_beneficios > 0 else 1

        return {
            'total_beneficios_solicitados': total_beneficios,
            'limite_40_pct': limite_40_pct,
            'limite_uvt_anual': normativa['tope_uvt_anual'],
            'limite_uvt_mensual_pesos': limite_uvt_mensual,
            'limite_aplicable': limite_aplicable,
            'beneficios_aceptados': beneficios_aceptados,
            'exceso': exceso,
            'factor_ajuste': factor_ajuste,
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
        }

    def _aplicar_tabla_retencion_ret(self, ibr_uvts, subtotal_ibr3, annual_parameters, contract):
        """
        PASO 7: Aplicar Tabla de Retención
        Base Legal: Art. 383 ET (Procedimiento 1) o Art. 386 ET (Procedimiento 2)
        """
        normativa = NORMATIVA_RETENCION['paso_7_tabla_retencion']
        retencion = 0
        rate = 0
        rango_aplicado = None

        # Procedimiento 2: Usar porcentaje fijo calculado
        if contract.retention_procedure == '102':
            retencion = subtotal_ibr3 * (contract.rtf_rate / 100.0)
            rate = contract.rtf_rate
            return retencion, rate, {
                'procedimiento': '102',
                'base_legal': 'Art. 386 ET',
                'porcentaje_fijo': contract.rtf_rate,
            }

        # Procedimiento 1: Usar tabla de retención
        for rango in normativa['tabla']:
            if rango['desde'] <= ibr_uvts < rango['hasta']:
                rango_aplicado = rango
                if rango['desde'] > 0:
                    retencion = (((ibr_uvts - rango['resta_uvt']) * (rango['tarifa'] / 100.0)) + rango['suma_uvt']) * annual_parameters.value_uvt
                    rate = rango['tarifa']
                break

        return retencion, rate, {
            'procedimiento': '100',
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
            'base_uvt': ibr_uvts,
            'rango_aplicado': rango_aplicado,
            'formula': normativa['formula'],
        }

    def _obtener_deduccion_contrato(self, contract, codigo, fecha_nomina=None, retornar_detalle=False):
        """
        Obtiene el valor de una deducción configurada en el contrato.

        Valida que la deducción esté vigente según las fechas configuradas.
        Base Legal: Art. 387 ET - Las deducciones deben estar debidamente soportadas
        y corresponder al período fiscal.

        Args:
            contract: Contrato del empleado
            codigo: Código de la regla salarial ('MEDPRE', 'INTVIV', etc.)
            fecha_nomina: Fecha de la nómina para validar vigencia
            retornar_detalle: Si True, retorna diccionario con detalle completo

        Returns:
            float o dict: Valor mensual o diccionario con detalle si retornar_detalle=True
        """
        resultado_vacio = {'id': False, 'code': codigo, 'value': 0, 'vigente': False} if retornar_detalle else 0

        try:
            deduccion = self.env['hr.contract.deductions.rtf'].search([
                ('contract_id', '=', contract.id),
                ('input_id.code', '=', codigo)
            ], limit=1)

            if not deduccion or not deduccion.value_monthly:
                return resultado_vacio

            vigente = True
            # Validar vigencia si se especifica fecha de nómina
            if fecha_nomina:
                # Si tiene fecha de inicio y la nómina es anterior, no aplica
                if deduccion.date_start and fecha_nomina < deduccion.date_start:
                    vigente = False
                # Si tiene fecha de fin y la nómina es posterior, no aplica
                if deduccion.date_end and fecha_nomina > deduccion.date_end:
                    vigente = False

            if not vigente:
                return resultado_vacio

            if retornar_detalle:
                return {
                    'id': deduccion.id,
                    'code': codigo,
                    'name': deduccion.input_id.name if deduccion.input_id else '',
                    'rule_id': deduccion.input_id.id if deduccion.input_id else False,
                    'value': deduccion.value_monthly,
                    'value_total': deduccion.value_total,
                    'date_start': deduccion.date_start,
                    'date_end': deduccion.date_end,
                    'limite_uvt_mensual': deduccion.limite_uvt_mensual if deduccion.limite_uvt_mensual else 0,
                    'limite_uvt_anual': deduccion.limite_uvt_anual if deduccion.limite_uvt_anual else 0,
                    'base_legal': deduccion.base_legal if deduccion.base_legal else '',
                    'vigente': vigente,
                }

            return deduccion.value_monthly
        except Exception:
            return resultado_vacio

    def _calcular_retencion_definitiva_ret(self, localdict, retencion, debe_proyectar):
        """Calcula la retención definitiva restando la anterior y aplicando proyección."""
        retencion_anterior = self._get_totalizar_reglas(
            localdict, 'RT_MET_01',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        retencion_def = max(0, retencion - abs(retencion_anterior))

        if debe_proyectar:
            retencion_def = retencion_def / 2.0

        return retencion_def, abs(retencion_anterior)

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODO PRINCIPAL - PROCEDIMIENTO 1 (Art. 385 ET)
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_retention_ordinary(self, localdict, retention_data, tipo_especial=None):
        """
        Cálculo de retención - Procedimiento 1 (Art. 385 ET)

        Flujo normativo:
        1. Ingresos Brutos (Art. 103 ET)
        2. INCR - Aportes obligatorios (Art. 55, 56 ET)
        3. Deducciones (Art. 387 ET)
        4. Rentas Exentas AFC/AVC (Art. 126-1, 126-4 ET)
        5. Renta Exenta 25% (Art. 206 Num. 10 ET)
        6. Límite Global 40% (Art. 336 ET)
        7. Tabla de Retención (Art. 383 ET)
        """
        contract = localdict['contract']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')

        if not annual_parameters:
            retention_data['status'] = 'error'
            retention_data['reason'] = 'no_annual_parameters'
            return 0, 0, 0, 'Error: Faltan parámetros anuales', retention_data, {}

        uvt = annual_parameters.value_uvt
        pasos = []

        # ═══════════════════════════════════════════════════════════════════
        # PASO 1: INGRESOS BRUTOS (Art. 103 ET)
        # ═══════════════════════════════════════════════════════════════════
        dias_trabajados = self._calcular_dias_trabajados_ret(localdict)
        debe_proyectar = self._verificar_proyeccion_ret(contract, slip)
        ingresos = self._calcular_ingresos_ret(localdict, tipo_especial)

        if debe_proyectar:
            ingresos = self._aplicar_proyeccion_ret(ingresos, dias_trabajados)

        ingresos_total = ingresos['total']
        pasos.append({
            'paso': 1,
            'nombre': 'Ingresos Laborales Brutos',
            'base_legal': 'Art. 103 ET',
            'valor': ingresos_total,
            'detalle': ingresos,
        })

        # ═══════════════════════════════════════════════════════════════════
        # PASO 2: INCR - INGRESOS NO CONSTITUTIVOS DE RENTA (Art. 55, 56 ET)
        # ═══════════════════════════════════════════════════════════════════
        aportes = self._calcular_aportes_ret(localdict)
        incr = aportes['total']
        subtotal_1 = ingresos_total - incr

        pasos.append({
            'paso': 2,
            'nombre': 'INCR - Aportes Obligatorios',
            'base_legal': 'Art. 55 y 56 ET',
            'valor': incr,
            'subtotal_1': subtotal_1,
            'detalle': aportes,
        })

        # ═══════════════════════════════════════════════════════════════════
        # PASO 3: DEDUCCIONES (Art. 387 ET)
        # ═══════════════════════════════════════════════════════════════════
        deducciones = self._calcular_deducciones_ret(localdict, ingresos_total, subtotal_1, annual_parameters)

        pasos.append({
            'paso': 3,
            'nombre': 'Deducciones Tributarias',
            'base_legal': 'Art. 387 ET',
            'valor': deducciones['total'],
            'detalle': deducciones,
        })

        # ═══════════════════════════════════════════════════════════════════
        # PASO 4: RENTAS EXENTAS AFC/AVC (Art. 126-1, 126-4 ET)
        # ═══════════════════════════════════════════════════════════════════
        rentas_exentas = self._calcular_rentas_exentas_ret(localdict, subtotal_1, annual_parameters)

        pasos.append({
            'paso': 4,
            'nombre': 'Rentas Exentas AFC/AVC',
            'base_legal': 'Art. 126-1 y 126-4 ET',
            'valor': rentas_exentas['total_aceptado'],
            'detalle': rentas_exentas,
        })

        # Subtotal 2: Base para renta exenta 25%
        subtotal_2 = subtotal_1 - deducciones['total'] - rentas_exentas['total_aceptado']

        # ═══════════════════════════════════════════════════════════════════
        # PASO 5: RENTA EXENTA 25% (Art. 206 Num. 10 ET)
        # ═══════════════════════════════════════════════════════════════════
        renta_25 = self._calcular_renta_exenta_25_ret(subtotal_2, annual_parameters)

        pasos.append({
            'paso': 5,
            'nombre': 'Renta Exenta 25%',
            'base_legal': 'Art. 206 Num. 10 ET',
            'valor': renta_25['valor_aplicado'],
            'detalle': renta_25,
        })

        # ═══════════════════════════════════════════════════════════════════
        # PASO 6: LÍMITE GLOBAL 40% (Art. 336 ET)
        # ═══════════════════════════════════════════════════════════════════
        limite_global = self._aplicar_limite_global_ret(
            subtotal_1, deducciones, rentas_exentas, renta_25, annual_parameters
        )

        pasos.append({
            'paso': 6,
            'nombre': 'Límite Global 40%',
            'base_legal': 'Art. 336 ET',
            'valor': limite_global['beneficios_aceptados'],
            'detalle': limite_global,
        })

        # Base gravable final
        base_gravable = subtotal_1 - limite_global['beneficios_aceptados']
        base_gravable_uvt = base_gravable / uvt if uvt > 0 else 0

        # ═══════════════════════════════════════════════════════════════════
        # PASO 7: APLICAR TABLA DE RETENCIÓN (Art. 383 ET)
        # ═══════════════════════════════════════════════════════════════════
        retencion, rate, detalle_tabla = self._aplicar_tabla_retencion_ret(
            base_gravable_uvt, base_gravable, annual_parameters, contract
        )

        pasos.append({
            'paso': 7,
            'nombre': 'Aplicación Tabla Retención',
            'base_legal': 'Art. 383 ET',
            'valor': retencion,
            'tarifa': rate,
            'detalle': detalle_tabla,
        })

        # ═══════════════════════════════════════════════════════════════════
        # PASO 8: RETENCIÓN DEFINITIVA
        # ═══════════════════════════════════════════════════════════════════
        retencion_def, retencion_anterior = self._calcular_retencion_definitiva_ret(
            localdict, retencion, debe_proyectar
        )
        
        # Obtener línea anterior para trazabilidad
        retencion_line_anterior = self._get_previous_payslip_line(
            contract,
            'RT_MET_01',
            slip.date_from,
        )
        
        diferencia_retencion = retencion_def - retencion_anterior
        linea_anterior = self._build_payslip_line_info(
            retencion_line_anterior,
            include_total=True,
            include_amount=False,
            include_quantity=False,
            fallback_payslip_number=None,
        )
        linea_anterior_formateada = self._build_payslip_line_info(
            retencion_line_anterior,
            include_total=True,
            include_amount=False,
            include_quantity=False,
            date_format='%Y-%m-%d',
            fallback_payslip_number=None,
        )
        linea_anterior_simple = self._build_payslip_line_info(
            retencion_line_anterior,
            include_total=False,
            include_amount=False,
            include_quantity=False,
            fallback_payslip_number=None,
        )

        pasos.append({
            'paso': 8,
            'nombre': 'Retención Definitiva',
            'base_legal': 'Art. 385 ET',
            'valor': retencion_def,
            'retencion_calculada': retencion,
            'retencion_anterior': retencion_anterior,
            'diferencia': diferencia_retencion,
            'proyectada': debe_proyectar,
            'payslip_line_anterior': linea_anterior,
        })
        
        # Agregar información de línea anterior a retention_data
        retention_data['payslip_line_anterior'] = linea_anterior_formateada
        retention_data['diferencia_retencion'] = diferencia_retencion

        # ═══════════════════════════════════════════════════════════════════
        # CONSTRUIR RESPUESTA CON TRAZABILIDAD NORMATIVA
        # ═══════════════════════════════════════════════════════════════════
        retention_data['pasos_aplicados'] = pasos
        retention_data['dias_trabajados'] = dias_trabajados
        retention_data['es_proyectado'] = debe_proyectar
        retention_data['ingresos'] = ingresos
        retention_data['aportes'] = aportes
        retention_data['subtotales'] = {
            'subtotal_1': subtotal_1,
            'subtotal_2': subtotal_2,
            'base_gravable': base_gravable,
            'base_gravable_uvt': base_gravable_uvt,
        }
        retention_data['beneficios'] = {
            'deducciones': deducciones,
            'rentas_exentas': rentas_exentas,
            'renta_25': renta_25,
            'limite_global': limite_global,
        }
        retention_data['retencion_calculada'] = retencion
        retention_data['retencion_anterior'] = retencion_anterior
        retention_data['retencion_definitiva'] = retencion_def
        retention_data['tarifa'] = rate
        retention_data['status'] = 'calculated'
        retention_data['procedimiento'] = {
            'codigo': '100',
            'nombre': 'Procedimiento 1',
            'base_legal': 'Art. 385 ET',
        }

        # KPI para reportes
        data_kpi = {
            'periodo': {
                'year': slip.date_to.year,
                'month': slip.date_to.month,
                'date_from': slip.date_from,
                'date_to': slip.date_to
            },
            'ingresos': {
                'salario': ingresos.get('salario', 0),
                'devengados': ingresos.get('devengados', 0),
                'total': ingresos.get('total', 0),
            },
            'aportes': aportes,
            'base_gravable': {
                'ing_base': subtotal_1,
                'ibr1_antes_deducciones': subtotal_1,
                'ibr2_antes_renta_exenta': subtotal_2,
                'ibr3_final': base_gravable,
                'ibr_uvts': base_gravable_uvt,
                'deducciones': deducciones['total'],
                'rentas_exentas': rentas_exentas['total_aceptado'],
                'renta_exenta_25': renta_25['valor_aplicado'],
                'total_beneficios': limite_global['total_beneficios_solicitados'],
                'limite_40': limite_global['limite_40_pct'],
                'limite_uvt': limite_global['limite_uvt_mensual_pesos'],
                'beneficios_limitados': limite_global['beneficios_aceptados'],
            },
            'beneficios': {
                'deducciones': deducciones['total'],
                'ded_dependientes': deducciones['dependientes'],
                'ded_prepagada': deducciones['prepagada'],
                'ded_vivienda': deducciones['vivienda'],
                'rentas_exentas': rentas_exentas['total_aceptado'],
                'renta_exenta_25': renta_25['valor_aplicado'],
                'total_beneficios': limite_global['total_beneficios_solicitados'],
                'beneficios_limitados': limite_global['beneficios_aceptados'],
            },
            'retencion': {
                'calculada': retencion,
                'anterior': retencion_anterior,
                'definitiva': retencion_def,
                'diferencia': diferencia_retencion,
                'tarifa_porcentaje': rate,
                'proyectada': debe_proyectar,
                'payslip_line_anterior': linea_anterior_simple
            },
            'lineas_usadas': {
                'ingresos': ingresos.get('lineas_detalle', []),
                'aportes': aportes.get('lineas_detalle', []),
                'deducciones': deducciones.get('detalle', []),
                'rentas_exentas': rentas_exentas.get('lineas_detalle', []),
            },
            'parametros': {
                'valor_uvt': uvt,
                'dias_trabajados': dias_trabajados,
                'debe_proyectar': debe_proyectar
            },
            'pasos_normativos': pasos,
        }

        localdict['retention_data'] = retention_data
        localdict['retention_kpi'] = data_kpi

        nombre = f'Retención Art.385 - Base: ${base_gravable:,.0f} ({base_gravable_uvt:.2f} UVT) - Tarifa {rate}%'

        # Retornar con rate=100 porque retencion_def ya tiene la tarifa aplicada
        # Odoo calcula: total = amount × quantity × rate / 100
        return retencion_def, -1, 100, nombre, retention_data, data_kpi

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PARA OTROS PROCEDIMIENTOS
    # ═══════════════════════════════════════════════════════════════════════════

    def _calculate_retention_fixed(self, localdict, retention_data):
        """
        Retención con monto fijo definido en contrato.
        """
        contract = localdict['contract']
        slip = localdict['slip']

        valor_fijo = contract.fixed_value_retention_procedure or 0

        retention_data['tipo'] = 'monto_fijo'
        retention_data['valor'] = valor_fijo
        retention_data['status'] = 'calculated'
        retention_data['procedimiento'] = {
            'codigo': 'fixed',
            'nombre': 'Valor Fijo',
            'base_legal': 'Acuerdo contractual',
        }

        data_kpi = {
            'periodo': {
                'year': slip.date_to.year,
                'month': slip.date_to.month,
                'date_from': slip.date_from,
                'date_to': slip.date_to
            },
            'tipo_retencion': 'monto_fijo',
            'retencion': {
                'valor_fijo': valor_fijo,
                'tarifa_porcentaje': 100
            }
        }

        localdict['retention_data'] = retention_data
        localdict['retention_kpi'] = data_kpi

        return valor_fijo, -1, 100, f'Retención Fijo: ${valor_fijo:,.0f}', retention_data, data_kpi

    def _calculate_retention_foreigner(self, localdict, retention_data):
        """
        Retención para extranjero no residente - 20% sobre ingresos totales.
        Base Legal: Art. 408 ET
        """
        slip = localdict['slip']
        normativa = NORMATIVA_RETENCION['casos_especiales']['extranjero_no_residente']

        basic, _ = self._get_totalizar_categorias(localdict, categorias=['BASIC'])
        dev_salarial, _ = self._get_totalizar_categorias(localdict, categorias=['DEV_SALARIAL'])
        dev_no_salarial, _ = self._get_totalizar_categorias(localdict, categorias=['DEV_NO_SALARIAL'])

        base = basic + dev_salarial + dev_no_salarial
        retencion = base * (normativa['tarifa_fija'] / 100.0)

        retention_data['tipo'] = 'extranjero_no_residente'
        retention_data['base'] = base
        retention_data['tarifa'] = normativa['tarifa_fija']
        retention_data['retencion'] = retencion
        retention_data['status'] = 'calculated'
        retention_data['procedimiento'] = {
            'codigo': 'extranjero_no_residente',
            'nombre': normativa['nombre'],
            'base_legal': normativa['base_legal'],
            'elemento_ley': normativa['elemento_ley'],
        }

        data_kpi = {
            'periodo': {
                'year': slip.date_to.year,
                'month': slip.date_to.month,
                'date_from': slip.date_from,
                'date_to': slip.date_to
            },
            'tipo_retencion': 'extranjero_no_residente',
            'ingresos': {
                'basic': basic,
                'dev_salarial': dev_salarial,
                'dev_no_salarial': dev_no_salarial,
                'base_total': base
            },
            'retencion': {
                'calculada': retencion,
                'tarifa_porcentaje': normativa['tarifa_fija'],
                'base_calculo': base
            },
            'base_legal': normativa['base_legal'],
        }

        localdict['retention_data'] = retention_data
        localdict['retention_kpi'] = data_kpi

        return retencion, -1, normativa['tarifa_fija'], f"Retención Art.408 - Base: ${base:,.0f}", retention_data, data_kpi

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE REGISTRO Y REPORTE
    # ═══════════════════════════════════════════════════════════════════════════

    def _crear_registro_retencion(self, localdict, data_kpi, retention_data):
        """
        Crea o actualiza el registro de reporte de retención.
        """
        employee = localdict['employee']
        slip = localdict['slip']

        report_obj = self.env['lavish.retencion.reporte']

        existing_report = report_obj.search([
            ('employee_id', '=', employee.id),
            ('payslip_id', '=', slip.id)
        ])

        if existing_report:
            existing_report.unlink()

        quincena = '0'
        if slip.date_from.day <= 15 and slip.date_to.day <= 15:
            quincena = '1'
        elif slip.date_from.day > 15:
            quincena = '2'

        periodo = data_kpi.get('periodo', {})
        ingresos = data_kpi.get('ingresos', {})
        aportes = data_kpi.get('aportes', {})
        base_gravable = data_kpi.get('base_gravable', {})
        beneficios = data_kpi.get('beneficios', {})
        retencion = data_kpi.get('retencion', {})
        parametros = data_kpi.get('parametros', {})

        report_obj.create({
            'employee_id': employee.id,
            'date': slip.date_to,
            'payslip_id': slip.id,
            'year': periodo.get('year', slip.date_to.year),
            'month': periodo.get('month', slip.date_to.month),
            'quincena': quincena,
            'salario_basico': ingresos.get('salario', 0),
            'comisiones': 0,
            'dev_salarial': ingresos.get('devengados', 0),
            'dev_no_salarial': 0,
            'total_ingresos': ingresos.get('total', 0),
            'salud': aportes.get('salud', 0),
            'pension': aportes.get('pension', 0),
            'subsistencia': aportes.get('subsistencia', 0),
            'solidaridad': aportes.get('solidaridad', 0),
            'pension_total': aportes.get('total_pension', 0),
            'total_aportes': aportes.get('total', 0),
            'ded_vivienda': beneficios.get('ded_vivienda', 0),
            'ded_dependientes': beneficios.get('ded_dependientes', 0),
            'ded_salud': beneficios.get('ded_prepagada', 0),
            'total_deducciones': beneficios.get('deducciones', 0),
            'valor_avp_afc': beneficios.get('rentas_exentas', 0),
            'renta_exenta_25': beneficios.get('renta_exenta_25', 0),
            'total_rentas_exentas': beneficios.get('rentas_exentas', 0) + beneficios.get('renta_exenta_25', 0),
            'subtotal_ibr1': base_gravable.get('ibr1_antes_deducciones', 0),
            'subtotal_ibr2': base_gravable.get('ibr2_antes_renta_exenta', 0),
            'beneficios_limitados': beneficios.get('beneficios_limitados', 0),
            'base_gravable': base_gravable.get('ibr3_final', 0),
            'ibr_uvts': base_gravable.get('ibr_uvts', 0),
            'tasa_aplicada': retencion.get('tarifa_porcentaje', 0),
            'retencion_calculada': retencion.get('calculada', 0),
            'retencion_anterior': retencion.get('anterior', 0),
            'retencion_aplicada': retencion.get('definitiva', 0),
            'uvt_valor': parametros.get('valor_uvt', 0),
            'ingresos_totales': ingresos.get('total', 0),
            'es_proyectado': parametros.get('debe_proyectar', False),
            'base_legal': 'Art. 383-389 ET, Ley 2277/2022',
        })

    def _rtf_prima(self, liquidacion_data):
        """
        Retención en la fuente para prima de servicios.
        Base Legal: Art. 385 Parágrafo ET
        """
        return self._calculate_retention_generic(liquidacion_data, tipo='prima')

    def _obtener_otros_embargos(self, liquidacion_data, current_concept_id):
        """Obtiene otros embargos activos en la nómina."""
        return []
