# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_round, date_utils
from odoo.tools.safe_eval import safe_eval

from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any, Optional, Union
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal, getcontext, ROUND_CEILING, ROUND_HALF_UP
from psycopg2 import sql
import calendar
import ast
import re
import logging
import json
import math
# Imports desde módulo base lavish_hr_employee
from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_data_structures import (
    CategoryCollection,
    CategoryData,
    RulesCollection,
    RuleData
)
from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import (
    DAYS_YEAR,
    DAYS_YEAR_NATURAL,
    DAYS_MONTH,
    PRECISION_TECHNICAL,
    PRECISION_DISPLAY,
    DATETIME_MIN,
    DATETIME_MAX,
    HOURS_PER_DAY,
    UTC,
    TPCT,
    TPCP,
    NCI,
    CATEGORY_MAPPINGS,
    VALID_NOVELTY_TYPES,
    TYPE_PERIOD,
    TYPE_BIWEEKLY,
    MOVE_TYPE_SELECTION,
    COMPUTATION_STATUS_SELECTION,
    RIBBON_COLOR_SELECTION,
    round_1_decimal,
    to_decimal,
    json_serial,
    days360,
    get_month_name,
    PayslipLineAccumulator,
)
from odoo.addons.lavish_hr_payroll.models.utils.payroll_utils import (
    round_payroll_amount,
    round_to_100,
    round_to_1000,
    round_up_to_hundred_decimal as round_up_to_hundred,
)
from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_acumulacion import HrPayslipAccumulation
from .hr_slip_constante import PayslipCalculationContext
from .services import (
    PeriodNoveltiesService,
    WorkedDaysCalculationService,
    LeaveCalculationService,
    PeriodCalculationService,
    PayslipHtmlReportService,
    PayslipHistoryService,
    PayslipLineCalculationService,
)

_logger = logging.getLogger(__name__)

getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

# to_decimal importado desde hr_payslip_constants
# round_up_to_hundred importado desde payroll_utils

def calculate_contribution(base, rate):
    """base * rate (%) / 100, todo en Decimal."""
    return to_decimal(base) * to_decimal(rate) / Decimal('100')

class RulesComputedCompat:
    """
    Wrapper de compatibilidad para rules_computed (Odoo 15/17 -> Odoo 18).

    Permite sintaxis antigua: rules_computed.AVG
    que en Odoo 18 es: rules['AVG'].total

    Uso en reglas salariales:
        # Antiguo (Odoo 15/17):
        result = rules_computed.AVG / 360

        # Nuevo (Odoo 18):
        result = rules['AVG'].total / 360

        # Con compatibilidad (ambas funcionan):
        result = rules_computed.AVG / 360  # ← usa este wrapper
    """
    __slots__ = ('_rules',)

    def __init__(self, rules_collection):
        """
        Args:
            rules_collection: RulesCollection de Odoo 18
        """
        self._rules = rules_collection

    def __getattr__(self, code):
        """
        Permite acceso por atributo: rules_computed.AVG
        Retorna el total de la regla o 0 si no existe.

        Args:
            code: Código de la regla (ej: 'AVG', 'BASIC', etc.)

        Returns:
            float: Total de la regla o 0.0
        """
        rule_data = self._rules.get(code)
        if rule_data:
            return rule_data.total
        return 0.0

    def __getitem__(self, code):
        """Acceso tipo diccionario: rules_computed['AVG']"""
        return self.__getattr__(code)

    def get(self, code, default=0.0):
        """Método get estándar"""
        rule_data = self._rules.get(code)
        if rule_data:
            return rule_data.total
        return default

class HrPayslipCalculation(models.Model):
    """Extensión de hr.payslip para lógica de cálculo de nómina."""
    _inherit = 'hr.payslip'

    _normalize_states = HrPayslipAccumulation._normalize_states
    _build_state_filter_sql = HrPayslipAccumulation._build_state_filter_sql

    # Accumulation methods from mixin
    _get_categories_accumulated = HrPayslipAccumulation._get_categories_accumulated
    _get_concepts_accumulated = HrPayslipAccumulation._get_concepts_accumulated
    _get_leave_days_accumulated = HrPayslipAccumulation._get_leave_days_accumulated
    _get_categories_accumulated_by_payslip = HrPayslipAccumulation._get_categories_accumulated_by_payslip
    _get_concepts_accumulated_by_payslip = HrPayslipAccumulation._get_concepts_accumulated_by_payslip
    _get_leave_days_no_pay = HrPayslipAccumulation._get_leave_days_no_pay
    _get_salary_in_leave = HrPayslipAccumulation._get_salary_in_leave

    def convert_tuples_to_dict(self, tuple_list):
        """Convierte una lista de tuplas a diccionario"""
        data_list = ast.literal_eval(tuple_list)
        return data_list

    def days_between(self, start_date: date, end_date: date):
        """
        Calcula días entre dos fechas usando el método comercial 360.

        Método: Cada mes tiene 30 días, año tiene 360 días.
        Los días 31 se ajustan a 30 para mantener la consistencia.

        Args:
            start_date: Fecha inicial
            end_date: Fecha final

        Returns:
            int: Número de días calculados en sistema 360
        """
        return days360(start_date, end_date)

    computo_completo = fields.Boolean(
        string='Cómputo Completo',
        default=False,
        tracking=True,
        help='Si está activado, se llenan automáticamente todos los datos de la nómina (ausencias, horas extras, préstamos, novedades, días trabajados y líneas). Puede modificarse manualmente después.'
    )

    contract_change_wage_ids = fields.One2many(
        'hr.contract.change.wage',
        compute='_compute_contract_related_fields',
        string='Historial Salarial',
        readonly=True,
        help='Historial de cambios salariales del contrato asociado a esta nomina'
    )

    # Campos de configuración de prestaciones desde el contrato
    no_promediar_sueldo_prestaciones = fields.Boolean(
        compute='_compute_contract_related_fields',
        string='No Promediar Sueldo',
        readonly=True,
        help='Indica si el contrato tiene configurado NO promediar el sueldo básico para prestaciones. '
             'Si True: usa salario actual. Si False: promedia salario histórico.'
    )

    def _get_effective_contract_for_display(self):
        self.ensure_one()
        contract = self._fields.get('contract_id') and self.contract_id
        if not contract and self.employee_id and self.employee_id._fields.get('contract_id'):
            contract = self.employee_id.contract_id
        return contract

    @api.depends('employee_id', 'employee_id.contract_id', 'employee_id.contract_id.change_wage_ids')
    def _compute_contract_related_fields(self):
        for record in self:
            contract = record._get_effective_contract_for_display()
            record.contract_change_wage_ids = contract.change_wage_ids if contract else False
            record.no_promediar_sueldo_prestaciones = bool(
                contract and getattr(contract, 'no_promediar_sueldo_prestaciones', False)
            )

    @api.onchange('computo_completo')
    def _onchange_computo_completo(self):
        """
        Cuando se activa computo_completo, llena automáticamente todos los datos de la nómina.
        Permite que se pueda cambiar manualmente después.
        """
        if self.computo_completo and self.state in ('draft', 'verify'):
            # Solo ejecutar si la nómina está en estado draft o verify
            try:
                # Ejecutar el cómputo completo
                self._ejecutar_computo_completo()
            except Exception as e:
                # Si hay error, desactivar el campo y mostrar mensaje
                self.computo_completo = False
                return {
                    'warning': {
                        'title': 'Error en Cómputo Completo',
                        'message': f'No se pudo completar el cómputo automático: {str(e)}'
                    }
                }
    
    def _ejecutar_computo_completo(self):
        """
        Ejecuta el cómputo completo de la nómina llenando todos los datos automáticamente.
        Este método puede ser llamado manualmente o automáticamente cuando se activa computo_completo.
        """
        self.ensure_one()
        
        if not self.contract_id or not self.employee_id or not self.struct_id:
            raise UserError('Debe tener contrato, empleado y estructura definidos para ejecutar el cómputo completo.')
        
        if self.state not in ('draft', 'verify'):
            raise UserError('Solo se puede ejecutar el cómputo completo en nóminas en estado Borrador o Verificar.')
        
        # Actualizar fechas de prima y cesantías si aplica
        slip_data = {
            'id': self.id,
            'struct_id': self.struct_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'contract_id': self.contract_id.id,
            'employee_id': self.employee_id.id,
            'struct_process': getattr(self.struct_id, 'process', 'nomina'),
            'date_liquidacion': getattr(self, 'date_liquidacion', False),
            'pay_primas_in_payroll': getattr(self, 'pay_primas_in_payroll', False),
            'pay_cesantias_in_payroll': getattr(self, 'pay_cesantias_in_payroll', False),
            'number': self.number
        }
        self._update_prima_cesantias_dates(self, slip_data)
        
        # Asignar período
        if self.date_from and self.date_to:
            days_diff = (self.date_to - self.date_from).days + 1
            period_type = 'monthly' if days_diff > 15 else 'bi-monthly'
            period = self.env['hr.period'].get_period(
                self.date_from,
                self.date_to,
                period_type,
                self.company_id.id if self.company_id else self.env.company.id
            )
            if period:
                self.period_id = period.id
        
        # Limpiar y calcular ausencias
        self.leave_ids.unlink()
        self.compute_sheet_leave()

        # Calcular horas extras
        self._compute_extra_hours()

        # Procesar préstamos
        self._process_loan_lines()

        # Calcular novedades
        self._compute_novedades()

        # Calcular días trabajados
        self.worked_days_line_ids.unlink()
        self._action_compute_worked_days()

        # Calcular líneas de nómina
        self.line_ids.unlink()
        PayslipLine = self.env['hr.payslip.line']
        line_vals = self._get_payslip_lines_lavish()
        totalization_codes = {'TOTALDEV', 'TOTALDED', 'NET'}
        line_vals = [
            line for line in line_vals
            if line.get('code') in totalization_codes
            or abs(float(line.get('total') or 0.0)) > 1e-9
        ]
        if line_vals:
            valid_fields = PayslipLine._fields
            sanitized_vals = [
                {key: value for key, value in line.items() if key in valid_fields}
                for line in line_vals
            ]
            PayslipLine.create(sanitized_vals)
        
        # Actualizar estado y fecha de cómputo
        today = fields.Date.today()
        name = f"Nomina de {self.contract_id.name}" if self.contract_id else self.name
        self.write({
            'name': name,
            'state': 'verify',
            'compute_date': today
        })
    
    @api.onchange('employee_id', 'contract_id', 'struct_id', 'date_to')
    def load_dates_liq_contrato(self):
        """
        Carga las fechas para liquidación de contrato desde históricos.
        Delega al servicio PayslipHistoryService.

        IMPORTANTE: Si date_prima, date_vacaciones o date_cesantias ya tienen valor,
        NO se recomputan. Solo se calculan si están vacíos.
        """
        service = PayslipHistoryService(self)
        service.apply_liquidation_dates()

    @api.depends('line_ids.computation')
    def _compute_prestaciones_sociales_report(self):
        for payslip in self:
            prestaciones_lines = payslip.line_ids.filtered(lambda line: line.computation and line.salary_rule_id.code not in ('IBD','IBC_R','RT_MET_01'))
            if prestaciones_lines:
                all_reports = []
                for line in prestaciones_lines:
                    try:
                        computation_data = json.loads(line.computation)
                        report = PayslipHtmlReportService.format_prestaciones_report(line, computation_data)
                        all_reports.append(report)
                    except json.JSONDecodeError:
                        all_reports.append(f'<p>Error al procesar los datos de la línea {line.name}.</p>')

                payslip.prestaciones_sociales_report = PayslipHtmlReportService.combine_reports(all_reports)
            else:
                payslip.prestaciones_sociales_report = PayslipHtmlReportService.empty_prestaciones_report()

    @api.depends('line_ids', 'leave_ids', 'worked_days_line_ids')
    def _compute_payslip_detail(self):
        for payslip in self:
            payslip.payslip_detail = 'Calculated'

    def _periodo(self):
        for rec in self:
            service = PeriodCalculationService(rec)
            rec.periodo = service.get_periodo_string()
    
    def _compute_extra_hours(self):
        """
        Asigna horas extras al payslip.
        Delega al servicio PeriodNoveltiesService.
        """
        for payslip in self:
            service = PeriodNoveltiesService(self.env, payslip)
            service.compute_extra_hours()

    def _compute_novedades(self):
        """
        Asigna novedades diferentes al payslip.
        Delega al servicio PeriodNoveltiesService.
        """
        for payslip in self:
            service = PeriodNoveltiesService(self.env, payslip)
            service.compute_novedades()

    def compute_slip(self):
        self_ids = tuple(self._ids)
        if not self_ids:
            return True
        self._cr.execute("""
            SELECT id, struct_id, date_from, date_to, contract_id, employee_id, 
                struct_process, date_liquidacion, pay_primas_in_payroll, 
                pay_cesantias_in_payroll, number
            FROM hr_payslip
            WHERE id IN %s AND state IN ('draft', 'verify')
        """, (self_ids,))
        slips_data = self._cr.dictfetchall()
        if not slips_data:
            return True
        today = fields.Date.today()
        PayslipLine = self.env['hr.payslip.line']
        for slip_data in slips_data:
            slip = self.browse(slip_data['id'])
            slip._update_prima_cesantias_dates(slip, slip_data)
            #if slip._check_duplicate_slip(slip_data):
            #    raise UserError(f"No puede existir más de una nómina del mismo tipo y periodo para el empleado {slip.employee_id.name}")
            name = f"Nomina de {slip.contract_id.name}"
            slip.write({
                'name': name,
                'state': 'verify',
                'compute_date': today
            })
            date_from = slip_data['date_from']
            date_to = slip_data['date_to']
            days_diff = (date_to - date_from).days + 1
            period_type = 'monthly' if days_diff > 15 else 'bi-monthly'
            period = self.env['hr.period'].get_period(
                date_from, 
                date_to,
                period_type,
                self.company_id.id
            )
            if period:
                self.period_id = period.id
            else:
                self.assign_periods_to_draft_payslips()
                self.period_id = self.env['hr.period'].get_period(date_from, date_to, period_type, self.company_id.id).id
            slip.leave_ids.unlink()
            slip.compute_sheet_leave()
            slip._compute_extra_hours()
            slip._process_loan_lines()
            slip._compute_novedades()
            # Usar ORM en lugar de SQL directo para respetar triggers y caché
            slip.worked_days_line_ids.unlink()
            slip.line_ids.unlink()
            slip._action_compute_worked_days()
            lines = slip._get_payslip_lines_lavish()
            PayslipLine.create(lines)
        return True

    def get_selection_label(self, field_name):
        """
        Obtiene la etiqueta en español de un campo Selection usando _description_selection().

        Args:
            field_name (str): Nombre del campo Selection

        Returns:
            str: Etiqueta del valor actual del campo en español, o '' si no existe

        Ejemplo:
            payslip.get_selection_label('move_type')  # Retorna 'Nomina'
        """
        if field_name not in self._fields:
            return ''
        field = self._fields[field_name]
        if field.type != 'selection':
            return ''
        field_value = getattr(self, field_name, False)
        if not field_value:
            return ''
        selection_list = field._description_selection(self.env)
        selection_dict = dict(selection_list)
        return selection_dict.get(field_value, '')

    def _update_prima_cesantias_dates(self, slip, slip_data):
        """Actualiza las fechas de prima y cesantías en la nómina."""
        service = PayslipHistoryService(slip)
        service.update_prima_cesantias_dates(slip_data)

    def _get_base_local_dict(self):
        """
        Retorna el dict base con utilidades para safe_eval.
        Estructura NATIVA de Odoo 18.
        """
        return {
            'float_round': float_round,
            'float_compare': float_compare,
            'relativedelta': relativedelta,
            'ceil': math.ceil,
            'floor': math.floor,
            'UserError': UserError,
            'date': date,
            'datetime': datetime,
            'defaultdict': defaultdict,
            'to_decimal': to_decimal,
            'round_up_to_hundred': round_up_to_hundred,
            'calculate_contribution': calculate_contribution,
            'Decimal': Decimal,
        }

    def _get_localdict(self):
        """
        Retorna localdict con estructura NATIVA Odoo 18 SIMPLIFICADA.

        OPTIMIZACIÓN: Si existe payroll_batch_context en el contexto,
        usa datos pre-cargados para evitar consultas repetidas.

        CAMBIOS vs versión anterior:
        - Usa DefaultDictPayroll nativo SOLO para 'categories' y 'rules'
        - rules incluye: total, amount, quantity, rate, category_id, rule, has_leave
        """
        self.ensure_one()

        # OPTIMIZACIÓN: Verificar si hay contexto de lote disponible
        batch_ctx = self.env.context.get('payroll_batch_context')

        input_list = [line.code for line in self.input_line_ids if line.code]
        cnt = Counter(input_list)
        multi_input_lines = [k for k, v in cnt.items() if v > 1]
        same_type_input_lines = {
            line_code: [line for line in self.input_line_ids if line.code == line_code]
            for line_code in multi_input_lines
        }

        rules_collection = RulesCollection()

        # Obtener parámetros anuales (OPTIMIZADO si hay batch_ctx)
        if batch_ctx:
            annual_params = batch_ctx.get_annual_parameters()
        else:
            search_year = self.date_to.year if self.date_to else None
            company_id = self.company_id.id if self.company_id else self.env.company.id

            # Usar método get_for_year que maneja búsqueda por empresa y fallbacks
            annual_params = self.env['hr.annual.parameters'].get_for_year(
                self.date_to.year, company_id=company_id, raise_if_not_found=False
            )

        localdict = {
            **self._get_base_local_dict(),
            **{
                'categories': CategoryCollection(),
                'rules': rules_collection,
                'rules_computed': RulesComputedCompat(rules_collection),  # Compatibilidad Odoo 15/17

                'payslip': self,
                'worked_days': {line.code: line for line in self.worked_days_line_ids if line.code},
                'inputs': {line.code: line for line in self.input_line_ids if line.code},
                'employee': self.employee_id,
                'contract': self.contract_id,
                'same_type_input_lines': same_type_input_lines,

                'slip': self,
                'wage': self.contract_id.wage if self.contract_id else 0,
                'annual_parameters': annual_params,
                '_batch_context': batch_ctx,  # Referencia al contexto para uso posterior
            }
        }

        # Agregar informacion de ausencias al localdict para uso en reglas (ej: IBD)
        # El detalle incluye ibc_day que puede ser diferente al valor pagado
        try:
            novelties_service = PeriodNoveltiesService(self.env, self, batch_ctx)
            ausencias_info = novelties_service.get_ausencias()
            localdict['ausencias'] = ausencias_info
        except Exception:
            localdict['ausencias'] = {'detalle': [], 'total_valor': 0}

        return localdict

    def _sum_salary_rule_category(self, localdict, category, amount, rule_code=None, line_id=None):
        """
        Suma recursivamente el monto en la categoría y sus padres.
        Usa estructura NATIVA Odoo 18 con tracking de líneas y reglas.

        Args:
            localdict: Diccionario local de contexto
            category: Objeto hr.salary.rule.category
            amount: Monto a sumar
            rule_code: Código de la regla que contribuye (opcional)
            line_id: ID de la línea de nómina (opcional, se generará después)
        """
        if category.parent_id:
            localdict = self._sum_salary_rule_category(localdict, category.parent_id, amount, rule_code, line_id)

        categories = localdict['categories']
        cat_data = categories.get(category.code)

        if not cat_data:
            from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_data_structures import CategoryData
            cat_data = CategoryData(code=category.code)
            categories.add_category(cat_data)

        cat_data.add_value(amount=amount, rule_code=rule_code)

        if rule_code and rule_code not in cat_data.rule_codes:
            cat_data.rule_codes.append(rule_code)

        if line_id and line_id not in cat_data.line_ids:
            cat_data.line_ids.append(line_id)

        return localdict

    def _sum_salary_rule(self, localdict, rule, amount, quantity=1.0, rate=100.0,
                         has_leave=False, leave_id=0, leave_novelty='', leave_liquidacion_value=''):
        """
        Actualiza la suma de reglas usando RulesCollection (Odoo 18).

        Usa RuleData objects que son tipo-seguros y se acumulan automáticamente.
        """
        from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_data_structures import RuleData

        rules = localdict['rules']
        existing_rule = rules.get(rule.code)

        if existing_rule:
            leave_id = leave_id or existing_rule.leave_id
            leave_novelty = leave_novelty or existing_rule.leave_novelty
            leave_liquidacion_value = leave_liquidacion_value or existing_rule.leave_liquidacion_value

        rule_data = RuleData(
            code=rule.code,
            total=amount,
            amount=amount,
            quantity=quantity,
            rate=rate,
            category_id=rule.category_id.id if rule.category_id else 0,
            category_code=rule.category_id.code if rule.category_id else '',
            rule_id=rule.id,
            rule=rule,
            has_leave=has_leave or (existing_rule.has_leave if existing_rule else False),
            leave_id=leave_id,
            leave_novelty=leave_novelty,
            leave_liquidacion_value=leave_liquidacion_value,
            payslip_id=self.id,
        )

        rules.add_rule(rule_data)

        return localdict

    def _get_payslip_lines_lavish(self) -> list[dict[str, Any]]:
        """
        Calcula las lineas de nomina para un payslip.

        IMPORTANTE: Este metodo debe llamarse con un solo registro (self.ensure_one()).
        Si se necesita procesar multiples nominas, llamar en un loop externo.
        """
        self.ensure_one()  # Garantiza que solo se procesa un registro

        if not self.contract_id:
            raise UserError(_("No hay ningun contrato establecido en La nomina %s para %s. Verifique que haya al menos un contrato establecido en el formulario del empleado.", self.name, self.employee_id.name))

        localdict = self.env.context.get('force_payslip_localdict', None) or self._get_localdict()
        result_leave = {}
        result = {}
        absence_dict = self._calculate_absences()
        localdict, result_leave = self._update_localdict_for_absences(localdict, absence_dict)
        localdict, result = self._calculate_absences_and_update_dict(self, localdict)
        result = self._process_salary_rules(self, localdict, result)

        combined_result = {**result_leave, **result}
        return list(combined_result.values())  

    def _calculate_absences_and_update_dict(self, payslip:'HrPayslip', localdict:dict[str,Any]) -> tuple[dict[str,Any], dict[str,Any]]:
        """
        Procesa conceptos y actualiza el diccionario local.

        OPTIMIZACIÓN: Si existe payroll_batch_context, usa conceptos pre-cargados
        en lugar de acceder a concepts_ids por cada nómina (evita N consultas).
        """
        result = {}
        skip_novelties = (payslip.struct_id.process == 'contrato' and not payslip.novelties_payroll_concepts)
        applicable_rules = payslip._get_rules_to_process()

        # OPTIMIZACIÓN: Obtener conceptos de contrato
        batch_ctx = localdict.get('_batch_context')
        contract_id = localdict['contract'].id

        if batch_ctx:
            # Usar conceptos pre-cargados del batch context
            contract_concepts = batch_ctx.get_contract_concepts(contract_id)
        else:
            # Fallback: acceder directamente (legacy)
            contract_concepts = localdict['contract'].concepts_ids.filtered(lambda l: l.state in ['done', 'closed'])

        # 1. Procesar conceptos de contrato
        # OPTIMIZACIÓN: Separar conceptos por tipo de regla para procesamiento eficiente
        for concept in contract_concepts.filtered(lambda l: l.state in ['done', 'closed']):
            if skip_novelties:
                continue
            
            rule = concept.input_id
            if not rule:
                continue
                
            # OPTIMIZACIÓN: Solo saltar reglas con amount_select='code' que computan por código Python
            # Las reglas con amount_select='concept' DEBEN procesarse aquí porque su lógica
            # está en el método del concepto, no en código Python evaluado
            if rule.amount_select == 'code':
                continue

            # EMBARGO: Los conceptos tipo Embargo (E) se procesan desde reglas salariales
            # usando _embargo001() a _embargo005() que tienen límites legales CST Art. 154
            if concept.type_deduction == 'E':
                continue
            
            # Verificar si la regla es aplicable antes de procesar el concepto
            if rule.id not in applicable_rules.ids:
                continue

            # ANTI-DUPLICACION: Verificar si el concepto ya fue liquidado en otra nómina del período
            # Evita doble cómputo cuando: vacaciones + nómina, o nómina + liquidación
            if self._concept_already_computed(payslip, concept, rule):
                continue

            # OPTIMIZACIÓN: Para reglas tipo 'concept', ejecutar directamente sin evaluación previa
            # La lógica de si debe ejecutarse está dentro del método del concepto mismo
            concept_process_result = concept.get_computed_amount_for_payslip(
                payslip=payslip,
                date_from=payslip.date_from,
                date_to=payslip.date_to,
                localdict=localdict
            )
            if not concept_process_result.get('create_line', False):
                continue
            line_values = concept_process_result.get('values', {})
            code = rule.code
            name = line_values.get('name', concept.input_id.name)
            amount = line_values.get('amount', 0.0)
            quantity = line_values.get('quantity', 1.0)
            rate = line_values.get('rate', 100.0)
            if amount == 0 and not concept_process_result.get('force_create', False):
                continue
            localdict, result = self._create_concept_line(
                    localdict, 
                    concept, 
                    amount,
                    concept_process_result,
                    name,
                    result
                )
        if payslip.loan_installment_ids:
            for installment in payslip.loan_installment_ids:
                localdict, result = self._create_loan_line(
                    localdict,
                    installment,
                    result
                )

        # OPTIMIZACIÓN: Obtener novedades diferentes
        employee_id = localdict['employee'].id
        if batch_ctx:
            # Usar novedades pre-cargadas del batch context
            obj_novelties = batch_ctx.get_employee_novelties(employee_id)
        else:
            # Fallback: consulta directa (legacy)
            obj_novelties = self.env['hr.novelties.different.concepts'].search([
                ('employee_id', '=', employee_id),
                ('date', '>=', localdict['slip'].date_from),
                ('date', '<=', localdict['slip'].date_to)
            ])

        for concepts in obj_novelties:
            if concepts.amount != 0 and self._should_process_novelty(concepts, payslip):
                localdict, result = self._update_localdict_for_novelty(localdict, concepts, result)
        return localdict, result
    def _create_loan_line(self, localdict, installment, result):
        """Crea una línea para una cuota de préstamo."""
        service = PayslipLineCalculationService(self)
        return service.create_loan_line(localdict, installment, result)
    
    def _should_process_novelty(self, novelty, payslip):
        """Determina si una novedad debe ser procesada según estructuras y condiciones."""
        service = PayslipLineCalculationService(payslip)
        return service.should_process_novelty(novelty, payslip)

    def _process_salary_rules(self, payslip, localdict, result):
        # Convertir categories y rules a objetos tipo-seguros ANTES de procesar reglas
        self._convert_localdict_to_collections(localdict)

        rules_to_process = self._get_rules_to_process()
        blacklisted_rule_ids = self.env.context.get('prevent_payslip_computation_line_ids', [])
        rule_results = {}
        overrides = {}
        if payslip.has_overrides or self.env.context.get('simulate_override'):
            if self.env.context.get('simulate_override'):
                overrides = {
                    self.env.context.get('override_rule'): {
                        'type': self.env.context.get('override_type'),
                        'value': self.env.context.get('override_value')
                    }
                }
            else:
                overrides = {
                    o.rule_id.code: {
                        'type': o.override_type,
                        'value': o.value_override
                    } for o in payslip.rule_override_ids.filtered('active')
                }
        for rule in sorted(rules_to_process, key=lambda x: (x.sequence, x.id)):
            if rule.id in blacklisted_rule_ids:
                continue
                
            temp_dict = localdict.copy()
            
            # OPTIMIZACIÓN: Para reglas tipo 'concept', ejecutar directamente sin evaluar condición
            # La lógica de si debe ejecutarse está dentro del método del concepto mismo
            should_execute = True
            if rule.amount_select != 'concept':
                # Solo evaluar condición para reglas que NO son tipo 'concept'
                should_execute = rule._satisfy_condition(temp_dict)
            
            if should_execute:
                amount, qty, rate, name, log, data = rule._compute_rule_lavish(temp_dict)#monto:float, cantidad:float, tasa:float, nombre:str, log:opticonal[dict,any], data:dict

                # Flag para saber si hay override de tipo 'total'
                has_total_override = False

                if rule.code in overrides:
                    override = overrides[rule.code]
                    if override['type'] == 'amount':
                        amount = override['value']
                    elif override['type'] == 'quantity':
                        qty = override['value']
                    elif override['type'] == 'rate':
                        rate = override['value']
                    elif override['type'] == 'total':
                        has_total_override = True

                # Calcular total: amount × qty × rate / 100
                if has_total_override:
                    tot_rule = overrides[rule.code]['value']
                else:
                    tot_rule = float(amount) * float(qty) * float(rate) / 100.0

                previous_amount = rule.code in temp_dict and temp_dict[rule.code] or 0.0

                temp_dict = self._sum_salary_rule_category(
                    temp_dict,
                    rule.category_id,
                    tot_rule - previous_amount,
                    rule_code=rule.code  # Tracking: agregar código de regla
                )
                temp_dict = self._sum_salary_rule(temp_dict, rule, tot_rule, qty, rate, has_leave=False)
                if rule.code in ('IBD'):
                    # Store resultado_full data for access by other rules (SSOCIAL001, SSOCIAL002, etc.)
                    if data and isinstance(data, dict):
                        ibd_payload = data.get('datos', data)
                        temp_dict['ibc_final'] = ibd_payload.get('ibc_final', 0)
                        temp_dict['vac_monto'] = ibd_payload.get('vac_monto', 0)
                        temp_dict['vac_dias'] = ibd_payload.get('vac_dias', 0)
                        temp_dict['day_value'] = ibd_payload.get('day_value', 0)
                        temp_dict['effective_days'] = ibd_payload.get('effective_days', 0)
                        temp_dict['ibc_full'] = ibd_payload.get('ibc_final', 0)

                        # Almacenar datos extra en RuleData.extra_data
                        rules = localdict['rules']
                        if 'IBD' in rules:
                            ibd_rule = rules.get('IBD')
                            if ibd_rule:
                                ibd_rule.extra_data.update({
                                    'ibc_final': ibd_payload.get('ibc_final', 0),
                                    'ibc_full': ibd_payload.get('ibc_final', 0),
                                    'vac_monto': ibd_payload.get('vac_monto', 0),
                                    'vac_dias': ibd_payload.get('vac_dias', 0),
                                    'day_value': ibd_payload.get('day_value', 0),
                                    'effective_days': ibd_payload.get('effective_days', 0),
                                })
                    if log and 'calculo' in log and 'ibc_final' in log['calculo']:
                        temp_dict['ibc_full'] += log['calculo']['ibc_final']
                        rules = localdict['rules']
                        if 'IBD' in rules:
                            ibd_rule = rules.get('IBD')
                            if ibd_rule:
                                ibd_rule.extra_data['ibc_full'] = temp_dict.get('ibc_full', 0)
                # Reglas de totalización SIEMPRE generan línea (incluso con total=0)
                # porque _compute_liquidation_totals depende de encontrar estas líneas
                _TOTALIZATION_CODES = {'TOTALDEV', 'TOTALDED', 'NET'}
                if tot_rule != 0.0 or rule.code in _TOTALIZATION_CODES:
                    # Pasar override_total solo si hay un override de tipo 'total' activo
                    # Esto evita que _process_prestacion_result sobrescriba el total ajustado
                    override_total_param = tot_rule if has_total_override else None
                    rule_results[rule.code] = self._prepare_rule_result(
                        rule, temp_dict, amount, qty, rate, name, log, payslip, data,
                        override_total=override_total_param
                    )
        result.update(rule_results)
        return result

    def _convert_localdict_to_collections(self, localdict):
        """
        Convierte localdict['categories'] y localdict['rules'] a objetos tipo-seguros.

        CATEGORIES:
        - De: {'BASIC': {'total': X, 'line_ids': [...], 'rule_codes': [...]}, ...}
        - A: CategoryCollection con CategoryData objects

        RULES:
        - De: {'BASIC': {'total': X, 'amount': Y, ...}, ...}
        - A: RulesCollection con RuleData objects

        Esto elimina la necesidad de usar .get() y garantiza tipos.
        """
        # Convertir categories a CategoryCollection
        categories_dict = localdict.get('categories', {})
        if categories_dict and not isinstance(categories_dict, CategoryCollection):
            categories_collection = CategoryCollection()

            for cat_code, cat_data in categories_dict.items():
                if isinstance(cat_data, dict):
                    # Crear CategoryData
                    category = CategoryData(
                        code=cat_code,
                        total=cat_data.get('total', 0.0),
                        rule_codes=cat_data.get('rule_codes', []),
                        line_ids=cat_data.get('line_ids', [])
                    )

                    # Agregar RuleData por cada regla en la categoría
                    for rule_code in cat_data.get('rule_codes', []):
                        # Buscar datos de la regla en localdict['rules']
                        rule_data_dict = localdict.get('rules', {}).get(rule_code, {})
                        if rule_data_dict:
                            rule_data = RuleData(
                                code=rule_code,
                                total=rule_data_dict.get('total', 0.0),
                                amount=rule_data_dict.get('amount', 0.0),
                                quantity=rule_data_dict.get('quantity', 1.0),
                                rate=rule_data_dict.get('rate', 100.0),
                                category_code=cat_code,
                                rule_id=rule_data_dict.get('rule_id', 0),
                                rule=rule_data_dict.get('rule'),
                                has_leave=rule_data_dict.get('has_leave', False),
                                payslip_id=rule_data_dict.get('payslip_id', 0)
                            )
                            category.add_rule(rule_data)

                    categories_collection.add_category(category)

            localdict['categories'] = categories_collection

        # Convertir rules a RulesCollection
        rules_dict = localdict.get('rules', {})
        if rules_dict and not isinstance(rules_dict, RulesCollection):
            rules_collection = RulesCollection()

            for rule_code, rule_data_dict in rules_dict.items():
                if isinstance(rule_data_dict, dict):
                    rule_data = RuleData(
                        code=rule_code,
                        total=rule_data_dict.get('total', 0.0),
                        amount=rule_data_dict.get('amount', 0.0),
                        quantity=rule_data_dict.get('quantity', 1.0),
                        rate=rule_data_dict.get('rate', 100.0),
                        category_code=rule_data_dict.get('category_code', ''),
                        rule_id=rule_data_dict.get('rule_id', 0),
                        rule=rule_data_dict.get('rule'),
                        has_leave=rule_data_dict.get('has_leave', False),
                        payslip_id=rule_data_dict.get('payslip_id', 0)
                    )
                    rules_collection.add_rule(rule_data)

            localdict['rules'] = rules_collection

    def _concept_already_computed(self, payslip, concept, rule):
        """Verifica si un concepto ya fue liquidado en otra nómina del período."""
        service = PayslipLineCalculationService(payslip)
        return service.concept_already_computed(payslip, concept, rule)

    def _create_concept_line(self, localdict, concept, amount, data, description, result):
        """Crea una línea de concepto y actualiza el localdict."""
        service = PayslipLineCalculationService(self)
        return service.create_concept_line(localdict, concept, amount, data, description, result)

    def _update_localdict_for_novelty(self, localdict, concepts, result):
        """Crea una línea de novedad y actualiza el localdict."""
        service = PayslipLineCalculationService(self)
        return service.create_novelty_line(localdict, concepts, result)
    
    def _prepare_rule_result(self, rule, localdict, amount, qty, rate, name, log, payslip, data, override_total=None) -> Dict[str, Union[float, str, int, Dict[str, str], bool]]:
        """
        Prepara el diccionario de resultado para una línea de nómina.

        Args:
            override_total: Total con override aplicado (opcional). Si se proporciona,
                           indica que hay un ajuste manual y se debe respetar este valor.
        """
        service = PayslipLineCalculationService(payslip)
        return service.prepare_rule_result(rule, localdict, amount, qty, rate, name, log, data, override_total=override_total)

    def _calculate_absences(self):
        """
        Calcula y agrupa las ausencias para el procesamiento de la nómina.

        Returns:
            dict: Diccionario con las ausencias agrupadas por leave_id y rule_id
        """
        return self._get_grouped_leave_days()

    def _get_grouped_leave_days(self):
        """Agrupa los días de ausencia por ausencia y regla."""
        self.ensure_one()
        temp_dict = {}
        for leave_day in self.leave_days_ids:
            composite_key = (leave_day.leave_id.id, leave_day.rule_id.id)
            if composite_key not in temp_dict:
                temp_dict[composite_key] = {
                    'name': leave_day.leave_id.name,
                    'total_days': 0,
                    'total_amount': 0,
                    'leave_type': leave_day.leave_id.holiday_status_id.name,
                    'date_from': leave_day.date,
                    'date_to': leave_day.date,
                    'rule_id': leave_day.rule_id,
                    'leave_id': leave_day.leave_id,
                    'entity_id': leave_day.leave_id.entity.id if leave_day.leave_id.entity else False,
                    'days_work': 0,
                    'days_holiday': 0,
                    'days_31': 0,
                    'days_holiday_31': 0,
                    'additional_novelties': [],
                }
            else:
                temp_dict[composite_key]['date_from'] = min(temp_dict[composite_key]['date_from'], leave_day.date)
                temp_dict[composite_key]['date_to'] = max(temp_dict[composite_key]['date_to'], leave_day.date)
                
            # Acumular los días y montos
            temp_dict[composite_key]['total_days'] += leave_day.days_payslip
            temp_dict[composite_key]['total_amount'] += leave_day.amount
            temp_dict[composite_key]['days_work'] += leave_day.days_work
            temp_dict[composite_key]['days_holiday'] += leave_day.days_holiday
            temp_dict[composite_key]['days_31'] += leave_day.days_31
            temp_dict[composite_key]['days_holiday_31'] += leave_day.days_holiday_31
            
            # Agregar novedad individual con información de variación de porcentaje
            temp_dict[composite_key]['additional_novelties'].append({
                'date': leave_day.date,
                'amount': leave_day.amount,
                'days': leave_day.days_payslip,
                'days_work': leave_day.days_work,
                'days_holiday': leave_day.days_holiday,
                'days_31': leave_day.days_31,
                'days_holiday_31': leave_day.days_holiday_31,
                # Información adicional para incapacidades
                'sequence': getattr(leave_day, 'sequence', 0),
                'rate_applied': getattr(leave_day, 'rate_applied', 100),
                'ibc_day': getattr(leave_day, 'ibc_day', 0),
                'ibc_base': getattr(leave_day, 'ibc_base', 0),
                'base_type': getattr(leave_day, 'base_type', 'wage'),
            })
        
        absence_dict = {}
        for (leave_id, rule_id), data in temp_dict.items():
            composite_key = f"{leave_id}_{rule_id}"
            absence_dict[composite_key] = {
                'name': data['name'],
                'total_days': data['total_days'],
                'total_amount': data['total_amount'],
                'leave_type': data['leave_type'],
                'date_from': data['date_from'],
                'date_to': data['date_to'],
                'rule_id': data['rule_id'],
                'leave_id': data['leave_id'],
                'entity_id': data['entity_id'],
                'days_work': data['days_work'],
                'days_holiday': data['days_holiday'],
                'days_31': data['days_31'],
                'days_holiday_31': data['days_holiday_31'],
            }
            
            # Ordenar las novedades por fecha
            data['additional_novelties'].sort(key=lambda x: x['date'])
            absence_dict[composite_key]['additional_novelties'] = data['additional_novelties']
        return absence_dict

    def _update_localdict_for_absences(self, localdict, absence_dict):
        result = {}
        for leave_id, absence_data in absence_dict.items():
            if not absence_data['rule_id']:
                continue

            # Para prima/cesantias/intereses_cesantias, solo procesar ausencias NO PAGADAS
            # (para descontar dias). Omitir ausencias PAGADAS (incapacidades, licencias remuneradas)
            if self.struct_process in ['prima', 'cesantias', 'intereses_cesantias']:
                leave = absence_data['leave_id']
                if not leave:
                    continue  # Omitir ausencias sin leave_id
                leave_type = leave.holiday_status_id if leave else None
                is_unpaid = getattr(leave_type, 'unpaid_absences', False) if leave_type else False
                if not leave:
                    continue  # Omitir ausencias pagadas en prima/cesantias

            concept = {
                'input_id': absence_data['rule_id'],
                'leave_id': absence_data['leave_id'],
                'partner_id': absence_data['entity_id'],
                'loan_id': False,
                'days': absence_data['total_days'],
                'days_work': absence_data['days_work'],
                'days_holiday': absence_data['days_holiday'],
                'days_31': absence_data['days_31'],
                'days_holiday_31': absence_data['days_holiday_31'],
                'leave_type': absence_data['leave_type'],
                'date_from': absence_data['date_from'],
                'date_to': absence_data['date_to'],
                # Información de líneas individuales para variación de porcentaje
                'additional_novelties': absence_data.get('additional_novelties', []),
            }
            tot_rule = absence_data['total_amount']

            localdict, result = self._update_localdict_for_leave(localdict, concept, tot_rule, result)

        return localdict, result
    
    def _update_localdict_for_leave(self, localdict, concept, tot_rule, result):
        """Crea una línea de ausencia y actualiza el localdict."""
        service = PayslipLineCalculationService(self)
        return service.create_leave_line(localdict, concept, tot_rule, result)
        
    def action_update_vacation_data(self):
        """Actualiza los datos de vacaciones de una nómina ya confirmada."""
        self.ensure_one()
        service = PayslipHistoryService(self)
        return service.update_vacation_data()
        
    def get_holiday_book(self, contract, date_from=False, date_ref=False):
        """
        Calcula los días de vacaciones acumulados y disponibles para un empleado
        
        Args:
            contract: Contrato del empleado
            date_ref: Fecha de referencia para el cálculo (por defecto, fecha actual)
            
        Returns:
            dict: Diccionario con información de días trabajados, disponibles, disfrutados, etc.
        """
        date_ref = date_ref or contract.date_ref_holiday_book or self.date_to
        worked_days = days360(date_from, date_ref)
        
        days_enjoyed, days_paid, days_suspension = 0, 0, 0
        
        for holiday_book in contract.vacaciones_ids:
            days_enjoyed += holiday_book.business_units
        
        leave_domain = [
            ("leave_id.employee_id", "=", contract.employee_id.id),
            ("leave_id.state", "=", "validate"),
            ("leave_id.unpaid_absences", "=", True),
            ("date", ">=", date_from),
            ("date", "<=", date_ref),
        ]
        grouped = self.env["hr.leave.line"]._read_group(
            leave_domain,
            groupby=[],
            aggregates=["days_payslip:sum"],
        )
        days_suspension = float(grouped[0][0] or 0.0) if grouped else 0.0

        worked_days_adjusted = worked_days - days_suspension

        days_left = (worked_days_adjusted * 15 / DAYS_YEAR) - days_enjoyed
        return {
            'worked_days': round_1_decimal(worked_days),
            'worked_days_adjusted': round_1_decimal(worked_days_adjusted),
            'days_left': round_1_decimal(days_left),
            'days_enjoyed': round_1_decimal(days_enjoyed),
            'days_paid': round_1_decimal(days_paid),
            'days_suspension': round_1_decimal(days_suspension),
        }

    def _get_rules_to_process(self):
        """
        Obtiene las reglas salariales a procesar según el tipo de estructura.

        OPTIMIZACIÓN: Si existe payroll_batch_context, usa reglas pre-cargadas
        en lugar de hacer múltiples consultas a la BD.
        """
        self.ensure_one()
        process = self.struct_id.process

        # OPTIMIZACIÓN: Verificar si hay contexto de lote disponible
        batch_ctx = self.env.context.get('payroll_batch_context')

        if batch_ctx:
            # Usar reglas pre-cargadas del contexto
            def get_specific_rules(proc):
                return batch_ctx.get_rules_for_process(proc, include_common=False)

            common_rules = batch_ctx.get('salary_rules', {}).get('common', self.env['hr.salary.rule'])
            rules_by_code = batch_ctx.get('salary_rules', {}).get('by_code', {})
            rules_by_category = batch_ctx.get('salary_rules', {}).get('by_category', {})
        else:
            # Método legacy - consultas directas
            def get_specific_rules(proc):
                return self.env['hr.salary.rule'].search([
                    ('struct_id.process', '=', proc),
                    ('active', '=', True)
                ])

            common_rules = self.env['hr.salary.rule'].search([
                ('code', 'in', ['TOTALDEV', 'TOTALDED', 'NET']),
                ('active', '=', True)
            ])
            rules_by_code = {}
            rules_by_category = {}

        if process == 'nomina':
            rules = get_specific_rules('nomina')
            if self.pay_primas_in_payroll:
                rules |= get_specific_rules('prima')
            if self.pay_cesantias_in_payroll:
                if batch_ctx and 'INTCES_YEAR' in rules_by_code:
                    rules |= rules_by_code['INTCES_YEAR']
                else:
                    rules |= self.env['hr.salary.rule'].search([('code','=','INTCES_YEAR')])
            if self.pay_vacations_in_payroll:
                if batch_ctx:
                    for code in ('VACDISFRUTADAS', 'VAC001', 'VAC002'):
                        if code in rules_by_code:
                            rules |= rules_by_code[code]
                else:
                    rules |= self.env['hr.salary.rule'].search([('code','in',('VACDISFRUTADAS','VAC001','VAC002'))])

        elif process == 'vacaciones':
            # Reglas base de vacaciones
            vac_codes = ['VACDISFRUTADAS','VACATIONS_MONEY','SSOCIAL001','SSOCIAL002','VAC001','VAC002','IBD','IBC_R', 'TOTALDEV', 'TOTALDED', 'NET']
            if batch_ctx:
                rules = self.env['hr.salary.rule']
                for code in vac_codes:
                    if code in rules_by_code:
                        rules |= rules_by_code[code]
            else:
                rules = self.env['hr.salary.rule'].search([('code', 'in', vac_codes)])

            # AGREGAR PROVISIONES
            if batch_ctx and 'PROV' in rules_by_category:
                rules |= rules_by_category['PROV']
            else:
                provision_rules = self.env['hr.salary.rule'].search([
                    ('category_id.code', '=', 'PROV'),
                    ('active', '=', True)
                ])
                rules |= provision_rules

        elif process in ['prima', 'cesantias', 'intereses_cesantias']:
            rules = get_specific_rules(process)

        elif process == 'contrato':
            rules = get_specific_rules('nomina') | get_specific_rules('prima') | \
                    get_specific_rules('cesantias') | get_specific_rules('intereses_cesantias') | \
                    get_specific_rules('vacaciones')
            if self.have_compensation:
                rules |= self.struct_id.rule_ids
            if not self.settle_payroll_concepts:
                # Filtrar reglas de nómina pero SIEMPRE mantener las provisiones
                rules = rules.filtered(lambda r: r.struct_id.process != 'nomina' or r.category_id.code == 'PROV')
            # AGREGAR PROVISIONES explícitamente para liquidación de contrato
            if batch_ctx and 'PROV' in rules_by_category:
                rules |= rules_by_category['PROV']
            else:
                provision_rules = self.env['hr.salary.rule'].search([
                    ('category_id.code', '=', 'PROV'),
                    ('active', '=', True)
                ])
                rules |= provision_rules
            if self.no_days_worked:
                rules = rules.filtered(lambda r: r.category_id.code not in ('BASIC','AUX'))
            if not self.novelties_payroll_concepts:
                rules = rules.filtered(lambda r: r.type_concepts != 'novedad')
        else:
            rules = self.struct_id.rule_ids

        return rules | common_rules

    def _round1(self, amount: Decimal | float) -> Decimal:
        """Redondea al entero más cercano usando función centralizada."""
        return round_payroll_amount(amount, decimals=0)

    def _round100(self, amount):
        """Redondea al múltiplo de 100 usando función centralizada."""
        return round_to_100(amount)

    def _round1000(self, amount):
        """Redondea al múltiplo de 1000 usando función centralizada."""
        return round_to_1000(amount)

    @api.depends('line_ids')
    def _compute_concepts_category(self):
        category_mapping = {
            'EARNINGS': ['BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO', 'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC', 'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA', 'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'],
            'DEDUCTIONS': ['DED', 'DEDUCCIONES', 'TOTALDED', 'SANCIONES', 'DESCUENTO_AFC', 'SSOCIAL'],
            'PROVISIONS': ['PROV'],
            'OUTCOME': ['NET']}
        categorized_lines = {
            'EARNINGS': [],
            'DEDUCTIONS': [],
            'PROVISIONS': [],
            'BASES': [],
            'OUTCOME': []}
        for payslip_line in self.line_ids:
            category_found = False
            for category, codes in category_mapping.items():
                if payslip_line.category_id.code in codes or payslip_line.category_id.parent_id.code in codes:
                    categorized_lines[category].append(payslip_line.id)
                    category_found = True
                    break
            if not category_found:
                categorized_lines['BASES'].append(payslip_line.id)
        for category, line_ids in categorized_lines.items():
            setattr(self, f'{category.lower()}_ids', self.env['hr.payslip.line'].browse(line_ids))
    
    def _get_payslip_line_total(self, amount, quantity, rate, rule):
        """
        Calcula el total de una línea de nómina.

        IMPORTANTE: TODAS las líneas se redondean a entero (sin decimales) para evitar descuadres contables.
        Esto incluye:
        - Devengos individuales (BASIC, HED, HEN, REC, etc.)
        - Deducciones (SSOCIAL, préstamos, retenciones, etc.)
        - Provisiones (PROV) - también redondeadas desde v1.2
        - Totales (NET, TOTALDEV, TOTALDED)

        La línea NET absorbe automáticamente cualquier diferencia mínima de redondeo
        ya que se calcula como: NET = TOTALDEV - TOTALDED (ambos redondeados).

        Args:
            amount: Monto base
            quantity: Cantidad
            rate: Tasa porcentual
            rule: Regla salarial

        Returns:
            float: Total redondeado a entero (sin decimales)
        """
        self.ensure_one()
        total = amount * quantity * rate / 100.0
        return round(total) 

    @api.depends(
        'payslip_run_id',
        'payslip_run_id.name',
        'struct_id',
        'struct_id.name',
        'employee_id',
        'employee_id.name',
        'date_from'
    )
    def _compute_display_name(self):
        for record in self:
            employee_name = record.employee_id.name if record.employee_id else ''
            if record.payslip_run_id:
                record.display_name = "{} - {}".format(
                    record.payslip_run_id.name,
                    employee_name
                )
            else:
                struct_name = record.struct_id.name if record.struct_id else ''
                record.display_name = "{} - {} - {}".format(
                    struct_name,
                    employee_name,
                    str(record.date_from)
                )

    def get_hr_payslip_reports_template(self):
        type_report = self.struct_process if self.struct_process != 'otro' else 'nomina'
        obj = self.env['hr.payslip.reports.template'].search([('company_id','=',self.employee_id.company_id.id),('type_report','=',type_report)])
        if len(obj) == 0:
            raise ValidationError(_('No tiene configurada plantilla de liquidacion. Por favor verifique!'))
        return obj

    def get_pay_vacations_in_payroll(self):
        return bool(self.env['ir.config_parameter'].sudo().get_param('lavish_hr_payroll.pay_vacations_in_payroll')) or False

    @api.onchange('employee_id', 'struct_id', 'contract_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return
        employee = self.employee_id
        date_from = self.date_from
        date_to = self.date_to
        self.company_id = employee.company_id
        if not self.contract_id or self.employee_id != self.contract_id.employee_id:  # Add a default contract if not already defined
            contracts = employee._get_contracts(date_from, date_to, states=['open', 'finished'])
            default_structure = False
            if contracts:
                struct_type = contracts[0].structure_type_id
                if hasattr(struct_type, '_get_default_struct_id'):
                    default_structure = struct_type._get_default_struct_id()
                else:
                    default_structure = getattr(struct_type, 'default_struct_id', False)
            if not contracts or not default_structure:
                self.contract_id = False
                self.struct_id = False
                return
            self.contract_id = contracts[0]
            self.struct_id = default_structure
        days_diff = (date_to - date_from).days + 1
        period_type = 'monthly' if days_diff > 15 else 'bi-monthly'
        period = self.env['hr.period'].get_period(
            date_from, 
            date_to,
            period_type,
            self.company_id.id
        )
        if period:
            self.period_id = period.id
        else:
            self.assign_periods_to_draft_payslips()
            self.period_id = self.env['hr.period'].get_period(date_from, date_to, period_type, self.company_id.id).id
        payslip_name = self.struct_id.payslip_name or _('Recibo de Salario')
        
        mes = self.date_from.month
        month_name = self.get_name_month(mes)
        
        date_name = month_name + ' ' + str(self.date_from.year)
        self.name = '%s - %s - %s' % (payslip_name, self.employee_id.name or '', date_name)
        self.analytic_account_id = self.contract_id.analytic_account_id
        
        if date_to > date_utils.end_of(fields.Date.today(), 'month'):
            self.warning_message = _("This payslip can be erroneous! Work entries may not be generated for the period from %s to %s." %
                (date_utils.add(date_utils.end_of(fields.Date.today(), 'month'), days=1), date_to))
        else:
            self.warning_message = False
            
    def get_name_month(self, month_number):
        """
        Obtiene el nombre del mes en español.
        Delega a la función común get_month_name.
        """
        return get_month_name(month_number)
    
    def compute_sheet(self):
        for payslip in self.filtered(lambda slip: slip.state not in ['cancel', 'done','paid']):
            payslip.compute_slip()

    def action_payslip_draft(self):
        for payslip in self:
            payslip.payslip_day_ids.unlink()
            for line in payslip.input_line_ids:
                if line.loan_line_id:
                    line.loan_line_id.paid = False
                    line.loan_line_id.payslip_id = False
                    line.loan_line_id.loan_id._compute_loan_amount()
            payslip.leave_ids.leave_id.line_ids.filtered(lambda l: l.date <= payslip.date_to).write({'payslip_id': False})
        return self.write({'state': 'draft'})

    def restart_payroll(self):
        for payslip in self:
            for line in payslip.input_line_ids:
                if line.loan_line_id:
                    line.loan_line_id.paid = False
                    line.loan_line_id.payslip_id = False
                    line.loan_line_id.loan_id._compute_loan_amount()
            payslip.leave_ids.leave_id.line_ids.filtered(lambda l: l.date <= payslip.date_to).write({'payslip_id': False})
            payslip.mapped('move_id').unlink()
            obj_payslip_line = self.env['hr.payslip.line'].search(
                [('slip_id', '=', payslip.id), ('loan_id', '!=', False)])
            for payslip_line in obj_payslip_line:
                obj_loan_line = self.env['hr.loan.installment'].search(
                    [('employee_id', '=', payslip_line.employee_id.id),
                     ('payslip_id', '>=', payslip.id)])
                if payslip.struct_id.process == 'contrato' and payslip_line.loan_id.final_settlement_contract == True:
                    obj_loan_line.unlink()
                else:
                    obj_loan_line.write({
                        'paid': False,
                        'payslip_id': False
                    })
                obj_loan = self.env['hr.loan'].search(
                    [('employee_id', '=', payslip_line.employee_id.id), ('id', '=', payslip_line.loan_id.id)])
                #if obj_loan.balance_amount > 0:
                #    self.env['hr.contract.concepts'].search([('loan_id', '=', payslip_line.loan_id.id)]).write(
                #        {'state': 'done'})
            payslip.line_ids.unlink()
            payslip.action_payslip_draft()            

    #--------------------------------------------------LIQUIDACIÓN DE LA NÓMINA PERIÓDICA---------------------------------------------------------#

    @api.depends('line_ids.total')
    def _compute_basic_net(self):
        line_values = (self._origin)._get_line_values(['BASIC', 'BASIC002', 'BASIC003', 'GROSS',  'TOTALDEV', 'NET'])
        for payslip in self:
            payslip.basic_wage = line_values['BASIC'][payslip._origin.id]['total'] + line_values['BASIC002'][payslip._origin.id]['total'] + line_values['BASIC003'][payslip._origin.id]['total']
            payslip.gross_wage = line_values['GROSS'][payslip._origin.id]['total'] + line_values['TOTALDEV'][payslip._origin.id]['total']
            payslip.net_wage = line_values['NET'][payslip._origin.id]['total']

    def _get_history_key_fields(self, model_name):
        """Define campos clave para cada modelo de historial."""
        service = PayslipHistoryService(self)
        return service.get_history_key_fields(model_name)
    
    def _create_or_update_history(self, model_name, values):
        """Crea o actualiza cualquier historial basado en campos clave."""
        service = PayslipHistoryService(self)
        return service.create_or_update_history(model_name, values)
    
    def _get_vacation_values(self, record, line):
        """Obtiene valores de vacaciones según el código de línea."""
        service = PayslipHistoryService(record)
        return service.get_vacation_values(line)
    
    def _get_severance_values(self, record, line_cesantias=None, line_interes=None):
        """Obtiene valores consolidados de cesantías e intereses."""
        service = PayslipHistoryService(record)
        return service.get_severance_values(line_cesantias, line_interes)
    
    def _process_history_lines(self, record):
        """Procesa todas las líneas de historial (vacaciones, cesantías, prima)."""
        service = PayslipHistoryService(record)
        service.process_history_lines()
    
    def _process_loans_and_reverse_payments(self, record):
        """
        Procesa préstamos y pagos inversos en un solo método
        """
        for line in record.input_line_ids.filtered(lambda l: l.loan_line_id):
            line.loan_line_id.write({'paid': True, 'payslip_id': record.id})
            line.loan_line_id.loan_id._compute_loan_amount()
        
        for line in record.line_ids.filtered(lambda l: l.loan_id):
            installments = self.env['hr.loan.installment'].search([
                ('employee_id', '=', line.employee_id.id),
                ('date', '>=', record.date_from),
                ('date', '<=', record.date_to)
            ])
            installments.write({'paid': True, 'payslip_id': record.id})
            
            #if line.loan_id.balance_amount <= 0:
            #    self.env['hr.contract.concepts'].search([
            #        ('loan_id', '=', line.loan_id.id)
            #    ]).write({'state': 'cancel'})
        
        for payment in record.severance_payments_reverse.filtered(lambda p: p.payslip):
            lines_to_update = {}
            for line in payment.payslip.line_ids:
                if line.code in ('CESANTIAS', 'INTCESANTIAS'):
                    lines_to_update[line.code] = line.total
                    line.write({'amount': 0})

            observation = payment.payslip.observation or ''
            new_obs = f"El valor se trasladó a la liquidación {record.number} de {record.struct_id.name}"
            payment.payslip.write({
                'observation': f"{observation}\n{new_obs}" if observation else new_obs
            })
    
    def action_payslip_done(self):
        """
        Versión ultra optimizada del método de confirmación de nómina
        """
        if any(slip.state == 'cancel' for slip in self):
            raise ValidationError(_("You can't validate a cancelled payslip."))

        self.write({'state': 'done'})
        self.mapped('payslip_run_id').action_close()
        self._action_create_account_move()

        for record in self:
            if record.number == '/':
                record._set_next_sequence()

            self._process_history_lines(record)
            self._process_loans_and_reverse_payments(record)
            if record.struct_id.process == 'contrato':
                record.contract_id.write({
                    'retirement_date': record.date_liquidacion,
                    'state': 'close'
                })

            # Auto-generar/actualizar seguridad social del período
            record._update_social_security()

    def _update_social_security(self):
        """
        Auto-genera o actualiza la seguridad social del período cuando se confirma una nómina.
        Este método:
        1. Verifica si existe un registro de seguridad social para el período de la nómina
        2. Si NO existe, lo crea y ejecuta cálculo COMPLETO para todos los empleados del período
        3. Si YA existe y está en borrador, ejecuta el cálculo solo para el empleado de esta nómina
        4. Si está contabilizado, no hace nada (no se puede modificar)
        """
        self.ensure_one()

        # Solo procesar nóminas normales (no liquidaciones ni otras estructuras especiales)
        if self.struct_id.process != 'normal':
            return

        # Verificar que la nómina tenga fecha de inicio
        if not self.date_from:
            return

        # Buscar o crear registro de seguridad social para este período
        SocialSecurity = self.env['hr.payroll.social.security']

        year = self.date_from.year
        month = str(self.date_from.month)

        ss_record = SocialSecurity.search([
            ('year', '=', year),
            ('month', '=', month),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        # Determinar si es creación nueva o actualización
        is_new_record = not ss_record

        # Si no existe, crear el registro de seguridad social
        if is_new_record:
            ss_record = SocialSecurity.create({
                'year': year,
                'month': month,
                'company_id': self.company_id.id,
                'state': 'draft',
            })

        # Si el registro está en estado contabilizado, no modificar
        if ss_record.state == 'accounting':
            return

        # Ejecutar cálculo de seguridad social
        try:
            if is_new_record:
                # Primera vez: Calcular COMPLETO (todos los empleados del período)
                ss_record.executing_social_security()
                ss_record.message_post(
                    body=f"Seguridad social calculada automáticamente al confirmar nómina {self.number} del empleado {self.employee_id.name}. "
                         f"Se procesaron todos los empleados con nóminas confirmadas en el período {month}/{year}.",
                    subject="Cálculo Automático de Seguridad Social"
                )
            else:
                # Ya existe: Actualizar solo este empleado
                ss_record.executing_social_security(employee_id=self.employee_id.id)

        except Exception as e:
            # Si hay error, generar mensaje en el chatter y loguear
            error_msg = f"Error al calcular seguridad social para nómina {self.number} del empleado {self.employee_id.name}: {str(e)}"

            # Mensaje en el chatter del registro de seguridad social
            ss_record.message_post(
                body=error_msg,
                subject="Error en Cálculo de Seguridad Social",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            # Log de error
            _logger.error(error_msg)

            # No detener la confirmación de la nómina, solo notificar

    def check_payslips_without_period(self):
        """
        Busca nóminas sin período asignado.
        Delega al servicio PeriodCalculationService.
        """
        return PeriodCalculationService.check_payslips_without_period(self.env)

    def assign_periods_to_draft_payslips(self):
        """
        Asigna períodos a nóminas sin período.
        Delega al servicio PeriodCalculationService.
        """
        return PeriodCalculationService.assign_periods_to_draft_payslips(
            self.env,
            self.env.company.id
        )

    def _get_entry_types(self):
        """
        Obtiene tipos de entrada de trabajo necesarios para el cálculo.
        Busca y carga los tipos de entrada de trabajo utilizados en el
        cálculo de días trabajados y valida que todos existan en el sistema.
        
        Returns:
            dict: Diccionario con los tipos de entrada encontrados
            
        Raises:
            UserError: Si algún tipo de entrada requerido no existe
        """
        types = {}
        missing_types = []
        for code, name in [
            ('WORK131', 'days31'), ('OUT', 'outdays'), ('WORK100', 'wdays'),
            ('WORK_D', 'wdayst'), ('PREV_PAYS', 'prevdays')
        ]:
            entry_type = self.env['hr.work.entry.type'].search([("code", "=", code)], limit=1)
            if not entry_type:
                missing_types.append(code)
            else:
                types[name] = entry_type
        
        if missing_types:
            raise UserError(_(f"Faltan tipos de entrada: {', '.join(missing_types)}"))
            
        return types
    
    def _validate_leave_types(self):
        """
        Valida que los tipos de ausencia estén correctamente configurados.
        Delega al servicio LeaveCalculationService.

        Returns:
            bool: True si todos los tipos están correctamente configurados
        """
        service = LeaveCalculationService(self)
        return service.validate_leave_types()
    
    def _action_compute_worked_days(self):
        """
        Calcula los días trabajados para la nómina.
        
        Este método integra la validación de tipos de ausencia,
        carga los tipos de entrada necesarios y calcula las líneas
        de días trabajados para la nómina.
        """
        for payslip in self:
            payslip.worked_days_line_ids.unlink()
            payslip._validate_leave_types()
            payslip.compute_sheet_leave()
            worked_days_lines = payslip.get_worked_day_lines()
            valid_fields = self.env['hr.payslip.worked_days']._fields
            for line in worked_days_lines:
                sanitized_line = {
                    key: value for key, value in line.items()
                    if key in valid_fields
                }
                self.env['hr.payslip.worked_days'].create({
                    'payslip_id': payslip.id,
                    **sanitized_line
                })
        
        return True
    
    def get_worked_day_lines(self):
        """
        Calcula y genera las líneas de días trabajados para la nómina.
        Delega al servicio WorkedDaysCalculationService.

        Returns:
            list: Lista de diccionarios con la información de cada línea
        """
        res = []
        for rec in self:
            service = WorkedDaysCalculationService(rec)
            res.extend(service.calculate())
        return res
    
    def compute_sheet_leave(self):
        """
        Calcula y asigna las ausencias para la nómina.
        Delega al servicio LeaveCalculationService.

        Returns:
            bool: True si se procesó correctamente
        """
        for rec in self:
            service = LeaveCalculationService(rec)
            service.compute_sheet_leave()
        return True

    def compute_worked_days(self):
        """
        Calcula los días trabajados para la nómina.
        Delega al servicio LeaveCalculationService.

        Returns:
            bool: True si se procesó correctamente
        """
        for rec in self:
            service = LeaveCalculationService(rec)
            service.compute_worked_days()
        return True

    def action_open_ibc_audit(self):
        """Abre el wizard de auditoría de IBC para esta nómina"""
        self.ensure_one()
        return {
            'name': 'Auditoría de IBC',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.ibc.audit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_payslip_id': self.id,
                'default_employee_id': self.employee_id.id,
                'default_date_from': self.date_from,
                'default_date_to': self.date_to,
            }
        }
