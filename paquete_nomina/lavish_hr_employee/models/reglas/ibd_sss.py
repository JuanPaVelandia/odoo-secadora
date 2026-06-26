# -*- coding: utf-8 -*-

"""Reglas salariales para calculo de IBD/IBC."""

import logging
from odoo import models, api
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)
from .config_reglas import (
    DAYS_MONTH, crear_log_data, crear_resultado_regla, crear_resultado_vacio, crear_data_kpi,
    crear_computation_estandar, crear_indicador, crear_paso_calculo
)


class HrSalaryRuleIbdSss(models.AbstractModel):
    """Mixin para calculo de IBD (Ingreso Base de Cotizacion)."""

    _name = 'hr.salary.rule.ibd.sss'
    _description = 'Metodos para IBD'
    LNR_CODES = {'LICENCIA_NO_REMUNERADA', 'LIC_NR'}

    @api.model
    def _set_limits_ibc(self, ibc, valor_minimo):
        if ibc < valor_minimo:
            return valor_minimo
        else:
            return ibc

    def _obtener_ibc_diario_previo(self, contract, ref_date, usar_valor_pagado=False, rule=None):
        """
        Obtiene el IBC diario del mes anterior.

        IMPORTANTE: El IBC diario retornado puede respetar el minimo legal (SMMLV/30)
        si la regla tiene liquidar_con_base=True.

        Args:
            contract: Contrato del empleado
            ref_date: Fecha de referencia
            usar_valor_pagado: Si True, usa el valor pagado efectivamente (no IBC ajustado)
            rule: hr.salary.rule opcional. Si tiene liquidar_con_base=True, aplica limite minimo.

        Returns:
            float: IBC diario del mes anterior
        """
        from ...utils.param_loader import ParamLoader

        ini = ref_date.replace(day=1) - relativedelta(months=1)
        fin = ref_date.replace(day=1) - timedelta(days=1)

        ss_data = self.env['hr.executing.social.security']._read_group(
            domain=[
                ('employee_id', '=', contract.employee_id.id),
                ('contract_id', '=', contract.id),
                ('k_start', '>=', ini), ('k_start', '<=', fin),
            ],
            groupby=[],
            aggregates=[
                'nValorBaseSalud:sum',
                'nDiasLiquidados:sum',
                'nDiasVacaciones:sum',
                'nDiasLicenciaRenumerada:sum',
                'nDiasMaternidad:sum',
                'nDiasIncapacidadEPS:sum',
                'nDiasIncapacidadARP:sum',
            ],
        )

        ibc_diario = None

        if ss_data:
            (base, dias_liq, dias_vac, dias_lic, dias_mat, dias_eps, dias_arp) = ss_data[0]
            base = base or 0.0
            dias = (
                (dias_liq or 0)
                + (dias_vac or 0)
                + (dias_lic or 0)
                + (dias_mat or 0)
                + (dias_eps or 0)
                + (dias_arp or 0)
            )

            if dias:
                ibc_diario = base / dias

        if not ibc_diario:
            lines_domain = [
                ('state_slip', 'in', ['done', 'paid']),
                ('slip_id.contract_id', '=', contract.id),
                ('date_from', '>=', ini),
                ('date_from', '<=', fin),
            ]

            base_lines = self.env['hr.payslip.line'].search(
                lines_domain + [('salary_rule_id.base_seguridad_social', '=', True)]
            )
            # Filtrar manualmente por excluir_seguridad_social
            base = sum(abs(line.total or 0.0)
                      for line in base_lines
                      if not line.salary_rule_id.excluir_seguridad_social)

            nos_lines = self.env['hr.payslip.line'].search(
                lines_domain + [('category_code', '=', 'DEV_NO_SALARIAL')]
            )
            # Filtrar por excluir_40_porciento_ss y excluir_seguridad_social
            nos = sum(abs(line.total or 0.0)
                     for line in nos_lines
                     if not line.salary_rule_id.excluir_40_porciento_ss and
                        not line.salary_rule_id.excluir_seguridad_social)

            params = ParamLoader.for_date(self.env, fin)
            extra = max(0.0, nos - (base + nos) * params['TOPE_40'])
            ibc_mes = min(base + extra, params['TOPE_25_SMMLV'])

            if ibc_mes > 0:
                ibc_diario = ibc_mes / DAYS_MONTH

        if not ibc_diario:
            params = ParamLoader.for_date(self.env, fin)
            wage = contract.wage
            if params.get('TOPE_25_SMMLV'):
                wage = min(wage, params['TOPE_25_SMMLV'])
            ibc_diario = wage / DAYS_MONTH

        # Determinar si aplicar limite minimo basado en el campo aplicar_limite_minimo_ibc de la regla
        # Si no hay regla, usar contract.minimum_wage como fallback
        params = ParamLoader.for_date(self.env, fin)
        smmlv_mensual = params.get('SMMLV', 0)

        aplicar_limite_minimo = False
        if rule is not None and 'aplicar_limite_minimo_ibc' in rule._fields:
            # Prioridad: usar campo aplicar_limite_minimo_ibc de la regla
            aplicar_limite_minimo = rule.aplicar_limite_minimo_ibc
        elif contract.minimum_wage:
            # Fallback: si no hay regla, usar campo del contrato
            aplicar_limite_minimo = True

        if smmlv_mensual > 0 and aplicar_limite_minimo:
            ibc_minimo_diario = smmlv_mensual / DAYS_MONTH
            ibc_diario = max(ibc_diario, ibc_minimo_diario)

        return ibc_diario


    def _get_ibd_previous_values(self, contract, slip_date_from):
        """
        Obtiene valores anteriores de IBD con IDs y fechas para trazabilidad.

        Returns:
            dict: {
                'valor_anterior': float,
                'payslip_lines': [{'id': int, 'date_from': date, 'date_to': date, 'total': float, 'payslip_id': int}],
                'fecha_ultimo_calculo': date or None,
                'payslip_id_anterior': int or None
            }
        """
        mes_anterior = slip_date_from.replace(day=1) - relativedelta(months=1)
        fin_mes_anterior = (mes_anterior + relativedelta(months=1)) - timedelta(days=1)

        # Fuente de verdad para IBC mes anterior:
        # sumar líneas IBD de nóminas del mes anterior en estado done/paid.
        ibd_lines = self.env['hr.payslip.line'].search([
            ('slip_id.contract_id', '=', contract.id),
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.date_from', '>=', mes_anterior),
            ('slip_id.date_to', '<=', fin_mes_anterior),
            ('code', '=', 'IBD'),
        ], order='date_to asc, id asc')

        total_ibd = sum(ibd_lines.mapped('total'))
        payslip_lines = []
        payslip_ids = set()
        fecha_ultimo = None
        payslip_id_anterior = None

        # Detalle trazable de las líneas IBD usadas (limitado para compatibilidad UI).
        for line in ibd_lines[:10]:
            payslip_ids.add(line.slip_id.id)
            payslip_lines.append({
                'id': line.id,
                'date_from': line.slip_id.date_from,
                'date_to': line.slip_id.date_to,
                'total': line.total,
                'payslip_id': line.slip_id.id,
            })

            date_to = line.slip_id.date_to
            if date_to and (fecha_ultimo is None or date_to > fecha_ultimo):
                fecha_ultimo = date_to
                payslip_id_anterior = line.slip_id.id

        # En IBC mes anterior se conserva la suma mensual consolidada.
        cantidad_calculos = len(payslip_ids) if payslip_ids else 0
        promedio = total_ibd

        return {
            'valor_anterior': total_ibd,
            'valor_anterior_promedio': promedio,
            'payslip_lines': payslip_lines,
            'fecha_ultimo_calculo': fecha_ultimo,
            'payslip_id_anterior': payslip_id_anterior,
            'cantidad_calculos_anteriores': cantidad_calculos
        }

    def _get_novelty_name(self, novelty_code):
        """
        Retorna el nombre legible del tipo de ausencia.

        Args:
            novelty_code: Código del tipo (ige, vdi, lnr, etc.)

        Returns:
            str: Nombre legible del tipo
        """
        NOVELTY_NAMES = {
            'sln': 'Suspensión Temporal',
            'ige': 'Incapacidad EPS',
            'irl': 'Incapacidad ARL',
            'lma': 'Licencia Maternidad',
            'lpa': 'Licencia Paternidad',
            'vco': 'Vacaciones Compensadas',
            'vdi': 'Vacaciones Disfrutadas',
            'vre': 'Vacaciones Retiro',
            'lr': 'Licencia Remunerada',
            'lnr': 'Licencia No Remunerada',
            'lt': 'Licencia de Luto',
            'p': 'Permisos No Remunerados',
        }
        return NOVELTY_NAMES.get(novelty_code, f'Tipo {novelty_code}')

    def _get_ibd_legal_explanation(self, ibc_pre, ibc_final, salary, o_earnings, absences_amount,
                                   include_absences_1393, modality_salary, smmlv):
        """
        Genera explicación legal del cálculo de IBC con términos normativos.

        Base Legal:
        - Art. 27 Ley 1393/2010: Regla del 40%
        - Art. 30 Ley 1393/2010: Límite máximo 25 SMMLV
        - Art. 132 CST: Salario integral (70% factor salarial)
        """
        explicaciones = []
        pasos_calculo = []

        explicaciones.append({
            'paso': 1,
            'titulo': 'Ingresos Salariales',
            'base_legal': 'Art. 27 Ley 1393/2010',
            'explicacion': 'Se suman todos los ingresos de naturaleza salarial del período.',
            'valor': salary,
            'termino_legal': 'Ingresos de naturaleza salarial'
        })
        pasos_calculo.append(f"1. Ingresos salariales: ${salary:,.2f}")

        if include_absences_1393 and absences_amount > 0:
            explicaciones.append({
                'paso': 2,
                'titulo': 'Inclusión de Ausencias',
                'base_legal': 'Art. 27 Ley 1393/2010',
                'explicacion': 'Según configuración de la empresa, se incluyen ausencias remuneradas en la base para regla del 40%.',
                'valor': absences_amount,
                'termino_legal': 'Ausencias remuneradas'
            })
            pasos_calculo.append(f"2. + Ausencias remuneradas: ${absences_amount:,.2f}")
            salary_for_40 = salary + absences_amount
        else:
            salary_for_40 = salary
            if absences_amount > 0:
                explicaciones.append({
                    'paso': 2,
                    'titulo': 'Ausencias (No incluidas en regla 40%)',
                    'base_legal': 'Art. 27 Ley 1393/2010',
                    'explicacion': 'Las ausencias se suman después de aplicar la regla del 40%.',
                    'valor': absences_amount,
                    'termino_legal': 'Ausencias remuneradas'
                })

        if o_earnings > 0:
            explicaciones.append({
                'paso': 3,
                'titulo': 'Ingresos No Salariales',
                'base_legal': 'Art. 27 Ley 1393/2010',
                'explicacion': 'Ingresos de naturaleza no salarial (viáticos, bonificaciones no salariales, etc.).',
                'valor': o_earnings,
                'termino_legal': 'Ingresos no constitutivos de salario'
            })
            pasos_calculo.append(f"3. + Ingresos no salariales: ${o_earnings:,.2f}")

        top40 = (salary_for_40 + o_earnings) * 0.4
        if o_earnings > top40:
            ibc_antes_tope = salary_for_40 + o_earnings - top40
            explicaciones.append({
                'paso': 4,
                'titulo': 'Aplicación Regla del 40%',
                'base_legal': 'Art. 27 Ley 1393/2010',
                'explicacion': f'Los ingresos no salariales (${o_earnings:,.2f}) superan el 40% del total (${top40:,.2f}). Se excluye el exceso.',
                'valor': ibc_antes_tope,
                'formula': f'IBC = Ingresos salariales + Ingresos no salariales - Exceso del 40%',
                'termino_legal': 'Regla del cuarenta por ciento (40%)'
            })
            pasos_calculo.append(f"4. Aplicar regla 40%: ${salary_for_40 + o_earnings:,.2f} - ${top40:,.2f} = ${ibc_antes_tope:,.2f}")
        else:
            ibc_antes_tope = salary_for_40
            explicaciones.append({
                'paso': 4,
                'titulo': 'Aplicación Regla del 40%',
                'base_legal': 'Art. 27 Ley 1393/2010',
                'explicacion': f'Los ingresos no salariales (${o_earnings:,.2f}) no superan el 40% del total (${top40:,.2f}). No se aplica exclusión.',
                'valor': ibc_antes_tope,
                'formula': f'IBC = Ingresos salariales (no se excluye nada)',
                'termino_legal': 'Regla del cuarenta por ciento (40%)'
            })
            pasos_calculo.append(f"4. Regla 40% no aplica: ${ibc_antes_tope:,.2f}")

        if not include_absences_1393 and absences_amount > 0:
            ibc_antes_tope += absences_amount
            pasos_calculo.append(f"5. + Ausencias (fuera de regla 40%): ${absences_amount:,.2f} = ${ibc_antes_tope:,.2f}")

        if modality_salary == 'integral':
            ibc_antes_tope_integral = ibc_antes_tope * 0.7
            explicaciones.append({
                'paso': 6,
                'titulo': 'Aplicación Factor Salarial',
                'base_legal': 'Art. 132 CST',
                'explicacion': 'En salario integral, solo el 70% constituye factor salarial para cotización.',
                'valor': ibc_antes_tope_integral,
                'formula': f'IBC = IBC anterior × 70%',
                'termino_legal': 'Factor salarial del salario integral'
            })
            pasos_calculo.append(f"6. Factor salarial (70%): ${ibc_antes_tope:,.2f} × 0.7 = ${ibc_antes_tope_integral:,.2f}")
            ibc_antes_tope = ibc_antes_tope_integral

        limite_25_smmlv = 25 * smmlv
        if ibc_antes_tope > limite_25_smmlv:
            explicaciones.append({
                'paso': 7,
                'titulo': 'Aplicación Límite Máximo',
                'base_legal': 'Art. 30 Ley 1393/2010',
                'explicacion': f'El IBC calculado (${ibc_antes_tope:,.2f}) supera el límite legal de 25 SMMLV (${limite_25_smmlv:,.2f}). Se aplica el límite.',
                'valor': ibc_final,
                'formula': f'IBC Final = min(IBC calculado, 25 × SMMLV)',
                'termino_legal': 'Límite máximo de cotización'
            })
            pasos_calculo.append(f"7. Aplicar límite 25 SMMLV: min(${ibc_antes_tope:,.2f}, ${limite_25_smmlv:,.2f}) = ${ibc_final:,.2f}")
        else:
            explicaciones.append({
                'paso': 7,
                'titulo': 'Verificación Límite Máximo',
                'base_legal': 'Art. 30 Ley 1393/2010',
                'explicacion': f'El IBC calculado (${ibc_antes_tope:,.2f}) no supera el límite legal de 25 SMMLV (${limite_25_smmlv:,.2f}).',
                'valor': ibc_final,
                'termino_legal': 'Límite máximo de cotización'
            })
            pasos_calculo.append(f"7. Límite 25 SMMLV no aplica: ${ibc_final:,.2f}")

        return {
            'explicaciones_legales': explicaciones,
            'pasos_calculo': pasos_calculo,
            'resumen': {
                'base_legal_principal': 'Ley 1393 de 2010',
                'articulos_aplicados': ['Art. 27', 'Art. 30'],
                'terminos_legales': [
                    'Ingreso Base de Cotización (IBC)',
                    'Regla del cuarenta por ciento (40%)',
                    'Límite máximo de cotización',
                    'Factor salarial'
                ]
            }
        }

    def _ibd(self, localdict):
        """
        Calcula IBD (Ingreso Base de Cotización) adaptado de .
        Aplica regla del 40% según Ley 1393.
        Aplica tabla especial para cotizante tipo 51.
        """
        slip = localdict['slip']
        contract = localdict['contract']
        employee = localdict['employee']
        annual_parameters = localdict.get('annual_parameters')

        if employee.tipo_coti_id and employee.tipo_coti_id.code in ['12', '19']:
            return 0, 0, 0, "IBD - No aplica aprendiz", "", {}

        if employee.tipo_coti_id and employee.tipo_coti_id.code == '51':
            # exclude_leaves=True: Las ausencias tienen su propio IBC del mes anterior
            nom_data = self.compute_payslip_2_values(localdict, exclude_leaves=True)
            salary_real = nom_data['grand_totals']['total_salary']
            o_earnings_real = nom_data['grand_totals']['total_no_salary']
            total_devengos = salary_real + o_earnings_real

            dias_periodo = (slip.date_to - slip.date_from).days + 1
            es_quincenal = dias_periodo <= 16
            es_primera_quincena = slip.date_from.day <= 15

            if es_quincenal:
                tipo_periodo = "QUINCENAL"
                quincena_actual = "1Q" if es_primera_quincena else "2Q"
            else:
                tipo_periodo = "MENSUAL"
                quincena_actual = "N/A"

            if slip.use_manual_days and slip.manual_days and slip.manual_days > 0:
                dias_periodo_actual = float(slip.manual_days)
                origen_dias = "manual"
            else:
                worked = localdict.get('worked_days', {}).get('WORK100')
                dias_periodo_actual = worked.number_of_days if worked else 0
                origen_dias = "worked_days"

            dias_otra_quincena = 0
            dias_mes_completo = dias_periodo_actual

            if es_quincenal:
                if es_primera_quincena:
                    fecha_inicio_otra = slip.date_from.replace(day=16)
                    fecha_fin_otra = (slip.date_from.replace(day=1) + relativedelta(months=1)) - timedelta(days=1)
                else:
                    fecha_inicio_otra = slip.date_from.replace(day=1)
                    fecha_fin_otra = slip.date_from.replace(day=15)

                otra_nomina = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('contract_id', '=', contract.id),
                    ('state', 'in', ['done', 'paid']),
                    ('date_from', '>=', fecha_inicio_otra),
                    ('date_to', '<=', fecha_fin_otra),
                ], limit=1)

                if otra_nomina:
                    if otra_nomina.use_manual_days and otra_nomina.manual_days:
                        dias_otra_quincena = float(otra_nomina.manual_days)
                    else:
                        otra_line = self.env['hr.payslip.worked_days'].search([
                            ('payslip_id', '=', otra_nomina.id),
                            ('code', '=', 'WORK100')
                        ], limit=1)
                        dias_otra_quincena = otra_line.number_of_days if otra_line else 0

                dias_mes_completo = dias_periodo_actual + dias_otra_quincena

            smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0

            number_of_days = dias_mes_completo

            if number_of_days <= 0:
                semanas = 1
                factor = 0.25
                rango_tabla = "0 dias (sin tiempo trabajado)"
                descripcion_rango = "Sin dias trabajados - minimo 1 semana"
            elif number_of_days >= 1 and number_of_days <= 7:
                semanas = 1
                factor = 0.25
                rango_tabla = "1-7 dias (1 semana)"
                descripcion_rango = "Menos de una semana laboral"
            elif number_of_days >= 8 and number_of_days <= 14:
                semanas = 2
                factor = 0.50
                rango_tabla = "8-14 dias (2 semanas)"
                descripcion_rango = "Entre 1 y 2 semanas laborales"
            elif number_of_days >= 15 and number_of_days <= 21:
                semanas = 3
                factor = 0.75
                rango_tabla = "15-21 dias (3 semanas)"
                descripcion_rango = "Entre 2 y 3 semanas laborales"
            elif number_of_days >= 22 and number_of_days <= 30:
                semanas = 4
                factor = 1.0
                rango_tabla = "22-30 dias (4 semanas)"
                descripcion_rango = "Mes completo o mas de 3 semanas"
            else:
                semanas = 4
                factor = 1.0
                rango_tabla = "30+ dias (mes completo)"
                descripcion_rango = "Mes completo"

            ibc_cotizante_51 = employee.tipo_coti_id.get_value_cotizante_51(
                slip.date_to.year,
                number_of_days
            )

            ibc_tabla = ibc_cotizante_51 if ibc_cotizante_51 > 0 else smmlv * factor

            ibc_final = ibc_tabla
            if es_quincenal:
                nota_proporcional = f"IBC segun tabla: ${ibc_tabla:,.0f} (aplica completo en quincena)"
            else:
                nota_proporcional = "IBC mensual completo"

            effective_days = 30 if not es_quincenal else 15
            day_value = ibc_final / effective_days if effective_days > 0 else 0

            resultado_full = {
                'ibc_final': ibc_final,
                'ibc_pre': ibc_tabla,
                'ibc_tabla_mensual': ibc_tabla,
                'day_value': day_value,
                'effective_days': effective_days,
                'smmlv': smmlv,
                'cotizante_51': True,
                'tipo_periodo': tipo_periodo,
                'es_quincenal': es_quincenal,
                'quincena_actual': quincena_actual,
                'dias_periodo_actual': dias_periodo_actual,
                'dias_otra_quincena': dias_otra_quincena,
                'dias_mes_completo': dias_mes_completo,
                'nota_proporcional': nota_proporcional,
                'number_of_days': number_of_days,
                'tabla_aplicada': f"{number_of_days} dias = ${ibc_tabla:,.0f}",
                'origen_dias': origen_dias,
                'use_manual_days': slip.use_manual_days,
                'manual_days': slip.manual_days if slip.use_manual_days else None,
                'salary': salary_real,
                'o_earnings': o_earnings_real,
                'total_devengos': total_devengos,
                'semanas_51': semanas,
                'factor_51': factor,
                'rango_tabla_51': rango_tabla,
                'descripcion_rango': descripcion_rango,
                'nota_legal': 'Res. 2388/2016 - Cotizante tiempo parcial regimen subsidiado',
                'explicacion_calculo': [
                    f"1. Tipo de periodo: {tipo_periodo}" + (f" ({quincena_actual})" if es_quincenal else ""),
                    f"2. Dias trabajados este periodo: {dias_periodo_actual}",
                    f"3. Dias otra quincena: {dias_otra_quincena}" if es_quincenal else "3. N/A (periodo mensual)",
                    f"4. Total dias mes: {dias_mes_completo}",
                    f"5. Rango tabla: {rango_tabla} ({descripcion_rango})",
                    f"6. IBC segun tabla: ${ibc_tabla:,.0f}",
                    f"7. IBC final periodo: ${ibc_final:,.0f} (aplica completo)",
                ],
            }

            periodo = f"IBD COTIZANTE 51 {slip.date_from.strftime('%B %Y')}" + (f" ({quincena_actual})" if es_quincenal else "")
            return day_value, effective_days, 100, periodo, "", resultado_full

        # exclude_leaves=True: Las ausencias tienen su propio IBC del mes anterior
        nom_data = self.compute_payslip_2_values(localdict, exclude_leaves=True)

        def _ibc_rule_value(rule, value):
            """Normaliza el signo para base IBC en reglas de deducción con IBC mes anterior."""
            value = value or 0.0
            if not rule:
                return value
            if (
                getattr(rule, 'dev_or_ded', '') == 'deduccion'
                and getattr(rule, 'base_seguridad_social', False)
                and getattr(rule, 'liquidar_con_base', False)
            ):
                return abs(value)
            return value

        salary = nom_data['grand_totals']['total_salary']
        # Base salarial IBC (authoritative): reglas con base_seguridad_social=True
        salary_ss = 0.0
        # Base no salarial para regla 40% (authoritative): DEV_NO_SALARIAL sin excluir_40
        no_salary_ss = 0.0
        rules_current = localdict.get('rules', {})
        try:
            rules_iter = rules_current.values()
        except (AttributeError, TypeError):
            rules_iter = rules_current
        for rule_data in rules_iter:
            try:
                rule = rule_data.rule
                total = rule_data.total
                has_leave = rule_data.has_leave
            except Exception:
                # Fallback si viene como dict
                rule = rule_data.get('rule') if isinstance(rule_data, dict) else None
                total = rule_data.get('total', 0.0) if isinstance(rule_data, dict) else 0.0
                has_leave = rule_data.get('has_leave', False) if isinstance(rule_data, dict) else False
            if not rule or total == 0.0:
                continue
            if has_leave or getattr(rule, 'is_leave', False):
                continue
            cat = rule.category_id
            cat_code = cat.code if cat else ''
            # Excluir auxilios de la base salarial IBC
            if cat_code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX'):
                continue
            if getattr(rule, 'excluir_seguridad_social', False):
                continue
            if getattr(rule, 'liquidar_con_base', False):
                # Esta regla usa IBC mes anterior y se procesa en el loop de ausencias
                continue
            if hasattr(rule, 'base_seguridad_social') and not rule.base_seguridad_social:
                # Solo cuenta como no salarial si pertenece a DEV_NO_SALARIAL
                cat = rule.category_id
                cat_code = cat.code if cat else ''
                parent_code = cat.parent_id.code if cat and cat.parent_id else ''
                if cat_code == 'DEV_NO_SALARIAL' or parent_code == 'DEV_NO_SALARIAL':
                    if getattr(rule, 'excluir_40_porciento_ss', False):
                        continue
                    no_salary_ss += total
                continue
            salary_ss += _ibc_rule_value(rule, total)
        # Fallback: usar líneas ya calculadas del slip (consulta directa a BD)
        salary_ss_lines = 0.0
        try:
            line_domain = [
                ('slip_id', '=', slip.id),
                ('salary_rule_id.base_seguridad_social', '=', True),
                ('salary_rule_id.excluir_seguridad_social', '=', False),
                ('salary_rule_id.liquidar_con_base', '=', False),
                ('salary_rule_id.code', 'not in', ['IBD', 'IBC', 'IBC_R']),
            ]
            lines = self.env['hr.payslip.line'].search(line_domain)
            for line in lines:
                rule = line.salary_rule_id
                if not rule:
                    continue
                cat = rule.category_id
                if cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX')):
                    continue
                if getattr(rule, 'is_leave', False) or getattr(line, 'leave_id', False):
                    continue
                salary_ss_lines += _ibc_rule_value(rule, line.total)
        except Exception:  # noqa: BLE001 – fallback a 0.0 para base IBC por líneas
            _logger.warning("Error calculando base IBC por líneas (método principal) para nómina %s", getattr(slip, 'name', '?'), exc_info=True)
            salary_ss_lines = 0.0

        if salary_ss_lines == 0.0:
            try:
                for line in slip.line_ids:
                    rule = line.salary_rule_id
                    if not rule or not rule.base_seguridad_social:
                        continue
                    if rule.excluir_seguridad_social:
                        continue
                    if getattr(rule, 'liquidar_con_base', False):
                        continue
                    cat = rule.category_id
                    if cat and (cat.code == 'AUX' or (cat.parent_id and cat.parent_id.code == 'AUX')):
                        continue
                    if getattr(rule, 'is_leave', False) or getattr(line, 'leave_id', False):
                        continue
                    salary_ss_lines += _ibc_rule_value(rule, line.total)
            except Exception:  # noqa: BLE001 – fallback a 0.0 para base IBC por líneas (método alternativo)
                _logger.warning("Error calculando base IBC por líneas (método alternativo) para nómina %s", getattr(slip, 'name', '?'), exc_info=True)
                salary_ss_lines = 0.0

        if salary_ss_lines > 0:
            salary = salary_ss_lines
        elif salary_ss > 0:
            salary = salary_ss
        if no_salary_ss != 0:
            o_earnings = no_salary_ss
        else:
            o_earnings = nom_data['grand_totals']['total_no_salary']

        absences_amount = 0
        paid_absences_amount = 0  # Valor pagado al empleado
        unpaid_absences_amount = 0
        absences_ids_by_category = {}
        absences_by_novelty = {'paid': {}, 'unpaid': {}}

        def _register_absence(rule_code, rule_total, novelty, is_unpaid, category_code, line_ids):
            nonlocal absences_amount, paid_absences_amount, unpaid_absences_amount
            is_lnr = (
                novelty == 'lnr'
                or rule_code in self.LNR_CODES
                or category_code == 'AUSENCIA_NO_PAGO'
            )
            if is_unpaid:
                unpaid_absences_amount += abs(rule_total)
                # Licencia no remunerada no debe mostrarse como "pago" en el detalle IBC
                if is_lnr:
                    return
                bucket = absences_by_novelty['unpaid']
                absences_amount += rule_total
            else:
                paid_absences_amount += rule_total
                bucket = absences_by_novelty['paid']
                absences_amount += rule_total

            if novelty:
                if novelty not in bucket:
                    bucket[novelty] = {
                        'total': 0,
                        'count': 0,
                        'rule_codes': []
                    }
                bucket[novelty]['total'] += abs(rule_total) if is_unpaid else rule_total
                bucket[novelty]['count'] += 1
                bucket[novelty]['rule_codes'].append(rule_code)

            if category_code:
                cat_data = absences_ids_by_category.setdefault(category_code, {
                    'total': 0.0,
                    'line_ids': [],
                    'rules': []
                })
                cat_data['total'] += rule_total
                if line_ids:
                    cat_data['line_ids'].extend(line_ids)
                cat_data['rules'].append({
                    'code': rule_code,
                    'total': rule_total,
                    'line_ids': list(line_ids) if line_ids else [],
                    'novelty': novelty or None,
                })

        rules_current = localdict.get('rules', {})
        try:
            rules_iter = rules_current.values()
        except (AttributeError, TypeError):
            rules_iter = rules_current
        for rule in rules_iter:
            if isinstance(rule, dict):
                if not rule.get('has_leave'):
                    continue
                rule_code = rule.get('code', '')
                novelty = rule.get('leave_novelty') or ''
                if not novelty and rule_code in self.LNR_CODES:
                    novelty = 'lnr'
                if not novelty:
                    continue
                _register_absence(
                    rule_code,
                    rule.get('total', 0.0),
                    novelty,
                    novelty in ['lnr', 'p', 'sln'],
                    rule.get('category_code', ''),
                    rule.get('line_ids', [])
                )
                continue

            try:
                has_leave = rule.has_leave
            except (AttributeError, KeyError):
                has_leave = False
            if not has_leave:
                continue
            try:
                novelty = rule.leave_novelty or ''
            except (AttributeError, KeyError):
                novelty = ''
            if not novelty and rule.code in self.LNR_CODES:
                novelty = 'lnr'
            if not novelty:
                continue
            _register_absence(
                rule.code,
                rule.total,
                novelty,
                novelty in ['lnr', 'p', 'sln'],
                rule.category_code or '',
                rule.line_ids
            )

        # Detectar licencias no remuneradas desde worked_days o lineas (fallback)
        def _is_lnr_worked_day(wd):
            leave_code = (getattr(wd, 'leave_type_code', '') or '').strip().upper()
            novelty = (getattr(wd, 'leave_type_novelty', '') or '').strip().lower()
            wd_name = (getattr(wd, 'name', '') or '').upper()
            wet_code = ''
            try:
                wet_code = (wd.work_entry_type_id.code or '').upper()
            except Exception:
                wet_code = ''
            return (
                leave_code in self.LNR_CODES
                or novelty == 'lnr'
                or 'LICENCIA NO REMUNERADA' in wd_name
                or 'LICENCIA NO REMUNERADA' in wet_code
                or 'LIC_NR' in wet_code
            )

        has_lnr = False
        try:
            for wd in slip.worked_days_line_ids:
                if _is_lnr_worked_day(wd):
                    has_lnr = True
                    break
        except Exception:
            has_lnr = False

        if not has_lnr:
            try:
                for rule in rules_iter:
                    if isinstance(rule, dict):
                        code = rule.get('code', '')
                        cat = rule.get('category_code', '')
                        if code in self.LNR_CODES or cat == 'AUSENCIA_NO_PAGO':
                            has_lnr = True
                            break
                    else:
                        if rule.code in self.LNR_CODES or rule.category_code == 'AUSENCIA_NO_PAGO':
                            has_lnr = True
                            break
            except Exception:
                has_lnr = False

        # No tomar ausencias de otros periodos (p. ej. 1ra quincena) para la 2da.
        # Solo se consideran las ausencias del slip actual en rules_current.

        # o_earnings ya calculado arriba (base no salarial)

        # Si hay ausencias no remuneradas, forzar IBC con salario completo del periodo
        # (días del periodo + días descontados)
        dias_periodo = (slip.date_to - slip.date_from).days + 1
        es_quincenal = dias_periodo <= 16
        ibc_days_override = None
        lnr_days_for_ibc = 0.0
        lnr_day_value = 0.0
        lnr_amount_for_ibc = 0.0
        if unpaid_absences_amount > 0 or has_lnr:
            # Base IBC por dias trabajados + LNR (no vacaciones)
            worked_days = 0.0
            try:
                worked = localdict.get('worked_days', {}).get('WORK100')
                worked_days = worked.number_of_days if worked else 0.0
            except Exception:
                worked_days = 0.0

            lnr_days = 0.0
            try:
                for wd in slip.worked_days_line_ids:
                    if _is_lnr_worked_day(wd):
                        lnr_days += wd.number_of_days or 0.0
            except Exception:
                lnr_days = 0.0

            salario_mensual = self.env['hr.salary.rule.basic']._obtener_salario_efectivo_contrato(
                contract, annual_parameters=annual_parameters
            )
            worked_day_value = salario_mensual / 30.0 if salario_mensual else 0.0
            lnr_day_value_eff = worked_day_value
            if lnr_days > 0:
                lnr_line = slip.line_ids.filtered(
                    lambda l: l.code in self.LNR_CODES
                    and l.salary_rule_id
                    and l.salary_rule_id.liquidar_con_base
                    and (l.ibc_daily or 0.0) > 0.0
                )[:1]
                if lnr_line:
                    lnr_day_value_eff = lnr_line.ibc_daily
                else:
                    lnr_rule = None
                    for _, rd in localdict.get('rules', {}).items():
                        r = rd.rule
                        if r and r.code in self.LNR_CODES:
                            lnr_rule = r
                            break
                    if lnr_rule and lnr_rule.liquidar_con_base:
                        prev_ibd = self._get_ibd_previous_values(contract, slip.date_from)
                        prev_ibd_month = prev_ibd.get('valor_anterior_promedio', 0.0) or 0.0
                        if prev_ibd_month > 0:
                            lnr_day_value_eff = prev_ibd_month / 30.0
                        else:
                            lnr_day_value_eff = self._obtener_ibc_diario_previo(
                                contract, slip.date_from, usar_valor_pagado=False, rule=lnr_rule
                            )
            ibc_days_override = worked_days + lnr_days
            if ibc_days_override > 0:
                salary = (worked_days * worked_day_value) + (lnr_days * lnr_day_value_eff)
            # Guardar valores LNR para mostrar ajuste en el detalle
            if lnr_days > 0:
                lnr_days_for_ibc = lnr_days
                lnr_day_value = lnr_day_value_eff
                lnr_amount_for_ibc = lnr_day_value * lnr_days_for_ibc

        company = slip.company_id or self.env.company
        include_absences_1393 = company.include_absences_1393 if company else False

        # CALCULAR IBC de ausencias basado en el campo liquidar_con_base de cada regla
        # Si liquidar_con_base=True -> usar IBC mes anterior
        # Si liquidar_con_base=False -> usar valor pagado de la ausencia
        paid_absences_ibc_amount = 0
        vacaciones_ibc_amount = 0  # Vacaciones pagadas en ESTA nomina
        vacaciones_otro_periodo = 0  # Vacaciones de otro periodo (solo para regla 40%)
        vacaciones_detalle = []  # Detalle de vacaciones para frontend
        ausencias_con_base_ss = False  # Flag: si hay ausencias CON base_seguridad_social=True procesadas
        ausencias_data = localdict.get('ausencias', {})
        ausencias_detalle = ausencias_data.get('detalle', [])
        por_leave = ausencias_data.get('por_leave', {})

        # Obtener IBC diario del mes anterior (solo se calcula si alguna regla lo necesita)
        ibc_diario_anterior = None

        for item in ausencias_detalle:
            leave_id = item.get('leave_id')
            days_payslip = item.get('days_payslip', 0) or 0

            if days_payslip <= 0:
                continue

            # Verificar tipo de ausencia
            is_unpaid = False
            is_vac_esta_nomina = False
            is_vac_otro_periodo = False
            novelty = ''

            if leave_id and leave_id in por_leave:
                novelty = por_leave[leave_id].get('novelty', '')
                if novelty in ['vdi']:
                    # Vacaciones disfrutadas
                    payslip_id = item.get('payslip_id')
                    if payslip_id == slip.id:
                        is_vac_esta_nomina = True  # Pagadas en ESTA nomina
                    else:
                        # Fallback: validar por rango de fechas de la ausencia
                        if leave_id and slip:
                            leave = self.env['hr.leave'].browse(leave_id)
                            leave_start = leave.date_from or leave.request_date_from
                            leave_end = leave.date_to or leave.request_date_to
                            if isinstance(leave_start, datetime):
                                leave_start = leave_start.date()
                            if isinstance(leave_end, datetime):
                                leave_end = leave_end.date()
                            if leave_start and leave_end:
                                overlaps = leave_start <= slip.date_to and leave_end >= slip.date_from
                            else:
                                overlaps = False
                            if overlaps and not payslip_id:
                                is_vac_esta_nomina = True
                            else:
                                is_vac_otro_periodo = True  # De otro periodo
                        else:
                            is_vac_otro_periodo = True  # De otro periodo
                if novelty in ['lnr', 'p', 'sln']:
                    is_unpaid = True

            if is_unpaid:
                continue  # Ausencias no remuneradas no suman al IBC

            # Obtener la regla para verificar liquidar_con_base
            rule_id = item.get('rule_id')
            rule = self.env['hr.salary.rule'].browse(rule_id) if rule_id else None

            # Calcular monto IBC para esta ausencia/vacacion
            # IMPORTANTE: Si liquidar_con_base=True, usar ibc_day del item (ya calculado)
            # ignorando el valor manual forzado en la ausencia
            usando_ibc_anterior = False
            if rule and rule.exists() and getattr(rule, 'liquidar_con_base', False):
                # Regla usa IBC diario del item (ya viene pre-calculado en ausencias_detalle)
                usando_ibc_anterior = True
                ibc_daily = item.get('ibc_day', 0) or 0
                item_ibc_amount = ibc_daily * days_payslip if ibc_daily > 0 else 0
            else:
                # Regla usa valor pagado de la ausencia
                amount = item.get('amount', 0) or 0
                item_ibc_amount = amount * days_payslip

            # Clasificar segun tipo
            if is_vac_esta_nomina:
                # Vacaciones de ESTA nomina -> sumar al IBC SOLO si base_seguridad_social=True
                # Y liquidar_con_base=True (si es False, la regla ya entra por salary_ss normalmente)
                has_base_ss = rule and rule.exists() and getattr(rule, 'base_seguridad_social', False)
                uses_ibc_base = rule and rule.exists() and getattr(rule, 'liquidar_con_base', False)
                if has_base_ss and uses_ibc_base:
                    vacaciones_ibc_amount += item_ibc_amount
                vacaciones_detalle.append({
                    'leave_id': leave_id,
                    'days': days_payslip,
                    'amount': item_ibc_amount,
                    'rule_id': rule_id,
                    'usa_ibc_anterior': usando_ibc_anterior,
                    'es_nomina_actual': True,
                    'incluida_en_ibc': has_base_ss and uses_ibc_base,
                })
            elif is_vac_otro_periodo:
                # Vacaciones de OTRO periodo -> solo para regla 40%, NO sumar al IBC
                vacaciones_otro_periodo += item_ibc_amount
                vacaciones_detalle.append({
                    'leave_id': leave_id,
                    'days': days_payslip,
                    'amount': item_ibc_amount,
                    'rule_id': rule_id,
                    'usa_ibc_anterior': usando_ibc_anterior,
                    'es_nomina_actual': False,
                })
            else:
                # Otras ausencias (incapacidades, licencias) -> sumar al IBC SOLO si base_seguridad_social=True
                has_base_ss = rule and rule.exists() and getattr(rule, 'base_seguridad_social', False)
                if has_base_ss:
                    paid_absences_ibc_amount += item_ibc_amount
                    ausencias_con_base_ss = True

        # Fallback si no hay calculo: SOLO si hay ausencias pero NINGUNA tiene base_seguridad_social
        # Si todas las ausencias tienen base_seguridad_social=False, mantener paid_absences_ibc_amount=0
        if paid_absences_ibc_amount == 0 and ausencias_con_base_ss:
            # Ya procesamos ausencias con base_ss, no usar fallback
            pass
        elif paid_absences_ibc_amount == 0 and not ausencias_con_base_ss and paid_absences_amount > 0:
            # Hay ausencias pero TODAS tienen base_seguridad_social=False: NO sumar
            # Este es el caso correcto cuando reglas como VACVAR con base_seguridad_social=False
            pass  # Mantener paid_absences_ibc_amount = 0
        elif paid_absences_ibc_amount == 0 and not ausencias_detalle:
            # No hay ausencias detectadas en el loop, usar fallback normal
            paid_absences_ibc_amount = paid_absences_amount

        # IMPORTANTE: Para seguridad social, usar IBC de ausencias (paid_absences_ibc_amount)
        # en lugar del valor pagado (paid_absences_amount)
        # El IBC puede ser diferente al valor pagado (ej: incapacidad usa IBC mes anterior)

        # Calcular base para regla del 40%
        # Incluir: salario + ausencias (si aplica config) + vacaciones de OTRO periodo
        # Las vacaciones de otro periodo cuentan para el 40% pero NO se suman al IBC
        if include_absences_1393:
            salary_for_40 = salary + paid_absences_ibc_amount + vacaciones_otro_periodo
        else:
            salary_for_40 = salary + vacaciones_otro_periodo

        top40 = (salary_for_40 + o_earnings) * 0.4
        if o_earnings > top40:
            # Calcular IBC SIN las vacaciones de otro periodo (solo para calculo 40%)
            base_sin_vac_otro = salary_for_40 - vacaciones_otro_periodo
            ibc_pre = base_sin_vac_otro + o_earnings - top40
        else:
            # Calcular IBC SIN las vacaciones de otro periodo
            ibc_pre = salary_for_40 - vacaciones_otro_periodo

        if not include_absences_1393:
            # Usar IBC de ausencias para seguridad social
            ibc_pre += paid_absences_ibc_amount

        if include_absences_1393:
            # Incluir vacaciones de ESTA nomina cuando la empresa incluye ausencias en 1393
            ibc_pre += vacaciones_ibc_amount
        elif vacaciones_ibc_amount > 0:
            # Siempre sumar vacaciones si tienen base_seguridad_social=True (ya filtrado en el loop)
            ibc_pre += vacaciones_ibc_amount
        else:
            # Caso especial (solo nómina): si hay incapacidad, incluir vacaciones actuales en IBC
            # Esto evita excluir VACVAR cuando existe incapacidad en el mismo periodo.
            has_incapacity = any(
                code in absences_by_novelty.get('paid', {})
                for code in ('ige', 'irl', 'lma')
            )
            if slip.struct_process == 'nomina' and has_incapacity:
                ibc_pre += vacaciones_ibc_amount

        # NOTA: Las vacaciones de ESTA nomina YA estan incluidas en salary (DEV_SALARIAL)
        # Solo se suman si include_absences_1393 está activo para la compañía
        # Las vacaciones de otro periodo NO se suman (ya se pagaron en su nomina)
        # Solo se usan para el calculo del 40% y para mostrar en el desglose visual

        # Acumular desglose de factor salarial (para explicación en frontend)
        es_salario_integral = contract.modality_salary == 'integral'
        ibc_antes_factor = ibc_pre
        desglose_factor = {
            'aplica_70': [],
            'aplica_100': [],
            'total_base_70': 0.0,
            'total_base_100': 0.0,
            'total_ajustado_70': 0.0,
            'total_ajustado_100': 0.0,
        }

        if es_salario_integral:
            # Acumular desglose mientras iteramos las reglas (solo para explicación)
            rules = localdict.get('rules', {})
            for _, rule_data in rules.items():
                rule = rule_data.rule
                if not rule:
                    continue
                cat = rule.category_id
                amount = rule_data.total
                if amount == 0.0 or not cat:
                    continue
                # Solo reglas con base_seguridad_social y no excluidas
                if not rule.base_seguridad_social or rule.excluir_seguridad_social:
                    continue
                # Excluir ausencias (se suman aparte en IBC Ausencias)
                # Verificar has_leave en rule_data (no en rule)
                try:
                    has_leave = rule_data.has_leave
                except (AttributeError, KeyError):
                    has_leave = False
                if has_leave or rule.is_leave:
                    continue

                cat_code = cat.code if cat else ''
                es_basic = cat_code == 'BASIC' or (cat.parent_id and cat.parent_id.code == 'BASIC')
                try:
                    aplica_factor = es_basic or rule.aplica_factor_integral
                except (AttributeError, KeyError):
                    aplica_factor = es_basic
                factor = 0.7 if aplica_factor else 1.0

                regla_info = {
                    'code': rule.code,
                    'name': rule.name,
                    'category_code': cat_code,
                    'monto_original': amount,
                    'factor': factor,
                    'monto_ajustado': amount * factor,
                    'es_basic': es_basic,
                }

                if aplica_factor:
                    desglose_factor['aplica_70'].append(regla_info)
                    desglose_factor['total_base_70'] += amount
                    desglose_factor['total_ajustado_70'] += amount * factor
                else:
                    desglose_factor['aplica_100'].append(regla_info)
                    desglose_factor['total_base_100'] += amount
                    desglose_factor['total_ajustado_100'] += amount

            # Calcular IBC con factor por regla (no global)
            ibc_pre = desglose_factor['total_ajustado_70'] + desglose_factor['total_ajustado_100']
            # Sumar IBC de ausencias (al 100%)
            ibc_pre += paid_absences_ibc_amount
            # NOTA: Las vacaciones de esta nomina YA estan en el desglose_factor (DEV_SALARIAL)
            # NO sumar vacaciones_ibc_amount porque duplicaria

        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        limite_25_smmlv = 25 * smmlv if smmlv > 0 else 0
        ibc_antes_limite = ibc_pre
        aplico_limite_25 = ibc_pre > limite_25_smmlv if limite_25_smmlv > 0 else False
        ibc_final = min(ibc_pre, limite_25_smmlv) if limite_25_smmlv > 0 else ibc_pre

        effective_days = ibc_days_override or 30
        day_value = ibc_final / effective_days if effective_days > 0 else 0

        # Obtener valores anteriores para comparacion y trazabilidad
        valores_anteriores = self._get_ibd_previous_values(contract, slip.date_from)

        # Mapa de rule_id -> datos IBC agregados para reglas con liquidar_con_base=True
        # Permite mostrar en el visual el valor correcto (ibc_day * dias) en lugar del monto pagado
        vac_ibc_map = {}
        for vd in vacaciones_detalle:
            if not vd.get('usa_ibc_anterior'):
                continue
            rid = vd.get('rule_id')
            if not rid:
                continue
            if rid not in vac_ibc_map:
                vac_ibc_map[rid] = {'total': 0.0, 'days': 0.0, 'ibc_day': 0.0}
            vac_ibc_map[rid]['total'] += vd.get('amount', 0)
            vac_ibc_map[rid]['days'] += vd.get('days', 0)
            # Tomar la tasa diaria del primer item (todos usan el mismo ibc_day)
            if vac_ibc_map[rid]['ibc_day'] == 0 and vd.get('days', 0) > 0:
                vac_ibc_map[rid]['ibc_day'] = vd.get('amount', 0) / vd['days']

        reglas_usadas_detalle = []
        rules = localdict.get('rules', {})
        for _, rule_data in rules.items():
            rule = rule_data.rule
            if not rule:
                continue

            cat = rule.category_id
            amount = rule_data.total
            # Excluir auxilios y reglas sin valor
            if cat and cat.code in ('AUX'):
                continue

            # Determinar categoría de la regla (simplificado: base_seguridad_social define salarial)
            is_basic = cat.code == 'BASIC' or (cat.parent_id and cat.parent_id.code == 'BASIC')
            is_dev_salarial = bool(rule.base_seguridad_social) and not is_basic
            is_dev_no_salarial = (cat.code == 'DEV_NO_SALARIAL' or (cat.parent_id and cat.parent_id.code == 'DEV_NO_SALARIAL')) and not rule.base_seguridad_social

            es_lnr = rule.code in self.LNR_CODES
            # Incluir BASIC, DEV_SALARIAL, DEV_NO_SALARIAL y LNR
            if not (is_basic or is_dev_salarial or is_dev_no_salarial or es_lnr):
                continue
            # Excluir si tiene excluir_seguridad_social marcado
            if rule.excluir_seguridad_social and not es_lnr:
                continue
            # Para devengos salariales, ya controlado por base_seguridad_social

            # Determinar tipo de categoría para el frontend
            if is_basic:
                tipo_categoria = 'BASIC'
            elif is_dev_salarial:
                tipo_categoria = 'DEV_SALARIAL'
            elif es_lnr:
                tipo_categoria = 'AUSENCIA_NO_PAGO'
            else:
                tipo_categoria = 'DEV_NO_SALARIAL'

            # Ajustar cantidad para VACDISFRUTADAS segun worked days o linea real del slip
            cantidad = rule_data.quantity
            if rule.code == 'VACDISFRUTADAS':
                try:
                    wd_vac = slip.worked_days_line_ids.filtered(
                        lambda wd: wd.leave_type_code == 'VACDISFRUTADAS'
                    )[:1]
                    if wd_vac:
                        cantidad = wd_vac.number_of_days
                except Exception:
                    pass
                try:
                    line_vac = slip.line_ids.filtered(lambda l: l.code == 'VACDISFRUTADAS')[:1]
                    if line_vac:
                        cantidad = line_vac.quantity
                except Exception:
                    pass

            total_regla = rule_data.total
            amount_regla = rule_data.amount
            quantity_regla = cantidad

            if (
                getattr(rule, 'dev_or_ded', '') == 'deduccion'
                and getattr(rule, 'base_seguridad_social', False)
                and getattr(rule, 'liquidar_con_base', False)
            ):
                total_regla = abs(total_regla or 0.0)
                amount_regla = abs(amount_regla or 0.0)

            if es_lnr and lnr_amount_for_ibc > 0:
                total_regla = lnr_amount_for_ibc
                amount_regla = lnr_day_value
                quantity_regla = lnr_days_for_ibc

            # Para reglas con liquidar_con_base=True, mostrar valores IBC (no monto pagado)
            nota_ibc = None
            if getattr(rule, 'liquidar_con_base', False) and rule.id in vac_ibc_map:
                ibc_data = vac_ibc_map[rule.id]
                amount_regla = ibc_data['ibc_day']
                quantity_regla = ibc_data['days']
                total_regla = ibc_data['total']
                nota_ibc = 'IBC mes anterior'

            reglas_usadas_detalle.append({
                'rule_id': rule.id,
                'code': rule.code,
                'name': rule.name,
                'category_code': tipo_categoria,  # Usar tipo normalizado
                'category_name': cat.name if cat else '',
                'amount': amount_regla,
                'quantity': quantity_regla,
                'rate': rule_data.rate,
                'total': total_regla,
                'origen': 'NOM ACTUAL',
                'tiene_valor': amount != 0.0,  # Flag para mostrar si tiene valor
                'es_ausencia': es_lnr,
                'nota': nota_ibc,
            })

        # Recalcular ingresos salariales para explicación legal con base en reglas usadas
        codigos_ausencias = set([
            'VAC', 'VACDISFRUTADAS', 'VACREMUNERADAS', 'VACATIONS_MONEY',
            'LICENCIA_REMUNERADA', 'INCAPACIDAD_EPS', 'INCAPACIDAD_ARL',
            'INCAPACIDAD_ENTIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_PATERNIDAD',
            'LUTO', 'LNR', 'LICENCIA_LUTO'
        ])
        salary_explicacion = 0.0
        # Pre-construir mapa de code -> regla desde el localdict para no hacer queries por cada regla
        rules_map = {}
        for _, rd in (localdict.get('rules', {}) or {}).items():
            r = rd.rule if hasattr(rd, 'rule') else None
            if r:
                rules_map[r.code] = r
        for regla in reglas_usadas_detalle:
            code = regla.get('code', '')
            if code in codigos_ausencias:
                continue
            # Excluir reglas con liquidar_con_base=True (se manejan en vacaciones_ibc_amount)
            rule_obj = rules_map.get(code)
            if rule_obj and getattr(rule_obj, 'liquidar_con_base', False):
                continue
            if regla.get('category_code') in ('BASIC', 'DEV_SALARIAL') and regla.get('total', 0) > 0:
                salary_explicacion += regla.get('total', 0.0)

        # Si el subtotal de reglas usadas difiere del salario calculado, priorizarlo
        # (evita que el IBC quede solo con salario básico cuando hay HEYREC en base)
        if not es_salario_integral and salary_explicacion > 0 and abs(salary_explicacion - salary) > 0.01:
            salary = salary_explicacion
            if include_absences_1393:
                salary_for_40 = salary + paid_absences_ibc_amount + vacaciones_otro_periodo
            else:
                salary_for_40 = salary + vacaciones_otro_periodo

            top40 = (salary_for_40 + o_earnings) * 0.4
            if o_earnings > top40:
                base_sin_vac_otro = salary_for_40 - vacaciones_otro_periodo
                ibc_pre = base_sin_vac_otro + o_earnings - top40
            else:
                ibc_pre = salary_for_40 - vacaciones_otro_periodo

            if not include_absences_1393:
                ibc_pre += paid_absences_ibc_amount

            if include_absences_1393:
                ibc_pre += vacaciones_ibc_amount
            elif vacaciones_ibc_amount > 0:
                ibc_pre += vacaciones_ibc_amount
            else:
                has_incapacity = any(
                    code in absences_by_novelty.get('paid', {})
                    for code in ('ige', 'irl', 'lma')
                )
                if slip.struct_process == 'nomina' and has_incapacity:
                    ibc_pre += vacaciones_ibc_amount

            smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
            limite_25_smmlv = 25 * smmlv if smmlv > 0 else 0
            ibc_antes_limite = ibc_pre
            aplico_limite_25 = ibc_pre > limite_25_smmlv if limite_25_smmlv > 0 else False
            ibc_final = min(ibc_pre, limite_25_smmlv) if limite_25_smmlv > 0 else ibc_pre
            day_value = ibc_final / effective_days if effective_days > 0 else 0

        explicacion_legal = self._get_ibd_legal_explanation(
            ibc_pre, ibc_final, salary_explicacion or salary, o_earnings, absences_amount,
            include_absences_1393, contract.modality_salary, smmlv
        )

        diferencia = ibc_final - valores_anteriores['valor_anterior_promedio'] if valores_anteriores['valor_anterior_promedio'] > 0 else 0
        porcentaje_cambio = (diferencia / valores_anteriores['valor_anterior_promedio'] * 100) if valores_anteriores['valor_anterior_promedio'] > 0 else 0

        # Preparar detalle de ausencias para el frontend (con IBC individual por leave)
        # Usar por_leave que tiene los datos agregados por ausencia, no por linea
        ausencias_detalle_frontend = []
        por_leave = ausencias_data.get('por_leave', {})

        # Totales de complemento empresa
        total_complemento_empresa = 0
        total_pagar_ausencias = 0

        # Calcular IBC por cada ausencia (sumando ibc_day * days por sus lineas)
        ibc_por_leave = {}
        for item in ausencias_detalle:
            leave_id = item.get('leave_id')
            if not leave_id:
                continue
            ibc_day = item.get('ibc_day', 0) or 0
            days_payslip = item.get('days_payslip', 0) or 0
            ibc_linea = ibc_day * days_payslip if ibc_day > 0 else item.get('amount', 0) or 0
            if leave_id not in ibc_por_leave:
                ibc_por_leave[leave_id] = {'ibc_total': 0, 'ibc_day': ibc_day}
            ibc_por_leave[leave_id]['ibc_total'] += ibc_linea

        # Construir lista final desde por_leave (una fila por ausencia)
        total_valor_adicional = 0

        for leave_id, leave_info in por_leave.items():
            tipo_code = leave_info.get('tipo_code', '')
            tipo_name = leave_info.get('tipo', '')
            novelty = leave_info.get('novelty', '')
            dias = leave_info.get('dias', 0) or 0
            if novelty == 'lnr' or tipo_code in self.LNR_CODES:
                # No mostrar LNR como pago en el detalle IBC
                continue

            # Valores separados: EPS, Complemento y Adicional
            valor_eps = leave_info.get('valor_eps', 0) or leave_info.get('valor', 0) or 0
            complemento_empresa = leave_info.get('complemento_empresa', 0) or 0
            valor_adicional_manual = leave_info.get('valor_adicional_manual', 0) or 0
            total_pagar = leave_info.get('total_pagar', 0) or (valor_eps + complemento_empresa + valor_adicional_manual)

            # Campos especiales vacaciones en dinero
            is_vacation_money = leave_info.get('is_vacation_money', False)
            dias_a_liquidar = leave_info.get('dias_a_liquidar', 0) or 0
            incluir_festivos = leave_info.get('incluir_festivos', True)

            # Compatibilidad: payment sigue siendo el valor EPS
            payment = valor_eps

            # IBC calculado (diferente al pago para incapacidades)
            ibc_info = ibc_por_leave.get(leave_id, {})

            ibc_amount = ibc_info.get('ibc_total', 0) or payment
            ibc_day = ibc_info.get('ibc_day', 0)

            # Determinar tipo para mostrar
            if is_vacation_money:
                tipo_display = 'VAC$'  # Indicador especial vacaciones en dinero
            elif novelty in ['ige', 'irl']:
                tipo_display = 'INC'
            else:
                tipo_display = 'AUS'

            # Determinar si tiene valores adicionales para mostrar
            tiene_complemento = complemento_empresa > 0
            tiene_adicional = valor_adicional_manual > 0

            # Acumular valor adicional
            total_valor_adicional += valor_adicional_manual

            ausencias_detalle_frontend.append({
                'code': tipo_code,
                'name': tipo_name,
                'type': tipo_display,
                'payment': payment,  # Valor EPS/ARL o calculado
                'complemento_empresa': complemento_empresa,  # Abono adicional empresa
                'valor_adicional_manual': valor_adicional_manual,  # Valor adicional manual
                'total_pagar': total_pagar,  # Total = EPS + Complemento + Adicional
                'ibc_amount': ibc_amount,
                'ibc_day': ibc_day,
                'days_payslip': dias,
                'ibc_source': 'IBC mes anterior' if ibc_day > 0 and ibc_amount != payment else 'Pago directo',
                'tiene_complemento': tiene_complemento,
                'tiene_adicional': tiene_adicional,
                # Campos vacaciones en dinero
                'is_vacation_money': is_vacation_money,
                'dias_a_liquidar': dias_a_liquidar,
                'incluir_festivos': incluir_festivos,
            })

            # Acumular totales
            total_complemento_empresa += complemento_empresa
            total_pagar_ausencias += total_pagar

        # Flags para indicar si hay valores adicionales en esta nomina
        hay_complementos = total_complemento_empresa > 0
        hay_adicionales = total_valor_adicional > 0

        resultado_full = {
            'ibc_final': ibc_final,
            'ibc_pre': ibc_pre,
            'day_value': day_value,
            'effective_days': effective_days,
            'salary': salary,
            'absences_amount': absences_amount,
            'paid_absences_amount': paid_absences_amount,  # Valor pagado al empleado
            'paid_absences_ibc_amount': paid_absences_ibc_amount,  # IBC para SS (puede ser diferente)
            'vacaciones_ibc_amount': vacaciones_ibc_amount,  # Vacaciones de ESTA nomina (opcional según configuración)
            'vacaciones_otro_periodo': vacaciones_otro_periodo,  # Vacaciones de OTRO periodo (solo 40%)
            'vacaciones_detalle': vacaciones_detalle,  # Detalle de cada vacacion
            'unpaid_absences_amount': unpaid_absences_amount,
            'o_earnings': o_earnings,
            'top40': top40,
            'smmlv': smmlv,
            'include_absences_1393': include_absences_1393,
            'salary_for_40': salary_for_40,
            'acum_line_ids': nom_data.get('line_ids', []),
            'absences_by_category': absences_ids_by_category,
            'absences_by_novelty': absences_by_novelty,
            'ausencias_detalle': ausencias_detalle_frontend,  # Detalle individual para frontend
            'ibc_effects': {
                'paid_absences_payment': paid_absences_amount,  # Valor pagado por EPS/ARL
                'paid_absences_ibc': paid_absences_ibc_amount,  # IBC para SS
                'ibc_vs_payment_diff': paid_absences_ibc_amount - paid_absences_amount,  # Diferencia
                'unpaid_absences_subtracted': unpaid_absences_amount,
                'net_effect': paid_absences_ibc_amount - unpaid_absences_amount,
                # Vacaciones (separado de ausencias)
                'vacaciones_ibc': vacaciones_ibc_amount,  # Solo esta nomina, suma al IBC si está activo
                'vacaciones_otro_periodo': vacaciones_otro_periodo,  # Otro periodo, solo 40%
                'vacaciones_detalle': vacaciones_detalle,
                'hay_vacaciones': vacaciones_ibc_amount > 0,
                'hay_vacaciones_otro_periodo': vacaciones_otro_periodo > 0,
                # Complementos y adicionales
                'complemento_empresa_total': total_complemento_empresa,
                'valor_adicional_total': total_valor_adicional,
                'total_pagar_ausencias': total_pagar_ausencias,
                'hay_complementos': hay_complementos,
                'hay_adicionales': hay_adicionales,
            },
            'valores_anteriores': valores_anteriores,
            'diferencia_periodo_anterior': diferencia,
            'porcentaje_cambio': porcentaje_cambio,
            'explicacion_legal': explicacion_legal,
            'reglas_usadas': [r for r in reglas_usadas_detalle if r.get('total', 0) != 0],
            # Desglose salario integral
            'es_salario_integral': es_salario_integral,
            'ibc_antes_factor': ibc_antes_factor,
            'ibc_antes_limite': ibc_antes_limite,
            'limite_25_smmlv': limite_25_smmlv,
            'aplico_limite_25': aplico_limite_25,
            'desglose_factor': desglose_factor,
        }

        periodo = f"IBD {slip.date_from.strftime('%B %Y')}"

        indicadores = [
            crear_indicador('Dias', float(effective_days), 'info', 'number'),
        ]

        if es_salario_integral:
            indicadores.append(crear_indicador('Sal. Integral', '70%', 'primary', 'text'))

        if o_earnings > top40:
            indicadores.append(crear_indicador('Regla 40%', 'Aplicada', 'warning', 'text'))

        if aplico_limite_25:
            indicadores.append(crear_indicador('Límite 25 SMMLV', 'Aplicado', 'danger', 'text'))

        if porcentaje_cambio != 0:
            color_var = 'success' if porcentaje_cambio > 0 else 'danger'
            indicadores.append(crear_indicador('Variacion', f'{porcentaje_cambio:.1f}%', color_var, 'text'))

        if vacaciones_ibc_amount > 0:
            dias_vac = sum(v.get('days', 0) for v in vacaciones_detalle if v.get('es_nomina_actual', False))
            indicadores.append(crear_indicador('Vac. (en Sal.)', f'{dias_vac}d', 'info', 'text'))

        if vacaciones_otro_periodo > 0:
            dias_vac_otro = sum(v.get('days', 0) for v in vacaciones_detalle if not v.get('es_nomina_actual', True))
            indicadores.append(crear_indicador('Vac. Otro Per.', f'{dias_vac_otro}d', 'secondary', 'text'))

        # Crear pasos con items detallados para el widget
        pasos_widget = []

        # Codigos de ausencias para excluir del paso de ingresos salariales
        codigos_ausencias = {aus.get('code', '') for aus in ausencias_detalle_frontend}
        # Agregar codigos comunes de ausencias por si no estan en detalle
        codigos_ausencias.update([
            'INCAPACIDAD001', 'INCAPACIDAD002', 'INCAPACIDAD007', 'EGH',
            'AT', 'EP', 'MAT', 'PAT', 'LICENCIA001', 'LICENCIA_NO_REMUNERADA', 'LIC_NR',
            'LUTO', 'LNR', 'LICENCIA_LUTO'
        ])

        # Obtener IBC diario del mes anterior para mostrar en ausencias
        ibc_diario_anterior = None
        if absences_amount > 0:
            try:
                ibc_diario_anterior = self._obtener_ibc_diario_previo(contract, slip.date_from)
            except Exception:
                ibc_diario_anterior = None

        for exp in explicacion_legal.get('explicaciones_legales', []):
            paso_num = exp.get('paso', 0)
            items_detalle = []
            descripcion_paso = exp.get('explicacion', '')

            # Paso 1: Ingresos Salariales - excluir ausencias, mostrar solo reglas con valor > 0
            if paso_num == 1:
                subtotal_ingresos = 0
                for regla in reglas_usadas_detalle:
                    code = regla.get('code', '')
                    # Excluir ausencias del paso de ingresos
                    if code in codigos_ausencias:
                        continue
                    if regla.get('category_code') in ('BASIC', 'DEV_SALARIAL') and regla.get('total', 0) > 0:
                        valor = regla['total']
                        subtotal_ingresos += valor
                        items_detalle.append({
                            'nombre': f"{code} - {regla['name']}",
                            'valor': valor,
                            'formato': 'currency',
                            'esSuma': True,
                            'icono': 'fa-money',
                            'line_id': regla.get('rule_id'),  # Para link a la linea
                        })
                # Agregar subtotal al final
                if items_detalle:
                    items_detalle.append({
                        'nombre': 'SUBTOTAL INGRESOS SALARIALES',
                        'valor': subtotal_ingresos,
                        'formato': 'currency',
                        'esSubtotal': True,
                        'icono': 'fa-calculator',
                    })

            # Paso 2: Ausencias (si hay)
            elif paso_num == 2 and absences_amount > 0:
                # Mostrar parametros de IBC mes anterior si aplica
                hay_ibc_anterior = any(
                    'mes anterior' in (a.get('ibc_source', '') or '').lower()
                    for a in ausencias_detalle_frontend
                )
                if hay_ibc_anterior and ibc_diario_anterior:
                    ibc_mensual_anterior = ibc_diario_anterior * DAYS_MONTH
                    items_detalle.append({
                        'nombre': 'PARAMETROS IBC MES ANTERIOR',
                        'valor': None,
                        'formato': 'text',
                        'esEncabezado': True,
                        'icono': 'fa-cog',
                    })
                    items_detalle.append({
                        'nombre': '  IBC Diario (mes anterior)',
                        'valor': ibc_diario_anterior,
                        'formato': 'currency',
                        'nota': f'Base: ${ibc_mensual_anterior:,.0f} / 30',
                        'icono': 'fa-calendar',
                    })
                    items_detalle.append({
                        'nombre': '  IBC Mensual (referencia)',
                        'valor': ibc_mensual_anterior,
                        'formato': 'currency',
                        'nota': 'Art. 40 D.1406/99',
                        'icono': 'fa-history',
                    })
                    items_detalle.append({
                        'nombre': '',
                        'valor': None,
                        'formato': 'separator',
                    })

                # Detalle de cada ausencia
                subtotal_ausencias = 0
                subtotal_ibc = 0
                for aus in ausencias_detalle_frontend:
                    ibc_source = aus.get('ibc_source', '')
                    usa_ibc_anterior = 'mes anterior' in ibc_source.lower() if ibc_source else False
                    dias = aus.get('days_payslip', 0)
                    pago = aus.get('payment', 0)
                    ibc_amount = aus.get('ibc_amount', pago)
                    ibc_day = aus.get('ibc_day', 0)

                    # Calcular variacion entre pago y IBC
                    variacion = ((ibc_amount - pago) / pago * 100) if pago > 0 else 0

                    # Fila principal de la ausencia
                    items_detalle.append({
                        'nombre': f"{aus['name']}",
                        'valor': None,
                        'formato': 'text',
                        'esEncabezado': True,
                        'icono': 'fa-calendar-times-o' if not usa_ibc_anterior else 'fa-history',
                        'dias': dias,
                    })

                    # Detalle: Pago (base)
                    items_detalle.append({
                        'nombre': f"  Pago EPS/ARL ({dias} dias)",
                        'valor': pago,
                        'formato': 'currency',
                        'nota': 'Valor pagado',
                        'icono': 'fa-money',
                        'esBase': True,
                    })

                    # Detalle: IBC para SS (si es diferente al pago)
                    if usa_ibc_anterior and ibc_amount != pago:
                        items_detalle.append({
                            'nombre': f"  IBC para SS ({dias} dias x ${ibc_day:,.0f})",
                            'valor': ibc_amount,
                            'formato': 'currency',
                            'nota': f'{variacion:+.1f}%' if variacion != 0 else 'IBC mes anterior',
                            'icono': 'fa-arrow-right',
                            'esResultado': True,
                            'variacion': variacion,
                        })

                    subtotal_ausencias += pago
                    subtotal_ibc += ibc_amount

                    # Si tiene complemento empresa
                    complemento = aus.get('complemento_empresa', 0) or 0
                    valor_adicional = aus.get('valor_adicional_manual', 0) or 0
                    is_vac_money = aus.get('is_vacation_money', False)

                    # Mostrar etiqueta especial para vacaciones en dinero
                    if is_vac_money:
                        dias_liq = aus.get('dias_a_liquidar', 0) or dias
                        inc_fest = aus.get('incluir_festivos', True)
                        nota_vac = f"Liquidando {dias_liq} dias"
                        if not inc_fest:
                            nota_vac += " (sin festivos)"
                        items_detalle.append({
                            'nombre': f"  [VACACIONES EN DINERO]",
                            'valor': None,
                            'formato': 'text',
                            'nota': nota_vac,
                            'icono': 'fa-money',
                            'esEtiqueta': True,
                        })

                    if complemento > 0:
                        items_detalle.append({
                            'nombre': f"  + Complemento Empresa",
                            'valor': complemento,
                            'formato': 'currency',
                            'nota': 'Abono adicional',
                            'esSuma': True,
                            'icono': 'fa-building',
                        })

                    # Si tiene valor adicional manual
                    if valor_adicional > 0:
                        items_detalle.append({
                            'nombre': f"  + Valor Adicional Manual",
                            'valor': valor_adicional,
                            'formato': 'currency',
                            'nota': 'Ajuste manual',
                            'esSuma': True,
                            'icono': 'fa-plus-square',
                        })

                    # Mostrar total si hay complemento o adicional
                    if complemento > 0 or valor_adicional > 0:
                        total_pagar = aus.get('total_pagar', 0)
                        componentes = []
                        if pago > 0:
                            componentes.append('EPS' if not is_vac_money else 'Calculado')
                        if complemento > 0:
                            componentes.append('Complemento')
                        if valor_adicional > 0:
                            componentes.append('Adicional')
                        nota_total = ' + '.join(componentes)

                        items_detalle.append({
                            'nombre': f"  = TOTAL A PAGAR",
                            'valor': total_pagar,
                            'formato': 'currency',
                            'nota': nota_total,
                            'esTotal': True,
                            'icono': 'fa-calculator',
                        })

                # Subtotales de ausencias
                if len(ausencias_detalle_frontend) > 1 or subtotal_ibc != subtotal_ausencias:
                    items_detalle.append({
                        'nombre': '',
                        'valor': None,
                        'formato': 'separator',
                    })
                    items_detalle.append({
                        'nombre': 'SUBTOTAL PAGOS AUSENCIAS',
                        'valor': subtotal_ausencias,
                        'formato': 'currency',
                        'esSubtotal': True,
                        'icono': 'fa-money',
                    })
                    if subtotal_ibc != subtotal_ausencias:
                        var_total = ((subtotal_ibc - subtotal_ausencias) / subtotal_ausencias * 100) if subtotal_ausencias > 0 else 0
                        items_detalle.append({
                            'nombre': 'SUBTOTAL IBC PARA SS',
                            'valor': subtotal_ibc,
                            'formato': 'currency',
                            'nota': f'{var_total:+.1f}%',
                            'esSubtotal': True,
                            'esResultado': True,
                            'icono': 'fa-shield',
                        })

            # Paso 3: Ingresos No Salariales - mostrar solo reglas con valor > 0
            elif paso_num == 3 and o_earnings > 0:
                for regla in reglas_usadas_detalle:
                    if regla.get('category_code') == 'DEV_NO_SALARIAL' and regla.get('total', 0) > 0:
                        items_detalle.append({
                            'nombre': f"{regla['code']} - {regla['name']}",
                            'valor': regla['total'],
                            'formato': 'currency',
                            'esSuma': True,
                            'icono': 'fa-plus-circle',
                        })

            # Paso 4: Regla 40% - mostrar calculo
            elif paso_num == 4:
                total_base = salary_for_40 + o_earnings
                if o_earnings > top40:
                    items_detalle = [
                        {'nombre': 'Total ingresos (salariales + no salariales)', 'valor': total_base, 'formato': 'currency'},
                        {'nombre': 'Ingresos no salariales', 'valor': o_earnings, 'formato': 'currency'},
                        {'nombre': 'Limite 40% del total', 'valor': top40, 'formato': 'currency'},
                        {'nombre': 'Exceso a excluir de la base', 'valor': o_earnings - top40, 'formato': 'currency', 'esResta': True, 'icono': 'fa-minus-circle'},
                        {'nombre': 'Base despues de regla 40%', 'valor': total_base - (o_earnings - top40), 'formato': 'currency', 'icono': 'fa-check'},
                    ]
                else:
                    items_detalle = [
                        {'nombre': 'Total ingresos (salariales + no salariales)', 'valor': total_base, 'formato': 'currency'},
                        {'nombre': 'Ingresos no salariales', 'valor': o_earnings, 'formato': 'currency'},
                        {'nombre': 'Limite 40% del total', 'valor': top40, 'formato': 'currency'},
                        {'nombre': 'No hay exceso - No se aplica exclusion', 'valor': 0, 'formato': 'currency', 'nota': 'INS <= 40%'},
                    ]

            # Paso 6: Factor Salarial (salario integral)
            elif paso_num == 6 and es_salario_integral:
                aplica_70 = desglose_factor.get('aplica_70', [])
                aplica_100 = desglose_factor.get('aplica_100', [])
                total_base_70 = desglose_factor.get('total_base_70', 0)
                total_ajustado_70 = desglose_factor.get('total_ajustado_70', 0)
                total_base_100 = desglose_factor.get('total_base_100', 0)
                total_ajustado_100 = desglose_factor.get('total_ajustado_100', 0)

                # Seccion: Conceptos al 70%
                if aplica_70:
                    items_detalle.append({
                        'nombre': 'CONCEPTOS AL 70% (Factor Salarial)',
                        'valor': None,
                        'formato': 'text',
                        'esEncabezado': True,
                        'icono': 'fa-percent',
                    })
                    for regla_70 in aplica_70:
                        items_detalle.append({
                            'nombre': f"{regla_70['code']} - {regla_70['name']}",
                            'valor': regla_70['monto_original'],
                            'formato': 'currency',
                            'nota': f"x70% = ${regla_70['monto_ajustado']:,.0f}",
                        })
                    # Subtotal 70%
                    items_detalle.append({
                        'nombre': 'Subtotal 70%',
                        'valor': total_ajustado_70,
                        'formato': 'currency',
                        'esSubtotal': True,
                        'nota': f"Base: ${total_base_70:,.0f}",
                        'icono': 'fa-calculator',
                    })

                # Separador
                if aplica_70 and aplica_100:
                    items_detalle.append({'nombre': '', 'valor': None, 'formato': 'separator'})

                # Seccion: Conceptos al 100%
                if aplica_100:
                    items_detalle.append({
                        'nombre': 'CONCEPTOS AL 100% (Sin reduccion)',
                        'valor': None,
                        'formato': 'text',
                        'esEncabezado': True,
                        'icono': 'fa-check-circle',
                    })
                    for regla_100 in aplica_100:
                        items_detalle.append({
                            'nombre': f"{regla_100['code']} - {regla_100['name']}",
                            'valor': regla_100['monto_original'],
                            'formato': 'currency',
                            'nota': "100%",
                        })
                    # Subtotal 100%
                    items_detalle.append({
                        'nombre': 'Subtotal 100%',
                        'valor': total_ajustado_100,
                        'formato': 'currency',
                        'esSubtotal': True,
                        'icono': 'fa-calculator',
                    })

                # Total IBC despues de factor
                if aplica_70 or aplica_100:
                    items_detalle.append({'nombre': '', 'valor': None, 'formato': 'separator'})
                    items_detalle.append({
                        'nombre': 'IBC DESPUES DE FACTOR',
                        'valor': total_ajustado_70 + total_ajustado_100,
                        'formato': 'currency',
                        'esResultado': True,
                        'icono': 'fa-flag-checkered',
                    })

            # Paso 7: Limite 25 SMMLV
            elif paso_num == 7:
                items_detalle = [
                    {'nombre': 'IBC calculado', 'valor': ibc_antes_limite, 'formato': 'currency'},
                    {'nombre': 'Limite 25 SMMLV', 'valor': limite_25_smmlv, 'formato': 'currency'},
                    {'nombre': 'IBC final', 'valor': ibc_final, 'formato': 'currency', 'icono': 'fa-check'},
                ]

            pasos_widget.append(
                crear_paso_calculo(
                    exp.get('titulo', ''),
                    exp.get('valor', 0),
                    'currency',
                    highlight=exp.get('paso') == 7,
                    base_legal=exp.get('base_legal', ''),
                    items=items_detalle if items_detalle else None,
                    descripcion=descripcion_paso,
                    formula=exp.get('formula', None),
                )
            )

        # Paso adicional: Vacaciones (si hay de esta nomina o de otro periodo)
        if vacaciones_ibc_amount > 0 or vacaciones_otro_periodo > 0:
            items_vacaciones = []

            # Vacaciones de ESTA nomina (ya incluidas en Salary como DEV_SALARIAL)
            vac_esta_nomina = [v for v in vacaciones_detalle if v.get('es_nomina_actual', False)]
            if vac_esta_nomina:
                items_vacaciones.append({
                    'nombre': 'VACACIONES ESTA NOMINA (Ya en Salary)',
                    'valor': None,
                    'formato': 'text',
                    'esEncabezado': True,
                    'icono': 'fa-sun-o',
                })
                for vac in vac_esta_nomina:
                    leave_id = vac.get('leave_id')
                    vac_info = por_leave.get(leave_id, {}) if leave_id else {}
                    vac_name = vac_info.get('tipo', 'Vacaciones')
                    nota_vac = 'SUMA al IBC' if include_absences_1393 else 'NO suma al IBC (ya pagado)'
                    icono_vac = 'fa-plus-circle' if include_absences_1393 else 'fa-ban'
                    items_vacaciones.append({
                        'nombre': f"  {vac_name} ({vac['days']} dias)",
                        'valor': vac['amount'],
                        'formato': 'currency',
                        'nota': nota_vac,
                        'icono': icono_vac,
                        'esInfo': True,
                    })
                items_vacaciones.append({
                    'nombre': 'TOTAL VACACIONES (suma al IBC)' if include_absences_1393 else 'TOTAL VACACIONES (no suma)',
                    'valor': vacaciones_ibc_amount if include_absences_1393 else 0.0,
                    'formato': 'currency',
                    'esSubtotal': True,
                    'nota': 'Incluidas por configuración' if include_absences_1393 else 'No se suma de nuevo',
                    'icono': 'fa-info-circle',
                })

            # Vacaciones de OTRO periodo (solo para regla 40%)
            vac_otro_periodo = [v for v in vacaciones_detalle if not v.get('es_nomina_actual', True)]
            if vac_otro_periodo:
                if vac_esta_nomina:
                    items_vacaciones.append({'nombre': '', 'valor': None, 'formato': 'separator'})
                items_vacaciones.append({
                    'nombre': 'VACACIONES OTRO PERIODO (Solo para regla 40%)',
                    'valor': None,
                    'formato': 'text',
                    'esEncabezado': True,
                    'icono': 'fa-history',
                })
                for vac in vac_otro_periodo:
                    leave_id = vac.get('leave_id')
                    vac_info = por_leave.get(leave_id, {}) if leave_id else {}
                    vac_name = vac_info.get('tipo', 'Vacaciones')
                    items_vacaciones.append({
                        'nombre': f"  {vac_name} ({vac['days']} dias)",
                        'valor': vac['amount'],
                        'formato': 'currency',
                        'nota': 'NO suma al IBC (ya pagado)',
                        'icono': 'fa-ban',
                        'esInfo': True,
                    })
                items_vacaciones.append({
                    'nombre': 'TOTAL OTRO PERIODO (no suma)',
                    'valor': vacaciones_otro_periodo,
                    'formato': 'currency',
                    'esSubtotal': True,
                    'nota': 'Solo cuenta para calculo 40%',
                    'icono': 'fa-info-circle',
                })

            descripcion_vac = (
                'Vacaciones de esta nomina se suman al IBC por configuración. '
                'Vacaciones de otro periodo solo afectan la regla del 40%.'
                if include_absences_1393 else
                'Vacaciones de esta nomina ya incluidas en Ingresos Salariales (DEV_SALARIAL). '
                'Vacaciones de otro periodo solo afectan la regla del 40%.'
            )
            vacaciones_valor_paso = vacaciones_ibc_amount if include_absences_1393 else 0.0
            pasos_widget.insert(-1, crear_paso_calculo(
                'Vacaciones Disfrutadas',
                vacaciones_valor_paso,  # Solo muestra lo que suma al IBC
                'currency',
                highlight=False,
                base_legal='Art. 186 CST',
                items=items_vacaciones,
                descripcion=descripcion_vac,
                formula=None,
            ))

        if o_earnings > top40:
            formula = 'Salario + (O.Dev - Exceso 40%)'
        else:
            formula = 'Salario + Otros Devengos'

        if paid_absences_ibc_amount > 0:
            formula += ' + Ausencias'

        # Las vacaciones de esta nomina ya estan incluidas en Salario (DEV_SALARIAL)
        # Solo mostrar nota si hay vacaciones de otro periodo que afectan el 40%
        if vacaciones_otro_periodo > 0:
            formula += ' (Vac. otro per. en 40%)'

        if contract.modality_salary == 'integral':
            formula += ' x 70%'

        computation = crear_computation_estandar(
            'ibd',
            titulo='Ingreso Base de Cotizacion',
            formula=formula,
            explicacion=f'IBC calculado segun Ley 1393/2010',
            indicadores=indicadores,
            pasos=pasos_widget,
            base_legal='Ley 1393 de 2010',
            elemento_ley='Art. 27: Regla del 40% para ingresos no salariales. Art. 30: Limite maximo 25 SMMLV.',
            articulos=['Art. 27', 'Art. 30'],
            datos=resultado_full,
            line_ids=nom_data.get('line_ids', []),
            valor_anterior=valores_anteriores.get('valor_anterior_promedio', 0),
            variacion=porcentaje_cambio,
        )

        return day_value, effective_days, 100, periodo, "", computation


    def _get_ibd_data_from_rules(self, liquidacion_data):
        """
        Obtiene datos de IBD desde rules de manera centralizada.
        Elimina duplicación de código en métodos de seguridad social.

        Returns:
            dict: {
                'ibd_rule': objeto rule o None,
                'ibc_full': float,
                'ingreso_base_cotizacion': float,
                'ibc': float,
                'vac_monto': float,
                'vac_dias': float
            }
        """
        slip = liquidacion_data.get('slip')
        rules = liquidacion_data.get('rules', {})
        rules_keys = list(rules.keys()) if rules else []

        _logger.info(
            f"[IBD_DATA] _get_ibd_data_from_rules() - "
            f"Slip: {slip.id if slip else 'N/A'}, "
            f"Struct: {slip.struct_id.name if slip else 'N/A'}, "
            f"Rules disponibles: {rules_keys}"
        )

        ibd_rule = rules.get('IBD')
        if not ibd_rule:
            _logger.warning(
                f"[IBD_DATA] NO SE ENCONTRO REGLA IBD en rules! "
                f"Slip: {slip.id if slip else 'N/A'}, Struct: {slip.struct_id.name if slip else 'N/A'}"
            )
            return {
                'ibd_rule': None,
                'ibc_full': 0,
                'ingreso_base_cotizacion': 0,
                'ibc': 0,
                'vac_monto': 0,
                'vac_dias': 0
            }

        ibc_full = 0
        if ibd_rule and ibd_rule.extra_data:
            ibc_full = (
                ibd_rule.extra_data.get('ibc_full', 0) or
                ibd_rule.extra_data.get('ibc_final', 0)
            )
        ingreso_base_cotizacion = ibd_rule.total if ibd_rule else 0
        if not ibc_full:
            ibc_full = ingreso_base_cotizacion
        ibc = ibc_full - ingreso_base_cotizacion
        vac_monto = ibd_rule.extra_data.get('vac_monto', 0) if ibd_rule.extra_data else 0
        vac_dias = ibd_rule.extra_data.get('vac_dias', 0) if ibd_rule.extra_data else 0

        _logger.info(
            f"[IBD_DATA] Regla IBD encontrada - ibc_full={ibc_full}, "
            f"ingreso_base_cotizacion={ingreso_base_cotizacion}, ibc={ibc}, "
            f"vac_monto={vac_monto}, vac_dias={vac_dias}"
        )

        return {
            'ibd_rule': ibd_rule,
            'ibc_full': ibc_full,
            'ingreso_base_cotizacion': ingreso_base_cotizacion,
            'ibc': ibc,
            'vac_monto': vac_monto,
            'vac_dias': vac_dias
        }
