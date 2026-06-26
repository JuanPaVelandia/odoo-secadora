# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - CÁLCULO BASE
====================================
Métodos core de cálculo y trazabilidad.
"""

import logging
from odoo import models
from dateutil.relativedelta import relativedelta
from odoo.addons.lavish_hr_employee.models.hr_slip_data_structures import CategoryCollection
from odoo.addons.lavish_hr_employee.models.hr_slip_utils import days360, PeriodoAnterior
from .config_reglas import get_prestacion_base_field

_logger = logging.getLogger(__name__)


class HrSalaryRulePrestacionesCalculo(models.AbstractModel):
    _inherit = 'hr.salary.rule.prestaciones'

    def _compute_social_benefits(self, localdict, date_from, date_to, tipo_prestacion, descontar_suspensiones=True):
        """
        Calcula prestaciones sociales (prima, cesantías, vacaciones, intereses).
        Filtra reglas según base_prima, base_cesantias, base_vacaciones, base_intereses_cesantias.

        Args:
            localdict: Diccionario de contexto de nómina
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            descontar_suspensiones: Si True, resta días no pagados

        Returns:
            tuple: (base_diaria, days_worked, 100, nombre, "", datos)
        """
        contract = localdict['contract']
        slip = localdict['slip']
        employee = localdict['employee']
        annual_parameters = localdict.get('annual_parameters', {})

        # ========== OBTENER PARAMETROS DE CONFIGURACION ==========
        config_params = self._get_provision_config_params(annual_parameters)

        # Ajustar descontar_suspensiones segun configuracion para prima
        if tipo_prestacion == 'prima' and config_params.get('prst_wo_susp'):
            descontar_suspensiones = False
        # Ignorar ausencias si está configurado globalmente
        if config_params.get('prst_wo_absences'):
            descontar_suspensiones = False

        # Validar aprendices - ACTUALIZADO Ley 2466/2025
        # Usa metodo centralizado en prestaciones_helpers.py
        aplica_aprendiz, motivo_aprendiz = self._aprendiz_tiene_prestaciones(
            employee, contract, tipo_prestacion
        )
        if not aplica_aprendiz:
            return 0, 0, 0, motivo_aprendiz, "", {}

        # Validar salario integral - vacaciones SI aplican, prima/cesantias/intereses NO
        if contract.modality_salary == 'integral' and tipo_prestacion != 'vacaciones':
            return 0, 0, 0, f"{tipo_prestacion.upper()} - No aplica salario integral", "", {}

        use_simple_method = self.env.company.simple_provisions
        es_liquidacion = slip.struct_process == 'contrato'
        es_provision_mensual = slip.struct_process == 'nomina'
        is_cesantias = tipo_prestacion in ['cesantias', 'intereses']

        # PROVISIONES MENSUALES: NO acumular, usar salario actual
        if use_simple_method or es_provision_mensual:
            compute_average = False
        elif es_liquidacion and is_cesantias:
            # LIQUIDACIÓN FINAL: Promediar si hubo cambio salarial
            date_3_months_before = date_to - relativedelta(months=3)
            if date_from > date_3_months_before:
                date_3_months_before = date_from
            compute_average = contract.has_change_salary(date_3_months_before, date_to)
        else:
            compute_average = False

        # Calcular días trabajados
        days_worked = days360(date_from, date_to)

        days_no_pay = slip._get_leave_days_no_pay(date_from, date_to, contract.id)

        # Si descontar_suspensiones=True, restar días no pagados (suspensiones)
        if descontar_suspensiones:
            if is_cesantias or tipo_prestacion == 'prima':
                days_worked -= days_no_pay

        # ══════════════════════════════════════════════════════════════════════════
        # DIAS ADICIONALES (cuotas especiales, ajustes manuales, configuracion)
        # ══════════════════════════════════════════════════════════════════════════
        dias_adicionales_info = self._calcular_dias_adicionales_prestacion(
            contract, slip, tipo_prestacion, days_worked
        )
        days_worked = dias_adicionales_info['dias_total']

        data_base = {}
        ids_by_type = {
            'basic_current': [],
            'basic_accumulated': [],
            'variable_current': [],
            'variable_accumulated': [],
        }

        # Calcular salario base
        # IMPORTANTE: Para prestaciones sociales (Art. 249, 306 CST), la base es el
        # SALARIO MENSUAL completo. La proporcionalización viene de los días en /360.
        # Fórmula: (Salario Mensual × Días Trabajados) / 360
        if compute_average:
            categories = localdict.get('categories', CategoryCollection())
            salary_base = 0
            meses_con_salario = set()  # Para contar meses distintos con datos

            basic_data = categories.get('BASIC')
            if basic_data:
                salary_base += basic_data.total
                ids_by_type['basic_current'] = basic_data.line_ids
                # Agregar mes actual si hay datos
                if slip.date_from:
                    meses_con_salario.add((slip.date_from.year, slip.date_from.month))

            salary_in_leave = slip._get_salary_in_leave(date_from, date_to, contract.id)
            salary_base += salary_in_leave

            periodo_anterior = PeriodoAnterior(slip)

            accumulated = periodo_anterior.cargar_periodo(date_from, date_to)
            basic_accumulated = accumulated.get('BASIC')
            if basic_accumulated:
                salary_base += basic_accumulated.total
                ids_by_type['basic_accumulated'] = basic_accumulated.line_ids

            # CORRECCIÓN: Contar meses con datos de nóminas confirmadas
            # Usar search_read para eficiencia (solo traer date_from)
            payslips_data = self.env['hr.payslip'].search_read([
                ('contract_id', '=', contract.id),
                ('state', 'in', ['done', 'paid']),
                ('date_from', '>=', date_from),
                ('date_from', '<=', date_to),
                ('id', '!=', slip.id),
            ], fields=['date_from'])
            for ps_data in payslips_data:
                if ps_data.get('date_from'):
                    dt = ps_data['date_from']
                    meses_con_salario.add((dt.year, dt.month))

            # CORRECCIÓN: Calcular promedio de salario dividiendo entre meses con datos
            # En lugar de sumar sin dividir (bug anterior)
            num_meses = len(meses_con_salario) if meses_con_salario else 1
            data_base['salary_total_acumulado'] = salary_base  # Guardar suma total para trazabilidad
            data_base['meses_con_salario'] = num_meses
            # El promedio mensual es la suma dividida entre meses con datos
            data_base['salary'] = salary_base / num_meses if num_meses > 0 else salary_base
        else:
            # Método simple: usar salario mensual completo (NO proporcionalizar aquí)
            # La proporcionalización viene de days_worked en la fórmula final /360
            full_wage = contract.wage
            data_base['salary'] = full_wage

            # IMPORTANTE: Recopilar line_ids del salario básico actual para reglas_usadas
            # Aunque usamos el salario del contrato, necesitamos las líneas para trazabilidad
            categories = localdict.get('categories', CategoryCollection())
            basic_data = categories.get('BASIC')
            if basic_data:
                ids_by_type['basic_current'] = basic_data.line_ids

        # Determinar campo de filtro según tipo de prestación (separado para liquidación)
        base_field = get_prestacion_base_field(tipo_prestacion, contexto='liquidacion')

        # Calcular meses del período para el promedio
        # Prima: 6 meses, Cesantías/Intereses: 12 meses
        meses_periodo = 6 if tipo_prestacion == 'prima' else 12

        # ══════════════════════════════════════════════════════════════════════════
        # CONSULTA DIRECTA POR CAMPO BASE (base_prima, base_cesantias, etc.)
        # ══════════════════════════════════════════════════════════════════════════
        # Consultamos directamente las líneas de nómina del período que tienen
        # reglas con el base_field activo (ej: base_prima=True).
        # Esto es más preciso porque respeta la configuración de cada regla salarial.

        # Separar variable acumulado vs actual para cálculo correcto
        variable_salary_acumulado = 0  # De nóminas anteriores (se promedia)
        variable_salary_actual = 0      # De nómina actual (NO se promedia)
        lineas_base_variable = []

        variable_lines = self._get_variable_lines_for_prestacion(
            slip, contract, date_from, date_to, base_field
        )

        include_aux_variables = bool(
            es_liquidacion
            and annual_parameters
            and getattr(annual_parameters, 'aux_in_variables_liquidation', False)
        )
        excluded_categories = ['BASIC', 'DED', 'PROV', 'SSOCIAL', 'PRESTACIONES_SOCIALES', 'NET']
        if not include_aux_variables:
            excluded_categories.append('AUX')
        for line_data in variable_lines:
            if line_data.get('category_code') in excluded_categories:
                continue
            variable_salary_acumulado += line_data['total']
            ids_by_type['variable_accumulated'].append(line_data['line_id'])

            # El acumulado se promedia usando días trabajados / 360
            valor_usado = line_data['total'] * days_worked / 360 if days_worked > 0 else line_data['total']
            lineas_base_variable.append({
                'codigo': line_data['rule_code'],
                'nombre': line_data['rule_name'],
                'categoria': line_data['category_code'],
                'total': line_data['total'],
                'valor_usado': valor_usado,
                'dias_formula': f"{days_worked}/360",
                'tipo': 'variable_acumulado',
                'payslip_id': line_data['payslip_id'],
                'slip_number': line_data['slip_number'] or '',
                'fecha': line_data['date_from'].strftime('%Y-%m-%d') if line_data['date_from'] else '',
            })

        # ══════════════════════════════════════════════════════════════════════════
        # INCLUIR LINEAS VARIABLES DE LA NOMINA ACTUAL (HE, comisiones, etc.)
        # ══════════════════════════════════════════════════════════════════════════
        # Usamos localdict['rules'] que contiene las reglas ya calculadas en este
        # compute_sheet() (igual que el IBC). slip.line_ids puede no tener las
        # lineas actualizadas durante el calculo.
        # IMPORTANTE: El variable ACTUAL no se promedia - es el valor real del período.
        rules = localdict.get('rules', {})
        for code, rule_data in rules.items():
            rule = rule_data.rule
            if not rule:
                continue

            cat = rule.category_id
            if not cat or cat.code in excluded_categories:
                continue
            # Tambien verificar categoria padre
            if cat.parent_id and cat.parent_id.code in excluded_categories:
                continue

            amount = rule_data.total
            if amount <= 0:
                continue

            # Verificar si la regla tiene el base_field activo
            try:
                if base_field in rule._fields:
                    has_base_field = getattr(rule, base_field)
                else:
                    has_base_field = False
            except (AttributeError, KeyError):
                has_base_field = False

            if has_base_field:
                variable_salary_actual += amount
                ids_by_type['variable_current'].append(rule.id)

                # Si días < 30: tomar completo (100%) - liquidaciones parciales
                # Si días >= 30: promediar con días/360
                if days_worked < 30:
                    valor_usado_actual = amount
                    formula_actual = '100%'
                else:
                    valor_usado_actual = amount * days_worked / 360 if days_worked > 0 else amount
                    formula_actual = f"{days_worked}/360"

                lineas_base_variable.append({
                    'codigo': rule.code,
                    'nombre': rule.name if isinstance(rule.name, str) else str(rule.name),
                    'categoria': cat.code,
                    'total': amount,
                    'valor_usado': valor_usado_actual,
                    'dias_formula': formula_actual,
                    'tipo': 'variable_actual',
                    'payslip_id': slip.id,
                    'slip_number': slip.number or '',
                    'fecha': slip.date_from.strftime('%Y-%m-%d') if slip.date_from else '',
                })

        # ══════════════════════════════════════════════════════════════════════════
        # CALCULO DEL SALARIO VARIABLE PARA LA BASE
        # ══════════════════════════════════════════════════════════════════════════
        # - ACUMULADO (meses anteriores): siempre se promedia con días_trabajados / 360
        # - ACTUAL (mismo mes): si días < 30 -> 100%, si días >= 30 -> promedia
        variable_acumulado_promedio = variable_salary_acumulado * days_worked / 360 if days_worked > 0 else variable_salary_acumulado

        if days_worked < 30:
            variable_actual_para_base = variable_salary_actual  # 100%
            formula_actual = '100%'
        else:
            variable_actual_para_base = variable_salary_actual * days_worked / 360 if days_worked > 0 else variable_salary_actual
            formula_actual = f"{days_worked}/360"

        # El variable total para la base
        variable_salary_para_base = variable_acumulado_promedio + variable_actual_para_base

        data_base['variable'] = variable_salary_para_base
        data_base['variable_acumulado'] = variable_acumulado_promedio
        data_base['variable_actual'] = variable_actual_para_base
        data_base['dias_formula_acumulado'] = f"{days_worked}/360"
        data_base['dias_formula_actual'] = formula_actual
        data_base['variable_total_acumulado'] = variable_salary_acumulado + variable_salary_actual

        # ══════════════════════════════════════════════════════════════════════════
        # SALARIO MENSUAL PARA BASE DE PRESTACIONES
        # ══════════════════════════════════════════════════════════════════════════
        # Para prestaciones sociales, la base debe ser el SALARIO MENSUAL (30 días).
        # Fórmula legal: (Salario Mensual × Días Trabajados) / 360
        # NOTA: Cuando compute_average=True, salary ya ES el promedio mensual
        # (suma de salarios / meses con datos), NO necesita normalización adicional.

        # ========== AUXILIO DE TRANSPORTE SEGUN TIPO DE PRESTACION ==========
        # Usa configuracion de res.config.settings para cada tipo:
        # - prima_incluye_auxilio (default True)
        # - cesantias_incluye_auxilio (default True)
        # - vacaciones_incluye_auxilio (default False)
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0

        # Determinar base variable para validar tope segun only_wage
        only_wage = contract.only_wage or 'wage'
        salario_variable_tope = data_base.get('variable', 0)
        if only_wage == 'wage_dev_exc':
            salario_variable_tope = self.env['hr.salary.rule.aux']._get_devengos_base_auxilio_tope(
                localdict,
                solo_marcadas=True,
            )
        data_base['variable_tope'] = salario_variable_tope

        # Determinar si aplica auxilio segun configuracion por tipo
        auxilio_validacion = self._provision_incluye_auxilio(
            tipo_prestacion,
            config_params,
            contract,
            data_base.get('salary', 0),  # Solo salario base para validacion de tope
            smmlv,
            salario_variable=salario_variable_tope,  # Variables para tope segun only_wage
            employee=employee,
            annual_parameters=annual_parameters,
            return_detail=True
        )
        aplica_auxilio = auxilio_validacion.get('aplica', False)

        if aplica_auxilio:
            metodo_auxilio = config_params.get('auxilio_prestaciones_metodo', 'dias_trabajados')
            auxilio_info = self.env['hr.salary.rule.aux'].compute_auxilio(
                metodo_auxilio,
                annual_parameters,
                contract,
                days_worked,
                30,
                dias_ausencias_no_justificadas=days_no_pay,
                date_from=date_from,
                date_to=date_to,
                exclude_payslip_id=slip.id,
                slip=slip,
            )
            # Si el contrato está en "Sin variación" y es liquidación, usar auxilio mensual completo
            if contract.modality_aux == 'basico' and slip.struct_process == 'contrato' and tipo_prestacion in ['prima', 'cesantias']:
                auxilio_mensual = annual_parameters.transportation_assistance_monthly if annual_parameters else 0
                auxilio_info = {
                    'auxilio': auxilio_mensual,
                    'auxilio_mensual': auxilio_mensual,
                    'modality_aux': contract.modality_aux or 'basico',
                    'proporcion': 1,
                    'dias_usados': 30,
                    'dias_descontados': 0,
                    'fuente': 'sin_variacion_contrato',
                }
            if contract.full_auxtransportation_settlement and slip.struct_id.process == 'contrato':
                auxilio_info = {
                    'auxilio': annual_parameters.transportation_assistance_monthly if annual_parameters else 0,
                    'auxilio_mensual': annual_parameters.transportation_assistance_monthly if annual_parameters else 0,
                    'modality_aux': contract.modality_aux or 'basico',
                    'proporcion': 1,
                    'dias_usados': 30,
                    'fuente': 'full_settlement',
                }
            data_base['static'] = auxilio_info['auxilio']
            data_base['static_mensual'] = auxilio_info['auxilio_mensual']
            data_base['auxilio_info'] = auxilio_info
        else:
            data_base['static'] = 0
            data_base['static_mensual'] = 0
            data_base['auxilio_info'] = {'auxilio': 0, 'auxilio_mensual': 0, 'modality_aux': 'no', 'proporcion': 0}

        # ══════════════════════════════════════════════════════════════════════════
        # CONCEPTOS ADICIONALES DEL CONTRATO (proyectar_prestaciones=True)
        # ══════════════════════════════════════════════════════════════════════════
        # Pasar fechas del período de prestación y flag de provisión simple
        conceptos_adicionales = self._get_conceptos_adicionales_prestacion(
            contract, slip, tipo_prestacion,
            date_from=date_from,
            date_to=date_to,
            es_provision_simple=use_simple_method
        )
        data_base['conceptos_adicionales'] = conceptos_adicionales
        data_base['conceptos_sumar'] = conceptos_adicionales['total_sumar']
        data_base['conceptos_restar'] = conceptos_adicionales['total_restar']
        data_base['conceptos_neto'] = conceptos_adicionales['neto']

        # ══════════════════════════════════════════════════════════════════════════
        # CALCULAR BASE MENSUAL PARA PRESTACIONES
        # ══════════════════════════════════════════════════════════════════════════
        # La base debe ser el salario MENSUAL que el empleado hubiera devengado
        # trabajando 30 días. La proporcionalización viene de days_worked en /360.
        # NOTA: Cuando compute_average=True, salary ya ES el promedio mensual
        # (suma de salarios / meses con datos), NO necesita normalización adicional.

        # Base = Salario (ya promediado si compute_average) + Variable (ya promediado) + Auxilio
        base = data_base.get('salary', 0) + data_base.get('variable', 0) + data_base.get('static', 0)

        # Agregar conceptos adicionales del contrato (devengos que suman, deducciones que restan)
        base += data_base.get('conceptos_neto', 0)

        base_diaria = base / 30

        # Calcular total según tipo de prestación
        if tipo_prestacion == 'prima':
            total = base * days_worked / 360
        elif tipo_prestacion == 'cesantias':
            total = base * days_worked / 360
        elif tipo_prestacion == 'intereses':
            # CORRECCIÓN: Fórmula correcta de intereses de cesantías
            # Cesantías proporcionales = base * (days_worked / 360)
            # Intereses = Cesantías proporcionales * 12% anual
            # Fórmula completa: base * (days_worked / 360) * 0.12
            cesantias_proporcionales = base * days_worked / 360
            total = cesantias_proporcionales * 0.12
        elif tipo_prestacion == 'vacaciones':
            total = base * days_worked / 720
        else:
            total = base * days_worked / 360

        # Generar nombre descriptivo
        if tipo_prestacion == 'prima':
            semestre = 1 if slip.date_to.month <= 6 else 2
            nombre = f"PRIMA DE SERVICIOS {semestre}° SEMESTRE {slip.date_to.year}"
        elif tipo_prestacion == 'cesantias':
            nombre = f"CESANTÍAS AÑO {slip.date_to.year}"
        elif tipo_prestacion == 'intereses':
            nombre = f"INTERESES DE CESANTÍAS {slip.date_to.year}"
        elif tipo_prestacion == 'vacaciones':
            nombre = f"VACACIONES {slip.date_to.year}"
        else:
            nombre = tipo_prestacion.upper()

        # Obtener valores anteriores para comparación
        code_regla_map = {
            'prima': 'PRIMA',
            'cesantias': 'CESANTIAS',
            'intereses': 'INTCESANTIAS',
            'vacaciones': 'VACCONTRATO'
        }
        code_regla = code_regla_map.get(tipo_prestacion, 'PRIMA')
        valores_anteriores = self._get_prestacion_previous_values(contract, code_regla, date_from, date_to)
        
        # Obtener reglas usadas para el calculo (retorna dict con 'detalle' y 'rule_ids')
        reglas_usadas_result = self._get_reglas_usadas_prestacion(localdict, tipo_prestacion, ids_by_type)
        reglas_usadas = reglas_usadas_result.get('detalle', [])
        source_rule_ids = reglas_usadas_result.get('rule_ids', [])

        # Calcular diferencia con periodo anterior
        diferencia = total - valores_anteriores['valor_anterior'] if valores_anteriores['valor_anterior'] > 0 else 0
        porcentaje_cambio = (diferencia / valores_anteriores['valor_anterior'] * 100) if valores_anteriores['valor_anterior'] > 0 else 0

        # Preparar datos de retorno
        data_kpi = {
            'base_diaria': base_diaria,
            'base_mensual': base,
            'days_worked': days_worked,
            'days_no_pay': days_no_pay,
            'salary_base': data_base.get('salary', 0),
            # Variable desglosado:
            'salary_variable': data_base.get('variable', 0),  # Total para base (acum_prom + actual)
            'salary_variable_acumulado': data_base.get('variable_acumulado', 0),  # Periodos ant promediado
            'salary_variable_actual': data_base.get('variable_actual', 0),  # Nomina actual (sin promediar)
            'salary_variable_total': data_base.get('variable_total_acumulado', 0),  # Total sin promediar
            'meses_periodo': meses_periodo,  # 6 para prima, 12 para cesantias
            'subsidy': data_base.get('static', 0),
            'subsidy_mensual': data_base.get('static_mensual', 0),
            'aplica_auxilio': aplica_auxilio,
            'compute_average': compute_average,
            'use_simple_method': use_simple_method,
            'descontar_suspensiones': descontar_suspensiones,
            'base_field_used': base_field,
            # Detalle de lineas que componen la base variable (HE, comisiones, bonificaciones, etc.)
            'lineas_base_variable': lineas_base_variable,
            # Trazabilidad y comparacion
            'valores_anteriores': valores_anteriores,
            'diferencia_periodo_anterior': diferencia,
            'porcentaje_cambio': porcentaje_cambio,
            'reglas_usadas': reglas_usadas,
            # Configuracion usada
            'configuracion': {
                'prst_wo_susp': config_params.get('prst_wo_susp', False),
                'prima_incluye_auxilio': config_params.get('prima_incluye_auxilio', True),
                'cesantias_incluye_auxilio': config_params.get('cesantias_incluye_auxilio', True),
                'vacaciones_incluye_auxilio': config_params.get('vacaciones_incluye_auxilio', False),
                'promedio_detectar_cambios': config_params.get('promedio_detectar_cambios', True),
                'aux_prst': config_params.get('aux_prst', False),
            },
            # Dias adicionales (cuotas especiales, ajustes)
            'dias_adicionales_info': dias_adicionales_info,
            # Conceptos adicionales del contrato
            'conceptos_adicionales': data_base.get('conceptos_adicionales', {}),
            'conceptos_sumar': data_base.get('conceptos_sumar', 0),
            'conceptos_restar': data_base.get('conceptos_restar', 0),
            'conceptos_neto': data_base.get('conceptos_neto', 0),
        }

        # Agregar informacion especifica para intereses de cesantias
        if tipo_prestacion == 'intereses':
            cesantias_value = base * days_worked / 360
            data_kpi.update({
                'cesantias_proporcionales': cesantias_value,
                'tasa_interes': 12.0,  # 12% anual
                'formula': f'Cesantias x 12% = {cesantias_value:,.2f} x 0.12 = {total:,.2f}',
            })

        # ========== ESTRUCTURA DETALLADA PARA WIDGET ==========
        # Obtener etiquetas dinamicas del contrato
        contract_labels = self._get_contract_labels(contract)
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        auxilio_mensual = annual_parameters.transportation_assistance_monthly if annual_parameters else 0

        # Tasas desde configuracion
        from .config_reglas import PRESTACIONES_CONFIG
        tasas_legales = {
            'prima': PRESTACIONES_CONFIG['prima']['tasa'],
            'cesantias': PRESTACIONES_CONFIG['cesantias']['tasa'],
            'vacaciones': PRESTACIONES_CONFIG['vacaciones']['tasa'],
            'intereses': PRESTACIONES_CONFIG['intereses']['tasa'],
        }
        tasa_usada = tasas_legales.get(tipo_prestacion, 8.33)

        # Determinar base para validacion de tope segun only_wage (logica centralizada)
        only_wage = contract.only_wage or 'wage'
        base_validacion_tope = self.env['hr.salary.rule.aux']._calcular_base_validacion_tope(
            only_wage,
            data_base.get('salary', 0),
            data_base.get('variable', 0),
            variable_tope=data_base.get('variable_tope', 0)
        )

        # Config auxilio detallada
        config_auxilio = {
            'aplica': aplica_auxilio,
            'razon_no_aplica': '',
            'modality_aux': contract.modality_aux or 'basico',
            'modality_aux_label': contract_labels['modality_aux_label'],
            'only_wage': only_wage,
            'only_wage_label': contract_labels['only_wage_label'],
            'not_pay_auxtransportation': contract.not_pay_auxtransportation,
            'not_validate_top_auxtransportation': contract.not_validate_top_auxtransportation,
            'auxilio_mensual_legal': auxilio_mensual,
            'auxilio_aplicado': data_base.get('static', 0),
            'smmlv': smmlv,
            'dos_smmlv': 2 * smmlv,
            'base_validacion_tope': base_validacion_tope,
            'supera_tope': base_validacion_tope >= 2 * smmlv if smmlv > 0 else False,
        }

        # Determinar razon si no aplica auxilio
        if not aplica_auxilio:
            if auxilio_validacion.get('razon'):
                config_auxilio['razon_no_aplica'] = auxilio_validacion['razon']
            elif contract.not_pay_auxtransportation:
                config_auxilio['razon_no_aplica'] = 'Contrato: No liquidar auxilio'
            elif contract.modality_aux == 'no':
                config_auxilio['razon_no_aplica'] = 'Modalidad: Sin auxilio'
            elif not config_params.get(f'{tipo_prestacion}_incluye_auxilio', False) and tipo_prestacion != 'intereses':
                config_auxilio['razon_no_aplica'] = f'Config: {tipo_prestacion} no incluye auxilio'
            elif config_auxilio['supera_tope']:
                config_auxilio['razon_no_aplica'] = 'Salario supera 2 SMMLV'

        # Config global
        config_global = {
            'metodo_simple_activo': use_simple_method,
            'descontar_suspensiones': descontar_suspensiones,
            'prst_wo_susp_activo': config_params.get('prst_wo_susp', False),
            'promedio_detectar_cambios': config_params.get('promedio_detectar_cambios', True),
            'prima_incluye_auxilio': config_params.get('prima_incluye_auxilio', True),
            'cesantias_incluye_auxilio': config_params.get('cesantias_incluye_auxilio', True),
            'vacaciones_incluye_auxilio': config_params.get('vacaciones_incluye_auxilio', False),
            'aux_prst': config_params.get('aux_prst', False),
            'tasa_prima': tasas_legales['prima'],
            'tasa_cesantias': tasas_legales['cesantias'],
            'tasa_vacaciones': tasas_legales['vacaciones'],
            'tasa_intereses': tasas_legales['intereses'],
        }

        # Resumen ejecutivo
        resumen = {
            'tipo_provision': tipo_prestacion.upper(),
            'metodo_calculo': 'LIQUIDACION' if slip.struct_process == 'contrato' else 'PRESTACION',
            'periodo': f"{date_from} al {date_to}",
            'empleado': slip.employee_id.name if slip.employee_id else '',
            'contrato': contract.sequence if contract else '',
            'base_total': base,
            'valor_prestacion': total,
            'tasa_aplicada': tasa_usada,
            'es_liquidacion': slip.struct_process == 'contrato',
            # Componentes del salario base
            'salary_basic': data_base.get('salary', 0),
            'salary_variable': data_base.get('variable', 0),  # Total para base
            'salary_variable_acumulado': data_base.get('variable_acumulado', 0),  # Periodos ant promediado
            'salary_variable_actual': data_base.get('variable_actual', 0),  # Nomina actual (SIN promediar)
            'salary_variable_total': data_base.get('variable_total_acumulado', 0),
            'salary_auxilio': data_base.get('static', 0),
            'meses_periodo': meses_periodo,
            # Conceptos adicionales del contrato
            'conceptos_sumar': data_base.get('conceptos_sumar', 0),
            'conceptos_restar': data_base.get('conceptos_restar', 0),
            'conceptos_neto': data_base.get('conceptos_neto', 0),
            'conceptos_detalle': data_base.get('conceptos_adicionales', {}).get('conceptos_sumar', []) +
                                 data_base.get('conceptos_adicionales', {}).get('conceptos_restar', []),
            # Dias adicionales
            'dias_adicionales': dias_adicionales_info.get('dias_adicionales', 0),
            'dias_descuento': dias_adicionales_info.get('dias_descuento', 0),
            'motivo_dias_adicionales': dias_adicionales_info.get('motivo_adicional', ''),
            'motivo_dias_descuento': dias_adicionales_info.get('motivo_descuento', ''),
        }

        # Indicadores visuales
        indicadores = []
        indicadores.append({
            'tipo': 'metodo',
            'icono': 'fa-file-text-o' if slip.struct_process == 'contrato' else 'fa-money',
            'color': 'danger' if slip.struct_process == 'contrato' else 'success',
            'texto': 'Liquidacion' if slip.struct_process == 'contrato' else 'Prestacion',
            'descripcion': nombre
        })

        modality_label = contract_labels['modality_aux_label']
        if aplica_auxilio:
            indicadores.append({
                'tipo': 'auxilio',
                'icono': 'fa-bus',
                'color': 'primary',
                'texto': f'Auxilio {modality_label}',
                'descripcion': f'${data_base.get("static", 0):,.0f}'
            })
        else:
            indicadores.append({
                'tipo': 'auxilio',
                'icono': 'fa-ban',
                'color': 'muted',
                'texto': 'Sin Auxilio',
                'descripcion': config_auxilio.get('razon_no_aplica', 'No aplica')
            })

        # Indicador de conceptos adicionales
        conceptos_neto = data_base.get('conceptos_neto', 0)
        if conceptos_neto != 0:
            if conceptos_neto > 0:
                indicadores.append({
                    'tipo': 'conceptos',
                    'icono': 'fa-plus-circle',
                    'color': 'success',
                    'texto': 'Conceptos Adicionales',
                    'descripcion': f'+${conceptos_neto:,.0f}'
                })
            else:
                indicadores.append({
                    'tipo': 'conceptos',
                    'icono': 'fa-minus-circle',
                    'color': 'warning',
                    'texto': 'Deducciones Adicionales',
                    'descripcion': f'${conceptos_neto:,.0f}'
                })

        # Indicador de dias adicionales
        dias_adicionales = dias_adicionales_info.get('dias_adicionales', 0)
        dias_descuento = dias_adicionales_info.get('dias_descuento', 0)
        if dias_adicionales > 0:
            indicadores.append({
                'tipo': 'dias_adicionales',
                'icono': 'fa-calendar-plus-o',
                'color': 'info',
                'texto': f'+{dias_adicionales} dias',
                'descripcion': dias_adicionales_info.get('motivo_adicional', 'Dias adicionales')
            })
        if dias_descuento > 0:
            indicadores.append({
                'tipo': 'dias_descuento',
                'icono': 'fa-calendar-minus-o',
                'color': 'danger',
                'texto': f'-{dias_descuento} dias',
                'descripcion': dias_adicionales_info.get('motivo_descuento', 'Dias descontados')
            })

        # Formula pasos
        formula_pasos = []
        formula_pasos.append({
            'paso': 1,
            'concepto': 'Periodo',
            'tipo': 'periodo',
            'resultado': f'{date_from} a {date_to}',
            'formula_texto': f'{days_worked} dias'
        })
        formula_pasos.append({
            'paso': 2,
            'concepto': 'Base Diaria',
            'tipo': 'base_diaria',
            'resultado': base_diaria,
            'formula_texto': f'${base_diaria:,.0f}/dia'
        })
        formula_pasos.append({
            'paso': 3,
            'concepto': 'Base Mensual',
            'tipo': 'base_mensual',
            'resultado': base,
            'formula_texto': f'${base_diaria:,.0f} x 30 = ${base:,.0f}'
        })

        if tipo_prestacion == 'intereses':
            cesantias_val = base * days_worked / 360
            formula_pasos.append({
                'paso': 4,
                'concepto': 'Cesantias Proporcionales',
                'tipo': 'cesantias',
                'resultado': cesantias_val,
                'formula_texto': f'${base:,.0f} x {days_worked}/360 = ${cesantias_val:,.0f}'
            })
            formula_pasos.append({
                'paso': 5,
                'concepto': f'Intereses ({tasa_usada}%)',
                'tipo': 'resultado',
                'resultado': total,
                'formula_texto': f'${cesantias_val:,.0f} x {tasa_usada}% = ${total:,.0f}'
            })
        else:
            formula_pasos.append({
                'paso': 4,
                'concepto': f'{tipo_prestacion.title()} ({days_worked} dias)',
                'tipo': 'resultado',
                'resultado': total,
                'formula_texto': f'${base:,.0f} x {days_worked}/360 = ${total:,.0f}'
            })

        # Formula final
        if tipo_prestacion == 'intereses':
            formula_final = {
                'base': base * days_worked / 360,
                'tasa': tasa_usada,
                'resultado': total,
                'texto': f'Cesantias x {tasa_usada}% = Intereses'
            }
        else:
            formula_final = {
                'base': base,
                'dias': days_worked,
                'resultado': total,
                'texto': f'Base x {days_worked}/360 = {tipo_prestacion.title()}'
            }

        datos = {
            'data_kpi': data_kpi,
            'ids_by_type': ids_by_type,
            'fecha_inicio': date_from.strftime('%Y-%m-%d') if date_from else '',
            'fecha_fin': date_to.strftime('%Y-%m-%d') if date_to else '',
            'monto_total': float(total),
            'source_rule_ids': source_rule_ids,  # IDs de reglas salariales usadas
            'trazabilidad': {
                'reglas_usadas': reglas_usadas,
                'valores_anteriores': valores_anteriores,
                'diferencia': diferencia,
                'porcentaje_cambio': porcentaje_cambio
            },
            # ========== DATOS DETALLADOS PARA WIDGET ==========
            'resumen': resumen,
            'config_auxilio': config_auxilio,
            'config_global': config_global,
            'indicadores': indicadores,
            'formula_pasos': formula_pasos,
            'formula_final': formula_final,
        }

        return base_diaria, days_worked, 100, nombre, "", datos


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE PRESTACIONES (PAGO)
    # ══════════════════════════════════════════════════════════════════════════


    def _get_reglas_usadas_prestacion(self, localdict, tipo_prestacion, ids_by_type):
        """
        Obtiene listado detallado de reglas usadas para el cálculo de prestaciones.

        Returns:
            dict: {
                'detalle': [{
                    'rule_id': int,
                    'codigo': str,
                    'nombre': str,
                    'categoria': str,
                    'total': float,
                    'line_ids': [int],
                    'tipo': str ('basic_current', 'basic_accumulated', 'variable_current', 'variable_accumulated')
                }],
                'rule_ids': [int] - Lista de IDs de reglas salariales usadas
            }
        """
        reglas_usadas = []
        rule_ids_set = set()  # Para evitar duplicados
        rules = localdict.get('rules', {})
        
        # Campo base separado para liquidación
        base_field = get_prestacion_base_field(tipo_prestacion, contexto='liquidacion')
        annual_parameters = localdict.get('annual_parameters')
        slip = localdict.get('slip')
        es_liquidacion = bool(slip and slip.struct_process == 'contrato')
        include_aux_variables = bool(
            es_liquidacion
            and annual_parameters
            and getattr(annual_parameters, 'aux_in_variables_liquidation', False)
        )
        
        # Procesar reglas basicas actuales
        for line_id in ids_by_type.get('basic_current', []):
            line = self.env['hr.payslip.line'].browse(line_id)
            if line.exists():
                rule = line.salary_rule_id
                if rule and rule[base_field]:
                    rule_ids_set.add(rule.id)
                    reglas_usadas.append({
                        'rule_id': rule.id,
                        'codigo': rule.code,
                        'nombre': rule.name,
                        'categoria': 'BASIC',
                        'total': line.total,
                        'line_ids': [line_id],
                        'tipo': 'basic_current',
                        'fecha_nomina': line.slip_id.date_to,
                        'payslip_id': line.slip_id.id,
                        'payslip_number': line.slip_id.number or 'Borrador'
                    })

        # Procesar reglas basicas acumuladas
        for line_id in ids_by_type.get('basic_accumulated', []):
            line = self.env['hr.payslip.line'].browse(line_id)
            if line.exists():
                rule = line.salary_rule_id
                if rule and rule[base_field]:
                    rule_ids_set.add(rule.id)
                    reglas_usadas.append({
                        'rule_id': rule.id,
                        'codigo': rule.code,
                        'nombre': rule.name,
                        'categoria': 'BASIC',
                        'total': line.total,
                        'line_ids': [line_id],
                        'tipo': 'basic_accumulated',
                        'fecha_nomina': line.slip_id.date_to,
                        'payslip_id': line.slip_id.id,
                        'payslip_number': line.slip_id.number or 'Borrador'
                    })

        # Procesar reglas variables actuales
        for line_id in ids_by_type.get('variable_current', []):
            line = self.env['hr.payslip.line'].browse(line_id)
            if line.exists():
                rule = line.salary_rule_id
                cat = rule.category_id if rule else None
                if not include_aux_variables and cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX')):
                    continue
                if rule and rule[base_field]:
                    rule_ids_set.add(rule.id)
                    reglas_usadas.append({
                        'rule_id': rule.id,
                        'codigo': rule.code,
                        'nombre': rule.name,
                        'categoria': rule.category_id.code if rule.category_id else 'VARIABLE',
                        'total': line.total,
                        'line_ids': [line_id],
                        'tipo': 'variable_current',
                        'fecha_nomina': line.slip_id.date_to,
                        'payslip_id': line.slip_id.id,
                        'payslip_number': line.slip_id.number or 'Borrador'
                    })

        # Procesar reglas variables acumuladas
        for line_id in ids_by_type.get('variable_accumulated', []):
            line = self.env['hr.payslip.line'].browse(line_id)
            if line.exists():
                rule = line.salary_rule_id
                cat = rule.category_id if rule else None
                if not include_aux_variables and cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX')):
                    continue
                if rule and rule[base_field]:
                    rule_ids_set.add(rule.id)
                    reglas_usadas.append({
                        'rule_id': rule.id,
                        'codigo': rule.code,
                        'nombre': rule.name,
                        'categoria': rule.category_id.code if rule.category_id else 'VARIABLE',
                        'total': line.total,
                        'line_ids': [line_id],
                        'tipo': 'variable_accumulated',
                        'fecha_nomina': line.slip_id.date_to,
                        'payslip_id': line.slip_id.id,
                        'payslip_number': line.slip_id.number or 'Borrador'
                    })

        return {
            'detalle': reglas_usadas,
            'rule_ids': list(rule_ids_set)
        }


    def _get_periodo_prestacion(self, slip, contract, tipo_prestacion):
        """
        Calcula el período de cálculo para prestaciones sociales de manera centralizada.
        Elimina duplicación de código en _prima, _cesantias, _intcesantias.
        
        IMPORTANTE: Si es liquidación de prima en nómina (pay_primas_in_payroll) y se liquida
        dentro de una quincena, usa date_prima si existe para determinar el período correcto.
        
        Args:
            slip: Objeto hr.payslip
            contract: Objeto hr.contract
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            
        Returns:
            tuple: (date_from, date_to)
        """
        es_prima_en_nomina = slip.pay_primas_in_payroll and tipo_prestacion == 'prima'
        es_estructura_prima = slip.struct_process == 'prima'
        es_liquidacion = slip.struct_process == 'contrato'

        # ──────────────────────────────────────────────────────────────────────
        # LIQUIDACION DE CONTRATO: si el usuario ajusto manualmente las fechas
        # date_prima / date_cesantias / date_vacaciones en la pestaña LIQ. DE
        # CONTRATO, esas son las fechas de corte que mandan, EXCEPTO cuando
        # use_manual_days esta activo (en ese caso, manual_days override las
        # fechas y se usa la logica estandar para el periodo).
        # ──────────────────────────────────────────────────────────────────────
        if es_liquidacion and not getattr(slip, 'use_manual_days', False):
            if tipo_prestacion == 'prima' and slip.date_prima:
                date_from = slip.date_prima
                date_to = slip.date_liquidacion or slip.date_to
            elif tipo_prestacion in ['cesantias', 'intereses'] and slip.date_cesantias:
                date_from = slip.date_cesantias
                date_to = slip.date_liquidacion or slip.date_to
            elif tipo_prestacion == 'vacaciones' and slip.date_vacaciones:
                date_from = slip.date_vacaciones
                date_to = slip.date_liquidacion or slip.date_to
            else:
                # Fallback a la logica estandar si no hay fecha manual
                date_from, date_to = self._get_periodo_estandar(slip, tipo_prestacion,
                    es_prima_en_nomina, es_estructura_prima)
            # En liquidacion sin use_manual_days, NO sobreescribir date_from
            # con contract.date_start (el usuario eligio explicitamente la fecha
            # de corte). El ajuste por contract.date_start solo aplica al
            # fallback estandar.
            return date_from, date_to

        # ──────────────────────────────────────────────────────────────────────
        # NOMINA REGULAR / VACACIONES / PRIMA EN NOMINA: logica estandar
        # ──────────────────────────────────────────────────────────────────────
        if tipo_prestacion == 'prima':
            # Si es liquidación de prima en nómina o estructura de primas, validar fecha de quincena
            if (es_prima_en_nomina or es_estructura_prima) and slip.date_prima and slip.date_to.day == 15:
                # Usar date_prima para determinar el semestre, pero calcular desde el inicio del semestre
                fecha_referencia = slip.date_prima
                if fecha_referencia.month <= 6:
                    date_from = fecha_referencia.replace(month=1, day=1)
                    date_to = fecha_referencia.replace(month=6, day=30)
                else:
                    date_from = fecha_referencia.replace(month=7, day=1)
                    date_to = fecha_referencia.replace(month=12, day=31)
            else:
                # Lógica estándar: inicio del semestre
                if slip.date_from.month <= 6:
                    date_from = slip.date_from.replace(month=1, day=1)
                    date_to = slip.date_from.replace(month=6, day=30)
                else:
                    date_from = slip.date_from.replace(month=7, day=1)
                    date_to = slip.date_from.replace(month=12, day=31)
        elif tipo_prestacion in ['cesantias', 'intereses']:
            date_from = slip.date_to.replace(month=1, day=1)
            date_to = slip.date_to.replace(month=12, day=31)
        else:  # vacaciones
            date_from = slip.date_from
            date_to = slip.date_to

        # Ajustar si contrato inició después del date_from calculado
        if contract.date_start and contract.date_start > date_from:
            date_from = contract.date_start

        # Ajustar por fecha de inicio de contrato
        if contract.date_start and date_from < contract.date_start:
            date_from = contract.date_start

        return date_from, date_to

    def _get_periodo_estandar(self, slip, tipo_prestacion, es_prima_en_nomina, es_estructura_prima):
        """Helper: calculo del periodo estandar (sin fechas manuales del usuario)."""
        if tipo_prestacion == 'prima':
            if slip.date_from.month <= 6:
                return slip.date_from.replace(month=1, day=1), slip.date_from.replace(month=6, day=30)
            return slip.date_from.replace(month=7, day=1), slip.date_from.replace(month=12, day=31)
        if tipo_prestacion in ['cesantias', 'intereses']:
            return slip.date_to.replace(month=1, day=1), slip.date_to.replace(month=12, day=31)
        return slip.date_from, slip.date_to

    def _get_variable_lines_for_prestacion(self, slip, contract, date_from, date_to, base_field):
        """
        Obtiene las líneas de nómina del período que tienen reglas con base_field=True.

        Esta consulta filtra por el campo base correspondiente (base_prima, base_cesantias, etc.)

        Args:
            slip: Objeto hr.payslip actual (para excluirlo)
            contract: Objeto hr.contract
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            base_field: Campo a filtrar ('base_prima', 'base_cesantias', etc.)

        Returns:
            list: Lista de dicts con información de cada línea
        """
        # Mapear base_field a tipo_prestacion
        tipo_map = {
            'base_prima': 'prima',
            'base_prima_provision': 'prima',
            'base_prima_liquidacion': 'prima',
            'base_cesantias': 'cesantias',
            'base_cesantias_provision': 'cesantias',
            'base_cesantias_liquidacion': 'cesantias',
            'base_vacaciones': 'vacaciones',
            'base_vacaciones_provision': 'vacaciones',
            'base_vacaciones_liquidacion': 'vacaciones',
            'base_vacaciones_dinero': 'vacaciones_dinero',
            'base_vacaciones_dinero_provision': 'vacaciones_dinero',
            'base_vacaciones_dinero_liquidacion': 'vacaciones_dinero',
            'base_intereses_cesantias': 'intereses_cesantias',
            'base_intereses_cesantias_provision': 'intereses_cesantias',
            'base_intereses_cesantias_liquidacion': 'intereses_cesantias',
        }
        tipo_prestacion = tipo_map.get(base_field, 'all')

        # Excluir categoría BASIC porque ya se suma en salary_base
        # y categorías de prestaciones/deducciones que no aplican
        excluded_categories = ['BASIC', 'DED', 'PROV', 'SSOCIAL', 'PRESTACIONES_SOCIALES', 'NET']

        # Usar servicio centralizado de consultas
        query_service = self.env['period.payslip.query.service']
        result = query_service.get_prestaciones_data(
            contract_id=contract.id,
            date_from=date_from,
            date_to=date_to,
            tipo_prestacion=tipo_prestacion,
            contexto_base='liquidacion',
            exclude_payslip_id=slip.id if slip else None,
            states=('done', 'paid'),
            excluded_categories=excluded_categories,
        )

        # Convertir resultado del servicio al formato esperado
        lines = []
        for line_detail in result.get('list', []):
            # NO FILTRAR por base_field aquí - el SQL ya filtró correctamente
            # El CASE en el SQL devuelve el PRIMER base_* que sea TRUE,
            # pero una regla puede tener múltiples base_* en TRUE (ej: COM_QA)
            # Por eso confiamos en el WHERE del SQL, no en el base_field devuelto

            lines.append({
                'line_id': line_detail['line_id'],
                'total': line_detail.get('total', 0.0),
                'rule_code': line_detail.get('rule_code', ''),
                'rule_name': line_detail.get('rule_name', ''),
                'category_code': line_detail.get('category_code', ''),
                'payslip_id': line_detail.get('payslip_id'),
                'slip_number': line_detail.get('payslip_number', ''),
                'date_from': line_detail.get('date_from'),
            })

        return lines
