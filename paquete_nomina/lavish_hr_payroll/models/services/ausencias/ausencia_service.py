# -*- coding: utf-8 -*-
"""
Servicio de Ausencias - Manejo de licencias y ausencias para nómina
Usa hr.leave.line que contiene la información detallada de cada día
Integra la lógica de hr.leave.type para cálculo de valores
"""

import logging
from odoo.addons.lavish_hr_payroll.models.utils import round_payroll_amount

_logger = logging.getLogger(__name__)


class AusenciaService:
    """
    Servicio para procesar ausencias usando hr.leave.line.
    Obtiene información detallada de cada día de ausencia.
    Recomputa valores cuando el tipo de ausencia está en modo código.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.employee_id = payslip.employee_id.id
        self.contract_id = payslip.contract_id.id
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to
        self._worked_days = None
        self._leave_lines = None
        self._leaves = None
        self._leave_types_cache = {}

    @property
    def worked_days(self):
        """Obtiene worked_days del payslip (cached)"""
        if self._worked_days is None:
            self._worked_days = {wd.code: wd for wd in self.payslip.worked_days_line_ids if wd.code}
        return self._worked_days

    @property
    def leaves(self):
        """Obtiene las ausencias del período (cached)"""
        if self._leaves is None:
            self._leaves = self.env['hr.leave'].search([
                ('employee_id', '=', self.employee_id),
                ('state', '=', 'validate'),
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from),
            ])
        return self._leaves

    @property
    def leave_lines(self):
        """Obtiene las líneas de ausencia del período (cached)"""
        if self._leave_lines is None:
            leave_ids = self.leaves.ids
            if leave_ids:
                self._leave_lines = self.env['hr.leave.line'].search([
                    ('leave_id', 'in', leave_ids),
                    ('date', '>=', self.date_from),
                    ('date', '<=', self.date_to),
                ], order='date')
            else:
                self._leave_lines = self.env['hr.leave.line']
        return self._leave_lines

    def get_leave_type_config(self, leave_type):
        """
        Obtiene la configuración del tipo de ausencia (cached).

        Args:
            leave_type: hr.leave.type record

        Returns:
            dict con configuración del tipo
        """
        if not leave_type:
            return {}

        lid = leave_type.id
        if lid in self._leave_types_cache:
            return self._leave_types_cache[lid]

        config = {
            'id': lid,
            'code': leave_type.code if 'code' in leave_type._fields else '',
            'name': leave_type.name,
            'novelty': leave_type.novelty if 'novelty' in leave_type._fields else '',
            'liquidacion_value': leave_type.liquidacion_value if 'liquidacion_value' in leave_type._fields else 'WAGE',
            'is_vacation': leave_type.is_vacation if 'is_vacation' in leave_type._fields else False,
            'is_vacation_money': leave_type.is_vacation_money if 'is_vacation_money' in leave_type._fields else False,
            'unpaid_absences': leave_type.unpaid_absences if 'unpaid_absences' in leave_type._fields else False,
            'num_days_no_assume': leave_type.num_days_no_assume if 'num_days_no_assume' in leave_type._fields else 0,
            'recognizing_factor_eps_arl': leave_type.recognizing_factor_eps_arl if 'recognizing_factor_eps_arl' in leave_type._fields else 0,
            'recognizing_factor_company': leave_type.recognizing_factor_company if 'recognizing_factor_company' in leave_type._fields else 0,
            'eps_arl_input_id': leave_type.eps_arl_input_id.id if 'eps_arl_input_id' in leave_type._fields and leave_type.eps_arl_input_id else False,
            'company_input_id': leave_type.company_input_id.id if 'company_input_id' in leave_type._fields and leave_type.company_input_id else False,
            'apply_day_31': leave_type.apply_day_31 if 'apply_day_31' in leave_type._fields else False,
            'discount_rest_day': leave_type.discount_rest_day if 'discount_rest_day' in leave_type._fields else False,
            'pagar_festivos': leave_type.evaluates_day_off if 'evaluates_day_off' in leave_type._fields else False,
            'completar_salario': leave_type.completar_salario if 'completar_salario' in leave_type._fields else False,
            'rango_adicionales_enfermedad': leave_type.rango_adicionales_enfermedad if 'rango_adicionales_enfermedad' in leave_type._fields else False,
            'gi_b2': leave_type.gi_b2 if 'gi_b2' in leave_type._fields else 100,
            'gi_b90': leave_type.gi_b90 if 'gi_b90' in leave_type._fields else 66.67,
            'gi_b180': leave_type.gi_b180 if 'gi_b180' in leave_type._fields else 50,
            'gi_a180': leave_type.gi_a180 if 'gi_a180' in leave_type._fields else 50,
            'gi_b180_eps_arl_input_id': leave_type.gi_b180_eps_arl_input_id.id if 'gi_b180_eps_arl_input_id' in leave_type._fields and leave_type.gi_b180_eps_arl_input_id else False,
            'gi_a180_eps_arl_input_id': leave_type.gi_a180_eps_arl_input_id.id if 'gi_a180_eps_arl_input_id' in leave_type._fields and leave_type.gi_a180_eps_arl_input_id else False,
        }

        self._leave_types_cache[lid] = config
        return config

    def get_rate_and_rule(self, leave_type, sequence):
        """
        Obtiene el porcentaje y regla salarial según la secuencia del día.
        Replica la lógica de hr.leave.type.get_rate_concept_id()

        Args:
            leave_type: hr.leave.type record
            sequence: Número de secuencia del día

        Returns:
            tuple (rate, rule_id) o (1.0, None) si no aplica
        """
        config = self.get_leave_type_config(leave_type)

        if not config:
            return 1.0, None

        novelty = config.get('novelty', '')
        num_days_no_assume = config.get('num_days_no_assume', 0)

        # Si no es IGE o IRL, usar regla estándar
        if novelty not in ['ige', 'irl']:
            return 1.0, config.get('eps_arl_input_id')

        # Lógica para IGE/IRL con rangos adicionales
        if config.get('rango_adicionales_enfermedad'):
            if sequence <= num_days_no_assume:
                rate = config.get('gi_b2', 100) / 100
                return rate, config.get('company_input_id')
            elif num_days_no_assume < sequence <= 90:
                rate = config.get('gi_b90', 66.67) / 100
                return rate, config.get('eps_arl_input_id')
            elif 91 <= sequence <= 180:
                rate = config.get('gi_b180', 50) / 100
                return rate, config.get('gi_b180_eps_arl_input_id')
            else:  # 181+
                rate = config.get('gi_a180', 50) / 100
                return rate, config.get('gi_a180_eps_arl_input_id')
        else:
            # Sin rangos adicionales - convertir porcentaje a decimal (100 -> 1.0)
            if sequence <= num_days_no_assume:
                factor = config.get('recognizing_factor_company', 100)
                rate = factor / 100 if factor else 1.0
                return rate, config.get('company_input_id')
            else:
                factor = config.get('recognizing_factor_eps_arl', 100)
                rate = factor / 100 if factor else 1.0
                return rate, config.get('eps_arl_input_id')

    def get_base_value(self, leave, localdict=None):
        """
        Obtiene el valor base para el cálculo según tipo de liquidación.

        Args:
            leave: hr.leave record
            localdict: dict con valores calculados

        Returns:
            float con el valor base
        """
        leave_type = leave.holiday_status_id
        config = self.get_leave_type_config(leave_type)
        liquidacion_type = config.get('liquidacion_value', 'WAGE')

        # Si hay valor forzado en la ausencia
        if 'force_base_amount' in leave._fields and leave.force_base_amount and leave.force_base_amount > 0:
            return leave.force_base_amount

        # Si fuerza salario mínimo
        if 'force_min_wage' in leave._fields and leave.force_min_wage:
            annual_params = self._get_annual_parameters()
            if annual_params:
                return annual_params.smmlv_monthly
            return 0

        # Según tipo de liquidación
        if liquidacion_type == 'IBC':
            # IBC del mes anterior o de la ausencia
            if 'ibc_pila' in leave._fields and leave.ibc_pila:
                return leave.ibc_pila
            if localdict and localdict.get('IBD'):
                return abs(localdict.get('IBD', 0))
            return self.contract.wage

        elif liquidacion_type == 'YEAR':
            # Promedio último año
            if 'ibc' in leave._fields and leave.ibc:
                return leave.ibc
            return self._get_average_last_year()

        elif liquidacion_type == 'MIN':
            # Salario mínimo
            annual_params = self._get_annual_parameters()
            if annual_params:
                return annual_params.smmlv_monthly
            return 0

        else:  # WAGE
            return self.contract.wage

    def _get_annual_parameters(self):
        """Obtiene parámetros anuales"""
        year = self.date_to.year if self.date_to else self.date_from.year
        company_id = (
            self.contract.company_id.id
            if self.contract and self.contract.company_id
            else self.env.company.id
        )
        return self.env['hr.annual.parameters'].get_for_year(
            year,
            company_id=company_id,
            raise_if_not_found=False,
        )

    def _get_average_last_year(self):
        """Calcula promedio del último año desde nóminas"""
        # Buscar nóminas del último año
        date_start = self.date_from - relativedelta(years=1)
        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id),
            ('state', 'in', ['done', 'paid']),
            ('date_from', '>=', date_start),
            ('date_to', '<', self.date_from),
        ], order='date_from')

        if not payslips:
            return self.contract.wage

        total_ibc = 0
        count = 0
        for slip in payslips[:12]:
            ibc_line = slip.line_ids.filtered(lambda l: l.code == 'IBD')
            if ibc_line:
                total_ibc += abs(ibc_line[0].total)
                count += 1

        if count > 0:
            return total_ibc / count
        return self.contract.wage

    def recompute_leave_line_amount(self, line, localdict=None, write_to_db=False):
        """
        Recomputa el valor de una línea de ausencia según la configuración.

        Args:
            line: hr.leave.line record
            localdict: dict con valores calculados
            write_to_db: Si True, actualiza hr.leave.line en BD

        Returns:
            dict con valores recomputados
        """
        leave = line.leave_id
        leave_type = leave.holiday_status_id
        config = self.get_leave_type_config(leave_type)

        # Obtener base
        base_value = self.get_base_value(leave, localdict)
        base_daily = base_value / 30 if base_value else 0

        # Obtener rate y regla según secuencia
        sequence = line.sequence or 1
        rate, rule_id = self.get_rate_and_rule(leave_type, sequence)

        # Calcular monto
        amount = base_daily * rate

        # Validar contra salario mínimo
        annual_params = self._get_annual_parameters()
        if annual_params and not (leave.force_wage_incapacity if 'force_wage_incapacity' in leave._fields else False):
            min_daily = annual_params.smmlv_monthly / 30
            amount = max(amount, min_daily)

        # Días efectivos
        days_payslip = line.days_payslip or 0

        result = {
            'amount': amount,
            'total': float(round_payroll_amount(amount * days_payslip)),
            'base_value': base_value,
            'base_daily': base_daily,
            'rate': rate,
            'rule_id': rule_id,
            'sequence': sequence,
            'days': days_payslip,
        }

        # Escribir a BD si se solicita
        if write_to_db and line.exists():
            vals = {
                'amount': amount,
                'ibc_base': base_value,
                'ibc_day': base_daily,
                'rate_applied': rate * 100,
            }
            if rule_id:
                vals['rule_id'] = rule_id
            line.write(vals)

        return result

    def recompute_all_leave_lines(self, localdict=None, write_to_db=True):
        """
        Recomputa todas las líneas de ausencia del período.

        Args:
            localdict: dict con valores calculados
            write_to_db: Si True, actualiza hr.leave.line en BD

        Returns:
            dict con resumen de líneas actualizadas
        """
        updated = []
        total_original = 0
        total_new = 0

        for line in self.leave_lines:
            total_original += line.amount or 0
            result = self.recompute_leave_line_amount(line, localdict, write_to_db)
            total_new += result['total']
            updated.append({
                'line_id': line.id,
                'leave_id': line.leave_id.id,
                'date': line.date,
                'original': line.amount or 0,
                'new': result['total'],
                'diff': result['total'] - (line.amount or 0),
            })

        # Actualizar totales en hr.leave
        if write_to_db:
            for leave in self.leaves:
                leave_lines = leave.line_ids.filtered(
                    lambda l: l.date >= self.date_from and l.date <= self.date_to
                )
                new_total = sum(l.amount for l in leave_lines)
                if not leave.force_payroll_value:
                    leave.write({'payroll_value': new_total})
                else:
                    leave._apply_manual_payroll_value()

        return {
            'lines_updated': len(updated),
            'total_original': total_original,
            'total_new': total_new,
            'difference': total_new - total_original,
            'detail': updated,
        }

    def get_worked_days_by_code(self, code):
        """Obtiene línea de worked_days por código."""
        return self.worked_days.get(code)

    def get_dias_trabajados(self):
        """Obtiene días trabajados (WORK100)."""
        work100 = self.get_worked_days_by_code('WORK100')
        return {
            'dias': work100.number_of_days if work100 else 30,
            'horas': work100.number_of_hours if work100 else 240,
            'code': 'WORK100'
        }

    def get_ausencias(self, localdict=None, recompute=False):
        """
        Obtiene todas las ausencias desde hr.leave.line.

        Args:
            localdict: dict con valores calculados (para recompute)
            recompute: Si True, recalcula valores con localdict

        Returns:
            dict con ausencias detalladas
        """
        resultado = {
            'total_dias': 0,
            'total_dias_trabajo': 0,
            'total_dias_festivo': 0,
            'total_horas': 0,
            'total_valor': 0,
            'por_tipo': {},
            'por_leave': {},
            'por_regla': {},
            'detalle': []
        }

        for line in self.leave_lines:
            leave = line.leave_id
            leave_type = leave.holiday_status_id
            config = self.get_leave_type_config(leave_type)

            # Datos básicos de la línea
            dias_payslip = line.days_payslip or 0
            dias_trabajo = line.days_work or 0
            dias_festivo = line.days_holiday or 0
            horas = line.hours or 0

            # Recomputar si es necesario
            if recompute:
                computed = self.recompute_leave_line_amount(line, localdict)
                amount = computed['total']
                rate = computed['rate']
                rule_id = computed['rule_id']
            else:
                amount = line.amount or 0
                rate = line.rate_applied or 100
                rule_id = line.rule_id.id if line.rule_id else None

            resultado['total_dias'] += dias_payslip
            resultado['total_dias_trabajo'] += dias_trabajo
            resultado['total_dias_festivo'] += dias_festivo
            resultado['total_horas'] += horas
            resultado['total_valor'] += amount

            # Agrupar por tipo de ausencia
            tipo_code = config.get('code') or str(leave_type.id)
            if tipo_code not in resultado['por_tipo']:
                resultado['por_tipo'][tipo_code] = {
                    'nombre': config.get('name', ''),
                    'novelty': config.get('novelty', ''),
                    'dias': 0,
                    'dias_trabajo': 0,
                    'dias_festivo': 0,
                    'horas': 0,
                    'valor': 0,
                    'es_pagada': not config.get('unpaid_absences', False),
                    'es_vacacion': config.get('is_vacation', False),
                    'unpaid_absences': config.get('unpaid_absences', False),
                    'completar_salario': config.get('completar_salario', False),
                }
            resultado['por_tipo'][tipo_code]['dias'] += dias_payslip
            resultado['por_tipo'][tipo_code]['dias_trabajo'] += dias_trabajo
            resultado['por_tipo'][tipo_code]['dias_festivo'] += dias_festivo
            resultado['por_tipo'][tipo_code]['horas'] += horas
            resultado['por_tipo'][tipo_code]['valor'] += amount

            # Agrupar por leave
            lid = leave.id
            if lid not in resultado['por_leave']:
                # Obtener campos adicionales del leave
                valor_adicional = leave.valor_adicional_manual if 'valor_adicional_manual' in leave._fields else 0
                is_vacation_money = config.get('is_vacation_money', False)
                dias_a_liquidar = leave.dias_a_liquidar if 'dias_a_liquidar' in leave._fields else 0
                incluir_festivos = leave.incluir_festivos_liquidacion if 'incluir_festivos_liquidacion' in leave._fields else True
                
                resultado['por_leave'][lid] = {
                    'leave_id': lid,
                    'tipo': config.get('name', ''),
                    'tipo_code': tipo_code,
                    'novelty': config.get('novelty', ''),
                    'fecha_inicio': leave.date_from,
                    'fecha_fin': leave.date_to,
                    'dias': 0,
                    'valor': 0,
                    'valor_eps': 0,  # Valor pagado por EPS/ARL
                    'complemento_empresa': 0,  # Complemento pagado por empresa
                    'valor_adicional_manual': valor_adicional or 0,  # Valor adicional manual
                    'total_pagar': 0,  # Total = EPS + Complemento + Adicional
                    'lineas': [],
                    'lineas_complemento': [],  # IDs de líneas de complemento
                    'config': config,
                    # Campos especiales para vacaciones en dinero
                    'is_vacation_money': is_vacation_money,
                    'dias_a_liquidar': dias_a_liquidar or 0,
                    'incluir_festivos': incluir_festivos,
                }
            
            # Separar valores de complemento
            is_complement = line.is_complement if 'is_complement' in line._fields else False
            if is_complement:
                resultado['por_leave'][lid]['complemento_empresa'] += amount
                resultado['por_leave'][lid]['lineas_complemento'].append(line.id)
            else:
                resultado['por_leave'][lid]['valor_eps'] += amount
                resultado['por_leave'][lid]['lineas'].append(line.id)
            
            resultado['por_leave'][lid]['dias'] += dias_payslip if not is_complement else 0
            resultado['por_leave'][lid]['valor'] += amount
            resultado['por_leave'][lid]['total_pagar'] = (
                resultado['por_leave'][lid]['valor_eps'] + 
                resultado['por_leave'][lid]['complemento_empresa'] +
                resultado['por_leave'][lid]['valor_adicional_manual']
            )

            # Agrupar por regla salarial
            if rule_id:
                if rule_id not in resultado['por_regla']:
                    rule = self.env['hr.salary.rule'].browse(rule_id)
                    resultado['por_regla'][rule_id] = {
                        'rule_id': rule_id,
                        'code': rule.code if rule else '',
                        'name': rule.name if rule else '',
                        'sequence': rule.sequence if rule else 0,
                        'category_id': rule.category_id.id if rule and rule.category_id else False,
                        'category_code': rule.category_id.code if rule and rule.category_id else '',
                        'dias': 0,
                        'valor': 0,
                        'leaves': [],
                    }
                resultado['por_regla'][rule_id]['dias'] += dias_payslip
                resultado['por_regla'][rule_id]['valor'] += amount
                if lid not in resultado['por_regla'][rule_id]['leaves']:
                    resultado['por_regla'][rule_id]['leaves'].append(lid)

            # Campos de complemento
            is_complement = line.is_complement if 'is_complement' in line._fields else False
            
            # Detalle por línea
            resultado['detalle'].append({
                'id': line.id,
                'leave_id': lid,
                'date': line.date,
                'sequence': line.sequence,
                'days_payslip': dias_payslip,
                'days_work': dias_trabajo,
                'days_holiday': dias_festivo,
                'days_31': line.days_31 or 0,
                'days_holiday_31': line.days_holiday_31 or 0,
                'hours': horas,
                'amount': amount,
                'rate': rate,
                'rule_id': rule_id,
                'ibc_day': line.ibc_day or 0,
                'ibc_base': line.ibc_base or 0,
                'base_type': line.base_type or 'ibc',
                'is_holiday': line.is_holiday if 'is_holiday' in line._fields else False,
                'is_virtual_day': line.is_virtual_day if 'is_virtual_day' in line._fields else False,
                'is_complement': is_complement,
            })

        return resultado

    def get_ausencias_no_pagadas(self, localdict=None):
        """Obtiene ausencias no pagadas (unpaid_absences=True)."""
        ausencias = self.get_ausencias(localdict)
        dias_no_pagados = 0
        horas_no_pagadas = 0
        detalle = []

        for tipo_code, data in ausencias['por_tipo'].items():
            if data.get('unpaid_absences', False):
                dias_no_pagados += data['dias']
                horas_no_pagadas += data['horas']

        for item in ausencias['detalle']:
            line = self.env['hr.leave.line'].browse(item['id'])
            leave = line.leave_id
            if leave and 'unpaid_absences' in leave._fields and leave.unpaid_absences:
                detalle.append(item)

        return {
            'dias': dias_no_pagados,
            'horas': horas_no_pagadas,
            'detalle': detalle,
            'tiene_descuento': dias_no_pagados > 0
        }

    def get_ausencias_pagadas(self, localdict=None):
        """Obtiene ausencias pagadas (licencias remuneradas)."""
        ausencias = self.get_ausencias(localdict)
        dias_pagados = 0
        horas_pagadas = 0
        valor = 0
        detalle = []

        for tipo_code, data in ausencias['por_tipo'].items():
            if not data.get('unpaid_absences', False):
                dias_pagados += data['dias']
                horas_pagadas += data['horas']
                valor += data['valor']

        for item in ausencias['detalle']:
            line = self.env['hr.leave.line'].browse(item['id'])
            leave = line.leave_id
            if leave:
                is_unpaid = leave.unpaid_absences if 'unpaid_absences' in leave._fields else False
                if not is_unpaid:
                    detalle.append(item)

        return {
            'dias': dias_pagados,
            'horas': horas_pagadas,
            'valor': valor,
            'detalle': detalle
        }

    def calcular_descuento_ausencias(self, salario_diario):
        """Calcula el descuento por ausencias no pagadas."""
        no_pagadas = self.get_ausencias_no_pagadas()
        monto = no_pagadas['dias'] * salario_diario

        return {
            'dias': no_pagadas['dias'],
            'monto': round(monto),
            'salario_diario': salario_diario,
            'detalle': no_pagadas['detalle']
        }

    def procesar_ausencias(self, localdict):
        """
        Procesa las ausencias y genera líneas para el payslip.
        Recomputa valores usando localdict cuando hay reglas en modo código.

        Args:
            localdict: Diccionario local del cálculo

        Returns:
            dict con líneas de ausencias a crear
        """
        lineas = {}
        ausencias = self.get_ausencias(localdict, recompute=True)

        # Agrupar por regla salarial para crear líneas consolidadas
        for rule_id, rule_data in ausencias['por_regla'].items():
            if not rule_id:
                continue

            valor = rule_data['valor']
            if valor == 0:
                continue

            rule = self.env['hr.salary.rule'].browse(rule_id)
            if not rule.exists():
                continue

            dias = rule_data['dias']
            code = f'LEAVE_{rule.code}'

            # Si ya existe, acumular
            if code in lineas:
                lineas[code]['amount'] += valor
                lineas[code]['quantity'] += dias
                lineas[code]['total'] = float(round_payroll_amount(lineas[code]['amount']))
            else:
                lineas[code] = {
                    'sequence': rule.sequence,
                    'code': code,
                    'name': f"{rule.name} ({dias} días)",
                    'salary_rule_id': rule.id,
                    'contract_id': self.contract_id,
                    'employee_id': self.employee_id,
                    'entity_id': False,
                    'amount': valor,
                    'quantity': dias,
                    'rate': 100.0,
                    'total': float(round_payroll_amount(valor)),
                    'slip_id': self.payslip.id,
                    'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
                }

        return lineas

    def get_resumen(self, localdict=None):
        """Obtiene resumen completo de días trabajados y ausencias."""
        trabajados = self.get_dias_trabajados()
        ausencias = self.get_ausencias(localdict)
        no_pagadas = self.get_ausencias_no_pagadas(localdict)
        pagadas = self.get_ausencias_pagadas(localdict)

        return {
            'trabajados': trabajados,
            'ausencias_total': ausencias,
            'ausencias_no_pagadas': no_pagadas,
            'ausencias_pagadas': pagadas,
            'dias_efectivos': trabajados['dias'] - no_pagadas['dias'],
            'total_valor_ausencias': ausencias['total_valor'],
            'por_regla': ausencias['por_regla'],
        }


# Import necesario para _get_average_last_year
try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    from datetime import timedelta
    class relativedelta:
        def __init__(self, years=0, months=0, days=0):
            self.years = years
            self.months = months
            self.days = days
