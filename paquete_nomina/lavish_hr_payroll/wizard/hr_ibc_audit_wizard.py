# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
from decimal import Decimal
from io import BytesIO
import base64
import math

DAYS_MONTH = 30


def roundup100(amount):
    """Redondea al siguiente múltiplo de 100."""
    return math.ceil(amount / 100.0) * 100


def roundupdecimal(amount):
    """Redondea al siguiente entero."""
    return math.ceil(amount)


class HrIbcAuditWizard(models.TransientModel):
    """Wizard para generar reporte de auditoría de IBC desde nómina individual."""
    _name = 'hr.ibc.audit.wizard'
    _description = 'Auditoría de IBC'

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Nómina',
        required=True,
        default=lambda self: self.env.context.get('active_id') if self.env.context.get('active_model') == 'hr.payslip' else False
    )
    employee_id = fields.Many2one('hr.employee', string='Empleado', related='payslip_id.employee_id')
    contract_id = fields.Many2one('hr.contract', string='Contrato', related='payslip_id.contract_id')
    date_from = fields.Date(string='Desde', related='payslip_id.date_from')
    date_to = fields.Date(string='Hasta', related='payslip_id.date_to')

    audit_html = fields.Html(string='Detalle de Auditoría', readonly=True)
    has_differences = fields.Boolean(string='Tiene Diferencias', readonly=True)

    def action_generate_audit(self):
        """Genera el reporte de auditoría de IBC."""
        self.ensure_one()
        slip = self.payslip_id
        contract = slip.contract_id
        employee = slip.employee_id

        if not slip:
            raise UserError(_('Debe seleccionar una nómina para generar la auditoría.'))

        annual_params = self.env['hr.annual.parameters'].get_for_year(
            slip.date_from.year,
            company_id=slip.company_id.id,
            raise_if_not_found=False,
        )

        smmlv = annual_params.smmlv_monthly if annual_params else 0

        audit_data = self._collect_payslip_data(slip, contract, annual_params)
        ibc_calculated = self._calculate_expected_ibc(audit_data, smmlv, contract, annual_params)
        ss_calculated = self._calculate_social_security(ibc_calculated, audit_data, contract, employee, annual_params)

        ibc_line = slip.line_ids.filtered(lambda l: l.salary_rule_id.code in ('IBD', 'IBC_R'))
        ibc_registered = ibc_line[0].total if ibc_line else 0

        difference = abs(ibc_calculated['ibc_final'] - ibc_registered)
        has_diff = difference > 1

        html = self._generate_audit_html(
            slip, contract, employee, audit_data,
            ibc_calculated, ss_calculated, ibc_registered, difference, smmlv, annual_params
        )

        self.write({
            'audit_html': html,
            'has_differences': has_diff,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.ibc.audit.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_criterio_ibc(self, rule, cat_code, parent_cat_code, novelty, novelty_name, novelty_excluidos_40, include_absences_1393):
        """
        Determina el criterio/justificación de por qué un concepto se incluye o excluye del IBC.

        Returns:
            dict: {
                'aplica': bool - si aplica al IBC,
                'criterio': str - explicación corta,
                'referencia_legal': str - artículo o ley aplicable,
                'color': str - color para visualización (green/red/yellow)
            }
        """
        base_ss = rule.base_seguridad_social if hasattr(rule, 'base_seguridad_social') else False

        # Determinar criterio según tipo de concepto
        if novelty:
            # Es una ausencia/novedad
            if novelty in novelty_excluidos_40:
                if novelty == 'ige':
                    return {
                        'aplica': True,
                        'criterio': 'Incapacidad EPS - Suma directo al IBC',
                        'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                        'color': 'blue'
                    }
                elif novelty == 'irl':
                    return {
                        'aplica': True,
                        'criterio': 'Accidente Trabajo - Suma directo al IBC',
                        'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                        'color': 'blue'
                    }
                elif novelty == 'lma':
                    return {
                        'aplica': True,
                        'criterio': 'Licencia Maternidad - Suma directo al IBC',
                        'referencia_legal': 'Art. 236 CST',
                        'color': 'blue'
                    }
                elif novelty in ('vco', 'vdi', 'vre'):
                    return {
                        'aplica': True,
                        'criterio': 'Vacaciones - Suma directo al IBC',
                        'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                        'color': 'blue'
                    }
                elif novelty == 'sln':
                    return {
                        'aplica': False,
                        'criterio': 'Licencia No Remunerada - No suma al IBC',
                        'referencia_legal': 'Concepto UGPP',
                        'color': 'gray'
                    }
            else:
                # Ausencias incluidas en 40% (lr, lt)
                if include_absences_1393:
                    return {
                        'aplica': True,
                        'criterio': f'Ausencia {novelty_name} - Participa en limite 40%',
                        'referencia_legal': 'Ley 1393/2010 Art. 30',
                        'color': 'yellow'
                    }
                else:
                    return {
                        'aplica': True,
                        'criterio': f'Ausencia {novelty_name} - Suma directo al IBC (UGPP)',
                        'referencia_legal': 'Concepto UGPP 2018',
                        'color': 'blue'
                    }

        # Conceptos salariales
        if cat_code == 'DEV_SALARIAL' or parent_cat_code == 'DEV_SALARIAL':
            if base_ss:
                return {
                    'aplica': True,
                    'criterio': 'Devengo Salarial - Base SS',
                    'referencia_legal': 'Art. 127 CST',
                    'color': 'green'
                }
            else:
                return {
                    'aplica': False,
                    'criterio': 'Devengo Salarial - NO marcado Base SS',
                    'referencia_legal': 'Configuracion regla',
                    'color': 'red'
                }

        # Conceptos no salariales
        if cat_code == 'DEV_NO_SALARIAL' or parent_cat_code == 'DEV_NO_SALARIAL':
            return {
                'aplica': True,
                'criterio': 'No Salarial - Sujeto a limite 40%',
                'referencia_legal': 'Ley 1393/2010 Art. 30',
                'color': 'yellow'
            }

        # Horas extras y recargos
        if cat_code == 'HEYREC':
            return {
                'aplica': True,
                'criterio': 'Horas Extras/Recargos - Base SS',
                'referencia_legal': 'Art. 127 CST',
                'color': 'green'
            }

        # Comisiones
        if cat_code == 'COMISIONES':
            return {
                'aplica': True,
                'criterio': 'Comisiones - Salario variable',
                'referencia_legal': 'Art. 127 CST',
                'color': 'green'
            }

        # Básico
        if cat_code == 'BASIC' or rule.code in ('BASIC', 'BASIC005'):
            return {
                'aplica': True,
                'criterio': 'Salario Basico',
                'referencia_legal': 'Art. 127 CST',
                'color': 'green'
            }

        # Vacaciones
        if cat_code == 'VACACIONES':
            return {
                'aplica': True,
                'criterio': 'Vacaciones - Base SS',
                'referencia_legal': 'Art. 3.2.1.10 Decreto 780/2016',
                'color': 'blue'
            }

        # Default
        if base_ss:
            return {
                'aplica': True,
                'criterio': 'Marcado como Base SS',
                'referencia_legal': 'Configuracion regla',
                'color': 'green'
            }
        else:
            return {
                'aplica': False,
                'criterio': 'NO marcado como Base SS',
                'referencia_legal': 'Configuracion regla',
                'color': 'gray'
            }

    def _collect_payslip_data(self, slip, contract, annual_params):
        """Recopila datos de la nómina para auditoría aplicando Ley 1393 con tipos PILA (novelty)."""
        category_news = ['INCAPACIDAD', 'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
                         'LICENCIA_MATERNIDAD', 'VACACIONES', 'ACCIDENTE_TRABAJO']

        # Detectar tipo de periodo (quincena o mes completo)
        dias_periodo = (slip.date_to - slip.date_from).days + 1
        es_quincena = dias_periodo <= 16
        es_primera_quincena = slip.date_from.day == 1 and slip.date_to.day <= 16
        es_segunda_quincena = slip.date_from.day >= 15

        # Tipos PILA (novelty) que NO participan en limite 40% segun UGPP
        novelty_excluidos_40 = ['sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi', 'vre']

        data = {
            'conceptos_salariales': [],
            'conceptos_no_salariales': [],
            'conceptos_vacaciones': [],
            'conceptos_ausencias': [],
            'conceptos_ausencias_excluidas': [],  # Ausencias que NO participan en 40%
            'conceptos_ausencias_incluidas': [],  # Ausencias que SI participan en 40%
            'conceptos_deducciones': [],
            'conceptos_ss_nomina': [],
            'total_salarial': 0,
            'total_no_salarial': 0,
            'total_vacaciones': 0,
            'total_ausencias': 0,
            'total_ausencias_excluidas': 0,
            'total_ausencias_incluidas': 0,
            'dias_trabajados': 30,
            'dias_basico_nomina': 0,  # Dias del concepto BASIC (para cotizante 51)
            'dias_ausencia_no_remunerada': 0,
            'dias_incapacidad_eps': 0,
            'dias_licencia_remunerada': 0,
            'dias_maternidad': 0,
            'dias_vacaciones': 0,
            'dias_accidente_trabajo': 0,
            # Valores de nómina para comparación
            'nomina_salud_empleado': 0,
            'nomina_pension_empleado': 0,
            'nomina_fondo_solidaridad': 0,
            'nomina_fondo_subsistencia': 0,
            # Bases calculadas como en seguridad social
            'base_seguridad_social': {},
            'base_parafiscales': {},
            # Configuracion Ley 1393
            'include_absences_1393': False,
            'ley_1393_detalle': {},
            # Info del periodo
            'dias_periodo': dias_periodo,
            'es_quincena': es_quincena,
            'es_primera_quincena': es_primera_quincena,
            'es_segunda_quincena': es_segunda_quincena,
        }

        # Obtener configuracion Ley 1393 de la empresa
        company = contract.company_id or self.env.company
        include_absences_1393 = company.include_absences_1393 if hasattr(company, 'include_absences_1393') else False
        data['include_absences_1393'] = include_absences_1393

        # Obtener porcentaje estatuto 1395
        porc_statute = annual_params.value_porc_statute_1395 if annual_params and hasattr(annual_params, 'value_porc_statute_1395') else 40
        porc_integral = annual_params.porc_integral_salary if annual_params and hasattr(annual_params, 'porc_integral_salary') else 70

        value_base = 0
        value_base_no_dev = 0
        value_ausencias_excluidas = 0
        value_ausencias_incluidas = 0

        for line in slip.line_ids.filtered(lambda l: l.total != 0):
            rule = line.salary_rule_id
            cat_code = line.category_id.code if line.category_id else ''
            parent_cat_code = line.category_id.parent_id.code if line.category_id and line.category_id.parent_id else ''

            # Obtener novelty si la linea tiene ausencia asociada
            novelty = None
            novelty_name = None
            if hasattr(line, 'leave_id') and line.leave_id and line.leave_id.holiday_status_id:
                novelty = line.leave_id.holiday_status_id.novelty
                novelty_name = dict(line.leave_id.holiday_status_id._fields['novelty'].selection).get(novelty, novelty)

            # Determinar si aplica teoricamente al IBC
            aplica_regla_ibc = rule.base_seguridad_social if hasattr(rule, 'base_seguridad_social') else False

            # Determinar criterio IBC segun tipo de concepto
            criterio_ibc = self._get_criterio_ibc(
                rule=rule,
                cat_code=cat_code,
                parent_cat_code=parent_cat_code,
                novelty=novelty,
                novelty_name=novelty_name,
                novelty_excluidos_40=novelty_excluidos_40,
                include_absences_1393=include_absences_1393
            )

            item = {
                'code': rule.code,
                'name': line.name or rule.name,
                'quantity': line.quantity,
                'amount': line.amount,
                'total': line.total,
                'category': cat_code,
                'base_ss': rule.base_seguridad_social if hasattr(rule, 'base_seguridad_social') else False,
                'base_parafiscales': rule.base_parafiscales if hasattr(rule, 'base_parafiscales') else False,
                'novelty': novelty,
                'novelty_name': novelty_name,
                'excluido_40': novelty in novelty_excluidos_40 if novelty else False,
                'aplica_regla': aplica_regla_ibc,
                'criterio_ibc': criterio_ibc,
            }

            if rule.dev_or_ded == 'devengo':
                # Capturar dias del basico para cotizante 51 (independiente de categoria)
                if rule.code in ('BASIC', 'BASIC005') and line.quantity > 0:
                    data['dias_basico_nomina'] += line.quantity

                # Verificar si es ausencia por novelty
                if novelty:
                    data['conceptos_ausencias'].append(item)
                    data['total_ausencias'] += abs(line.total)

                    if novelty in novelty_excluidos_40:
                        # Ausencia excluida del limite 40% (IGE, IRL, LMA, VAC, SLN)
                        value_ausencias_excluidas += abs(line.total)
                        data['conceptos_ausencias_excluidas'].append(item)
                        data['total_ausencias_excluidas'] += abs(line.total)
                    else:
                        # Ausencia incluida en limite 40% (LR, LT)
                        value_ausencias_incluidas += abs(line.total)
                        data['conceptos_ausencias_incluidas'].append(item)
                        data['total_ausencias_incluidas'] += abs(line.total)

                    # Clasificar días por tipo novelty
                    if novelty == 'ige':
                        data['dias_incapacidad_eps'] += line.quantity
                    elif novelty == 'sln' or novelty == 'lnr':
                        data['dias_ausencia_no_remunerada'] += line.quantity
                    elif novelty in ('lr', 'lt'):
                        data['dias_licencia_remunerada'] += line.quantity
                    elif novelty in ('lma', 'lpa'):
                        data['dias_maternidad'] += line.quantity
                    elif novelty in ('vco', 'vdi', 'vre'):
                        data['dias_vacaciones'] += line.quantity
                    elif novelty == 'irl':
                        data['dias_accidente_trabajo'] += line.quantity

                # Cálculo como en seguridad social (sin ausencias)
                elif cat_code == 'DEV_SALARIAL' or parent_cat_code == 'DEV_SALARIAL':
                    value_base += abs(line.total)
                    data['conceptos_salariales'].append(item)
                    if item['base_ss']:
                        data['total_salarial'] += line.total

                elif (cat_code == 'DEV_NO_SALARIAL' or parent_cat_code == 'DEV_NO_SALARIAL') and cat_code != 'AUX':
                    value_base_no_dev += abs(line.total)
                    data['conceptos_no_salariales'].append(item)
                    data['total_no_salarial'] += line.total

                elif cat_code in ('BASIC',):
                    value_base += abs(line.total)
                    data['conceptos_salariales'].append(item)
                    if item['base_ss']:
                        data['total_salarial'] += line.total

                elif cat_code == 'VACACIONES':
                    data['conceptos_vacaciones'].append(item)
                    data['total_vacaciones'] += line.total
                    data['dias_vacaciones'] += line.quantity

                elif cat_code in category_news and not novelty:
                    # Fallback si no hay novelty pero si categoria de ausencia
                    data['conceptos_ausencias'].append(item)
                    data['total_ausencias'] += abs(line.total)
                    # Contar dias por categoria cuando no hay novelty
                    if cat_code == 'INCAPACIDAD':
                        data['dias_incapacidad_eps'] += line.quantity
                    elif cat_code == 'LICENCIA_NO_REMUNERADA':
                        data['dias_ausencia_no_remunerada'] += line.quantity
                    elif cat_code == 'LICENCIA_REMUNERADA':
                        data['dias_licencia_remunerada'] += line.quantity
                    elif cat_code == 'LICENCIA_MATERNIDAD':
                        data['dias_maternidad'] += line.quantity
                    elif cat_code == 'VACACIONES':
                        data['dias_vacaciones'] += line.quantity
                    elif cat_code == 'ACCIDENTE_TRABAJO':
                        data['dias_accidente_trabajo'] += line.quantity

                elif cat_code == 'HEYREC' or cat_code == 'COMISIONES':
                    value_base += abs(line.total)
                    data['conceptos_salariales'].append(item)
                    if item['base_ss']:
                        data['total_salarial'] += line.total

            elif rule.dev_or_ded == 'deduccion':
                data['conceptos_deducciones'].append(item)
                if rule.code == 'SSOCIAL001':
                    data['nomina_salud_empleado'] = abs(line.total)
                    data['conceptos_ss_nomina'].append({**item, 'tipo': 'Salud Empleado'})
                elif rule.code == 'SSOCIAL002':
                    data['nomina_pension_empleado'] = abs(line.total)
                    data['conceptos_ss_nomina'].append({**item, 'tipo': 'Pension Empleado'})
                elif rule.code == 'SSOCIAL003':
                    data['nomina_fondo_subsistencia'] = abs(line.total)
                    data['conceptos_ss_nomina'].append({**item, 'tipo': 'Fondo Subsistencia'})
                elif rule.code == 'SSOCIAL004':
                    data['nomina_fondo_solidaridad'] = abs(line.total)
                    data['conceptos_ss_nomina'].append({**item, 'tipo': 'Fondo Solidaridad'})

        # Aplicar Ley 1393 segun configuracion include_absences_1393
        if include_absences_1393:
            # Todas las ausencias participan en el calculo del 40%
            base_for_40 = value_base + value_ausencias_excluidas + value_ausencias_incluidas
        else:
            # UGPP: Solo ausencias incluidas (lr, lt) participan en el 40%
            base_for_40 = value_base + value_ausencias_incluidas

        # Calcular limite 40%
        total_for_limit = base_for_40 + value_base_no_dev
        statute_value = total_for_limit * (porc_statute / 100)
        exceso_no_salarial = max(0, value_base_no_dev - statute_value)

        # IBC = base_for_40 + exceso de no salariales
        ibc_ss = base_for_40 + exceso_no_salarial

        # Si UGPP: sumar ausencias excluidas directamente al IBC
        if not include_absences_1393:
            ibc_ss += value_ausencias_excluidas

        # Ajustar para salario integral
        if contract.modality_salary == 'integral':
            ibc_ss = ibc_ss * (porc_integral / 100)

        # Guardar detalle del calculo Ley 1393
        data['ley_1393_detalle'] = {
            'include_absences': include_absences_1393,
            'base_salarial': value_base,
            'ausencias_excluidas': value_ausencias_excluidas,
            'ausencias_incluidas': value_ausencias_incluidas,
            'base_for_40': base_for_40,
            'no_salarial': value_base_no_dev,
            'total_for_limit': total_for_limit,
            'limite_40': statute_value,
            'exceso_no_salarial': exceso_no_salarial,
            'ibc_antes_integral': ibc_ss if contract.modality_salary != 'integral' else ibc_ss / (porc_integral / 100),
        }

        data['ibc_seguridad_social'] = ibc_ss
        data['value_base'] = value_base
        data['value_base_no_dev'] = value_base_no_dev
        data['base_40'] = exceso_no_salarial
        data['news_value'] = value_ausencias_excluidas + value_ausencias_incluidas
        data['dias_trabajados'] = DAYS_MONTH - data['dias_ausencia_no_remunerada']

        # Para cotizante 51: buscar otras nominas del mismo mes para acumular dias
        employee = contract.employee_id
        es_cotizante_51 = hasattr(employee, 'tipo_coti_id') and employee.tipo_coti_id and employee.tipo_coti_id.code == '51'

        if es_cotizante_51:
            # Buscar todas las nominas del mismo mes para este empleado
            primer_dia_mes = slip.date_from.replace(day=1)
            if slip.date_from.month == 12:
                ultimo_dia_mes = slip.date_from.replace(day=31)
            else:
                from dateutil.relativedelta import relativedelta
                ultimo_dia_mes = (primer_dia_mes + relativedelta(months=1)) - relativedelta(days=1)

            otras_nominas = self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('contract_id', '=', contract.id),
                ('state', 'in', ['done', 'paid']),
                ('date_from', '>=', primer_dia_mes),
                ('date_to', '<=', ultimo_dia_mes),
                ('id', '!=', slip.id),  # Excluir la nomina actual
            ])

            dias_otras_nominas = 0
            for otra_nomina in otras_nominas:
                for line in otra_nomina.line_ids.filtered(lambda l: l.salary_rule_id.code in ('BASIC', 'BASIC005') and l.quantity > 0):
                    dias_otras_nominas += line.quantity

            # Total de dias del mes para cotizante 51
            data['dias_otras_nominas_mes'] = dias_otras_nominas
            data['dias_totales_mes_51'] = data['dias_basico_nomina'] + dias_otras_nominas
        else:
            data['dias_otras_nominas_mes'] = 0
            data['dias_totales_mes_51'] = 0

        return data

    def _calculate_expected_ibc(self, audit_data, smmlv, contract, annual_params):
        """Calcula el IBC esperado según la fórmula de seguridad social."""
        salarial = audit_data['total_salarial']
        no_salarial = audit_data['total_no_salarial']
        vacaciones = audit_data['total_vacaciones']
        ausencias = audit_data['total_ausencias']
        dias_efectivos = audit_data['dias_trabajados']
        employee = contract.employee_id

        # Verificar si es cotizante 51 (tiempo parcial)
        es_cotizante_51 = False
        tope_min_51 = 0
        semanas_51 = 0
        dias_51_esta_nomina = 0
        dias_51_otras_nominas = 0
        dias_51_total_mes = 0

        if hasattr(employee, 'tipo_coti_id') and employee.tipo_coti_id and employee.tipo_coti_id.code == '51':
            es_cotizante_51 = True
            # Para cotizante 51: usar los dias reales de las nominas del mes
            dias_51_esta_nomina = audit_data.get('dias_basico_nomina', 0)
            dias_51_otras_nominas = audit_data.get('dias_otras_nominas_mes', 0)
            dias_51_total_mes = audit_data.get('dias_totales_mes_51', dias_51_esta_nomina)

            # Calcular tope minimo segun tabla cotizante 51 usando dias totales del mes
            dias_redondeados = round(dias_51_total_mes)
            if dias_redondeados >= 1 and dias_redondeados <= 7:
                tope_min_51 = smmlv / 4
                semanas_51 = 1
            elif dias_redondeados >= 8 and dias_redondeados <= 14:
                tope_min_51 = (smmlv / 4) * 2
                semanas_51 = 2
            elif dias_redondeados >= 15 and dias_redondeados <= 21:
                tope_min_51 = (smmlv / 4) * 3
                semanas_51 = 3
            elif dias_redondeados >= 22 and dias_redondeados <= 30:
                tope_min_51 = smmlv
                semanas_51 = 4

        # Método simplificado (wizard original)
        ibc_base = salarial + vacaciones + ausencias
        remuneracion_total = ibc_base + no_salarial
        tope_40 = remuneracion_total * 0.4 if remuneracion_total > 0 else 0
        excedente_40 = max(0, no_salarial - tope_40)
        ibc_40 = ibc_base + excedente_40

        # Método seguridad social (más preciso)
        ibc_ss = audit_data.get('ibc_seguridad_social', ibc_40)

        # Topes - usar logica especial para cotizante 51
        if es_cotizante_51:
            tope_min = tope_min_51
        else:
            tope_min = (smmlv / DAYS_MONTH) * dias_efectivos if smmlv else 0
        tope_max = smmlv * 25 if smmlv else float('inf')

        # IBC final
        ibc_final = max(tope_min, min(ibc_40, tope_max))
        ibc_final_ss = max(tope_min, min(ibc_ss, tope_max))

        # Ajuste salario integral
        porc_integral = annual_params.porc_integral_salary if annual_params and hasattr(annual_params, 'porc_integral_salary') else 70
        if contract.modality_salary == 'integral':
            ibc_final = ibc_final * (porc_integral / 100)
            ibc_final_ss = ibc_final_ss

        return {
            'ibc_base': ibc_base,
            'tope_40': tope_40,
            'excedente_40': excedente_40,
            'ibc_40': ibc_40,
            'ibc_ss': ibc_ss,
            'tope_min': tope_min,
            'tope_max': tope_max,
            'ibc_final': ibc_final,
            'ibc_final_ss': ibc_final_ss,
            'dias_efectivos': dias_efectivos,
            'value_base': audit_data.get('value_base', 0),
            'value_base_no_dev': audit_data.get('value_base_no_dev', 0),
            'base_40': audit_data.get('base_40', 0),
            'news_value': audit_data.get('news_value', 0),
            'es_integral': contract.modality_salary == 'integral',
            'porc_integral': porc_integral,
            'es_cotizante_51': es_cotizante_51,
            'tope_min_51': tope_min_51,
            'semanas_51': semanas_51,
            'dias_51_esta_nomina': dias_51_esta_nomina,
            'dias_51_otras_nominas': dias_51_otras_nominas,
            'dias_51_total_mes': dias_51_total_mes,
        }

    def _calculate_social_security(self, ibc_calc, audit_data, contract, employee, annual_params):
        """Calcula los aportes de seguridad social simulados segun reglas PILA.

        Reglas PILA aplicadas (Resolucion 2388 de 2016):
        - SLN: Empleado no aporta, empresa aporta tarifa completa a pension (12% o 16%)
        - IGE: No parafiscales, No ARL durante incapacidad
        - IRL: ARL paga, descuento max 99% del aporte
        - VAC/LR: Aporta normal sobre ultimo salario
        - Cotizante 51: IBC por semanas, ARL sobre 30 dias SMMLV
        - FSP en SLN: Solo si tarifa completa pension
        """
        ibc = ibc_calc['ibc_final_ss']
        smmlv = annual_params.smmlv_monthly if annual_params else 0

        # Verificar si es aprendiz
        es_aprendiz = contract.contract_type == 'aprendizaje' if hasattr(contract, 'contract_type') else False

        # Verificar si es Cotizante 51 (tiempo parcial)
        es_cotizante_51 = ibc_calc.get('es_cotizante_51', False)

        # Verificar exoneracion Ley 1607
        exonerado_1607 = employee.company_id.exonerated_law_1607 if hasattr(employee.company_id, 'exonerated_law_1607') else False
        sueldo = contract.wage or 0

        # Info de quincenas
        es_quincena = audit_data.get('es_quincena', False)
        es_primera_quincena = audit_data.get('es_primera_quincena', False)
        es_segunda_quincena = audit_data.get('es_segunda_quincena', False)
        dias_periodo = audit_data.get('dias_periodo', 30)

        # Dias de novedades
        dias_sln = audit_data.get('dias_ausencia_no_remunerada', 0)
        dias_ige = audit_data.get('dias_incapacidad_eps', 0)
        dias_irl = audit_data.get('dias_accidente_trabajo', 0)
        dias_vac = audit_data.get('dias_vacaciones', 0)
        dias_lr = audit_data.get('dias_licencia_remunerada', 0)
        dias_lma = audit_data.get('dias_maternidad', 0)

        # Porcentajes desde parametros anuales
        porc_salud_emp = annual_params.value_porc_health_employee if annual_params and hasattr(annual_params, 'value_porc_health_employee') else 4
        porc_salud_cia = annual_params.value_porc_health_company if annual_params and hasattr(annual_params, 'value_porc_health_company') else 8.5
        porc_pension_emp = annual_params.value_porc_pension_employee if annual_params and hasattr(annual_params, 'value_porc_pension_employee') else 4
        porc_pension_cia = annual_params.value_porc_pension_company if annual_params and hasattr(annual_params, 'value_porc_pension_company') else 12
        porc_caja = annual_params.value_porc_compensation_box_company if annual_params and hasattr(annual_params, 'value_porc_compensation_box_company') else 4
        porc_sena = annual_params.value_porc_sena_company if annual_params and hasattr(annual_params, 'value_porc_sena_company') else 2
        porc_icbf = annual_params.value_porc_icbf_company if annual_params and hasattr(annual_params, 'value_porc_icbf_company') else 3

        # Porcentaje ARL desde contrato
        porc_arl = contract.risk_id.percent if hasattr(contract, 'risk_id') and contract.risk_id else 0.522

        # Verificar naturaleza juridica (publica/privada) para reglas SLN
        es_empresa_publica = False
        if hasattr(employee.company_id, 'legal_nature'):
            es_empresa_publica = employee.company_id.legal_nature == 'public'

        # Buscar parametrizacion especial del cotizante
        tarifa_especial_pension = 'normal'
        tarifa_especial_salud = 'normal'
        porc_subsidio_pension = 0
        param_cotizante = None

        tipo_coti = employee.tipo_coti_id if hasattr(employee, 'tipo_coti_id') else None
        subtipo_coti = employee.subtipo_coti_id if hasattr(employee, 'subtipo_coti_id') else None

        if tipo_coti or subtipo_coti:
            domain = []
            if tipo_coti:
                domain.append(('type_of_contributor', '=', tipo_coti.id))
            if subtipo_coti:
                domain.append(('contributor_subtype', '=', subtipo_coti.id))

            param_cotizante = self.env['hr.parameterization.of.contributors'].search(domain, limit=1)

            if param_cotizante:
                tarifa_especial_pension = param_cotizante.tarifa_especial_pension or 'normal'
                tarifa_especial_salud = param_cotizante.tarifa_especial_salud or 'normal'
                porc_subsidio_pension = param_cotizante.porc_subsidio_pension or 0

        # Aplicar tarifas especiales de pension segun tipo
        porc_pension_total_especial = porc_pension_emp + porc_pension_cia  # 16% por defecto
        nota_tarifa_especial = ''

        if tarifa_especial_pension == 'alto_riesgo':
            porc_pension_total_especial = annual_params.value_porc_pension_alto_riesgo if hasattr(annual_params, 'value_porc_pension_alto_riesgo') else 26.0
            # En alto riesgo: empleado 4%, empresa 22% (10% adicional)
            porc_pension_emp = 4.0
            porc_pension_cia = porc_pension_total_especial - 4.0
            nota_tarifa_especial = f'Alto Riesgo: Tarifa {porc_pension_total_especial}% (Dec. 2090/2003)'
        elif tarifa_especial_pension == 'congresista':
            porc_pension_total_especial = annual_params.value_porc_pension_congresistas if hasattr(annual_params, 'value_porc_pension_congresistas') else 25.5
            porc_pension_emp = 4.0
            porc_pension_cia = porc_pension_total_especial - 4.0
            nota_tarifa_especial = f'Congresista: Tarifa {porc_pension_total_especial}%'
        elif tarifa_especial_pension == 'cti':
            porc_pension_total_especial = annual_params.value_porc_pension_cti if hasattr(annual_params, 'value_porc_pension_cti') else 35.0
            porc_pension_emp = 4.0
            porc_pension_cia = porc_pension_total_especial - 4.0
            nota_tarifa_especial = f'CTI: Tarifa {porc_pension_total_especial}%'
        elif tarifa_especial_pension == 'aviador':
            porc_pension_total_especial = annual_params.value_porc_pension_aviadores if hasattr(annual_params, 'value_porc_pension_aviadores') else 21.0
            porc_pension_emp = 4.0
            porc_pension_cia = porc_pension_total_especial - 4.0
            nota_tarifa_especial = f'Aviador Civil: Tarifa {porc_pension_total_especial}% (CAXDAC)'
        elif tarifa_especial_pension == 'psap':
            # PSAP: El beneficiario paga un porcentaje menor, el resto es subsidio
            porc_pension_emp = porc_subsidio_pension if porc_subsidio_pension > 0 else 4.0
            porc_pension_cia = 16.0 - porc_pension_emp  # El subsidio cubre el resto
            nota_tarifa_especial = f'PSAP: Beneficiario {porc_pension_emp}%, Subsidio {porc_pension_cia}%'

        # Aplicar tarifas especiales de salud (pensionados)
        nota_tarifa_salud = ''
        if tarifa_especial_salud == 'pensionado_1smmlv':
            porc_salud_emp = 4.0
            porc_salud_cia = 0
            nota_tarifa_salud = 'Pensionado <= 1 SMMLV: Tarifa 4% (Ley 2294/2023)'
        elif tarifa_especial_salud == 'pensionado_3smmlv':
            porc_salud_emp = 10.0
            porc_salud_cia = 0
            nota_tarifa_salud = 'Pensionado 1-3 SMMLV: Tarifa 10%'
        elif tarifa_especial_salud == 'pensionado_mas3smmlv':
            porc_salud_emp = 12.0
            porc_salud_cia = 0
            nota_tarifa_salud = 'Pensionado > 3 SMMLV: Tarifa 12%'

        result = {
            'ibc': ibc,
            'es_aprendiz': es_aprendiz,
            'es_cotizante_51': es_cotizante_51,
            'exonerado_1607': exonerado_1607,
            'es_quincena': es_quincena,
            'es_primera_quincena': es_primera_quincena,
            'es_segunda_quincena': es_segunda_quincena,
            'dias_periodo': dias_periodo,
            'dias_sln': dias_sln,
            'dias_ige': dias_ige,
            'dias_irl': dias_irl,
            'tiene_novedad_ausentismo': (dias_sln + dias_ige + dias_irl + dias_lma) > 0,
            'tarifa_especial_pension': tarifa_especial_pension,
            'tarifa_especial_salud': tarifa_especial_salud,
            'nota_tarifa_especial': nota_tarifa_especial,
            'nota_tarifa_salud': nota_tarifa_salud,
        }

        # =====================================================================
        # SALUD - Reglas PILA
        # =====================================================================
        # Cotizante 51: NO aporta a salud (solo pension, ARL, caja)
        # SLN: Empleado NO aporta. Empresa aporta si no es exonerada.
        #      Si exonerada Ley 1607: tarifa 0% (Resolucion 454/2020)
        # IGE/IRL/LMA: Aporta normal
        if es_cotizante_51:
            # Cotizante 51 no aporta a salud
            result['salud_empleado'] = 0
            result['salud_empresa'] = 0
            result['porc_salud_emp'] = 0
            result['porc_salud_cia'] = 0
            result['nota_salud'] = 'Cotizante 51 no aporta a Salud'
        elif es_aprendiz:
            result['salud_empleado'] = 0
            result['salud_empresa'] = roundup100(ibc * (porc_salud_emp + porc_salud_cia) / 100)
            result['porc_salud_emp'] = 0
            result['porc_salud_cia'] = porc_salud_emp + porc_salud_cia
            result['nota_salud'] = 'Aprendiz: empresa asume todo'
        elif dias_sln > 0:
            # SLN: Empleado no aporta, empresa aporta su parte
            result['salud_empleado'] = 0
            result['porc_salud_emp'] = 0
            if exonerado_1607 and sueldo < smmlv * 10:
                # Exonerado en SLN: tarifa 0% segun Res. 454/2020
                result['salud_empresa'] = 0
                result['porc_salud_cia'] = 0
                result['nota_salud'] = 'SLN + Exonerado Ley 1607: tarifa 0%'
            else:
                result['salud_empresa'] = roundup100(ibc * porc_salud_cia / 100)
                result['porc_salud_cia'] = porc_salud_cia
                result['nota_salud'] = 'SLN: solo aporte empresa'
        else:
            # Normal
            result['salud_empleado'] = roundup100(ibc * porc_salud_emp / 100)
            result['porc_salud_emp'] = porc_salud_emp
            if not exonerado_1607 or (exonerado_1607 and sueldo >= smmlv * 10):
                result['salud_empresa'] = roundup100(ibc * porc_salud_cia / 100)
                result['porc_salud_cia'] = porc_salud_cia
            else:
                result['salud_empresa'] = 0
                result['porc_salud_cia'] = 0
            result['nota_salud'] = ''

        result['salud_total'] = result['salud_empleado'] + result['salud_empresa']

        # =====================================================================
        # PENSION - Reglas PILA
        # =====================================================================
        # SLN: Res. 3016/2017 - Tarifas validas: 12% o 16% (privadas)
        #      Empresas publicas: 75% de tarifa total
        #      Empleado NO aporta, empresa asume tarifa completa
        # Cotizante 51: Aporta normal sobre IBC calculado por semanas
        subtipo_no_cotiza = False
        if hasattr(employee, 'subtipo_coti_id') and employee.subtipo_coti_id:
            subtipo_no_cotiza = employee.subtipo_coti_id.not_contribute_pension if hasattr(employee.subtipo_coti_id, 'not_contribute_pension') else False

        if es_aprendiz or subtipo_no_cotiza:
            result['pension_empleado'] = 0
            result['pension_empresa'] = 0
            result['porc_pension_emp'] = 0
            result['porc_pension_cia'] = 0
            result['nota_pension'] = 'No cotiza a pension'
        elif dias_sln > 0:
            # SLN: Empleado no aporta. Empresa asume tarifa 12% o 16%
            # Res. 3016/2017: Solo 12% o 16% validas en SLN
            result['pension_empleado'] = 0
            result['porc_pension_emp'] = 0
            if es_empresa_publica:
                # Publica: 75% de tarifa total (12% del 16% = 12%)
                tarifa_sln = (porc_pension_emp + porc_pension_cia) * 0.75
                result['pension_empresa'] = roundup100(ibc * tarifa_sln / 100)
                result['porc_pension_cia'] = tarifa_sln
                result['nota_pension'] = f'SLN Publica: 75% tarifa = {tarifa_sln}%'
            else:
                # Privada: empresa asume 12% o 16% (tarifa completa)
                tarifa_sln = porc_pension_emp + porc_pension_cia  # 16%
                result['pension_empresa'] = roundup100(ibc * tarifa_sln / 100)
                result['porc_pension_cia'] = tarifa_sln
                result['nota_pension'] = f'SLN: empresa asume {tarifa_sln}%'
        else:
            # Normal
            result['pension_empleado'] = roundup100(ibc * porc_pension_emp / 100)
            result['pension_empresa'] = roundup100(ibc * porc_pension_cia / 100)
            result['porc_pension_emp'] = porc_pension_emp
            result['porc_pension_cia'] = porc_pension_cia
            result['nota_pension'] = ''

        result['pension_total'] = result['pension_empleado'] + result['pension_empresa']

        # =====================================================================
        # FONDO SOLIDARIDAD PENSIONAL - Reglas PILA
        # =====================================================================
        # FSP en SLN (Memorando MinSalud Oct 2013):
        # - Si linea SLN tiene tarifa COMPLETA pension: SI aporta FSP
        # - Si linea SLN tiene tarifa EMPLEADOR: NO aporta FSP sobre dias SLN
        smmlv_ratio = ibc / smmlv if smmlv > 0 else 0
        porc_fondo = 0

        if smmlv_ratio > 4 and smmlv_ratio < 16:
            porc_fondo = 1
        elif smmlv_ratio >= 16 and smmlv_ratio <= 17:
            porc_fondo = 1.2
        elif smmlv_ratio > 17 and smmlv_ratio <= 18:
            porc_fondo = 1.4
        elif smmlv_ratio > 18 and smmlv_ratio <= 19:
            porc_fondo = 1.6
        elif smmlv_ratio > 19 and smmlv_ratio <= 20:
            porc_fondo = 1.8
        elif smmlv_ratio > 20:
            porc_fondo = 2

        result['porc_fondo'] = porc_fondo
        result['smmlv_ratio'] = smmlv_ratio

        # En SLN con tarifa empleador, no FSP
        aplica_fsp = porc_fondo > 0
        if dias_sln > 0 and result['porc_pension_emp'] == 0:
            # SLN sin aporte empleado = no FSP segun UGPP
            aplica_fsp = False
            result['nota_fsp'] = 'SLN: No FSP (tarifa empleador)'
        else:
            result['nota_fsp'] = ''

        if aplica_fsp:
            if contract.modality_salary == 'integral' and porc_fondo == 2:
                result['fondo_solidaridad'] = roundup100(ibc * 0.005)
                result['fondo_subsistencia'] = roundup100(ibc * 0.015)
            else:
                porc_cada_uno = (porc_fondo / 100) / 2
                result['fondo_solidaridad'] = roundup100(ibc * porc_cada_uno)
                result['fondo_subsistencia'] = roundup100(ibc * porc_cada_uno)
        else:
            result['fondo_solidaridad'] = 0
            result['fondo_subsistencia'] = 0

        result['fondo_total'] = result['fondo_solidaridad'] + result['fondo_subsistencia']

        # =====================================================================
        # ARL - Reglas PILA
        # =====================================================================
        # IGE: No ARL (Decreto 1772/1994 Art. 19)
        # IRL: ARL paga. Descuento max 99% del aporte
        # SLN: No ARL
        # VAC/LR: No ARL
        # Cotizante 51: ARL siempre sobre 30 dias SMMLV (Res. 5094 Art. 4)
        dias_sin_arl = dias_ige + dias_sln + dias_irl + dias_vac + dias_lr + dias_lma

        if es_cotizante_51:
            # Cotizante 51: ARL sobre SMMLV completo (30 dias)
            result['arl'] = roundup100(smmlv * porc_arl / 100)
            result['nota_arl'] = 'Cotizante 51: ARL sobre SMMLV 30 dias'
        elif dias_sin_arl > 0:
            result['arl'] = 0
            if dias_ige > 0:
                result['nota_arl'] = 'IGE: No ARL (Dec. 1772/1994)'
            elif dias_sln > 0:
                result['nota_arl'] = 'SLN: No ARL'
            elif dias_irl > 0:
                result['nota_arl'] = 'IRL: ARL paga incapacidad'
            else:
                result['nota_arl'] = 'Novedad: No ARL'
        else:
            result['arl'] = roundup100(ibc * porc_arl / 100)
            result['nota_arl'] = ''
        result['porc_arl'] = porc_arl

        # =====================================================================
        # PARAFISCALES - Reglas PILA
        # =====================================================================
        # IGE: No parafiscales (Concepto 17079/2005)
        # SLN: No parafiscales
        # IRL: No parafiscales
        # LMA: No parafiscales
        # VAC/LR: SI parafiscales
        # Cotizante 51: Solo Caja de Compensacion
        dias_sin_parafiscales = dias_ige + dias_sln + dias_irl + dias_lma

        if es_aprendiz:
            result['caja'] = 0
            result['sena'] = 0
            result['icbf'] = 0
            result['nota_parafiscales'] = 'Aprendiz: No parafiscales'
        elif es_cotizante_51:
            # Cotizante 51: Solo caja de compensacion
            result['caja'] = roundup100(ibc * porc_caja / 100)
            result['sena'] = 0
            result['icbf'] = 0
            result['nota_parafiscales'] = 'Cotizante 51: Solo Caja'
        elif dias_sin_parafiscales > 0:
            result['caja'] = 0
            result['sena'] = 0
            result['icbf'] = 0
            if dias_ige > 0:
                result['nota_parafiscales'] = 'IGE: No parafiscales (Concepto 17079/2005)'
            elif dias_sln > 0:
                result['nota_parafiscales'] = 'SLN: No parafiscales'
            else:
                result['nota_parafiscales'] = 'Novedad: No parafiscales'
        else:
            # Normal - VAC y LR si aportan parafiscales
            result['caja'] = roundup100(ibc * porc_caja / 100)
            if not exonerado_1607 or (exonerado_1607 and sueldo >= smmlv * 10):
                result['sena'] = roundup100(ibc * porc_sena / 100)
                result['icbf'] = roundup100(ibc * porc_icbf / 100)
            else:
                result['sena'] = 0
                result['icbf'] = 0
            result['nota_parafiscales'] = ''

        result['porc_caja'] = porc_caja
        result['porc_sena'] = porc_sena
        result['porc_icbf'] = porc_icbf
        result['parafiscales_total'] = result['caja'] + result['sena'] + result['icbf']

        # =====================================================================
        # TOTALES
        # =====================================================================
        result['total_empleado'] = result['salud_empleado'] + result['pension_empleado'] + result['fondo_total']
        result['total_empresa'] = (result['salud_empresa'] + result['pension_empresa'] +
                                   result['arl'] + result['parafiscales_total'])
        result['total_general'] = result['total_empleado'] + result['total_empresa']

        # COMPARACIÓN CON NÓMINA
        # En quincenas, los aportes pueden cobrarse:
        # - 50/50: mitad en cada quincena
        # - 100/0: todo en primera quincena
        # - 0/100: todo en segunda quincena
        # Detectamos automáticamente el patrón comparando valores
        if es_quincena:
            # Valores mensuales calculados
            salud_mes = result['salud_empleado']
            pension_mes = result['pension_empleado']
            solidaridad_mes = result['fondo_solidaridad']
            subsistencia_mes = result['fondo_subsistencia']

            # Valores en nómina
            salud_nomina = audit_data['nomina_salud_empleado']
            pension_nomina = audit_data['nomina_pension_empleado']

            # Detectar patrón de cobro: si el valor en nómina es cercano al 100% del mes,
            # entonces la empresa cobra todo en esta quincena
            tolerancia = 500  # tolerancia de $500 por redondeos
            cobra_100_pct = (
                abs(salud_nomina - salud_mes) < tolerancia or
                abs(pension_nomina - pension_mes) < tolerancia
            )

            if cobra_100_pct:
                # Empresa cobra 100% en esta quincena
                result['patron_cobro_ss'] = '100%'
                result['salud_esperado_periodo'] = salud_mes
                result['pension_esperado_periodo'] = pension_mes
                result['solidaridad_esperado_periodo'] = solidaridad_mes
                result['subsistencia_esperado_periodo'] = subsistencia_mes
            else:
                # Empresa cobra 50% por quincena
                result['patron_cobro_ss'] = '50%'
                result['salud_esperado_periodo'] = salud_mes / 2
                result['pension_esperado_periodo'] = pension_mes / 2
                result['solidaridad_esperado_periodo'] = solidaridad_mes / 2
                result['subsistencia_esperado_periodo'] = subsistencia_mes / 2

            # Comparar contra valor esperado del periodo
            result['dif_salud'] = result['salud_esperado_periodo'] - audit_data['nomina_salud_empleado']
            result['dif_pension'] = result['pension_esperado_periodo'] - audit_data['nomina_pension_empleado']
            result['dif_solidaridad'] = result['solidaridad_esperado_periodo'] - audit_data['nomina_fondo_solidaridad']
            result['dif_subsistencia'] = result['subsistencia_esperado_periodo'] - audit_data['nomina_fondo_subsistencia']
        else:
            # Mes completo - comparacion normal
            result['patron_cobro_ss'] = '100%'
            result['salud_esperado_periodo'] = result['salud_empleado']
            result['pension_esperado_periodo'] = result['pension_empleado']
            result['solidaridad_esperado_periodo'] = result['fondo_solidaridad']
            result['subsistencia_esperado_periodo'] = result['fondo_subsistencia']

            result['dif_salud'] = result['salud_empleado'] - audit_data['nomina_salud_empleado']
            result['dif_pension'] = result['pension_empleado'] - audit_data['nomina_pension_empleado']
            result['dif_solidaridad'] = result['fondo_solidaridad'] - audit_data['nomina_fondo_solidaridad']
            result['dif_subsistencia'] = result['fondo_subsistencia'] - audit_data['nomina_fondo_subsistencia']

        result['dif_total'] = (result['dif_salud'] + result['dif_pension'] +
                              result['dif_solidaridad'] + result['dif_subsistencia'])

        return result

    def _generate_audit_html(self, slip, contract, employee, audit_data,
                             ibc_calc, ss_calc, ibc_registered, difference, smmlv, annual_params):
        """Genera el HTML del reporte de auditoría completo."""
        html = []

        # Obtener tipo y subtipo de cotizante
        tipo_coti = employee.tipo_coti_id.name if hasattr(employee, 'tipo_coti_id') and employee.tipo_coti_id else 'No configurado'
        tipo_coti_code = employee.tipo_coti_id.code if hasattr(employee, 'tipo_coti_id') and employee.tipo_coti_id else ''
        subtipo_coti = employee.subtipo_coti_id.name if hasattr(employee, 'subtipo_coti_id') and employee.subtipo_coti_id else 'No configurado'
        subtipo_coti_code = employee.subtipo_coti_id.code if hasattr(employee, 'subtipo_coti_id') and employee.subtipo_coti_id else ''
        not_contribute_pension = employee.subtipo_coti_id.not_contribute_pension if hasattr(employee, 'subtipo_coti_id') and employee.subtipo_coti_id and hasattr(employee.subtipo_coti_id, 'not_contribute_pension') else False

        # Determinar si es aprendiz
        es_aprendiz = tipo_coti_code in ('12', '19', '20', '21')

        # Configuracion Ley 1393
        include_absences_1393 = audit_data.get('include_absences_1393', False)

        # Info del periodo
        es_quincena = audit_data.get('es_quincena', False)
        es_primera_quincena = audit_data.get('es_primera_quincena', False)
        es_segunda_quincena = audit_data.get('es_segunda_quincena', False)
        dias_periodo = audit_data.get('dias_periodo', 30)

        if es_primera_quincena:
            tipo_periodo = "1ra Quincena"
        elif es_segunda_quincena:
            tipo_periodo = "2da Quincena"
        elif es_quincena:
            tipo_periodo = f"Quincena ({dias_periodo} dias)"
        else:
            tipo_periodo = "Mes Completo"

        # Encabezado
        html.append(f'''
        <div style="font-family: Arial, sans-serif; padding: 15px;">
            <h2 style="color: #2c5282; border-bottom: 2px solid #2c5282; padding-bottom: 10px;">
                Auditoria Completa de IBC y Seguridad Social - {employee.name}
            </h2>
            <div style="display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px;">
                <div><strong>Nomina:</strong> {slip.number}</div>
                <div><strong>Periodo:</strong> {slip.date_from.strftime("%d/%m/%Y")} - {slip.date_to.strftime("%d/%m/%Y")}</div>
                <div><strong>Tipo Periodo:</strong> <span style="color: {'#f59e0b' if es_quincena else '#16a34a'}; font-weight: bold;">{tipo_periodo}</span></div>
                <div><strong>Contrato:</strong> {contract.name}</div>
                <div><strong>Salario:</strong> ${contract.wage:,.0f}</div>
                <div><strong>Tipo Salario:</strong> {"Integral" if ibc_calc['es_integral'] else "Ordinario"}</div>
                <div><strong>SMMLV:</strong> ${smmlv:,.0f}</div>
            </div>

            <!-- Seccion Tipo y Subtipo Cotizante -->
            <div style="background: #e0f2fe; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #0284c7;">
                <h3 style="color: #0369a1; margin-bottom: 10px;">Configuracion del Cotizante</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Tipo Cotizante</div>
                        <div style="font-weight: bold; color: #0369a1;">[{tipo_coti_code}] {tipo_coti}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Subtipo Cotizante</div>
                        <div style="font-weight: bold; color: #0369a1;">[{subtipo_coti_code}] {subtipo_coti}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Aporta Pension</div>
                        <div style="font-weight: bold; color: {'#dc2626' if not_contribute_pension else '#16a34a'};">
                            {'NO - Exento por subtipo' if not_contribute_pension else 'SI'}
                        </div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Es Aprendiz</div>
                        <div style="font-weight: bold; color: {'#f59e0b' if es_aprendiz else '#16a34a'};">
                            {'SI - Tipo {}'.format(tipo_coti_code) if es_aprendiz else 'NO'}
                        </div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Ley 1393 - Ausencias en 40%</div>
                        <div style="font-weight: bold; color: {'#f59e0b' if include_absences_1393 else '#16a34a'};">
                            {'SI - Incluidas' if include_absences_1393 else 'NO - UGPP (excluidas)'}
                        </div>
                    </div>
                </div>
            </div>
        ''')

        # Seccion especial Cotizante 51 (Tiempo Parcial)
        es_cotizante_51 = ibc_calc.get('es_cotizante_51', False)
        if es_cotizante_51:
            semanas_51 = ibc_calc.get('semanas_51', 0)
            tope_min_51 = ibc_calc.get('tope_min_51', 0)
            dias_51_esta_nomina = ibc_calc.get('dias_51_esta_nomina', 0)
            dias_51_otras_nominas = ibc_calc.get('dias_51_otras_nominas', 0)
            dias_51_total_mes = ibc_calc.get('dias_51_total_mes', 0)
            html.append(f'''
            <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #f59e0b;">
                <h3 style="color: #92400e; margin-bottom: 10px;">Cotizante 51 - Trabajador Tiempo Parcial</h3>
                <p style="font-size: 12px; color: #78350f; margin-bottom: 15px;">
                    El IBC minimo se calcula por semanas segun la Resolucion 2388 de 2016.
                    <a href="http://aportesenlinea.custhelp.com/app/answers/detail/a_id/464" target="_blank" style="color: #b45309;">Ver documentacion</a>
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px;">
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Dias Esta Nomina</div>
                        <div style="font-size: 20px; font-weight: bold; color: #92400e;">{dias_51_esta_nomina}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Dias Otras Nominas Mes</div>
                        <div style="font-size: 20px; font-weight: bold; color: #92400e;">{dias_51_otras_nominas}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Total Dias Mes</div>
                        <div style="font-size: 20px; font-weight: bold; color: #b45309;">{dias_51_total_mes}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Semanas Cotizadas</div>
                        <div style="font-size: 20px; font-weight: bold; color: #92400e;">{semanas_51}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">IBC Minimo (Tabla 51)</div>
                        <div style="font-size: 20px; font-weight: bold; color: #92400e;">${tope_min_51:,.0f}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 4px;">
                        <div style="font-size: 11px; color: #64748b;">Formula</div>
                        <div style="font-weight: bold; color: #92400e;">SMMLV / 4 x {semanas_51} sem</div>
                    </div>
                </div>
                <div style="margin-top: 15px; background: white; padding: 10px; border-radius: 4px;">
                    <div style="font-size: 11px; color: #64748b; margin-bottom: 5px;">Tabla de Referencia</div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                        <tr style="background: #fef3c7;">
                            <th style="padding: 5px; border: 1px solid #fcd34d;">Dias</th>
                            <th style="padding: 5px; border: 1px solid #fcd34d;">Semanas</th>
                            <th style="padding: 5px; border: 1px solid #fcd34d;">IBC Minimo</th>
                        </tr>
                        <tr style="{'background: #fde68a; font-weight: bold;' if semanas_51 == 1 else ''}">
                            <td style="padding: 5px; border: 1px solid #fcd34d;">1 - 7</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: center;">1</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: right;">${smmlv/4:,.0f}</td>
                        </tr>
                        <tr style="{'background: #fde68a; font-weight: bold;' if semanas_51 == 2 else ''}">
                            <td style="padding: 5px; border: 1px solid #fcd34d;">8 - 14</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: center;">2</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: right;">${smmlv/4*2:,.0f}</td>
                        </tr>
                        <tr style="{'background: #fde68a; font-weight: bold;' if semanas_51 == 3 else ''}">
                            <td style="padding: 5px; border: 1px solid #fcd34d;">15 - 21</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: center;">3</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: right;">${smmlv/4*3:,.0f}</td>
                        </tr>
                        <tr style="{'background: #fde68a; font-weight: bold;' if semanas_51 == 4 else ''}">
                            <td style="padding: 5px; border: 1px solid #fcd34d;">22 - 30</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: center;">4</td>
                            <td style="padding: 5px; border: 1px solid #fcd34d; text-align: right;">${smmlv:,.0f}</td>
                        </tr>
                    </table>
                </div>
            </div>
            ''')

        # Panel de resumen de diferencias
        has_ibc_diff = abs(difference) > 1
        has_ss_diff = abs(ss_calc['dif_total']) > 100

        if has_ibc_diff or has_ss_diff:
            html.append(f'''
            <div style="background: #fed7d7; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0; color: #c53030;">ALERTA - HAY DIFERENCIAS</h3>
            ''')
        else:
            html.append(f'''
            <div style="background: #c6f6d5; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0; color: #38a169;">OK - SIN DIFERENCIAS SIGNIFICATIVAS</h3>
            ''')

        html.append(f'''
                <div style="display: flex; flex-wrap: wrap; gap: 30px; margin-top: 10px;">
                    <div>
                        <div style="font-size: 12px; color: #666;">IBC Calculado</div>
                        <div style="font-size: 18px; font-weight: bold;">${ibc_calc['ibc_final']:,.0f}</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; color: #666;">IBC en Nómina</div>
                        <div style="font-size: 18px; font-weight: bold;">${ibc_registered:,.0f}</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; color: #666;">Diferencia IBC</div>
                        <div style="font-size: 18px; font-weight: bold; color: {'#c53030' if has_ibc_diff else '#38a169'};">${difference:,.0f}</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; color: #666;">Dif. Aportes Empleado</div>
                        <div style="font-size: 18px; font-weight: bold; color: {'#c53030' if has_ss_diff else '#38a169'};">${ss_calc['dif_total']:,.0f}</div>
                    </div>
                </div>
            </div>
        ''')

        # Conceptos salariales
        html.append(self._generate_concept_table(
            'Conceptos Salariales (Base SS)',
            audit_data['conceptos_salariales'],
            audit_data['total_salarial'],
            '#4299e1'
        ))

        html.append(self._generate_concept_table(
            'Conceptos No Salariales',
            audit_data['conceptos_no_salariales'],
            audit_data['total_no_salarial'],
            '#ed8936'
        ))

        if audit_data['conceptos_vacaciones']:
            html.append(self._generate_concept_table(
                'Vacaciones',
                audit_data['conceptos_vacaciones'],
                audit_data['total_vacaciones'],
                '#48bb78'
            ))

        if audit_data['conceptos_ausencias']:
            html.append(self._generate_concept_table(
                'Ausencias/Novedades',
                audit_data['conceptos_ausencias'],
                audit_data['total_ausencias'],
                '#9f7aea'
            ))

        # Seccion Ley 1393 con detalle de tipos PILA
        ley_1393 = audit_data.get('ley_1393_detalle', {})
        if ley_1393:
            config_text = "UGPP (ausencias excluidas del 40%)" if not ley_1393.get('include_absences') else "Ausencias incluidas en 40%"
            html.append(f'''
            <div style="margin-top: 20px; background: #fffbeb; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                <h3 style="color: #92400e; margin-bottom: 15px;">Ley 1393 - Calculo del Limite 40%</h3>
                <div style="margin-bottom: 10px; padding: 8px; background: #fef3c7; border-radius: 4px;">
                    <strong>Configuracion:</strong> {config_text}
                </div>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #fef3c7;">
                        <td style="padding: 8px; border: 1px solid #fcd34d;"><strong>Concepto</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;"><strong>Valor</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;"><strong>Descripcion</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Base Salarial</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('base_salarial', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Devengos salariales sin ausencias</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Ausencias Excluidas (IGE,IRL,LMA,VAC,SLN)</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('ausencias_excluidas', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">NO participan en limite 40% segun UGPP</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Ausencias Incluidas (LR,LT)</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('ausencias_incluidas', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">SI participan en limite 40%</td>
                    </tr>
                    <tr style="background: #fef3c7;">
                        <td style="padding: 8px; border: 1px solid #fcd34d;"><strong>Base para Limite 40%</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;"><strong>${ley_1393.get('base_for_40', 0):,.0f}</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Segun configuracion empresa</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">+ Pagos No Salariales</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('no_salarial', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;"></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">= Total para Limite</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('total_for_limit', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;"></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Limite 40%</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;">${ley_1393.get('limite_40', 0):,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Total x 40%</td>
                    </tr>
                    <tr style="background: #fde68a;">
                        <td style="padding: 8px; border: 1px solid #fcd34d;"><strong>Exceso No Salarial</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d; text-align: right;"><strong>${ley_1393.get('exceso_no_salarial', 0):,.0f}</strong></td>
                        <td style="padding: 8px; border: 1px solid #fcd34d;">Se suma al IBC</td>
                    </tr>
                </table>
            </div>
            ''')

            # Mostrar ausencias por tipo PILA si hay
            if audit_data.get('conceptos_ausencias_excluidas') or audit_data.get('conceptos_ausencias_incluidas'):
                html.append('''
                <div style="margin-top: 15px; display: flex; gap: 20px; flex-wrap: wrap;">
                ''')

                if audit_data.get('conceptos_ausencias_excluidas'):
                    html.append('''
                    <div style="flex: 1; min-width: 300px;">
                        <h4 style="color: #dc2626;">Ausencias Excluidas del 40% (UGPP)</h4>
                        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                            <tr style="background: #fef2f2;">
                                <th style="padding: 6px; border: 1px solid #fca5a5;">Concepto</th>
                                <th style="padding: 6px; border: 1px solid #fca5a5;">Tipo PILA</th>
                                <th style="padding: 6px; border: 1px solid #fca5a5; text-align: right;">Valor</th>
                            </tr>
                    ''')
                    for aus in audit_data['conceptos_ausencias_excluidas']:
                        html.append(f'''
                            <tr>
                                <td style="padding: 6px; border: 1px solid #fca5a5;">{aus['name']}</td>
                                <td style="padding: 6px; border: 1px solid #fca5a5;">{aus.get('novelty_name', aus.get('novelty', 'N/A'))}</td>
                                <td style="padding: 6px; border: 1px solid #fca5a5; text-align: right;">${abs(aus['total']):,.0f}</td>
                            </tr>
                        ''')
                    html.append(f'''
                            <tr style="background: #fef2f2; font-weight: bold;">
                                <td colspan="2" style="padding: 6px; border: 1px solid #fca5a5;">Total Excluidas</td>
                                <td style="padding: 6px; border: 1px solid #fca5a5; text-align: right;">${audit_data['total_ausencias_excluidas']:,.0f}</td>
                            </tr>
                        </table>
                    </div>
                    ''')

                if audit_data.get('conceptos_ausencias_incluidas'):
                    html.append('''
                    <div style="flex: 1; min-width: 300px;">
                        <h4 style="color: #16a34a;">Ausencias Incluidas en 40%</h4>
                        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                            <tr style="background: #f0fdf4;">
                                <th style="padding: 6px; border: 1px solid #86efac;">Concepto</th>
                                <th style="padding: 6px; border: 1px solid #86efac;">Tipo PILA</th>
                                <th style="padding: 6px; border: 1px solid #86efac; text-align: right;">Valor</th>
                            </tr>
                    ''')
                    for aus in audit_data['conceptos_ausencias_incluidas']:
                        html.append(f'''
                            <tr>
                                <td style="padding: 6px; border: 1px solid #86efac;">{aus['name']}</td>
                                <td style="padding: 6px; border: 1px solid #86efac;">{aus.get('novelty_name', aus.get('novelty', 'N/A'))}</td>
                                <td style="padding: 6px; border: 1px solid #86efac; text-align: right;">${abs(aus['total']):,.0f}</td>
                            </tr>
                        ''')
                    html.append(f'''
                            <tr style="background: #f0fdf4; font-weight: bold;">
                                <td colspan="2" style="padding: 6px; border: 1px solid #86efac;">Total Incluidas</td>
                                <td style="padding: 6px; border: 1px solid #86efac; text-align: right;">${audit_data['total_ausencias_incluidas']:,.0f}</td>
                            </tr>
                        </table>
                    </div>
                    ''')

                html.append('</div>')

        # Cálculo del IBC paso a paso
        html.append(f'''
            <div style="margin-top: 20px; background: #f7fafc; padding: 15px; border-radius: 8px;">
                <h3 style="color: #2d3748; margin-bottom: 15px;">Cálculo del IBC (Método Seguridad Social)</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #edf2f7;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>Paso</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>Concepto</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;"><strong>Valor</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">1</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Devengos Salariales (DEV_SALARIAL)</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['value_base']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">2</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Devengos No Salariales (DEV_NO_SALARIAL)</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['value_base_no_dev']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">3</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Regla 40%: Excedente que suma al IBC</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['base_40']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">4</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">(-) Valor Novedades/Ausencias</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-${ibc_calc['news_value']:,.0f}</td>
                    </tr>
                    <tr style="background: #ebf8ff;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">5</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>= IBC Seguridad Social</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;"><strong>${ibc_calc['ibc_ss']:,.0f}</strong></td>
                    </tr>
        ''')

        if ibc_calc['es_integral']:
            html.append(f'''
                    <tr style="background: #faf5ff;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">6</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Ajuste Salario Integral ({ibc_calc['porc_integral']}%)</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['ibc_final_ss']:,.0f}</td>
                    </tr>
            ''')

        html.append(f'''
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">7</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Días efectivos laborados</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">{ibc_calc['dias_efectivos']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">8</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Tope mínimo = (SMMLV / 30) x Días</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['tope_min']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">9</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Tope máximo = 25 x SMMLV</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ibc_calc['tope_max']:,.0f}</td>
                    </tr>
                    <tr style="background: #c6f6d5;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">10</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>IBC FINAL</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-size: 16px;"><strong>${ibc_calc['ibc_final_ss']:,.0f}</strong></td>
                    </tr>
                </table>
            </div>
        ''')

        # Simulación de aportes de Seguridad Social
        # Agregar nota si es quincena
        nota_quincena = ""
        patron_cobro = ss_calc.get('patron_cobro_ss', '100%')
        if es_quincena:
            if patron_cobro == '100%':
                msg_patron = "La empresa cobra el 100% de los aportes en esta quincena."
            else:
                msg_patron = "Los aportes se dividen 50% en cada quincena."
            nota_quincena = f'''
                <div style="background: #fef3c7; padding: 10px; border-radius: 4px; margin-bottom: 10px; border-left: 3px solid #f59e0b;">
                    <strong style="color: #92400e;">Periodo: {tipo_periodo} (Cobro SS: {patron_cobro})</strong><br/>
                    <span style="font-size: 11px; color: #78350f;">
                        {msg_patron}
                    </span>
                </div>
            '''

        # Columna adicional para quincenas
        col_esperado_header = '<th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">Esperado Periodo</th>' if es_quincena else ''

        html.append(f'''
            <div style="margin-top: 20px; background: #fffaf0; padding: 15px; border-radius: 8px;">
                <h3 style="color: #744210; margin-bottom: 15px;">Simulación de Aportes de Seguridad Social</h3>
                {nota_quincena}
                <p style="font-size: 12px; color: #666; margin-bottom: 10px;">
                    IBC Base: ${ss_calc['ibc']:,.0f} |
                    Ratio SMMLV: {ss_calc['smmlv_ratio']:.2f} |
                    {'Exonerado Ley 1607' if ss_calc['exonerado_1607'] else 'No Exonerado'}
                    {' | APRENDIZ' if ss_calc['es_aprendiz'] else ''}
                </p>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <tr style="background: #744210; color: white;">
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: left;">Concepto</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">%</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">Empleado (Mes)</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">Empresa (Mes)</th>
                        {col_esperado_header}
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">En Nómina</th>
                        <th style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">Diferencia</th>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Salud (EPS)</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_salud_emp']}% / {ss_calc['porc_salud_cia']}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['salud_empleado']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['salud_empresa']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-weight: bold;">${:,.0f}</td>'.format(ss_calc.get('salud_esperado_periodo', 0)) if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${audit_data['nomina_salud_empleado']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; color: {'#c53030' if abs(ss_calc['dif_salud']) > 100 else '#38a169'};">${ss_calc['dif_salud']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Pensión (AFP)</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_pension_emp']}% / {ss_calc['porc_pension_cia']}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['pension_empleado']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['pension_empresa']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-weight: bold;">${:,.0f}</td>'.format(ss_calc.get('pension_esperado_periodo', 0)) if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${audit_data['nomina_pension_empleado']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; color: {'#c53030' if abs(ss_calc['dif_pension']) > 100 else '#38a169'};">${ss_calc['dif_pension']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Fondo Solidaridad</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_fondo']/2 if ss_calc['porc_fondo'] else 0}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['fondo_solidaridad']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-weight: bold;">${:,.0f}</td>'.format(ss_calc.get('solidaridad_esperado_periodo', 0)) if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${audit_data['nomina_fondo_solidaridad']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; color: {'#c53030' if abs(ss_calc['dif_solidaridad']) > 100 else '#38a169'};">${ss_calc['dif_solidaridad']:,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">Fondo Subsistencia</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_fondo']/2 if ss_calc['porc_fondo'] else 0}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['fondo_subsistencia']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-weight: bold;">${:,.0f}</td>'.format(ss_calc.get('subsistencia_esperado_periodo', 0)) if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${audit_data['nomina_fondo_subsistencia']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; color: {'#c53030' if abs(ss_calc['dif_subsistencia']) > 100 else '#38a169'};">${ss_calc['dif_subsistencia']:,.0f}</td>
                    </tr>
                    <tr style="background: #feebc8;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>ARL</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_arl']:.3f}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['arl']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>' if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                    </tr>
                    <tr style="background: #e2e8f0;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>Caja Compensación</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_caja']}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['caja']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>' if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                    </tr>
                    <tr style="background: #e2e8f0;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>SENA</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_sena']}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['sena']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>' if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                    </tr>
                    <tr style="background: #e2e8f0;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;"><strong>ICBF</strong></td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">{ss_calc['porc_icbf']}%</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['icbf']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>' if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                    </tr>
                    <tr style="background: #744210; color: white; font-weight: bold;">
                        <td style="padding: 8px; border: 1px solid #e2e8f0;">TOTALES</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: center;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['total_empleado']:,.0f}</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['total_empresa']:,.0f}</td>
                        {'<td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right; font-weight: bold;">${:,.0f}</td>'.format(ss_calc['total_empleado']/2) if es_quincena else ''}
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">-</td>
                        <td style="padding: 8px; border: 1px solid #e2e8f0; text-align: right;">${ss_calc['dif_total']:,.0f}</td>
                    </tr>
                </table>
        ''')

        # Notas PILA aplicadas (si hay novedades o tarifas especiales)
        notas_pila = []
        # Tarifas especiales primero
        if ss_calc.get('nota_tarifa_especial'):
            notas_pila.append(f"<strong>Tarifa Especial:</strong> {ss_calc['nota_tarifa_especial']}")
        if ss_calc.get('nota_tarifa_salud'):
            notas_pila.append(f"<strong>Tarifa Salud:</strong> {ss_calc['nota_tarifa_salud']}")
        # Notas por novedades
        if ss_calc.get('nota_salud'):
            notas_pila.append(f"<strong>Salud:</strong> {ss_calc['nota_salud']}")
        if ss_calc.get('nota_pension'):
            notas_pila.append(f"<strong>Pension:</strong> {ss_calc['nota_pension']}")
        if ss_calc.get('nota_fsp'):
            notas_pila.append(f"<strong>FSP:</strong> {ss_calc['nota_fsp']}")
        if ss_calc.get('nota_arl'):
            notas_pila.append(f"<strong>ARL:</strong> {ss_calc['nota_arl']}")
        if ss_calc.get('nota_parafiscales'):
            notas_pila.append(f"<strong>Parafiscales:</strong> {ss_calc['nota_parafiscales']}")

        if notas_pila:
            html.append('''
                <div style="margin-top: 10px; background: #fef3c7; padding: 10px; border-radius: 4px; border-left: 3px solid #f59e0b;">
                    <strong style="color: #92400e; font-size: 12px;">Reglas PILA Aplicadas (Res. 2388/2016):</strong>
                    <ul style="margin: 5px 0 0 0; padding-left: 20px; font-size: 11px; color: #78350f;">
            ''')
            for nota in notas_pila:
                html.append(f'<li>{nota}</li>')
            html.append('</ul></div>')

        html.append('</div>')
        html.append('')  # Cerrar div de SS

        # Resumen de días
        html.append(f'''
            <div style="margin-top: 20px; background: #f0fff4; padding: 15px; border-radius: 8px;">
                <h3 style="color: #276749; margin-bottom: 15px;">Resumen de Días</h3>
                <div style="display: flex; flex-wrap: wrap; gap: 15px;">
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Trabajados</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_trabajados']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Incapacidad EPS</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_incapacidad_eps']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Licencia No Rem.</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_ausencia_no_remunerada']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Licencia Rem.</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_licencia_remunerada']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Vacaciones</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_vacaciones']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Maternidad</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_maternidad']}</div>
                    </div>
                    <div style="background: white; padding: 10px; border-radius: 5px; min-width: 120px;">
                        <div style="font-size: 11px; color: #666;">Accidente Trabajo</div>
                        <div style="font-size: 20px; font-weight: bold;">{audit_data['dias_accidente_trabajo']}</div>
                    </div>
                </div>
            </div>
        ''')

        html.append('</div>')
        return ''.join(html)

    def _generate_concept_table(self, title, concepts, total, color):
        """Genera tabla HTML para un grupo de conceptos."""
        if not concepts:
            return ''

        html = f'''
        <div style="margin-top: 15px;">
            <h4 style="color: {color}; margin-bottom: 10px;">{title}</h4>
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <tr style="background: {color}20;">
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: left;">Código</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: left;">Concepto</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">Cantidad</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">Valor Unit.</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">Total</th>
                    <th style="padding: 6px; border: 1px solid #e2e8f0; text-align: center;">Base SS</th>
                </tr>
        '''

        for c in concepts:
            base_ss_icon = 'Si' if c.get('base_ss') else ''
            html += f'''
                <tr>
                    <td style="padding: 6px; border: 1px solid #e2e8f0;">{c['code']}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0;">{c['name']}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">{c['quantity']:.2f}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">${c['amount']:,.0f}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">${c['total']:,.0f}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; text-align: center;">{base_ss_icon}</td>
                </tr>
            '''

        html += f'''
                <tr style="background: {color}30; font-weight: bold;">
                    <td colspan="4" style="padding: 6px; border: 1px solid #e2e8f0;">TOTAL</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0; text-align: right;">${total:,.0f}</td>
                    <td style="padding: 6px; border: 1px solid #e2e8f0;"></td>
                </tr>
            </table>
        </div>
        '''

        return html


class HrIbcAuditBatchWizard(models.TransientModel):
    """Wizard para generar reporte Excel de auditoría IBC desde lotes."""
    _name = 'hr.ibc.audit.batch.wizard'
    _description = 'Auditoría de IBC por Lotes'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Lote de Nómina',
        domain="[('state', '=', 'close')]",
        default=lambda self: self.env.context.get('active_id') if self.env.context.get('active_model') == 'hr.payslip.run' else False
    )
    date_from = fields.Date(string='Desde', compute='_compute_dates', store=False)
    date_to = fields.Date(string='Hasta', compute='_compute_dates', store=False)
    report_type = fields.Selection([
        ('standard', 'Reporte Estándar (Resumen Ejecutivo)'),
        ('detailed', 'Reporte Detallado (Todos los conceptos)'),
        ('both', 'Ambos Reportes'),
    ], string='Tipo de Reporte', default='both', required=True)

    file_data = fields.Binary(string='Archivo Excel', readonly=True)
    file_name = fields.Char(string='Nombre del archivo', readonly=True)

    @api.depends('payslip_run_id')
    def _compute_dates(self):
        for rec in self:
            if rec.payslip_run_id:
                rec.date_from = rec.payslip_run_id.date_start
                rec.date_to = rec.payslip_run_id.date_end
            else:
                rec.date_from = False
                rec.date_to = False

    def action_generate_excel(self):
        """Genera el reporte Excel de auditoría de IBC con múltiples hojas."""
        self.ensure_one()

        if not self.payslip_run_id:
            raise UserError(_('Debe seleccionar un lote de nómina.'))

        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_('Se requiere la librería xlsxwriter. Instálela con: pip install xlsxwriter'))

        payslip_run = self.payslip_run_id
        payslips = payslip_run.slip_ids.filtered(lambda s: s.state == 'done')

        if not payslips:
            raise UserError(_('No hay nóminas confirmadas en este lote.'))

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos
        formats = self._create_excel_formats(workbook)

        # Recopilar datos de todas las nóminas
        all_data = []
        for slip in payslips:
            contract = slip.contract_id
            employee = slip.employee_id
            annual_params = self.env['hr.annual.parameters'].get_for_year(
                slip.date_from.year,
                company_id=slip.company_id.id,
                raise_if_not_found=False,
            )
            smmlv = annual_params.smmlv_monthly if annual_params else 0

            audit_wizard = self.env['hr.ibc.audit.wizard'].create({'payslip_id': slip.id})
            audit_data = audit_wizard._collect_payslip_data(slip, contract, annual_params)
            ibc_calc = audit_wizard._calculate_expected_ibc(audit_data, smmlv, contract, annual_params)
            ss_calc = audit_wizard._calculate_social_security(ibc_calc, audit_data, contract, employee, annual_params)

            ibc_line = slip.line_ids.filtered(lambda l: l.salary_rule_id.code in ('IBD', 'IBC_R'))
            ibc_registered = ibc_line[0].total if ibc_line else 0

            all_data.append({
                'slip': slip,
                'employee': employee,
                'contract': contract,
                'audit_data': audit_data,
                'ibc_calc': ibc_calc,
                'ss_calc': ss_calc,
                'ibc_registered': ibc_registered,
            })

        # Generar hojas según el tipo de reporte
        if self.report_type in ('standard', 'both'):
            self._write_standard_report(workbook, formats, all_data, payslip_run, smmlv)

        if self.report_type in ('detailed', 'both'):
            self._write_detailed_report(workbook, formats, all_data, payslip_run, smmlv)
            self._write_concepts_detail(workbook, formats, payslips)
            self._write_ss_simulation(workbook, formats, all_data, smmlv)

        workbook.close()
        output.seek(0)

        file_data = base64.b64encode(output.read())
        file_name = f'Auditoria_IBC_{payslip_run.name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        self.write({
            'file_data': file_data,
            'file_name': file_name,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.ibc.audit.batch.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _create_excel_formats(self, workbook):
        """Crea los formatos para el Excel."""
        return {
            'title': workbook.add_format({
                'bold': True, 'font_size': 16, 'font_color': '#2c5282',
                'align': 'center', 'valign': 'vcenter'
            }),
            'subtitle': workbook.add_format({
                'bold': True, 'font_size': 12, 'font_color': '#2c5282',
                'align': 'left', 'valign': 'vcenter'
            }),
            'header': workbook.add_format({
                'bold': True, 'bg_color': '#2c5282', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            }),
            'header_green': workbook.add_format({
                'bold': True, 'bg_color': '#276749', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            }),
            'header_orange': workbook.add_format({
                'bold': True, 'bg_color': '#c05621', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            }),
            'money': workbook.add_format({'num_format': '$#,##0', 'border': 1}),
            'money_bold': workbook.add_format({'num_format': '$#,##0', 'border': 1, 'bold': True}),
            'number': workbook.add_format({'num_format': '#,##0.00', 'border': 1}),
            'percent': workbook.add_format({'num_format': '0.00%', 'border': 1}),
            'text': workbook.add_format({'border': 1}),
            'text_center': workbook.add_format({'border': 1, 'align': 'center'}),
            'diff_bad': workbook.add_format({
                'num_format': '$#,##0', 'border': 1, 'bg_color': '#fed7d7', 'font_color': '#c53030'
            }),
            'diff_good': workbook.add_format({
                'num_format': '$#,##0', 'border': 1, 'bg_color': '#c6f6d5', 'font_color': '#276749'
            }),
            'total_row': workbook.add_format({
                'bold': True, 'bg_color': '#e2e8f0', 'border': 1, 'num_format': '$#,##0'
            }),
            'total_label': workbook.add_format({
                'bold': True, 'bg_color': '#2c5282', 'font_color': 'white',
                'border': 1, 'align': 'right'
            }),
        }

    def _write_standard_report(self, workbook, formats, all_data, payslip_run, smmlv):
        """Escribe el reporte estándar (resumen ejecutivo)."""
        ws = workbook.add_worksheet('Resumen Ejecutivo')

        # Configurar anchos
        ws.set_column('A:A', 15)
        ws.set_column('B:B', 35)
        ws.set_column('C:N', 15)

        # Título
        ws.merge_range('A1:N1', f'AUDITORÍA DE IBC - {payslip_run.name}', formats['title'])
        ws.merge_range('A2:N2', f'Período: {payslip_run.date_start.strftime("%d/%m/%Y")} - {payslip_run.date_end.strftime("%d/%m/%Y")} | SMMLV: ${smmlv:,.0f}', formats['subtitle'])

        # Resumen
        total_payslips = len(all_data)
        with_diff = sum(1 for d in all_data if abs(d['ibc_calc']['ibc_final'] - d['ibc_registered']) > 1)
        ws.write('A4', f'Total Nóminas: {total_payslips}', formats['subtitle'])
        ws.write('D4', f'Con Diferencias: {with_diff}', formats['subtitle'])
        ws.write('G4', f'Sin Diferencias: {total_payslips - with_diff}', formats['subtitle'])

        # Headers
        headers = [
            'Documento', 'Empleado', 'Salario', 'Tipo',
            'IBC Calculado', 'IBC Nómina', 'Diferencia IBC',
            'Salud Calc.', 'Salud Nóm.', 'Dif. Salud',
            'Pensión Calc.', 'Pensión Nóm.', 'Dif. Pensión',
            'Estado'
        ]

        row = 6
        for col, header in enumerate(headers):
            ws.write(row, col, header, formats['header'])

        row = 7
        for data in sorted(all_data, key=lambda x: x['employee'].name):
            emp = data['employee']
            contract = data['contract']
            ibc_calc = data['ibc_calc']
            ss_calc = data['ss_calc']
            ibc_reg = data['ibc_registered']
            audit_data = data['audit_data']

            diff_ibc = ibc_calc['ibc_final'] - ibc_reg
            has_diff = abs(diff_ibc) > 1 or abs(ss_calc['dif_total']) > 100

            ws.write(row, 0, emp.identification_id or '', formats['text'])
            ws.write(row, 1, emp.name, formats['text'])
            ws.write(row, 2, contract.wage, formats['money'])
            ws.write(row, 3, 'Integral' if ibc_calc['es_integral'] else 'Ordinario', formats['text_center'])
            ws.write(row, 4, ibc_calc['ibc_final'], formats['money'])
            ws.write(row, 5, ibc_reg, formats['money'])
            ws.write(row, 6, diff_ibc, formats['diff_bad'] if abs(diff_ibc) > 1 else formats['diff_good'])
            ws.write(row, 7, ss_calc['salud_empleado'], formats['money'])
            ws.write(row, 8, audit_data['nomina_salud_empleado'], formats['money'])
            ws.write(row, 9, ss_calc['dif_salud'], formats['diff_bad'] if abs(ss_calc['dif_salud']) > 100 else formats['diff_good'])
            ws.write(row, 10, ss_calc['pension_empleado'], formats['money'])
            ws.write(row, 11, audit_data['nomina_pension_empleado'], formats['money'])
            ws.write(row, 12, ss_calc['dif_pension'], formats['diff_bad'] if abs(ss_calc['dif_pension']) > 100 else formats['diff_good'])
            ws.write(row, 13, 'REVISAR' if has_diff else 'OK', formats['diff_bad'] if has_diff else formats['diff_good'])

            row += 1

        # Totales
        row += 1
        ws.write(row, 0, 'TOTALES', formats['total_label'])
        ws.write(row, 4, sum(d['ibc_calc']['ibc_final'] for d in all_data), formats['total_row'])
        ws.write(row, 5, sum(d['ibc_registered'] for d in all_data), formats['total_row'])
        ws.write(row, 6, sum(d['ibc_calc']['ibc_final'] - d['ibc_registered'] for d in all_data), formats['total_row'])

    def _write_detailed_report(self, workbook, formats, all_data, payslip_run, smmlv):
        """Escribe el reporte detallado con todos los cálculos."""
        ws = workbook.add_worksheet('Detalle IBC')

        # Configurar anchos
        ws.set_column('A:A', 15)
        ws.set_column('B:B', 30)
        ws.set_column('C:U', 14)

        # Título
        ws.merge_range('A1:U1', f'DETALLE DE CÁLCULO IBC - {payslip_run.name}', formats['title'])

        # Headers
        headers = [
            'Documento', 'Empleado', 'Nómina', 'Salario', 'Tipo',
            'Dev. Salarial', 'Dev. No Sal.', 'Vacaciones', 'Ausencias',
            'Base 40%', 'Novedades', 'IBC SS',
            'Tope Mín', 'Tope Máx', 'IBC Final',
            'IBC Nómina', 'Diferencia',
            'Días Trab.', 'Días Lic.', 'Días Vac.', 'Estado'
        ]

        row = 3
        for col, header in enumerate(headers):
            ws.write(row, col, header, formats['header'])

        row = 4
        for data in sorted(all_data, key=lambda x: x['employee'].name):
            emp = data['employee']
            slip = data['slip']
            contract = data['contract']
            audit = data['audit_data']
            ibc_calc = data['ibc_calc']
            ibc_reg = data['ibc_registered']

            diff = ibc_calc['ibc_final'] - ibc_reg
            has_diff = abs(diff) > 1

            ws.write(row, 0, emp.identification_id or '', formats['text'])
            ws.write(row, 1, emp.name, formats['text'])
            ws.write(row, 2, slip.number, formats['text'])
            ws.write(row, 3, contract.wage, formats['money'])
            ws.write(row, 4, 'INT' if ibc_calc['es_integral'] else 'ORD', formats['text_center'])
            ws.write(row, 5, ibc_calc['value_base'], formats['money'])
            ws.write(row, 6, ibc_calc['value_base_no_dev'], formats['money'])
            ws.write(row, 7, audit['total_vacaciones'], formats['money'])
            ws.write(row, 8, audit['total_ausencias'], formats['money'])
            ws.write(row, 9, ibc_calc['base_40'], formats['money'])
            ws.write(row, 10, ibc_calc['news_value'], formats['money'])
            ws.write(row, 11, ibc_calc['ibc_ss'], formats['money'])
            ws.write(row, 12, ibc_calc['tope_min'], formats['money'])
            ws.write(row, 13, ibc_calc['tope_max'], formats['money'])
            ws.write(row, 14, ibc_calc['ibc_final'], formats['money_bold'])
            ws.write(row, 15, ibc_reg, formats['money'])
            ws.write(row, 16, diff, formats['diff_bad'] if has_diff else formats['diff_good'])
            ws.write(row, 17, audit['dias_trabajados'], formats['number'])
            ws.write(row, 18, audit['dias_ausencia_no_remunerada'], formats['number'])
            ws.write(row, 19, audit['dias_vacaciones'], formats['number'])
            ws.write(row, 20, 'REVISAR' if has_diff else 'OK', formats['diff_bad'] if has_diff else formats['diff_good'])

            row += 1

    def _write_concepts_detail(self, workbook, formats, payslips):
        """Escribe el detalle de conceptos por empleado."""
        ws = workbook.add_worksheet('Conceptos por Empleado')

        ws.set_column('A:A', 15)
        ws.set_column('B:B', 30)
        ws.set_column('C:C', 15)
        ws.set_column('D:D', 40)
        ws.set_column('E:H', 15)

        headers = ['Documento', 'Empleado', 'Código', 'Concepto', 'Cantidad', 'Valor Unit.', 'Total', 'Categoría', 'Base SS']
        for col, header in enumerate(headers):
            ws.write(0, col, header, formats['header'])

        row = 1
        for slip in payslips:
            emp = slip.employee_id
            for line in slip.line_ids.filtered(lambda l: l.total != 0 and l.salary_rule_id.dev_or_ded == 'devengo'):
                rule = line.salary_rule_id
                ws.write(row, 0, emp.identification_id or '', formats['text'])
                ws.write(row, 1, emp.name, formats['text'])
                ws.write(row, 2, rule.code, formats['text'])
                ws.write(row, 3, line.name or rule.name, formats['text'])
                ws.write(row, 4, line.quantity, formats['number'])
                ws.write(row, 5, line.amount, formats['money'])
                ws.write(row, 6, line.total, formats['money'])
                ws.write(row, 7, line.category_id.code if line.category_id else '', formats['text'])
                base_ss = rule.base_seguridad_social if hasattr(rule, 'base_seguridad_social') else False
                ws.write(row, 8, 'Sí' if base_ss else 'No', formats['text_center'])
                row += 1

    def _write_ss_simulation(self, workbook, formats, all_data, smmlv):
        """Escribe la simulación de seguridad social."""
        ws = workbook.add_worksheet('Simulación SS')

        ws.set_column('A:A', 15)
        ws.set_column('B:B', 30)
        ws.set_column('C:R', 14)

        # Headers
        headers = [
            'Documento', 'Empleado', 'IBC', 'Ratio SMMLV',
            'Salud Emp.', 'Salud Cia.', 'Salud Total',
            'Pensión Emp.', 'Pensión Cia.', 'Pensión Total',
            'F. Solidaridad', 'F. Subsistencia',
            'ARL', 'Caja', 'SENA', 'ICBF',
            'Total Empleado', 'Total Empresa'
        ]

        for col, header in enumerate(headers):
            ws.write(0, col, header, formats['header'])

        row = 1
        for data in sorted(all_data, key=lambda x: x['employee'].name):
            emp = data['employee']
            ss = data['ss_calc']

            ws.write(row, 0, emp.identification_id or '', formats['text'])
            ws.write(row, 1, emp.name, formats['text'])
            ws.write(row, 2, ss['ibc'], formats['money'])
            ws.write(row, 3, ss['smmlv_ratio'], formats['number'])
            ws.write(row, 4, ss['salud_empleado'], formats['money'])
            ws.write(row, 5, ss['salud_empresa'], formats['money'])
            ws.write(row, 6, ss['salud_total'], formats['money'])
            ws.write(row, 7, ss['pension_empleado'], formats['money'])
            ws.write(row, 8, ss['pension_empresa'], formats['money'])
            ws.write(row, 9, ss['pension_total'], formats['money'])
            ws.write(row, 10, ss['fondo_solidaridad'], formats['money'])
            ws.write(row, 11, ss['fondo_subsistencia'], formats['money'])
            ws.write(row, 12, ss['arl'], formats['money'])
            ws.write(row, 13, ss['caja'], formats['money'])
            ws.write(row, 14, ss['sena'], formats['money'])
            ws.write(row, 15, ss['icbf'], formats['money'])
            ws.write(row, 16, ss['total_empleado'], formats['money_bold'])
            ws.write(row, 17, ss['total_empresa'], formats['money_bold'])

            row += 1

        # Totales
        row += 1
        ws.write(row, 0, 'TOTALES', formats['total_label'])
        ws.write(row, 4, sum(d['ss_calc']['salud_empleado'] for d in all_data), formats['total_row'])
        ws.write(row, 5, sum(d['ss_calc']['salud_empresa'] for d in all_data), formats['total_row'])
        ws.write(row, 6, sum(d['ss_calc']['salud_total'] for d in all_data), formats['total_row'])
        ws.write(row, 7, sum(d['ss_calc']['pension_empleado'] for d in all_data), formats['total_row'])
        ws.write(row, 8, sum(d['ss_calc']['pension_empresa'] for d in all_data), formats['total_row'])
        ws.write(row, 9, sum(d['ss_calc']['pension_total'] for d in all_data), formats['total_row'])
        ws.write(row, 10, sum(d['ss_calc']['fondo_solidaridad'] for d in all_data), formats['total_row'])
        ws.write(row, 11, sum(d['ss_calc']['fondo_subsistencia'] for d in all_data), formats['total_row'])
        ws.write(row, 12, sum(d['ss_calc']['arl'] for d in all_data), formats['total_row'])
        ws.write(row, 13, sum(d['ss_calc']['caja'] for d in all_data), formats['total_row'])
        ws.write(row, 14, sum(d['ss_calc']['sena'] for d in all_data), formats['total_row'])
        ws.write(row, 15, sum(d['ss_calc']['icbf'] for d in all_data), formats['total_row'])
        ws.write(row, 16, sum(d['ss_calc']['total_empleado'] for d in all_data), formats['total_row'])
        ws.write(row, 17, sum(d['ss_calc']['total_empresa'] for d in all_data), formats['total_row'])
