# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - INDEMNIZACIÓN
==================================

Método para cálculo de indemnización por terminación de contrato.
Centraliza la lógica de negocio de la indemnización.

Referencia Legal:
- Artículo 64 del Código Sustantivo del Trabajo (CST)
  URL: http://www.secretariasenado.gov.co/senado/basedoc/codigo_sustantivo_trabajo_pr001.html#64
"""

from odoo import models, api
from dateutil.relativedelta import relativedelta
from .config_reglas import (
    DAYS_YEAR, DAYS_MONTH, dias_periodo_base, normalizar_base_dias,
    to_decimal, decimal_round,
    crear_log_data, crear_resultado_regla, crear_resultado_vacio, crear_data_kpi,
    crear_computation_estandar, crear_indicador, crear_paso_calculo
)


class HrSalaryRuleIndem(models.AbstractModel):
    """Mixin para reglas de indemnización"""

    _name = 'hr.salary.rule.indem'
    _description = 'Métodos para Indemnización'

    @api.model
    def _get_indemnization_base_days(self, contract):
        """Obtiene base de dias (360/365) para la indemnizacion."""
        base_days = None
        if contract and contract.employee_id:
            try:
                base_days = self._get_base_dias_empleado(contract.employee_id)
            except (AttributeError, KeyError):
                base_days = contract.employee_id.base_dias_prestaciones
        return normalizar_base_dias(base_days, default=DAYS_YEAR)

    @api.model
    def _calculate_variable_salary_details(self, contract, termination_date, contract_type):
        """Calcula totales y promedios del salario variable."""
        details = {
            'total_variable': 0.0,
            'daily_avg': 0.0,
            'monthly_avg': 0.0,
            'days_period': 0,
            'days_worked': 0,
            'days_no_pay': 0,
            'date_from': None,
            'date_to': None,
        }

        if not contract or not termination_date or not contract_type:
            return details

        if not contract_type.include_variable_salary:
            return details

        months = contract_type.variable_salary_months or 12
        date_from = termination_date - relativedelta(months=months)
        if contract.date_start and date_from < contract.date_start:
            date_from = contract.date_start

        base_days = self._get_indemnization_base_days(contract)
        dias_periodo = dias_periodo_base(date_from, termination_date, base_days, incluir_inicio=True)
        if dias_periodo <= 0:
            return details

        dias_ausencias = 0.0
        leave_domain = [
            ('date', '>=', date_from),
            ('date', '<=', termination_date),
            ('state', 'in', ['paid', 'validate', 'validated']),
            ('leave_id.contract_id', '=', contract.id),
            ('leave_id.employee_id', '=', contract.employee_id.id),
            ('leave_id.holiday_status_id.unpaid_absences', '=', True),
        ]
        grouped = self.env['hr.leave.line']._read_group(
            leave_domain,
            groupby=[],
            aggregates=['days_payslip:sum'],
        )
        dias_ausencias += float(grouped[0][0] or 0.0) if grouped else 0.0
        ausencias_historico = self.env['hr.absence.history'].search([
            ('star_date', '>=', date_from),
            ('end_date', '<=', termination_date),
            ('employee_id', '=', contract.employee_id.id),
            ('leave_type_id.unpaid_absences', '=', True),
        ])
        dias_ausencias += sum(a.days for a in ausencias_historico)

        dias_trabajados = dias_periodo - dias_ausencias
        if dias_trabajados <= 0:
            return details

        date_from_str = date_from.strftime('%Y-%m-%d')
        date_to_str = termination_date.strftime('%Y-%m-%d')

        self.env.cr.execute("""
            SELECT COALESCE(SUM(accumulated), 0) as accumulated
            FROM (
                SELECT COALESCE(SUM(pl.total), 0) as accumulated
                FROM hr_payslip as hp
                INNER JOIN hr_payslip_line as pl ON hp.id = pl.slip_id
                INNER JOIN hr_salary_rule hc ON pl.salary_rule_id = hc.id
                    AND hc.base_compensation = true
                INNER JOIN hr_salary_rule_category hsc ON hc.category_id = hsc.id
                    AND (hsc.code != 'BASIC' OR hc.code = 'BASICTURNOS')
                WHERE hp.state = 'done'
                    AND hp.contract_id = %s
                    AND (hp.date_from BETWEEN %s AND %s
                        OR hp.date_to BETWEEN %s AND %s)

                UNION ALL

                SELECT COALESCE(SUM(pl.amount), 0) as accumulated
                FROM hr_accumulated_payroll as pl
                INNER JOIN hr_salary_rule hc ON pl.salary_rule_id = hc.id
                    AND hc.base_compensation = true
                INNER JOIN hr_salary_rule_category hsc ON hc.category_id = hsc.id
                    AND (hsc.code != 'BASIC' OR hc.code = 'BASICTURNOS')
                WHERE pl.employee_id = %s
                    AND pl.date BETWEEN %s AND %s
            ) AS A
        """, (
            contract.id, date_from_str, date_to_str, date_from_str, date_to_str,
            contract.employee_id.id, date_from_str, date_to_str
        ))

        res = self.env.cr.fetchone()
        total_payslips = res[0] if res and res[0] else 0.0

        total_concepts = 0.0
  
        total_variable = total_payslips + total_concepts
        daily_avg = (total_variable / dias_trabajados) if total_variable and dias_trabajados else 0.0
        monthly_avg = daily_avg * DAYS_MONTH

        details.update({
            'total_variable': total_variable,
            'daily_avg': daily_avg,
            'monthly_avg': monthly_avg,
            'days_period': dias_periodo,
            'days_worked': dias_trabajados,
            'days_no_pay': dias_ausencias,
            'date_from': date_from,
            'date_to': termination_date,
        })
        return details

    @api.model
    def _calculate_indemnization_data(self, contract, termination_date, contract_type=None):
        """Calcula la indemnizacion segun tipo de contrato."""
        if not contract or not termination_date:
            return {}

        contract_type = contract_type or contract.contract_type_id
        base_days = self._get_indemnization_base_days(contract)
        daily_salary_basic = (contract.wage or 0.0) / 30.0

        result = {
            'base_salary': contract.wage,
            'variable_salary_avg': 0.0,
            'total_salary': contract.wage,
            'remaining_days': 0,
            'remaining_months': 0,
            'indemnization_amount': 0.0,
            'calculation_detail': '',
            'base_days': base_days,
            'daily_salary_basic': daily_salary_basic,
            'daily_salary_variable': 0.0,
            'daily_salary_total': daily_salary_basic,
        }

        if not contract_type or contract_type.indemnization_type == 'no_aplica':
            result['calculation_detail'] = 'No aplica indemnización para este tipo de contrato.'
            return result

        if contract_type.include_variable_salary:
            variable_details = self._calculate_variable_salary_details(
                contract, termination_date, contract_type
            )
            variable_avg = variable_details.get('monthly_avg', 0.0)
            result.update({
                'variable_salary_avg': variable_avg,
                'variable_salary_daily': variable_details.get('daily_avg', 0.0),
                'variable_salary_total': variable_details.get('total_variable', 0.0),
                'variable_salary_days': variable_details.get('days_worked', 0),
                'variable_salary_period_start': variable_details.get('date_from'),
                'variable_salary_period_end': variable_details.get('date_to'),
            })
            result['total_salary'] = (contract.wage or 0.0) + variable_avg
            result['daily_salary_variable'] = variable_details.get('daily_avg', 0.0)
            result['daily_salary_total'] = result['daily_salary_basic'] + result['daily_salary_variable']
        else:
            result['total_salary'] = contract.wage or 0.0
            result['daily_salary_total'] = result['daily_salary_basic']

        if contract_type.indemnization_type == 'dias_faltantes':
            return self._calculate_indemnization_fijo(contract, termination_date, contract_type, result)
        if contract_type.indemnization_type == 'tabla_antiguedad':
            return self._calculate_indemnization_indefinido(contract, termination_date, contract_type, result)

        return result

    @api.model
    def _calculate_indemnization_fijo(self, contract, termination_date, contract_type, result):
        """Calcula indemnizacion para contratos a termino fijo u obra."""
        if not contract.date_end:
            result['calculation_detail'] = (
                'El contrato no tiene fecha de fin definida. '
                'No se puede calcular la indemnización por días faltantes.'
            )
            return result

        if termination_date >= contract.date_end:
            result['calculation_detail'] = (
                'La fecha de terminación es igual o posterior a la fecha fin del contrato. '
                'No aplica indemnización.'
            )
            return result

        remaining = relativedelta(contract.date_end, termination_date)
        remaining_months = remaining.years * 12 + remaining.months
        remaining_days = remaining.days

        base_days = result.get('base_days') or self._get_indemnization_base_days(contract)
        total_remaining_days = dias_periodo_base(
            termination_date,
            contract.date_end,
            base_days,
            incluir_inicio=False
        )

        result['remaining_months'] = remaining_months
        result['remaining_days'] = remaining_days
        result['total_remaining_days'] = total_remaining_days

        daily_salary = result.get('daily_salary_total') or (result['total_salary'] / 30.0)

        if contract_type.contract_category == 'obra':
            min_days = contract_type.indemnization_min_days or 15
            if total_remaining_days < min_days:
                indemnization_days = min_days
                indemnization = daily_salary * indemnization_days
                result['calculation_detail'] = (
                    'Art. 64 CST - Contrato por obra/labor:\n'
                    '- Días restantes: %s\n'
                    '- Como es menor a %s días, se aplica el mínimo legal.\n'
                    '- Días indemnización: %s\n'
                    '- Indemnización: $%s'
                ) % (
                    total_remaining_days, min_days, min_days,
                    '{:,.0f}'.format(indemnization)
                )
            else:
                indemnization_days = total_remaining_days
                indemnization = daily_salary * indemnization_days
                result['calculation_detail'] = (
                    'Art. 64 CST - Contrato por obra/labor:\n'
                    '- Días restantes hasta fin de obra: %s\n'
                    '- Salario diario: $%s\n'
                    '- Indemnización: $%s'
                ) % (
                    total_remaining_days,
                    '{:,.0f}'.format(daily_salary),
                    '{:,.0f}'.format(indemnization)
                )
        else:
            indemnization_days = total_remaining_days
            indemnization = daily_salary * indemnization_days

        result['indemnization_amount'] = indemnization
        result['indemnization_days'] = indemnization_days

        if not result['calculation_detail']:
            result['calculation_detail'] = (
                'Cálculo según Art. 64 CST:\n'
                '- Fecha terminación: %s\n'
                '- Fecha fin contrato: %s\n'
                '- Tiempo restante: %s meses y %s días\n'
                '- Base días: %s\n'
                '- Salario mensual: $%s\n'
                '- Indemnización: $%s'
            ) % (
                termination_date, contract.date_end,
                remaining_months, remaining_days,
                base_days,
                '{:,.0f}'.format(result['total_salary']),
                '{:,.0f}'.format(indemnization)
            )

        return result

    @api.model
    def _calculate_indemnization_indefinido(self, contract, termination_date, contract_type, result):
        """Calcula indemnizacion para contratos a termino indefinido."""
        start_date = contract.date_start
        base_days = result.get('base_days') or self._get_indemnization_base_days(contract)
        total_days_worked = dias_periodo_base(start_date, termination_date, base_days, incluir_inicio=True)

        rel = relativedelta(termination_date, start_date)
        years = rel.years
        months = rel.months

        full_years = int(total_days_worked // base_days) if base_days else 0
        remaining_days = max(total_days_worked - (full_years * base_days), 0)
        fraction_year = (remaining_days / base_days) if base_days else 0
        total_years = full_years + fraction_year

        annual_params = self.env['hr.annual.parameters'].get_for_year(
            termination_date.year,
            company_id=(contract.company_id.id if contract.company_id else self.env.company.id),
            raise_if_not_found=True,
        )

        smmlv = annual_params.smmlv_monthly
        is_high_salary = result['total_salary'] >= (smmlv * 10)

        daily_salary = result.get('daily_salary_total') or (result['total_salary'] / 30.0)

        if is_high_salary:
            if total_years < 1:
                indemnization_days = 20
            else:
                indemnization_days = 20 + (15 * (max(full_years - 1, 0) + fraction_year))
        else:
            if total_years < 1:
                indemnization_days = 30
            else:
                indemnization_days = 30 + (20 * (max(full_years - 1, 0) + fraction_year))

        indemnization = daily_salary * indemnization_days
        result['indemnization_amount'] = indemnization
        result['indemnization_days'] = indemnization_days
        result['total_days_worked'] = total_days_worked
        result['total_years_worked'] = total_years

        result['calculation_detail'] = (
            'Cálculo según Art. 64 CST (Tabla por antigüedad):\n'
            '- Antigüedad: %s años y %s meses\n'
            '- Base días: %s\n'
            '- Salario mensual: $%s\n'
            '- Salario >= 10 SMMLV: %s\n'
            '- Días de indemnización: %.1f\n'
            '- Indemnización: $%s'
        ) % (
            years, months,
            base_days,
            '{:,.0f}'.format(result['total_salary']),
            'Sí' if is_high_salary else 'No',
            indemnization_days,
            '{:,.0f}'.format(indemnization)
        )

        return result

    def _indem(self, data_payslip):
        """
        Calcula la indemnización por terminación de contrato sin justa causa.
        Usa la lógica centralizada de indemnización.

        Args:
            data_payslip (dict): Diccionario con datos de liquidación

        Returns:
            tuple: (valor_diario, días, porcentaje, nombre, log_html, datos_para_visualización)
        """

        slip = data_payslip.get('slip')
        contract = data_payslip.get('contract')

        # Validaciones básicas
        if not slip or not contract:
            return 0, 0, 0, 0, "", {}

        if not slip.reason_retiro or not slip.have_compensation:
            return 0, 0, 0, 0, "", {}

        settlement_date = slip.date_liquidacion
        if not settlement_date:
            return 0, 0, 0, 0, "", {}

        date_start = contract.date_start
        if not date_start:
            return 0, 0, 0, 0, "", {}

        # Obtener tipo de contrato
        contract_type = contract.contract_type_id
        if not contract_type:
            return 0, 0, 0, 0, "", {}

        # Calcular indemnización con la lógica centralizada
        result = self._calculate_indemnization_data(contract, settlement_date, contract_type)

        # Si no hay indemnización, retornar vacío
        if result.get('indemnization_amount', 0) <= 0:
            return 0, 0, 0, 0, "", {}

        # Extraer valores del resultado
        salario_basico = to_decimal(result.get('base_salary', contract.wage))
        salario_variable = to_decimal(result.get('variable_salary_avg', 0))
        salario_total = to_decimal(result.get('total_salary', contract.wage))
        valor_indemnizacion = to_decimal(result.get('indemnization_amount', 0))
        base_days = result.get('base_days') or self._get_base_dias_empleado(contract.employee_id)
        base_days = normalizar_base_dias(base_days, default=DAYS_YEAR)
        salario_basico_diario = to_decimal(
            result.get('daily_salary_basic', float(salario_basico / DAYS_MONTH))
        )
        salario_variable_diario = to_decimal(
            result.get('daily_salary_variable', float(salario_variable / DAYS_MONTH))
        )

        # Calcular días y valor diario
        valor_diario = to_decimal(
            result.get('daily_salary_total', float(salario_total / DAYS_MONTH))
        )
        dias_indemnizacion = result.get('indemnization_days')
        if dias_indemnizacion is None:
            dias_indemnizacion = valor_indemnizacion / valor_diario if valor_diario > 0 else to_decimal(0)
        dias_indemnizacion = to_decimal(dias_indemnizacion)

        # Redondear valores
        dias_indemnizacion = decimal_round(dias_indemnizacion, 2)
        valor_diario = decimal_round(valor_diario, 2)
        valor_indemnizacion = decimal_round(valor_indemnizacion, 2)

        # Calcular antigüedad
        duration_days = dias_periodo_base(date_start, settlement_date, base_days, incluir_inicio=True)
        years_worked = to_decimal(duration_days) / to_decimal(base_days) if base_days else to_decimal(0)

        # Obtener categoría del contrato
        contract_category = contract_type.contract_category or 'indefinido'
        tipo_display = contract_type.name or contract_category

        # Construir pasos de cálculo para visualización
        pasos = []
        explicaciones = []

        # URL de referencia legal
        # Artículo 64 del Código Sustantivo del Trabajo (CST)
        url_art64 = "http://www.secretariasenado.gov.co/senado/basedoc/codigo_sustantivo_trabajo_pr001.html#64"

        # Explicación según tipo de contrato
        if contract_category in ['fijo', 'obra']:
            remaining_months = result.get('remaining_months', 0)
            remaining_days = result.get('remaining_days', 0)
            total_remaining_days = result.get('total_remaining_days', (remaining_months * 30) + remaining_days)

            if contract_category == 'obra':
                min_days = contract_type.indemnization_min_days or 15
                explicaciones.append(
                    f"Contrato por obra/labor ({tipo_display}). "
                    f"Art. 64 CST: indemnización por tiempo restante, mínimo {min_days} días."
                )

                if total_remaining_days < min_days:
                    explicaciones.append(
                        f"Días restantes ({total_remaining_days}) < mínimo ({min_days}). "
                        f"Se aplica el mínimo legal de {min_days} días."
                    )
                    pasos.append({
                        'detalle': 'Días restantes hasta fin de obra',
                        'calculo': f"{total_remaining_days} días (menor al mínimo)",
                        'valor': total_remaining_days
                    })
                    pasos.append({
                        'detalle': f'Mínimo Art. 64 CST aplicado',
                        'calculo': f"Se pagan {min_days} días en lugar de {total_remaining_days}",
                        'valor': min_days
                    })
                else:
                    explicaciones.append(
                        f"Días restantes ({total_remaining_days}) >= mínimo ({min_days}). "
                        f"Se pagan los {total_remaining_days} días restantes."
                    )
                    pasos.append({
                        'detalle': 'Días restantes hasta fin de obra',
                        'calculo': f"{total_remaining_days} días",
                        'valor': total_remaining_days
                    })
            else:
                # Contrato fijo
                explicaciones.append(
                    f"Contrato a término fijo ({tipo_display}). "
                    f"Se calcula indemnización por el tiempo restante del contrato."
                )
                pasos.append({
                    'detalle': 'Tiempo restante del contrato',
                    'calculo': f"{remaining_months} meses y {remaining_days} días",
                    'valor': float(dias_indemnizacion)
                })
        else:
            # Contrato indefinido
            annual_params = data_payslip.get('annual_parameters')
            smmlv = to_decimal(annual_params.smmlv_monthly)

            explicaciones.append(
                f"Contrato a término indefinido. "
                f"Salario total: ${float(salario_total):,.2f}, Límite 10 SMMLV: ${float(smmlv * 10):,.2f}."
            )

            if salario_total < smmlv * 10:
                explicaciones.append(
                    f"Salario menor a 10 SMMLV. "
                    f"Se aplica tabla: 30 días primer año + 20 días por año adicional (hasta 5to) "
                    f"+ 13.33 días por año después del 5to."
                )
            else:
                explicaciones.append(
                    f"Salario mayor o igual a 10 SMMLV. "
                    f"Se aplica: 20 días primer año + 15 días por año adicional."
                )

            pasos.append({
                'detalle': 'Antigüedad',
                'calculo': f"{float(years_worked):.2f} años ({int(duration_days)} días)",
                'valor': float(years_worked)
            })

            pasos.append({
                'detalle': 'Días de indemnización',
                'calculo': f"Según tabla Art. 64 CST",
                'valor': float(dias_indemnizacion)
            })

        # Paso final
        pasos.append({
            'detalle': 'Base diaria',
            'calculo': f"${float(salario_basico_diario):,.2f} + ${float(salario_variable_diario):,.2f}",
            'valor': float(valor_diario)
        })
        pasos.append({
            'detalle': 'Cálculo final',
            'calculo': f"Valor diario ${float(valor_diario):,.2f} x {float(dias_indemnizacion):.2f} días",
            'valor': float(valor_indemnizacion)
        })

        nombre = "INDEMNIZACIÓN POR TERMINACIÓN"

        # Datos para visualización
        visual_data = {
            'salario_basico': float(salario_basico),
            'salario_variable': float(salario_variable),
            'salario_total': float(salario_total),
            'salario_basico_diario': float(salario_basico_diario),
            'salario_variable_diario': float(salario_variable_diario),
            'salario_total_diario': float(valor_diario),
            'salario_variable_total': float(result.get('variable_salary_total', 0.0)),
            'salario_variable_dias': float(result.get('variable_salary_days', 0) or 0),
            'salario_variable_periodo': {
                'fecha_inicio': result.get('variable_salary_period_start'),
                'fecha_fin': result.get('variable_salary_period_end'),
            },
            'fecha_inicio': date_start.strftime('%d/%m/%Y'),
            'fecha_liquidacion': settlement_date.strftime('%d/%m/%Y'),
            'dias_totales': float(duration_days),
            'anios_trabajados': float(years_worked),
            'base_dias': int(base_days),
            'tipo_contrato': contract_category,
            'tipo_contrato_nombre': tipo_display,
            'pasos_calculo': pasos,
            'explicaciones': explicaciones,
            'total_indem': float(valor_indemnizacion),
            'valor_diario': float(valor_diario),
            'dias_indemnizacion': float(dias_indemnizacion),
            'calculation_detail': result.get('calculation_detail', ''),
            'url_referencia': url_art64,
        }

        # Indicadores para widget
        indicadores = [
            crear_indicador('Años', f'{float(years_worked):.1f}', 'info', 'text'),
            crear_indicador('Días Indem.', float(dias_indemnizacion), 'warning', 'number'),
            crear_indicador('Tipo', tipo_display.upper() if tipo_display else '', 'secondary', 'text'),
        ]

        # Convertir pasos al formato estándar del widget
        pasos_widget = []
        for p in pasos:
            pasos_widget.append(
                crear_paso_calculo(
                    p['detalle'],
                    p['valor'],
                    'currency' if 'Valor' in p['detalle'] or '$' in str(p.get('calculo', '')) else 'number',
                    highlight=p['detalle'] == 'Cálculo final'
                )
            )

        # Determinar base legal según tipo de contrato
        if contract_category in ['fijo', 'obra']:
            base_legal = f'Art. 64 CST - Contrato a término {contract_category}'
        else:
            annual_params = data_payslip.get('annual_parameters')
            smmlv = to_decimal(annual_params.smmlv_monthly)
            if float(salario_total) < float(smmlv * 10):
                base_legal = 'Art. 64 CST - Salario menor a 10 SMMLV'
            else:
                base_legal = 'Art. 64 CST - Salario mayor o igual a 10 SMMLV'

        computation = crear_computation_estandar(
            'indemnizacion',
            titulo=nombre,
            formula='Valor Diario x Días Indemnización',
            explicacion='\n'.join(explicaciones),
            indicadores=indicadores,
            pasos=pasos_widget,
            base_legal=base_legal,
            elemento_ley='Indemnización por terminación unilateral del contrato sin justa causa',
            datos=visual_data,
            url_referencia=url_art64,
        )

        return float(valor_diario), float(dias_indemnizacion), 100, nombre, False, computation
