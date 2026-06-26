# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - SALARIO BASICO
===================================

Metodos extraidos de hr_rule_adapted.py
Categoria: BASIC

ESTRUCTURA:
- Helpers de calculo de salario (reutilizables)
- Clase principal HrSalaryRuleBasic
"""

from odoo import models, api
from datetime import timedelta
from .config_reglas import (
    days360, crear_log_data, crear_resultado_regla, crear_resultado_vacio,
    crear_computation_estandar, crear_indicador, crear_paso_calculo
)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS DE CALCULO DE SALARIO - Funciones reutilizables
# ══════════════════════════════════════════════════════════════════════════════

def get_wage_changes_in_period(contract, date_from, date_to):
    """
    Obtiene los cambios de salario dentro de un periodo.

    Args:
        contract: hr.contract
        date_from: fecha inicio del periodo
        date_to: fecha fin del periodo

    Returns:
        list: Lista de cambios ordenados por fecha, cada uno con:
            - date_start: fecha del cambio
            - wage: nuevo salario
    """
    if not contract.change_wage_ids:
        return []

    cambios = sorted(contract.change_wage_ids, key=lambda c: c.date_start)
    return [c for c in cambios if date_from <= c.date_start <= date_to]


def calculate_weighted_average_wage(contract, date_from, date_to, parcial_factor=1.0):
    """
    Calcula el salario promedio ponderado en un periodo considerando cambios de salario.

    REUTILIZABLE para:
    - Calculo de salario basico mensual
    - Promedio de salario para prestaciones (prima, cesantias, vacaciones)
    - IBD (Ingreso Base de liquidacion)

    Args:
        contract: hr.contract
        date_from: fecha inicio del periodo
        date_to: fecha fin del periodo
        parcial_factor: factor de tiempo parcial (default 1.0 = tiempo completo)

    Returns:
        dict: {
            'salario_promedio': float,
            'dias_totales': int,
            'segmentos': list de dict con detalles por segmento,
            'tiene_cambios': bool
        }
    """
    wage_base = (contract.wage or 0) * parcial_factor
    dias_totales = days360(date_from, date_to)

    if dias_totales <= 0:
        return {
            'salario_promedio': wage_base,
            'dias_totales': 0,
            'segmentos': [],
            'tiene_cambios': False
        }

    # Obtener cambios en el periodo
    cambios = get_wage_changes_in_period(contract, date_from, date_to)

    if not cambios:
        # Sin cambios: salario uniforme
        return {
            'salario_promedio': wage_base,
            'dias_totales': dias_totales,
            'segmentos': [{
                'fecha_inicio': date_from,
                'fecha_fin': date_to,
                'salario': wage_base,
                'dias': dias_totales
            }],
            'tiene_cambios': False
        }

    # Con cambios: calcular promedio ponderado
    segmentos = []
    fecha_actual = date_from
    salario_actual = wage_base
    suma_ponderada = 0

    for cambio in cambios:
        # Segmento antes del cambio
        if cambio.date_start > fecha_actual:
            dias_segmento = days360(fecha_actual, cambio.date_start - timedelta(days=1))
            if dias_segmento > 0:
                segmentos.append({
                    'fecha_inicio': fecha_actual,
                    'fecha_fin': cambio.date_start - timedelta(days=1),
                    'salario': salario_actual,
                    'dias': dias_segmento
                })
                suma_ponderada += salario_actual * dias_segmento

        # Actualizar para siguiente segmento
        fecha_actual = cambio.date_start
        salario_actual = (cambio.wage or 0) * parcial_factor

    # Segmento final (desde ultimo cambio hasta date_to)
    if fecha_actual <= date_to:
        dias_segmento = days360(fecha_actual, date_to)
        if dias_segmento > 0:
            segmentos.append({
                'fecha_inicio': fecha_actual,
                'fecha_fin': date_to,
                'salario': salario_actual,
                'dias': dias_segmento
            })
            suma_ponderada += salario_actual * dias_segmento

    # Calcular promedio ponderado
    dias_calculados = sum(s['dias'] for s in segmentos)
    salario_promedio = suma_ponderada / dias_calculados if dias_calculados > 0 else wage_base

    return {
        'salario_promedio': salario_promedio,
        'dias_totales': dias_calculados,
        'segmentos': segmentos,
        'tiene_cambios': True
    }


def calculate_proportional_salary(wage_monthly, days_worked, is_hourly=False, hours_monthly=240, hours_worked=0):
    """
    Calcula el salario proporcional por dias u horas trabajadas.

    Args:
        wage_monthly: salario mensual
        days_worked: dias trabajados
        is_hourly: si es pago por hora
        hours_monthly: horas mensuales (default 240)
        hours_worked: horas trabajadas

    Returns:
        dict: {
            'total': monto total,
            'rate': tasa por dia/hora,
            'quantity': cantidad (dias u horas)
        }
    """
    if is_hourly:
        rate = float(wage_monthly) / float(hours_monthly) if hours_monthly else 0
        total = rate * float(hours_worked)
        quantity = hours_worked
    else:
        rate = float(wage_monthly) / 30.0
        total = rate * float(days_worked)
        quantity = days_worked

    return {
        'total': total,
        'rate': rate,
        'quantity': quantity
    }


def calculate_salary_with_changes(contract, slip, parcial_factor=1.0, is_hourly=False, hours_monthly=240):
    """
    Calcula el salario del periodo considerando cambios de salario.

    Funcion principal que combina las helpers para el calculo completo.

    Args:
        contract: hr.contract
        slip: hr.payslip
        parcial_factor: factor tiempo parcial
        is_hourly: si es pago por hora
        hours_monthly: horas mensuales

    Returns:
        dict: {
            'total_pay': monto total,
            'avg_rate': tasa promedio,
            'quantity': cantidad (dias u horas),
            'has_changes': bool,
            'details': dict con detalles del calculo
        }
    """
    date_from = slip.date_from
    date_to = slip.date_to

    # Obtener dias/horas trabajados
    worked = None
    for wd in slip.worked_days_line_ids:
        if wd.code == 'WORK100':
            worked = wd
            break

    total_days = worked.number_of_days if worked else 0
    total_hours = worked.number_of_hours if worked else 0

    old_wage = (contract.wage or 0) * parcial_factor

    # Buscar cambio de salario en el periodo
    cambios = get_wage_changes_in_period(contract, date_from, date_to)
    change = cambios[0] if cambios else None

    if change:
        change_date = change.date_start
        new_wage = (change.wage or 0) * parcial_factor

        days_before = days360(date_from, change_date - timedelta(days=1)) if change_date > date_from else 0
        days_after = days360(change_date, date_to)

        # Ajustar si excede dias trabajados
        if days_before + days_after > total_days:
            days_before = min(days_before, total_days)
            days_after = total_days - days_before

        if is_hourly:
            hours_before = round(total_hours * days_before / total_days, 2) if total_days > 0 else 0
            hours_after = total_hours - hours_before

            rate_before = float(old_wage) / float(hours_monthly)
            rate_after = float(new_wage) / float(hours_monthly)
            pay_before = rate_before * float(hours_before)
            pay_after = rate_after * float(hours_after)
        else:
            rate_before = float(old_wage) / 30.0
            rate_after = float(new_wage) / 30.0
            pay_before = rate_before * float(days_before)
            pay_after = rate_after * float(days_after)

        total_pay = pay_before + pay_after
        quantity = total_hours if is_hourly else total_days
        avg_rate = float(total_pay / quantity) if quantity > 0 else 0.0

        return {
            'total_pay': total_pay,
            'avg_rate': avg_rate,
            'quantity': quantity,
            'has_changes': True,
            'details': {
                'old_wage': float(old_wage),
                'new_wage': float(new_wage),
                'change_date': str(change_date),
                'days_before': float(days_before),
                'days_after': float(days_after),
                'rate_before': float(rate_before),
                'rate_after': float(rate_after),
                'pay_before': float(pay_before),
                'pay_after': float(pay_after),
            }
        }
    else:
        # Sin cambio de salario
        result = calculate_proportional_salary(
            old_wage,
            total_days,
            is_hourly,
            hours_monthly,
            total_hours
        )

        return {
            'total_pay': result['total'],
            'avg_rate': result['rate'],
            'quantity': result['quantity'],
            'has_changes': False,
            'details': {
                'wage': float(old_wage),
                'days': float(total_days),
                'rate': float(result['rate']),
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# HELPER DE NOMBRES - Funcion privada para nombres de reglas
# ══════════════════════════════════════════════════════════════════════════════

def _get_rule_name_fn(salary_type, localdict=None, **kwargs):
    """
    Funcion privada: Genera el nombre de la regla salarial segun el tipo.

    Args:
        salary_type: Tipo de salario (basic, integral, parcial, por_dia, sostenimiento)
        localdict: Diccionario de contexto (opcional, requerido para sostenimiento)
        **kwargs: Argumentos adicionales:
            - parcial_percentage: Porcentaje tiempo parcial
            - total_days: Dias trabajados (para por_dia)

    Returns:
        str: Nombre de la regla
    """
    parcial_percentage = kwargs.get('parcial_percentage', 100)
    total_days = kwargs.get('total_days', 0)

    names = {
        'basic': 'SUELDO BASICO',
        'integral': 'SUELDO BASICO INTEGRAL',
        'parcial': f'SUELDO TIEMPO PARCIAL ({parcial_percentage}%)',
        'por_dia': f'SUELDO POR DIA ({int(total_days)} dias)',
    }

    if salary_type == 'sostenimiento' and localdict:
        employee = localdict.get('employee')
        if employee and employee.tipo_coti_id:
            tipo_coti = employee.tipo_coti_id.code
            return 'CUOTA DE SOSTENIMIENTO LECTIVO' if tipo_coti == '12' else 'CUOTA DE SOSTENIMIENTO PRODUCTIVO'
        return 'CUOTA DE SOSTENIMIENTO'

    return names.get(salary_type, f'SALARIO {salary_type.upper()}')


# ══════════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL - Reglas de Salario Basico
# ══════════════════════════════════════════════════════════════════════════════

class HrSalaryRuleBasic(models.AbstractModel):
    """Mixin para reglas de salario basico"""

    _name = 'hr.salary.rule.basic'
    _description = 'Metodos para Reglas de Salario Basico'


    def _obtener_salario_efectivo_contrato(self, contract, wage_base=None, annual_parameters=None):
        """
        Obtiene el salario efectivo del contrato segun su modalidad.

        Considera las diferentes modalidades de salario:
        - basico/especie/variable: wage o partial_wage_computed
        - integral: wage * 0.7 (excluye factor prestacional 30%)
        - sostenimiento: cuota de sostenimiento basada en SMMLV
        - parcial: partial_wage_computed
        - subcontrato (obra_parcial/obra_integral): wage * factor

        Args:
            contract: Contrato del empleado
            wage_base: Salario base opcional (para cambios de salario)
            annual_parameters: Parametros anuales (para sostenimiento)

        Returns:
            float: Salario efectivo mensual
        """
        wage = wage_base if wage_base is not None else (contract.wage or 0)
        modality = contract.modality_salary or 'basico'
        subcontract = contract.subcontract_type
        full_hours = 48.0
        if annual_parameters:
            if annual_parameters.hours_weekly:
                full_hours = annual_parameters.hours_weekly
            elif annual_parameters.hours_monthly:
                full_hours = (annual_parameters.hours_monthly / 30.0) * 7
            elif annual_parameters.hours_daily:
                full_hours = annual_parameters.hours_daily * 7

        # 1. Salario Integral: solo 70% (excluye factor prestacional 30%)
        if modality == 'integral' and not subcontract:
            return wage * 0.7

        # 2. Sostenimiento (aprendices): usar cuota calculada de SMMLV
        if modality == 'sostenimiento' and not subcontract:
            if contract.apprentice_wage:
                return contract.apprentice_wage
            if annual_parameters:
                smmlv = annual_parameters.smmlv_monthly or 0
                pct = 100.0 if contract.apprentice_stage == 'productiva' else 75.0
                return smmlv * (pct / 100.0)
            return wage

        # 3. Tiempo parcial: usar salario proporcional calculado
        if contract.parcial:
            if wage_base is not None:
                hours = contract.partial_hours_weekly or full_hours
                proportion = hours / full_hours if full_hours else 0
                return wage_base * proportion
            return contract.partial_wage_computed or wage

        # 4. Subcontrato obra parcial/integral: aplicar factor 0.5
        if subcontract in ('obra_parcial', 'obra_integral'):
            factor = 0.5
            if contract.parcial:
                hours = contract.partial_hours_weekly or full_hours
                factor = factor * (hours / full_hours if full_hours else 0)
            return wage * factor

        # 5. Basico/especie/variable: salario directo
        return wage


    def _calcular_salario_periodo_con_cambios(self, contract, slip, date_from, date_to,
                                              dias_ausencias_no_pagadas=0, descontar_suspensiones=True,
                                              detectar_cambios_salario=True, annual_parameters=None):
        """
        Calcula el salario del periodo considerando cambios de salario y ausencias.

        Si hay cambios de salario en el periodo, calcula proporcional por cada franja.
        Las ausencias no pagadas se descuentan de la franja donde ocurrieron.

        IMPORTANTE: Usa _obtener_salario_efectivo_contrato para considerar las
        diferentes modalidades de salario (integral, sostenimiento, parcial, etc.)

        Args:
            contract: Contrato del empleado
            slip: Nomina actual
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            dias_ausencias_no_pagadas: Dias de ausencias no pagadas a descontar
            descontar_suspensiones: Si True, resta los dias no pagados
            detectar_cambios_salario: Si True, busca cambios de salario en el periodo
            annual_parameters: Parametros anuales (requerido para sostenimiento)

        Returns:
            dict: {
                'salario_total': float - Salario proporcional del periodo,
                'dias_pagados': float - Dias efectivos pagados,
                'franjas': list - Detalle de cada franja de salario,
                'hubo_cambio_salario': bool - Si hubo cambio de salario en el periodo
            }
        """
        hubo_cambio = False
        cambios_salario = []

        if detectar_cambios_salario:
            for change in sorted(contract.change_wage_ids, key=lambda x: x.date_start):
                if change.date_start <= date_to:
                    cambios_salario.append({
                        'fecha': change.date_start,
                        'salario': change.wage
                    })
            cambios_en_periodo = [c for c in cambios_salario if date_from <= c['fecha'] <= date_to]
            hubo_cambio = len(cambios_en_periodo) > 0

        if not hubo_cambio:
            dias_periodo = days360(date_from, date_to)
            usar_dias_manuales = False
            dias_manuales = 0
            if slip and slip.use_manual_days:
                usar_dias_manuales = True
                dias_manuales = slip.manual_days or 0

            salario_mensual = self._obtener_salario_efectivo_contrato(
                contract, wage_base=None, annual_parameters=annual_parameters
            )

            dias_pagados = float(dias_manuales) if usar_dias_manuales and dias_manuales > 0 else dias_periodo

            if descontar_suspensiones and dias_ausencias_no_pagadas > 0:
                dias_pagados = max(0, dias_pagados - dias_ausencias_no_pagadas)

            salario_proporcional = (salario_mensual / 30.0) * dias_pagados

            return {
                'salario_total': salario_proporcional,
                'dias_pagados': dias_pagados,
                'dias_periodo': dias_periodo,
                'dias_manuales_usados': usar_dias_manuales,
                'franjas': [{
                    'fecha_inicio': date_from,
                    'fecha_fin': date_to,
                    'salario_mensual': salario_mensual,
                    'dias': dias_pagados,
                    'salario_proporcional': salario_proporcional
                }],
                'hubo_cambio_salario': False,
                'salario_mensual_actual': salario_mensual
            }

        franjas = []
        fecha_actual = date_from
        wage_inicial = contract.get_wage_in_date(date_from)
        salario_actual = self._obtener_salario_efectivo_contrato(
            contract, wage_base=wage_inicial, annual_parameters=annual_parameters
        )

        cambios_aplicables = sorted(
            [c for c in cambios_salario if c['fecha'] > date_from and c['fecha'] <= date_to],
            key=lambda x: x['fecha']
        )

        for cambio in cambios_aplicables:
            fecha_fin_franja = cambio['fecha'] - timedelta(days=1)
            if fecha_fin_franja >= fecha_actual:
                dias_franja = days360(fecha_actual, fecha_fin_franja)
                franjas.append({
                    'fecha_inicio': fecha_actual,
                    'fecha_fin': fecha_fin_franja,
                    'salario_mensual': salario_actual,
                    'dias': dias_franja,
                    'salario_proporcional': (salario_actual / 30.0) * dias_franja
                })

            fecha_actual = cambio['fecha']
            salario_actual = self._obtener_salario_efectivo_contrato(
                contract, wage_base=cambio['salario'], annual_parameters=annual_parameters
            )

        if fecha_actual <= date_to:
            dias_franja = days360(fecha_actual, date_to)
            franjas.append({
                'fecha_inicio': fecha_actual,
                'fecha_fin': date_to,
                'salario_mensual': salario_actual,
                'dias': dias_franja,
                'salario_proporcional': (salario_actual / 30.0) * dias_franja
            })

        dias_total = sum(f['dias'] for f in franjas)
        salario_total = sum(f['salario_proporcional'] for f in franjas)

        if descontar_suspensiones and dias_ausencias_no_pagadas > 0:
            factor_descuento = max(0, (dias_total - dias_ausencias_no_pagadas) / dias_total) if dias_total > 0 else 0
            salario_total = salario_total * factor_descuento
            dias_total = max(0, dias_total - dias_ausencias_no_pagadas)

            for franja in franjas:
                franja['dias_despues_descuento'] = franja['dias'] * factor_descuento
                franja['salario_despues_descuento'] = franja['salario_proporcional'] * factor_descuento

        usar_dias_manuales = False
        dias_manuales = 0
        if slip and slip.use_manual_days:
            usar_dias_manuales = True
            dias_manuales = slip.manual_days or 0

        dias_periodo_original = sum(f['dias'] for f in franjas)
        if usar_dias_manuales and dias_manuales > 0 and dias_periodo_original > 0:
            factor_manual = float(dias_manuales) / float(dias_periodo_original)
            salario_total = salario_total * factor_manual
            dias_total = float(dias_manuales)

        return {
            'salario_total': salario_total,
            'dias_pagados': dias_total,
            'dias_periodo': dias_periodo_original,
            'dias_manuales_usados': usar_dias_manuales,
            'franjas': franjas,
            'hubo_cambio_salario': True,
            'salario_mensual_actual': salario_actual
        }


    def _get_rule_name(self, salary_type, localdict=None, **kwargs):
        """Wrapper de instancia para _get_rule_name_fn"""
        return _get_rule_name_fn(salary_type, localdict, **kwargs)


    def _calculate_salary_generic(self, localdict, salary_type='basic'):
        """
        Metodo generico para calcular salarios - solo construccion de datos.
        Soporta: basic, integral, sostenimiento, parcial, por_dia

        Usa las funciones helper para el calculo real.
        """

        contract = localdict['contract']
        slip = localdict['slip']

        if salary_type == 'basic' and (contract.subcontract_type or contract.parcial or contract.modality_salary not in ('basico', 'especie', 'variable')):
            return crear_resultado_vacio('SUELDO BASICO', 'Modalidad no aplicable', 'basic')

        if salary_type == 'integral' and (contract.subcontract_type or contract.modality_salary != 'integral'):
            return crear_resultado_vacio('SUELDO INTEGRAL', 'Modalidad integral no aplicable', 'basic')

        if salary_type == 'sostenimiento' and (contract.subcontract_type or contract.modality_salary != 'sostenimiento'):
            return crear_resultado_vacio('SOSTENIMIENTO', 'Modalidad sostenimiento no aplicable', 'basic')

        if salary_type == 'parcial' and contract.subcontract_type:
            return crear_resultado_vacio('SUELDO PARCIAL', 'No aplica para subcontratos', 'basic')

        if salary_type == 'por_dia' and not contract.subcontract_type:
            return crear_resultado_vacio('SUELDO POR DIA', 'Solo aplica para subcontratos', 'basic')

        # Obtener dias/horas trabajados
        worked = localdict['worked_days'].get('WORK100')
        total_days = worked.number_of_days if worked else 0
        total_hours = worked.number_of_hours if worked else 0

        if salary_type == 'por_dia':
            dias_calculo = localdict.get('dias_calculo', 0)
            # Tope segun el periodo del recibo (normativa Colombia)
            raw_days = (slip.date_to - slip.date_from).days + 1
            tope_periodo = 15 if raw_days <= 16 else 30

            # En liquidacion de contrato (struct_process == 'contrato'),
            # manual_days representa los dias trabajados en el ultimo mes
            # de pago (puede ser hasta 30) y NO esta sujeto al tope del
            # periodo del recibo (que suele ser solo unos dias).
            is_liquidation = getattr(slip, 'struct_process', '') == 'contrato'

            if slip.use_manual_days and slip.manual_days > 0:
                if is_liquidation:
                    # Liquidacion: respetar manual_days hasta 30 dias por mes
                    dias_calculo = min(float(slip.manual_days), 30.0)
                else:
                    # Nomina regular: aplicar tope del periodo (quincenal/mensual)
                    # para evitar inflar el sueldo cuando manual_days se usa
                    # como base de prima/cesantias.
                    dias_calculo = min(float(slip.manual_days), tope_periodo)
            elif worked and worked.number_of_days:
                # Usar WORK100 que ya tiene restadas las ausencias (incapacidad,
                # licencia, etc.) y normalizados los dias 31/febrero.
                dias_calculo = worked.number_of_days
            elif not dias_calculo:
                dias_calculo = min(raw_days, tope_periodo)
            total_days = dias_calculo

        is_hourly = slip.struct_type_id.wage_type == 'hourly'
        hours_monthly = localdict['annual_parameters'].hours_monthly

        # Factor parcial
        parcial_factor = 1.0
        parcial_percentage = 100
        if salary_type == 'parcial':
            parcial_factor = contract.factor or 50 / 100.0
            parcial_percentage = int(parcial_factor * 100)

        # Usar helper para calcular con cambios de salario
        calc_result = calculate_salary_with_changes(
            contract,
            slip,
            parcial_factor,
            is_hourly,
            hours_monthly
        )

        # Para sostenimiento de aprendices: recalcular con base en la etapa
        # efectiva del PERIODO de nómina (lectiva vs productiva), usando
        # apr_prod_date como referencia, no el campo computado apprentice_stage
        # que refleja siempre el estado ACTUAL del contrato.
        if salary_type == 'sostenimiento':
            contract_type = contract.contract_type_id
            is_apprenticeship = contract_type and getattr(contract_type, 'is_apprenticeship', False)
            annual_params = localdict.get('annual_parameters')
            smmlv = annual_params.smmlv_monthly if annual_params else 0
            if is_apprenticeship and smmlv:
                apr_prod_date = contract.apr_prod_date
                date_from = slip.date_from
                date_to = slip.date_to
                pct_l = contract_type.apprentice_wage_pct_lectiva or 75.0
                pct_p = contract_type.apprentice_wage_pct_productiva or 100.0

                _qty = calc_result['quantity']
                if apr_prod_date and date_from >= apr_prod_date:
                    # Periodo completamente en etapa productiva
                    wage_periodo = smmlv * (pct_p / 100.0)
                    rate = wage_periodo / 30.0
                    calc_result['avg_rate'] = rate
                    calc_result['total_pay'] = rate * float(_qty)
                    calc_result['has_changes'] = False
                    calc_result['details'] = {
                        'wage': wage_periodo,
                        'days': float(_qty),
                        'rate': rate,
                    }
                elif apr_prod_date and date_to >= apr_prod_date:
                    # Periodo dividido: parte en lectiva, parte en productiva
                    wage_l = smmlv * (pct_l / 100.0)
                    wage_p = smmlv * (pct_p / 100.0)
                    days_lectiva = (apr_prod_date - date_from).days
                    days_productiva = (date_to - apr_prod_date).days + 1
                    pay_l = (wage_l / 30.0) * float(days_lectiva)
                    pay_p = (wage_p / 30.0) * float(days_productiva)
                    total_pay_new = pay_l + pay_p
                    avg_rate_new = total_pay_new / float(_qty) if _qty else 0.0
                    calc_result['total_pay'] = total_pay_new
                    calc_result['avg_rate'] = avg_rate_new
                    calc_result['has_changes'] = True
                    calc_result['details'] = {
                        'old_wage': wage_l,
                        'new_wage': wage_p,
                        'change_date': str(apr_prod_date),
                        'days_before': float(days_lectiva),
                        'days_after': float(days_productiva),
                        'rate_before': wage_l / 30.0,
                        'rate_after': wage_p / 30.0,
                        'pay_before': pay_l,
                        'pay_after': pay_p,
                    }
                else:
                    # Periodo completamente en etapa lectiva (o sin apr_prod_date)
                    wage_periodo = smmlv * (pct_l / 100.0)
                    rate = wage_periodo / 30.0
                    calc_result['avg_rate'] = rate
                    calc_result['total_pay'] = rate * float(_qty)
                    calc_result['has_changes'] = False
                    calc_result['details'] = {
                        'wage': wage_periodo,
                        'days': float(_qty),
                        'rate': rate,
                    }

        # Ajustar para por_dia - SIEMPRE usar dias manuales cuando aplica
        if salary_type == 'por_dia':
            old_wage = (contract.wage or 0) * parcial_factor
            rate = float(old_wage) / 30.0
            calc_result['total_pay'] = rate * float(total_days)
            calc_result['quantity'] = total_days
            calc_result['avg_rate'] = rate
            calc_result['has_changes'] = False  # Reset para no afectar log

        total_pay = calc_result['total_pay']
        quantity = calc_result['quantity']
        avg_rate = calc_result['avg_rate']

        # Log data
        if calc_result['has_changes']:
            log_data = crear_log_data(
                'success', 'basic',
                has_changes=True,
                salary_type=salary_type,
                **calc_result['details']
            )
        else:
            log_data = crear_log_data(
                'success', 'basic',
                has_changes=False,
                total=float(total_pay),
                salary_type=salary_type,
                **calc_result['details']
            )

        # Nombre segun tipo - usando metodo generico
        name = self._get_rule_name(
            salary_type,
            localdict=localdict,
            parcial_percentage=parcial_percentage,
            total_days=total_days
        )

        # Crear computation estandarizada para el widget
        indicadores = [
            crear_indicador('Dias', float(quantity), 'info', 'number'),
        ]
        if salary_type == 'parcial':
            indicadores.append(crear_indicador('Factor', f'{parcial_percentage}%', 'warning', 'text'))

        old_wage = calc_result['details'].get('wage', calc_result['details'].get('old_wage', 0))

        pasos = [
            crear_paso_calculo('Salario Mensual', float(old_wage), 'currency'),
            crear_paso_calculo('Dias Trabajados', float(quantity), 'number'),
            crear_paso_calculo('Valor Dia', float(avg_rate), 'currency'),
            crear_paso_calculo('Total', float(avg_rate * quantity), 'currency', highlight=True),
        ]

        if calc_result['has_changes']:
            details = calc_result['details']
            pasos = [
                crear_paso_calculo('Salario Anterior', float(details['old_wage']), 'currency'),
                crear_paso_calculo('Salario Nuevo', float(details['new_wage']), 'currency'),
                crear_paso_calculo('Dias Salario Anterior', float(details['days_before']), 'number'),
                crear_paso_calculo('Dias Salario Nuevo', float(details['days_after']), 'number'),
                crear_paso_calculo('Total', float(total_pay), 'currency', highlight=True),
            ]

        computation = crear_computation_estandar(
            'basico',
            titulo=name,
            formula='Salario / 30 x Dias',
            indicadores=indicadores,
            pasos=pasos,
            base_legal='Art. 127 CST',
            datos=log_data,
        )

        return crear_resultado_regla(avg_rate, quantity, 100.0, name, log_data=log_data, data_kpi=computation)


    def _basic(self, localdict):
        """Calcula sueldo basico para modalidades: basico, especie, variable."""
        return self._calculate_salary_generic(localdict, salary_type='basic')

    def _basic002(self, localdict):
        """Calcula sueldo basico integral. Incluye factor prestacional (30%)."""
        return self._calculate_salary_generic(localdict, salary_type='integral')

    def _basic003(self, localdict):
        """Calcula cuota de sostenimiento para aprendices (etapa lectiva/productiva)."""
        return self._calculate_salary_generic(localdict, salary_type='sostenimiento')

    def _basic004(self, localdict):
        """Calcula sueldo tiempo parcial. Aplica factor configurado en contrato (contract.factor)."""
        contract = localdict['contract']

        # Solo aplica si el contrato tiene marcado tiempo parcial
        if not contract.parcial:
            return crear_resultado_vacio('SUELDO TIEMPO PARCIAL', 'Contrato no es tiempo parcial', 'parcial')

        return self._calculate_salary_generic(localdict, salary_type='parcial')

    def _basic005(self, localdict):
        """Calcula sueldo por dias especificos. Usa localdict['dias_calculo'] o slip.manual_days."""
        return self._calculate_salary_generic(localdict, salary_type='por_dia')
