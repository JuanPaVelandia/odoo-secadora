# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command, _
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
from odoo.addons.lavish_hr_payroll.models.hr_slip_data_structures import CategoryCollection, RulesCollection
from .hr_slip_acumulacion import HrPayslipAccumulation
from .services.ausencias import AusenciaService
from .services.horas_extras import HoraExtraService
from .hr_slip_data_structures import (
    CategoryCollection,
    CategoryData,
    RulesCollection,
    RuleData
)
from .hr_slip_constante import (
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
    json_serial,
    days360,
    PayslipLineAccumulator,
    PayslipCalculationContext,
)

_logger = logging.getLogger(__name__)

getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP

def to_decimal(value):
    """Convierte int/float/str/Decimal a Decimal (evita imprecisión de float)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def round_up_to_hundred(value: Decimal) -> Decimal:
    """Redondea al centenar superior (100) usando ROUND_CEILING."""
    return value.quantize(Decimal('1E2'), rounding=ROUND_CEILING)

def calculate_contribution(base, rate):
    """base * rate (%) / 100, todo en Decimal."""
    return to_decimal(base) * to_decimal(rate) / Decimal('100')


class DefaultDictPayroll(defaultdict):
    """
    Extensión de defaultdict nativa de Odoo 19.
    Permite get() con default sin modificar el dict.
    """
    def get(self, key, default=None):
        if key not in self and default is not None:
            self[key] = default
        return self[key]


class RulesComputedCompat:
    """
    Wrapper de compatibilidad para rules_computed (Odoo 15/17 -> Odoo 19).

    Permite sintaxis antigua: rules_computed.AVG
    que en Odoo 19 es: rules['AVG'].total

    Uso en reglas salariales:
        # Antiguo (Odoo 15/17):
        result = rules_computed.AVG / 360

        # Nuevo (Odoo 19):
        result = rules['AVG'].total / 360

        # Con compatibilidad (ambas funcionan):
        result = rules_computed.AVG / 360  # ← usa este wrapper
    """
    __slots__ = ('_rules',)

    def __init__(self, rules_collection):
        """
        Args:
            rules_collection: RulesCollection de Odoo 19
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

class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'sequence.mixin', 'portal.mixin', 'mail.thread', 'mail.activity.mixin']

    # Ensure move_id exists even if hr_payroll_account loads after this module
    move_id = fields.Many2one('account.move', 'Accounting Entry', readonly=True, copy=False, index='btree_not_null')

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

    def _infer_period_type(self, date_from, date_to, contract=None):
        """
        Determina el tipo de periodo usando primero la configuración del contrato.
        Evita clasificar 16-31 como mensual solo por cantidad de días.
        """
        schedule = getattr(contract, 'method_schedule_pay', False) if contract else False
        if schedule in ('bi-monthly', 'monthly'):
            return schedule

        days_diff = (date_to - date_from).days + 1
        if date_from.day == 1 and date_to.day <= 15:
            return 'bi-monthly'
        if date_from.day >= 16 and days_diff <= 16:
            return 'bi-monthly'
        return 'bi-monthly' if days_diff <= 16 else 'monthly'

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
        related='contract_id.change_wage_ids',
        string='Historial Salarial',
        readonly=True,
        help='Historial de cambios salariales del contrato asociado a esta nomina'
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
        if hasattr(self, '_update_prima_cesantias_dates'):
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
            period_type = self._infer_period_type(self.date_from, self.date_to, self.contract_id)
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
        if hasattr(self, 'compute_sheet_leave'):
            self.compute_sheet_leave()
        
        # Calcular horas extras
        if hasattr(self, '_compute_extra_hours'):
            self._compute_extra_hours()
        
        # Procesar préstamos
        if hasattr(self, '_process_loan_lines'):
            self._process_loan_lines()
        
        # Calcular novedades
        if hasattr(self, '_compute_novedades'):
            self._compute_novedades()
        
        # Calcular días trabajados
        self.worked_days_line_ids.unlink()
        if hasattr(self, '_action_compute_worked_days'):
            self._action_compute_worked_days()
        
        # Calcular líneas de nómina
        self.line_ids.unlink()
        if hasattr(self, '_get_payslip_lines_lavish'):
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
        # v19 hr.payslip.state Selection es draft/validated/paid/cancel.
        # No escribimos state aqui; el payslip permanece en 'draft' tras compute.
        self.write({
            'name': name,
            'compute_date': today
        })
    
    @api.onchange('employee_id', 'contract_id', 'struct_id', 'date_to')
    def load_dates_liq_contrato(self):
        """
        Carga las fechas para liquidación de contrato con manejo de excepciones.
        En caso de error, asigna la fecha de inicio del contrato como valor predeterminado.

        IMPORTANTE: Si date_prima o date_cesantias ya tienen valor (manual o previo),
        NO se recomputan. Solo se calculan si están vacíos.
        """
        if not self.struct_id or self.struct_id.process != 'contrato':
            return

        try:
            self.date_liquidacion = self.date_to
            contract_start_date = self.contract_id.date_start if self.contract_id else False

            # PRIMA: Solo calcular si NO tiene fecha previa
            if not self.date_prima:
                try:
                    date_prima = contract_start_date
                    if self.employee_id and self.contract_id:
                        obj_prima = self.env['hr.history.prima'].search([
                            ('employee_id', '=', self.employee_id.id),
                            ('contract_id', '=', self.contract_id.id)
                        ])

                        if obj_prima:
                            for history in sorted(obj_prima, key=lambda x: x.final_accrual_date):
                                if history.final_accrual_date and history.final_accrual_date > date_prima:
                                    date_prima = history.final_accrual_date + timedelta(days=1)

                    self.date_prima = date_prima
                except Exception as e:
                    _logger.warning("Error calculando fecha de prima para nómina %s: %s", self.name, e, exc_info=True)
                    self.date_prima = contract_start_date

            # VACACIONES: Solo calcular si NO tiene fecha previa
            if not self.date_vacaciones:
                try:
                    date_vacation = contract_start_date
                    if self.employee_id and self.contract_id:
                        obj_vacation = self.env['hr.vacation'].search([
                            ('employee_id', '=', self.employee_id.id),
                            ('contract_id', '=', self.contract_id.id)
                        ])

                        if obj_vacation:
                            for history in sorted(obj_vacation, key=lambda x: x.final_accrual_date):
                                if not history.final_accrual_date:
                                    continue

                                update_date = False
                                if history.leave_id:
                                    if not history.leave_id.holiday_status_id.unpaid_absences:
                                        update_date = True
                                else:
                                    update_date = True

                                if update_date and history.final_accrual_date > date_vacation:
                                    date_vacation = history.final_accrual_date + timedelta(days=1)
                    self.date_vacaciones = date_vacation
                except Exception as e:
                    _logger.warning("Error calculando fecha de vacaciones para nómina %s: %s", self.name, e, exc_info=True)
                    self.date_vacaciones = contract_start_date

            # CESANTIAS: Solo calcular si NO tiene fecha previa
            if not self.date_cesantias:
                try:
                    date_cesantias = contract_start_date
                    if self.employee_id and self.contract_id:
                        obj_cesantias = self.env['hr.history.cesantias'].search([
                            ('employee_id', '=', self.employee_id.id),
                            ('contract_id', '=', self.contract_id.id)
                        ])

                        if obj_cesantias:
                            for history in sorted(obj_cesantias, key=lambda x: x.final_accrual_date):
                                if history.final_accrual_date and history.final_accrual_date > date_cesantias:
                                    date_cesantias = history.final_accrual_date + timedelta(days=1)

                    self.date_cesantias = date_cesantias
                except Exception as e:
                    _logger.warning("Error calculando fecha de cesantías para nómina %s: %s", self.name, e, exc_info=True)
                    self.date_cesantias = contract_start_date

        except Exception as e:
            _logger.warning("Error calculando fechas de liquidación para nómina %s: %s", self.name, e, exc_info=True)
            contract_start_date = self.contract_id.date_start if self.contract_id else False
            self.date_liquidacion = self.date_to
            if not self.date_prima:
                self.date_prima = contract_start_date
            if not self.date_vacaciones:
                self.date_vacaciones = contract_start_date
            if not self.date_cesantias:
                self.date_cesantias = contract_start_date

    @api.depends('line_ids.computation')
    def _compute_prestaciones_sociales_report(self):
        for payslip in self:
            prestaciones_lines = payslip.line_ids.filtered(lambda line: line.computation and line.salary_rule_id.code not in ('IBD','IBC_R','RT_MET_01'))
            if prestaciones_lines:
                all_reports = []
                for line in prestaciones_lines:
                    try:
                        computation_data = json.loads(line.computation)
                        report = self._generate_formatted_prestaciones_report(line, computation_data)
                        all_reports.append(report)
                    except json.JSONDecodeError:
                        all_reports.append(f'<p>Error al procesar los datos de la línea {line.name}.</p>')
                
                payslip.prestaciones_sociales_report = self._combine_reports(all_reports)
            else:
                payslip.prestaciones_sociales_report = '<p>No hay datos de prestaciones sociales disponibles.</p>'

    def _format_reporte_html(self, data) -> str:
        """
        Genera un reporte HTML detallado de la retención en la fuente
        Args:
            data: Diccionario con los datos del reporte
        Returns:
            str: Reporte HTML formateado
        """
        def format_currency(value):
            try:
                return f"${value:,.0f}" if value else "$0"
            except (KeyError, AttributeError):
                return "$0"

        def format_section(title, content):
            return f"""
                <div class="section-container" style="margin-bottom: 15px;">
                    <div class="section-title" style="background-color: #C41E3A; color: white; padding: 8px; font-weight: bold;">
                        {title}
                    </div>
                    <div class="section-content" style="border: 1px solid #ddd; padding: 10px;">
                        {content}
                    </div>
                </div>
            """

        def format_row(label, value, observation=None, limit=None) -> str:
            limit_text = f'<div style="color: #0066cc; text-align: right; font-size: 0.9em;">Límite: {limit}</div>' if limit else ''
            obs_text = f'<div style="color: #C41E3A; font-size: 0.9em;">{observation}</div>' if observation else ''
            return f"""
                <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                    <div style="flex: 2;">
                        {label}
                        {obs_text}
                        {limit_text}
                    </div>
                    <div style="flex: 1; text-align: right; font-weight: bold;">
                        {value}
                    </div>
                </div>
            """

        if isinstance(data, list):
            data = data[0] if data else {}
        
        if not data:
            return "<div>No hay datos disponibles para mostrar</div>"

        html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px;">
            <div style="background-color: #C41E3A; color: white; padding: 10px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <div style="font-size: 16px; font-weight: bold;">RETENCIÓN EN LA FUENTE MENSUAL</div>
                <div>Valor UVT: {format_currency(data.get('uvt', 0))}</div>
            </div>
        """

        ingresos = data.get('ingresos', {})
        ingresos_content = "".join([
            format_row("Sueldo básico", format_currency(ingresos.get('salario', 0))),
            format_row("Comisiones", format_currency(ingresos.get('comisiones', 0))),
            format_row("Otros pagos laborales", format_currency(ingresos.get('otros_ingresos', 0))),
            format_row("Total Ingresos Laborales", format_currency(ingresos.get('total', 0)))
        ])
        html += format_section("1. PAGOS LABORALES DEL MES", ingresos_content)

        aportes = data.get('aportes_obligatorios', {})
        no_renta_content = "".join([
            format_row("Aportes obligatorios a Pensión", format_currency(aportes.get('pension', 0))),
            format_row("Aportes obligatorios a Salud", format_currency(aportes.get('salud', 0))),
            format_row("Total Ingresos No Constitutivos", format_currency(aportes.get('total', 0))),
            format_row("Subtotal 1", format_currency(data.get('base_calculo', {}).get('subtotal_1', 0)))
        ])
        html += format_section("2. INGRESOS NO CONSTITUTIVOS DE RENTA", no_renta_content)

        deducciones = data.get('deducciones', {})
        deducciones_content = "".join([
            format_row(
                "Intereses de vivienda", 
                format_currency(data['ded_vivienda']),
                "Límite máximo 100 UVT Mensuales",
                format_currency(deducciones.get('limite_vivienda', 0))
            ),
            format_row(
                "Dependientes", 
                format_currency(deducciones.get('dependientes', 0)),
                "No puede exceder del 10% del ingreso bruto y máximo 32 UVT mensuales",
                format_currency(deducciones.get('limite_dependientes', 0))
            ),
            format_row(
                "Medicina prepagada", 
                format_currency(deducciones.get('salud_prepagada', 0)),
                "No puede exceder 16 UVT Mensuales",
                format_currency(deducciones.get('limite_salud', 0))
            ),
            format_row("Total Deducciones", format_currency(deducciones.get('total', 0)))
        ])
        html += format_section("3. DEDUCCIONES", deducciones_content)

        rentas = data.get('rentas_exentas', {})
        rentas_content = "".join([
            format_row(
                "Aportes AFC", 
                format_currency(rentas.get('afc', 0)),
                "Límite del 30% del ingreso laboral y hasta 3.800 UVT anuales",
                format_currency(rentas.get('limite_afc', 0))
            ),
            format_row(
                "Renta Exenta 25%", 
                format_currency(rentas.get('renta_exenta_25', 0)),
                None,
                format_currency(rentas.get('limite_renta_25', 0))
            ),
            format_row("Total Rentas Exentas", format_currency(rentas.get('total', 0)))
        ])
        html += format_section("4. RENTAS EXENTAS", rentas_content)

        base_calculo = data.get('base_calculo', {})
        retencion = data.get('retencion', {})
        base_content = "".join([
            format_row("Base Gravable en UVTs", f"{base_calculo.get('base_uvts', 0):,.2f}"),
            format_row("Porcentaje de Retención", f"{data['rate']}%"),
            format_row("Retención calculada", format_currency(data.get('valor', 0))),
            format_row("Retención anterior", format_currency(data.get('anterior', 0))),
            format_row("Retención definitiva", format_currency(data.get('definitiva', 0)))
        ])
        html += format_section("5. BASE GRAVABLE Y RETENCIÓN", base_content)

        html += f"""
            <div style="background-color: #fff3cd; border: 1px solid #ffeeba; padding: 10px; margin-top: 15px; font-size: 0.9em;">
                <strong>NOTA IMPORTANTE:</strong><br>
                La sumatoria de las Deducciones, Rentas exentas y el 25% de la renta de trabajo exenta,
                no podrá superar el 40% del ingreso señalado en el subtotal 1 hasta 1340 UVT
            </div>
        """

        html += "</div>"
        return html


    def _generate_formatted_prestaciones_report(self, line, computation_data):
        """
        Genera un reporte HTML formateado para prestaciones sociales
        Args:
            line: hr.payslip.line record
            computation_data: Diccionario con los datos del cómputo
        Returns:
            str: Reporte HTML formateado
        """
        def format_currency(value):
            try:
                return f"${value:,.0f}" if value else "$0"
            except (KeyError, AttributeError):
                return "$0"

        def format_value(value):
            if isinstance(value, (int, float)):
                return format_currency(value)
            elif isinstance(value, dict):
                return format_dict(value)
            elif isinstance(value, list):
                return format_list(value)
            else:
                return str(value)

        def format_dict(data, level=0):
            indent = "  " * level
            html = '<div style="margin-left: 15px;">'
            for key, value in data.items():
                if isinstance(value, dict):
                    html += f'<div style="margin: 5px 0;"><strong>{key}:</strong></div>'
                    html += format_dict(value, level + 1)
                elif isinstance(value, list):
                    html += f'<div style="margin: 5px 0;"><strong>{key}:</strong></div>'
                    html += format_list(value, level + 1)
                else:
                    html += f'<div style="display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid #eee;">'
                    html += f'<span>{key}:</span><span style="font-weight: bold;">{format_value(value)}</span></div>'
            html += '</div>'
            return html

        def format_list(items, level=0):
            html = '<ul style="margin: 5px 0; padding-left: 20px;">'
            for item in items:
                if isinstance(item, dict):
                    html += '<li>' + format_dict(item, level + 1) + '</li>'
                else:
                    html += f'<li>{format_value(item)}</li>'
            html += '</ul>'
            return html

        html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 13px; margin-bottom: 20px;">
            <div style="background-color: #C41E3A; color: white; padding: 10px; margin-bottom: 10px;">
                <div style="font-size: 16px; font-weight: bold;">{line.name}</div>
                <div style="font-size: 12px;">Código: {line.code or 'N/A'}</div>
            </div>
            <div style="border: 1px solid #ddd; padding: 15px; background-color: #f9f9f9;">
                <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 2px solid #C41E3A; margin-bottom: 10px;">
                    <span style="font-weight: bold;">Total:</span>
                    <span style="font-weight: bold; font-size: 16px; color: #C41E3A;">{format_currency(line.total)}</span>
                </div>
        """

        if computation_data:
            html += '<div style="margin-top: 15px;"><strong>Detalle del Cálculo:</strong></div>'
            html += format_dict(computation_data)
        else:
            html += '<div style="color: #666; font-style: italic;">No hay datos de cálculo disponibles</div>'

        html += """
            </div>
        </div>
        """

        return html

    def _combine_reports(self, reports):
        combined_html = '<div class="prestaciones-sociales-combined-report">'
        combined_html += '<h1>Reporte de Prestaciones Sociales</h1>'
        for report in reports:
            combined_html += report
            combined_html += '<hr>'  # Separador entre reportes
        combined_html += '</div>'
        return combined_html

    @api.depends('line_ids', 'leave_ids', 'worked_days_line_ids')
    def _compute_payslip_detail(self):
        for payslip in self:
            payslip.payslip_detail = 'Calculated'

    def _periodo(self):
        for rec in self:
            if rec.date_to:
                rec.periodo = rec.date_to.strftime("%Y%m")
            else:
                rec.periodo = ''
    
    def old_payslip_moth(self):
        payslip_objs = self.env['hr.payslip'].search([('struct_id.process', 'in', ['vacaciones', 'prima'])])
        for record in self:
            record.payslip_old_ids = [(6, 0, payslip_objs.ids)]

    def _assign_old_payslips(self):
        for payslip in self:
            start_date = payslip.date_from.replace(day=1)
            end_date = (start_date + relativedelta(months=1, days=-1))
            
            domain = [
                ('id', '!=', payslip.id),  # Para excluir la nómina actual
                ('employee_id', '=', payslip.employee_id.id),
                ('contract_id', '=', payslip.contract_id.id),
                ('date_from', '>=', start_date.strftime('%Y-%m-%d')),
                ('date_to', '<=', end_date.strftime('%Y-%m-%d')),
                ('struct_id.process', 'in', ['vacaciones', 'prima']),
            ]
            old_payslips = self.env['hr.payslip'].search(domain)
            payslip.payslip_old_ids = [(6, 0, old_payslips.ids)]

    def _compute_extra_hours(self):
        for payslip in self:
            if payslip.struct_id.process in ('nomina', 'contrato', 'otro'):
                query = """
                UPDATE hr_overtime
                SET payslip_run_id = %s,
                    state = CASE
                        WHEN state IS NULL OR state = '' OR state = 'nuevo' THEN 'procesado'
                        ELSE state
                    END
                WHERE 
                    (state = 'validated' OR state = 'nuevo' OR state IS NULL OR state = '' OR payslip_run_id IS NULL)
                    AND date_end BETWEEN %s AND %s
                    AND employee_id = %s
                """
                self.env.cr.execute(query, (payslip.id, payslip.date_from, payslip.date_to, payslip.employee_id.id))

    def _compute_novedades(self):
        for payslip in self:
            query_params = [payslip.id, payslip.employee_id.id]
            date_conditions = ""
            if payslip.struct_id.process in ('nomina', 'contrato', 'otro', 'prima'):
                date_conditions = "AND date >= %s AND date <= %s"
                query_params.extend([payslip.date_from, payslip.date_to])

            query = """
            UPDATE hr_novelties_different_concepts
            SET payslip_id = %s
            WHERE payslip_id IS NULL 
            AND employee_id = %s 
            """ + date_conditions
            self.env.cr.execute(query, tuple(query_params))

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
            # v19: state Selection es draft/validated/paid/cancel; no escribimos
            # 'verify' (no existe). Payslip queda en 'draft' tras compute.
            slip.write({
                'name': name,
                'compute_date': today
            })
            date_from = slip_data['date_from']
            date_to = slip_data['date_to']
            period_type = slip._infer_period_type(date_from, date_to, slip.contract_id)
            period = self.env['hr.period'].get_period(
                date_from, 
                date_to,
                period_type,
                self.company_id.id
            )
            if period:
                slip.period_id = period.id
            else:
                self.assign_periods_to_draft_payslips()
                slip.period_id = self.env['hr.period'].get_period(date_from, date_to, period_type, self.company_id.id).id
            slip.leave_ids.unlink()
            slip.compute_sheet_leave()
            slip._compute_extra_hours()
            slip._process_loan_lines()
            slip._compute_novedades()
            # Usar ORM en lugar de SQL directo para respetar triggers y caché
            slip.worked_days_line_ids.unlink()
            slip.line_ids.unlink()
            slip._action_compute_worked_days()
            line_vals = slip._get_payslip_lines_lavish()
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

    def recompute_worked_days_action(self):
        errors = []
        success = 0
        for slip in self:
            try:
                slip.leave_ids.unlink()
                slip.worked_days_line_ids.unlink()
                slip.compute_sheet_leave()
                worked_days_line_ids = slip.get_worked_day_lines()
                slip.worked_days_line_ids = [(0, 0, line) for line in worked_days_line_ids]
            except Exception as e:
                errors.append(f'Error en nómina {slip.name}: {str(e)}')
        message = f'Proceso completado.\nNóminas actualizadas: {success}'
        if errors:
            message += '\n\nErrores encontrados:\n' + '\n'.join(errors)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Resultado del recálculo',
                'message': message,
                'sticky': True,
                'type': 'info' if success else 'warning',
            }
        }

    def _update_prima_cesantias_dates(self, slip, slip_data):
        # Si el usuario activo "Usar dias manuales" en el recibo, respetar las
        # fechas que haya ingresado manualmente y NO sobreescribirlas.
        if getattr(slip, 'use_manual_days', False):
            return

        if slip_data['struct_process'] in ['prima', 'contrato'] or slip_data['pay_primas_in_payroll']:
            # Solo recalcular date_prima si esta vacia (respetar valor previo manual)
            if not slip.date_prima:
                from_month = 1 if slip_data['date_from'].month <= 6 else 7
                date_from = slip_data['date_from'].replace(month=from_month, day=1)
                if date_from < slip.contract_id.date_start:
                    date_from = slip.contract_id.date_start
                slip.date_prima = date_from
        if slip_data['struct_process'] in ['cesantias', 'contrato'] or slip_data['pay_cesantias_in_payroll']:
            # Solo recalcular date_cesantias si esta vacia (respetar valor previo manual)
            if not slip.date_cesantias:
                date_ref = slip_data['date_to']
                date_from = date_ref.replace(month=1, day=1)
                if date_from < slip.contract_id.date_start:
                    date_from = slip.contract_id.date_start
                slip.date_cesantias = date_from

    def _check_duplicate_slip(self, slip_data):
        if slip_data['struct_process'] not in ('vacaciones', 'contrato', 'otro'):
            self._cr.execute("""
                SELECT COUNT(id) FROM hr_payslip
                WHERE contract_id = %s AND date_from >= %s AND date_to <= %s
                AND struct_process = %s AND id != %s
            """, (slip_data['contract_id'], slip_data['date_from'], slip_data['date_to'], 
                slip_data['struct_process'], slip_data['id']))
            return self._cr.fetchone()[0] > 0
        return False

    def compute_precise(self, value1: float =0.0, value2: float  =0.0, operation: str = '*', decimals: int = PRECISION_TECHNICAL) -> float:
        """Realiza cálculos con alta precisión"""
        factor = 10 ** decimals
        int_value1 = int(float(value1) * factor)
        int_value2 = int(float(value2) * factor)
        
        if operation == '*':
            result = (int_value1 * int_value2) // factor
        elif operation == '/':
            if int_value2 == 0:
                raise ValueError("División por cero")
            result = (int_value1 * factor) // int_value2
        elif operation == '+':
            result = int_value1 + int_value2
        elif operation == '-':
            result = int_value1 - int_value2
        else:
            raise ValueError(f"Operación {operation} no soportada")
        return result / factor
    
    def get_completed_paid_payslips_by_period(self, contract_id: int, from_year_month: Optional[str] = None, to_year_month: Optional[str] = None) -> Dict[str, int]:
        """
        Obtiene las nóminas con estado 'done' / 'paid' por período para un contrato específico.
        """
        query = """
        SELECT 
            to_char(p.date_from, 'YYYY-MM') as year_month,
            COUNT(p.id) as total_payslips,
            array_agg(p.id) as payslip_ids
        FROM 
            hr_payslip p
        WHERE 
            p.state IN ('done', 'paid')
            AND p.contract_id = %s
        """
        params = [contract_id]
        if from_year_month and not to_year_month:
            query += " AND to_char(p.date_from, 'YYYY-MM') = %s"
            params.append(from_year_month)
        elif from_year_month and to_year_month:
            query += " AND to_char(p.date_from, 'YYYY-MM') >= %s AND to_char(p.date_from, 'YYYY-MM') <= %s"
            params.extend([from_year_month, to_year_month])
        query += """
        GROUP BY to_char(p.date_from, 'YYYY-MM')
        ORDER BY year_month ASC
        """
        self.env.cr.execute(query, params)
        return self.env.cr.dictfetchall()

    def get_payslip_days_count(self, payslip_id: int) -> dict[str, int]:
        """
        Devuelve un diccionario con la cantidad de días de la nómina por tipo:
        - Días festivos
        - Domingos
        - Días trabajados
        - Ausencias
        
        Args:
            payslip_id (int): ID de la nómina
        
        Returns:
            dict: Diccionario con la cantidad de días por tipo
        """
        payslip_days = self.env['hr.payslip.day'].search([
            ('payslip_id', '=', payslip_id)
        ])
        
        festivos = 0
        domingos = 0
        ausencias = 0
        trabajados = 0
        sabado = 0
        for day in payslip_days:
            if day.is_holiday:
                festivos += 1
            elif day.is_sunday:
                domingos += 1
            elif day.is_saturday:
                sabado += 1
            elif day.is_absence:
                ausencias += 1
            elif not (day.is_holiday or day.is_sunday or day.is_absence):
                trabajados += 1
        
        result = {
            'sabado': sabado,
            'festivos': festivos,
            'domingos': domingos,
            'trabajados': trabajados,
            'ausencias': ausencias,
        }
        
        return result
    


    def _get_base_local_dict(self):
        """
        Retorna el dict base con utilidades para safe_eval.
        Estructura NATIVA de Odoo 19.
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
        Retorna localdict con estructura NATIVA Odoo 19 SIMPLIFICADA.

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
            _logger.info(f"[LOCALDICT] annual_params desde batch_ctx: {annual_params}")
        else:
            search_year = self.date_to.year if self.date_to else None
            company_id = self.company_id.id if self.company_id else self.env.company.id
            _logger.info(f"[LOCALDICT] Buscando annual_params para año: {search_year}, company: {company_id}, slip: {self.id}, struct: {self.struct_id.name if self.struct_id else 'N/A'}")

            # Usar sudo() para evitar reglas multicompañía y filtrar explícitamente
            annual_params = self.env['hr.annual.parameters'].sudo().search([
                ('year', '=', self.date_to.year),
                ('company_ids', 'in', [company_id])
            ], limit=1)

            # Si no encuentra con compañía específica, buscar sin filtro de compañía
            if not annual_params:
                _logger.warning(f"[LOCALDICT] No se encontró annual_params para compañía {company_id}, buscando global...")
                annual_params = self.env['hr.annual.parameters'].sudo().search([
                    ('year', '=', self.date_to.year)
                ], limit=1)

            _logger.info(f"[LOCALDICT] annual_params encontrados: {annual_params}, id: {annual_params.id if annual_params else 'N/A'}, smmlv: {annual_params.smmlv_monthly if annual_params else 'N/A'}")

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
            ausencia_service = AusenciaService(self.env, self, batch_ctx)
            ausencias_info = ausencia_service.get_ausencias()
            localdict['ausencias'] = ausencias_info
        except Exception:  # noqa: BLE001 – fallback seguro, ausencias no bloquean cómputo
            _logger.warning("Error al obtener ausencias para nómina %s, usando valores por defecto", self.name, exc_info=True)
            localdict['ausencias'] = {'detalle': [], 'total_valor': 0}

        return localdict

    def _sum_salary_rule_category(self, localdict, category, amount, rule_code=None, line_id=None):
        """
        Suma recursivamente el monto en la categoría y sus padres.
        Usa estructura NATIVA Odoo 19 con tracking de líneas y reglas.

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
            from odoo.addons.lavish_hr_payroll.models.hr_slip_data_structures import CategoryData
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
        Actualiza la suma de reglas usando RulesCollection (Odoo 19).

        Usa RuleData objects que son tipo-seguros y se acumulan automáticamente.
        """
        from odoo.addons.lavish_hr_payroll.models.hr_slip_data_structures import RuleData

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

        # Dedup framework-vs-regla: result_leave (ausencias, llaveado "CODE-PCD<leave>") y
        # result (reglas, llaveado por código) pueden generar línea para el mismo concepto
        # (ej. LICENCIA_NO_REMUNERADA). La regla 'concept' ya suma los días de leave_ids, así
        # que se descartan las líneas del framework cuyo código ya produjo una regla.
        rule_codes = {line.get('code') for line in result.values()
                      if isinstance(line, dict) and line.get('code')}
        combined = [line for line in result_leave.values()
                    if not (isinstance(line, dict) and line.get('code') in rule_codes)]
        combined.extend(result.values())
        return combined

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
            obj_novelties = batch_ctx.get_employee_novelties(employee_id).filtered(
                lambda n: n.state == 'approved'
            )
        else:
            # Fallback: consulta directa (legacy)
            obj_novelties = self.env['hr.novelties.different.concepts'].search([
                ('employee_id', '=', employee_id),
                ('date', '>=', localdict['slip'].date_from),
                ('date', '<=', localdict['slip'].date_to),
                ('state', '=', 'approved'),
            ])

        for concepts in obj_novelties:
            if concepts.amount != 0 and self._should_process_novelty(concepts, payslip):
                localdict, result = self._update_localdict_for_novelty(localdict, concepts, result)

        localdict, result = self._update_localdict_for_overtime(localdict, payslip, result, applicable_rules)
        return localdict, result

    def _update_localdict_for_overtime(self, localdict, payslip, result, applicable_rules):
        """
        Crea líneas de nómina para horas extras registradas en hr.overtime.

        Usa las reglas configuradas en hr.type.overtime para mantener
        la parametrización salarial vigente por tipo de recargo.
        """
        service = HoraExtraService(self.env, payslip, localdict.get('_batch_context'))
        extras = service.calcular_valor_horas()
        if not extras.get('detalle'):
            return localdict, result

        reference_date = payslip.date_to or payslip.date_from or fields.Date.today()
        TypeOvertime = self.env['hr.type.overtime']

        for item in extras['detalle']:
            if not item.get('valor_total'):
                continue

            overtime_type = TypeOvertime.get_percentage_for_date(
                item['tipo'],
                reference_date,
                payslip.company_id.id if payslip.company_id else self.env.company.id,
            ) or TypeOvertime.search([
                ('type_overtime', '=', item['tipo']),
                ('active', '=', True),
            ], order='valid_from desc', limit=1)

            rule = overtime_type.salary_rule if overtime_type else False
            if not rule or rule.id not in applicable_rules.ids:
                continue

            # Usamos rule.code como key del dict 'result' para que coincida con la
            # clave que usaria la regla HEYREC* al evaluarse via amount_select='concept'.
            # Asi evitamos lineas duplicadas: una desde aqui (OT-overtime_ext_d) y otra
            # desde _compute_overtime_with_log (HEYREC001). Con la misma key, la
            # segunda escritura sobreescribe la primera.
            line_key = rule.code
            total_amount = round(item['valor_total'])
            previous_amount = localdict[rule.code] if rule.code in localdict else 0.0
            localdict[line_key] = total_amount

            localdict = self._sum_salary_rule_category(
                localdict,
                rule.category_id,
                total_amount - previous_amount,
                rule_code=rule.code
            )
            localdict = self._sum_salary_rule(localdict, rule, total_amount, item['cantidad'], 100.0)

            computation_data = {
                'tipo': 'horas_extras',
                'regla': {
                    'id': rule.id,
                    'code': rule.code,
                    'name': rule.name if isinstance(rule.name, str) else '',
                },
                'hora_extra': {
                    'tipo': item['tipo'],
                    'descripcion': item['nombre'],
                    'cantidad': item['cantidad'],
                    'factor': item['factor'],
                    'valor_unitario': item['valor_unitario'],
                    'valor_total': total_amount,
                },
                'formula': f"{item['cantidad']} x ${item['valor_unitario']:,.0f}",
                'steps': [
                    {'label': 'Cantidad Horas', 'value': item['cantidad'], 'format': 'number'},
                    {'label': 'Valor Unitario', 'value': item['valor_unitario'], 'format': 'currency'},
                    {'label': 'Factor Legal', 'value': item['factor'] * 100, 'format': 'percent'},
                    {'label': 'Total', 'value': total_amount, 'format': 'currency', 'highlight': True},
                ],
                'indicators': [
                    {'label': 'Origen', 'value': 'hr.overtime', 'color': 'primary'},
                    {'label': 'Tipo', 'value': item['nombre'], 'color': 'success'},
                ]
            }

            result[line_key] = {
                'sequence': rule.sequence,
                'code': rule.code,
                'name': item['nombre'],
                'salary_rule_id': rule.id,
                'contract_id': localdict['contract'].id,
                'employee_id': localdict['employee'].id,
                'entity_id': False,
                'amount': item['valor_unitario'],
                'quantity': item['cantidad'],
                'rate': 100,
                'total': total_amount,
                'slip_id': self.id,
                'is_previous_period': False,
                'computation': json.dumps(computation_data, default=json_serial),
            }

        return localdict, result
    def _create_loan_line(self, localdict, installment, result):
        """
        Crea una línea para una cuota de préstamo
        """
        line_code = f'LOAN-{installment.loan_id.id}-{installment.sequence}'
        
        loan = installment.loan_id
        amount = -abs(installment.amount)  # Monto negativo para descuento
        
        description = f"Cuota {installment.sequence}/{len(loan.installment_ids)} -{[loan.category_id.code]} {loan.category_id.name}"
        if len(localdict['slip'].loan_installment_ids) > 1:
            description += f" ({installment.date})"
        
        # Obtener la regla salarial para préstamos
        rule = installment.loan_id.category_id.salary_rule_id#self.env.ref('hr_loan.rule_loan_payment', raise_if_not_found=False)
        if not rule:
            return localdict, result
        
        localdict[line_code] = amount

        localdict = self._sum_salary_rule_category(
            localdict,
            rule.category_id,
            amount,
            rule_code=rule.code  # Tracking: agregar código de regla
        )
        localdict = self._sum_salary_rule(localdict, rule, amount)
        
        # Crear diccionario de computation para préstamos
        computation_data = {
            'tipo': 'prestamo',
            'prestamo': {
                'id': loan.id,
                'nombre': loan.name,
                'categoria': loan.category_id.name if loan.category_id else '',
                'categoria_code': loan.category_id.code if loan.category_id else '',
                'monto_original': loan.amount if hasattr(loan, 'amount') else 0,
                'saldo': loan.balance_amount if hasattr(loan, 'balance_amount') else 0,
                'entidad': loan.entity_id.name if loan.entity_id else '',
            },
            'cuota': {
                'numero': installment.sequence,
                'total_cuotas': len(loan.installment_ids),
                'monto': abs(installment.amount),
                'fecha': str(installment.date) if installment.date else '',
            },
            'formula': f"Cuota {installment.sequence} de {len(loan.installment_ids)}",
            'steps': [
                {'label': 'Monto Original Préstamo', 'value': loan.amount if hasattr(loan, 'amount') else 0, 'format': 'currency'},
                {'label': 'Cuota Actual', 'value': abs(installment.amount), 'format': 'currency'},
                {'label': 'Saldo Pendiente', 'value': loan.balance_amount if hasattr(loan, 'balance_amount') else 0, 'format': 'currency'},
                {'label': 'Descuento en Nómina', 'value': round(amount), 'format': 'currency', 'highlight': True},
            ]
        }

        result[line_code] = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': description,
            'salary_rule_id': rule.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': loan.entity_id.id,
            'loan_id': loan.id,
            #'loan_installment_id': installment.id,
            'amount': amount,
            'quantity': 1.00,
            'rate': 100,
            'total': round(amount),  # Redondear préstamos también
            'slip_id': self.id,
            'is_previous_period': False,
            'computation': json.dumps(computation_data, default=json_serial),
        }

        return localdict, result
    
    def _should_process_novelty(self, novelty, payslip):
        """
        Determina si una novedad debe ser procesada según estructuras y condiciones
        """
        if not novelty.salary_structure_ids:
            return payslip.struct_process in ['nomina', 'contrato']
        return payslip.struct_id.id in novelty.salary_structure_ids.ids

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
                tot_rule = 0 

                if rule.code in overrides:
                    override = overrides[rule.code]
                    if override['type'] == 'amount':
                        amount = override['value']
                    elif override['type'] == 'quantity':
                        qty = override['value']
                    elif override['type'] == 'rate':
                        rate = override['value']
                    elif override['type'] == 'total':
                        tot_rule = override['value']
                # Para reglas de prestaciones sociales, usar el monto_total calculado
                # que viene en la tupla de retorno (índice 5: datos['monto_total'])
                if rule.code in ("CESANTIAS", "PRIMA", "INTCESANTIAS", "INTCES_YEAR", "CES_YEAR", "VACCONTRATO"):
                    if data and isinstance(data, dict):
                        # El total ya viene calculado en 'monto_total' del dict de datos
                        monto_total = data.get('monto_total', 0)
                        if monto_total:
                            tot_rule = float(self._round1(monto_total))
                if not tot_rule:
                    tot_rule = round(amount * qty * rate / 100.0)

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
                if tot_rule != 0.0:
                    rule_results[rule.code] = self._prepare_rule_result(
                        rule, temp_dict, amount, qty, rate, name, log, payslip, data
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
        """
        Verifica si un concepto ya fue liquidado en otra nómina del mismo período.

        ANTI-DUPLICACION: Evita doble cómputo cuando:
        - Se liquidan vacaciones y luego nómina quincenal
        - Se liquida nómina quincenal y luego liquidación de contrato
        - Cualquier combinación de nóminas en el mismo mes

        Args:
            payslip: Nómina actual que se está computando
            concept: Concepto (hr.contract.concepts) a verificar
            rule: Regla salarial del concepto

        Returns:
            bool: True si el concepto ya fue liquidado (saltar), False si debe procesarse
        """
        # Determinar rango del periodo actual (quincena)
        from calendar import monthrange
        year = payslip.date_from.year
        month = payslip.date_from.month
        last_day_num = monthrange(year, month)[1]
        if payslip.date_from.day <= 15:
            first_day = payslip.date_from.replace(day=1)
            last_day = payslip.date_from.replace(day=15)
        else:
            first_day = payslip.date_from.replace(day=16)
            last_day = payslip.date_from.replace(day=last_day_num)

        # Buscar nóminas del mismo empleado en la misma quincena que NO sean esta nómina
        # y que estén en estado válido (no borrador ni cancelada)
        other_payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', payslip.employee_id.id),
            ('id', '!=', payslip.id),
            ('date_from', '>=', first_day),
            ('date_to', '<=', last_day),
            ('state', 'not in', ['draft', 'cancel'])
        ])

        if not other_payslips:
            return False

        # Verificar si existe una línea con el mismo código de regla Y el mismo concept_id
        # Usamos concept_id para ser más específicos y evitar falsos positivos
        for other_slip in other_payslips:
            existing_line = self.env['hr.payslip.line'].search([
                ('slip_id', '=', other_slip.id),
                ('salary_rule_id', '=', rule.id),
                ('concept_id', '=', concept.id)
            ], limit=1)

            if existing_line:
                _logger.info(
                    f"[ANTI-DUPLICACION] Concepto {concept.name} (ID:{concept.id}) "
                    f"ya liquidado en nómina {other_slip.name} (ID:{other_slip.id}). "
                    f"Saltando en nómina actual {payslip.name}"
                )
                return True

        return False

    def _create_concept_line(self, localdict, concept, amount, data, description, result):
        """
        Crea una línea de concepto y actualiza el localdict
        """
        line_code = concept.input_id.code + '-PCD' + str(concept.id)

        previous_amount = concept.input_id.code in localdict and localdict[concept.input_id.code] or 0.0

        localdict[line_code] = amount

        rule = concept.input_id
        localdict = self._sum_salary_rule_category(
            localdict,
            concept.input_id.category_id,
            amount - previous_amount,
            rule_code=concept.input_id.code  # Tracking: agregar código de regla
        )
        localdict = self._sum_salary_rule(localdict, concept.input_id, amount, 1.0, 100.0)

        # Crear diccionario de computation para conceptos de contrato
        es_deduccion = concept.input_id.category_id.code in ['DED', 'DEDUCCION', 'DEDUCCIONES'] if concept.input_id.category_id else False
        computation_data = {
            'tipo': 'concepto_contrato',
            'concepto': {
                'id': concept.id,
                'descripcion': description or '',
                'regla': concept.input_id.name if concept.input_id else '',
                'regla_code': concept.input_id.code if concept.input_id else '',
                'categoria': concept.input_id.category_id.name if concept.input_id and concept.input_id.category_id else '',
                'entidad': concept.partner_id.name if concept.partner_id else '',
                'prestamo_id': concept.loan_id.id if concept.loan_id else None,
            },
            'formula': f"Monto = ${amount:,.0f}" if amount else 'Monto = $0',
            'explanation': 'Deducción de Contrato' if es_deduccion else 'Devengo de Contrato',
            'steps': [
                {'label': 'Monto Concepto', 'value': amount, 'format': 'currency'},
                {'label': 'Cantidad', 'value': 1.0, 'format': 'number'},
                {'label': 'Porcentaje', 'value': 100, 'format': 'percent'},
                {'label': 'Total', 'value': round(amount), 'format': 'currency', 'highlight': True},
            ],
            'indicators': [
                {'label': 'Tipo', 'value': 'Deducción' if es_deduccion else 'Devengo', 'color': 'danger' if es_deduccion else 'success'},
                {'label': 'Origen', 'value': 'Contrato', 'color': 'primary'},
            ]
        }

        result[line_code] = {
            'sequence': concept.input_id.sequence,
            'code': concept.input_id.code,
            'name': description,
            'salary_rule_id': concept.input_id.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': concept.partner_id.id,
            'loan_id': concept.loan_id.id,
            'concept_id': concept.id,
            'amount': amount,
            'quantity': 1.00,
            'rate': 100,
            'log_compute':data['detail_html'],
            'total': round(amount),  # Redondear conceptos también
            'slip_id': self.id,
            'computation': json.dumps(computation_data, default=json_serial),
            #'is_previous_period': is_previous
        }

        return localdict, result

    def _update_localdict_for_novelty(self, localdict, concepts, result):
        previous_amount = concepts.salary_rule_id.code in localdict and localdict[concepts.salary_rule_id.code] or 0.0
        tot_rule = self._get_payslip_line_total(concepts.amount, 1, 100, concepts.salary_rule_id)
        localdict[concepts.salary_rule_id.code+'-PCD'] = tot_rule
        localdict = self._sum_salary_rule_category(
            localdict,
            concepts.salary_rule_id.category_id,
            tot_rule - previous_amount,
            rule_code=concepts.salary_rule_id.code  # Tracking: agregar código de regla
        )
        localdict = self._sum_salary_rule(localdict, concepts.salary_rule_id, tot_rule, 1.0, 100.0)

        # Crear diccionario de computation para novedades
        es_deduccion = concepts.salary_rule_id.category_id.code in ['DED', 'DEDUCCION', 'DEDUCCIONES'] if concepts.salary_rule_id.category_id else False
        computation_data = {
            'tipo': 'novedad',
            'novedad': {
                'id': concepts.id,
                'descripcion': concepts.description or concepts.name or '',
                'fecha': str(concepts.date) if hasattr(concepts, 'date') and concepts.date else '',
                'estado': concepts.state if hasattr(concepts, 'state') else '',
                'regla': concepts.salary_rule_id.name if concepts.salary_rule_id else '',
                'regla_code': concepts.salary_rule_id.code if concepts.salary_rule_id else '',
                'categoria': concepts.salary_rule_id.category_id.name if concepts.salary_rule_id and concepts.salary_rule_id.category_id else '',
                'entidad': concepts.partner_id.name if concepts.partner_id else '',
            },
            'formula': f"Monto = ${concepts.amount:,.0f}" if concepts.amount else 'Monto = $0',
            'explanation': 'Deducción' if es_deduccion else 'Devengo',
            'steps': [
                {'label': 'Monto Novedad', 'value': concepts.amount, 'format': 'currency'},
                {'label': 'Cantidad', 'value': 1.0, 'format': 'number'},
                {'label': 'Porcentaje', 'value': 100, 'format': 'percent'},
                {'label': 'Total', 'value': tot_rule, 'format': 'currency', 'highlight': True},
            ],
            'indicators': [
                {'label': 'Tipo', 'value': 'Deducción' if es_deduccion else 'Devengo', 'color': 'danger' if es_deduccion else 'success'},
            ]
        }

        result_item = concepts.salary_rule_id.code+'-PCD'+str(concepts.id)
        result[result_item] = {
            'sequence': concepts.salary_rule_id.sequence,
            'code': concepts.salary_rule_id.code,
            'name': concepts.description or concepts.salary_rule_id.name,
            #'note': concepts.salary_rule_id.note,
            'salary_rule_id': concepts.salary_rule_id.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': concepts.partner_id.id if concepts.partner_id else False,
            'amount': tot_rule,
            'quantity': 1.0,
            'rate': 100,
            'total': tot_rule,
            'slip_id': self.id,
            'computation': json.dumps(computation_data, default=json_serial),
        }
        return localdict, result
    
    def _prepare_rule_result(self, rule, localdict, amount, qty, rate, name, log, payslip, data) -> Dict[str, Union[float, str, int,Dict[str,str],bool]]:
        # Calcular total - SIEMPRE redondeado a entero para evitar decimales y descuadres contables
        tot_rule = payslip._get_payslip_line_total(amount, qty, rate, rule)

        result = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name':  name or rule.name,
            'salary_rule_id': rule.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': False,
            'amount': amount,
            'quantity': qty,
            'rate': rate,
            'total': tot_rule,
            'slip_id': payslip.id,
            'run_id': payslip.payslip_run_id.id,
        }
        
        if rule.category_id.code == 'SSOCIAL':
            for entity in localdict['employee'].social_security_entities:
                if entity.contrib_id.type_entities == 'eps' and rule.code == 'SSOCIAL001':
                    result['entity_id'] = entity.partner_id.id
                elif entity.contrib_id.type_entities == 'pension' and rule.code in ['SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']:
                    result['entity_id'] = entity.partner_id.id
                elif entity.contrib_id.type_entities == 'subsistencia' and rule.code == 'SSOCIAL003':
                    result['entity_id'] = entity.partner_id.id
                elif entity.contrib_id.type_entities == 'solidaridad' and rule.code == 'SSOCIAL004':
                    result['entity_id'] = entity.partner_id.id
        if rule.category_id.code in ("PROV"):
            # Provisiones también se redondean a entero para mantener consistencia
            result.update({
            'total': round(amount * qty * rate / 100) })

            if data and isinstance(data, dict):
                if 'prov_line_ids' in data:
                    result['accounting_line_ids'] = [(6, 0, data['prov_line_ids'])]

                if 'acum_line_ids' in data:
                    result['accumulated_line_ids'] = [(6, 0, data['acum_line_ids'])]

                if 'acum_payroll_ids' in data:
                    result['accumulated_payroll_consulted_ids'] = [(6, 0, data['acum_payroll_ids'])]

                # Guardar reglas salariales usadas para provisiones
                if 'source_rule_ids' in data and data['source_rule_ids']:
                    result['source_rule_ids'] = [(6, 0, data['source_rule_ids'])]

                data_kpi = data.get('data_kpi', {})
                if data_kpi:
                    result['calculation_method'] = 'consolidado' if data_kpi.get('compute_average') else 'simple'
                    result['discount_suspensions'] = data_kpi.get('descontar_suspensiones', False)

                if 'fecha_inicio' in data:
                    result['period_start'] = data['fecha_inicio']
                if 'fecha_fin' in data:
                    result['period_end'] = data['fecha_fin']
        # Guardar computation para PRESTACIONES SOCIALES
        if rule.code in ("CESANTIAS","PRIMA","INTCESANTIAS", "INTCES_YEAR", "CES_YEAR", "VACCONTRATO"):
            if data and isinstance(data, dict):
                data_kpi = data.get('data_kpi', {})

                result.update({
                    'total': self._round1(data.get('monto_total', 0)),
                    'days_unpaid_absences': self._round1(data_kpi.get('days_no_pay', 0)),
                    'amount_base': self._round1(data_kpi.get('base_mensual', 0)),
                    'initial_accrual_date': data.get('fecha_inicio'),
                    'final_accrual_date': data.get('fecha_fin'),
                    # Guardar data completo para tener resumen, indicadores, formula_pasos, config_auxilio
                    'computation': json.dumps(data, default=json_serial) if data else '{}',
                })

                if 'acum_line_ids' in data:
                    result['accumulated_line_ids'] = [(6, 0, data['acum_line_ids'])]

                if 'acum_payroll_ids' in data:
                    result['accumulated_payroll_consulted_ids'] = [(6, 0, data['acum_payroll_ids'])]

                # Guardar reglas salariales usadas para el calculo
                if 'source_rule_ids' in data and data['source_rule_ids']:
                    result['source_rule_ids'] = [(6, 0, data['source_rule_ids'])]

        # Guardar computation para SALARIO BÁSICO y otras reglas con log_data
        elif rule.code in ("BASIC", "BASIC002", "BASIC003", "BASIC004", "BASIC005"):
            if data and isinstance(data, dict):
                result.update({
                    'computation': json.dumps(data, default=json_serial),
                })

        # Guardar computation para AUXILIO DE TRANSPORTE
        elif rule.code in ("AUX000",):
            if data and isinstance(data, dict):
                result.update({
                    'computation': json.dumps(data, default=json_serial),
                })

        # Guardar computation para IBD
        if rule.code in ("IBD"):
            if data and isinstance(data, dict):
                result.update({
                    'computation': json.dumps(data, default=json_serial),
                })
                if 'acum_line_ids' in data:
                    result['accumulated_line_ids'] = [(6, 0, data['acum_line_ids'])]

        # Guardar computation para SEGURIDAD SOCIAL
        elif rule.code in ('SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004'):
            if data and isinstance(data, dict):
                result.update({
                    'computation': json.dumps(data, default=json_serial),
                })

        # Guardar computation para RETENCIÓN
        elif rule.code in ('RT_MET_01',):
            if data:
                # Manejar data como lista o diccionario
                first_item = data[0] if isinstance(data, list) and len(data) > 0 else (data if isinstance(data, dict) else {})
                amount_base = 0
                if first_item:
                    if not first_item.get('es_proyectado', False):
                        amount_base = first_item.get('subtotal_ibr3', 0)
                    else:
                        otro_valor = first_item.get('otro_valor', 0) or 0
                        amount_base = otro_valor / 2
                result.update({
                    'amount_base': amount_base,
                    'computation': json.dumps(data, default=json_serial),

                })
                self.resulados_rt = log

        # Guardar computation genérico para otras reglas que retornen datos
        elif data and isinstance(data, dict) and 'computation' not in result:
            result.update({
                'computation': json.dumps(data, default=json_serial),
            })
        #elif rule.code in ('IBD'):
        #    result.update({
        #        'amount_base': data['ctx'].ibc_full,
        #        'computation': json.dumps(data, default=json_serial),                                          
        #    }) 
        #    self.resulados_op = self.generate_ibd_html_report(data)
        if log:
            result['log_compute'] = log
        return result

    def _calculate_absences(self):
        self.ensure_one()
        temp_dict = {}
        for leave_day in self.leave_days_ids:
            if not leave_day.leave_id:
                continue
            if leave_day.state not in ('validated', 'paid'):
                continue
            if leave_day.leave_id.state not in ('validate', 'validate1', 'validate2'):
                continue
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
                'sequence': leave_day.sequence if hasattr(leave_day, 'sequence') else 0,
                'rate_applied': leave_day.rate_applied if hasattr(leave_day, 'rate_applied') else 100,
                'ibc_day': leave_day.ibc_day if hasattr(leave_day, 'ibc_day') else 0,
                'ibc_base': leave_day.ibc_base if hasattr(leave_day, 'ibc_base') else 0,
                'base_type': leave_day.base_type if hasattr(leave_day, 'base_type') else 'wage',
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
                leave_type = leave.holiday_status_id if leave else None
                is_unpaid = leave_type.unpaid_absences if leave_type and hasattr(leave_type, 'unpaid_absences') else False
                if not is_unpaid:
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
        input_code = concept['input_id'].code
        previous_amount = localdict.get(input_code, 0.0)
        tot_rule = tot_rule * (1 if concept['input_id'].dev_or_ded == 'devengo' else -1)
        localdict[f"{input_code}-PCD{concept['leave_id']}"] = tot_rule
        rule = concept['input_id']
        days = concept['days']
        contract = localdict['contract']
        employee = localdict['employee']
        amount_per_day = tot_rule / days if days else 0
        
        leave = concept['leave_id']
        is_money_vacation = input_code == 'VACATIONS_MONEY' or (leave.holiday_status_id.is_vacation_money if hasattr(leave.holiday_status_id, 'is_vacation_money') else False)
        
        vacation_type = 'money' if is_money_vacation else 'enjoy'
        localdict[f"vacation_type-PCD{concept['leave_id']}"] = vacation_type
        
        localdict = self._sum_salary_rule_category(
            localdict,
            rule.category_id,
            tot_rule - previous_amount,
            rule_code=rule.code  # Tracking: agregar código de regla
        )
        leave_type = leave.holiday_status_id if leave else None
        localdict = self._sum_salary_rule(
            localdict,
            rule,
            tot_rule,
            days,
            100,
            has_leave=True,
            leave_id=leave.id if leave else 0,
            leave_novelty=leave_type.novelty if leave_type else '',
            leave_liquidacion_value=leave_type.liquidacion_value if leave_type else ''
        )
        result_item = f"{input_code}-PCD{concept['leave_id']}"
        
        # Crear diccionario de computation para ausencias
        leave_type = leave.holiday_status_id
        is_paid = not (leave_type.unpaid_absences if hasattr(leave_type, 'unpaid_absences') else False)
        novelty_type = leave_type.novelty if hasattr(leave_type, 'novelty') else ''

        # Obtener líneas individuales con variación de porcentaje
        additional_novelties = concept.get('additional_novelties', [])

        # Verificar si es incapacidad con variación de porcentaje (IGE, IRL)
        is_incapacity_with_variation = novelty_type in ['ige', 'irl'] and len(additional_novelties) > 0

        # Construir steps detallados según tipo de ausencia
        if is_incapacity_with_variation:
            # Agrupar por rango de porcentaje
            rates_summary = {}
            for nov in additional_novelties:
                rate = nov.get('rate_applied', 100)
                rate_key = str(rate)
                if rate_key not in rates_summary:
                    rates_summary[rate_key] = {'dias': 0, 'monto': 0, 'rate': rate}
                rates_summary[rate_key]['dias'] += nov.get('days', 0) or nov.get('days_work', 0) or 1
                rates_summary[rate_key]['monto'] += nov.get('amount', 0)

            # Construir pasos detallados para incapacidad
            steps = []
            ibc_base = additional_novelties[0].get('ibc_base', 0) if additional_novelties else 0
            ibc_day = additional_novelties[0].get('ibc_day', 0) if additional_novelties else 0

            if ibc_base:
                steps.append({'label': 'Base Mensual (IBC)', 'value': ibc_base, 'format': 'currency'})
            if ibc_day:
                steps.append({'label': 'Valor Diario (IBC/30)', 'value': ibc_day, 'format': 'currency'})

            # Agregar desglose por rango de porcentaje
            for rate_key, rate_data in sorted(rates_summary.items(), key=lambda x: float(x[0]), reverse=True):
                rate_label = f"Días al {rate_data['rate']:.0f}%"
                steps.append({
                    'label': rate_label,
                    'value': f"{rate_data['dias']} días = ${rate_data['monto']:,.0f}",
                    'format': 'text'
                })

            steps.append({'label': 'Total Días', 'value': days, 'format': 'number'})
            steps.append({'label': 'Total', 'value': round(tot_rule), 'format': 'currency', 'highlight': True})

            # Formula para incapacidad
            formula = "IBC/30 × Días × %Reconocimiento"
            explanation = f"Incapacidad {novelty_type.upper()} con variación de porcentaje por días"
        else:
            # Pasos estándar para ausencias normales
            steps = [
                {'label': 'Valor Diario', 'value': amount_per_day, 'format': 'currency'},
                {'label': 'Días de Trabajo', 'value': concept['days_work'], 'format': 'number'},
                {'label': 'Días Festivos', 'value': concept['days_holiday'], 'format': 'number'},
                {'label': 'Total Días', 'value': days, 'format': 'number'},
                {'label': 'Total', 'value': round(tot_rule), 'format': 'currency', 'highlight': True},
            ]
            formula = "Valor Diario × Días = Total"
            explanation = f"{'Licencia Remunerada' if is_paid else 'Ausencia No Pagada'} - {leave_type.name if leave_type else ''}"

        computation_data = {
            'tipo': 'ausencia',
            'ausencia': {
                'id': leave.id,
                'nombre': leave.name if hasattr(leave, 'name') else '',
                'tipo_ausencia': leave_type.name if leave_type else '',
                'tipo_code': leave_type.code if hasattr(leave_type, 'code') else '',
                'novelty': novelty_type,
                'fecha_inicio': str(concept['date_from']) if concept['date_from'] else '',
                'fecha_fin': str(concept['date_to']) if concept['date_to'] else '',
                'es_pagada': is_paid,
                'es_vacacion': leave_type.is_vacation if hasattr(leave_type, 'is_vacation') else False,
                'entidad': leave.entity.name if hasattr(leave, 'entity') and leave.entity else '',
            },
            'dias': {
                'total': days,
                'trabajo': concept['days_work'],
                'festivos': concept['days_holiday'],
                'dia_31': concept['days_31'],
                'festivo_31': concept['days_holiday_31'],
            },
            'formula': formula,
            'explanation': explanation,
            'steps': steps,
            'indicators': [
                {'label': 'Estado', 'value': 'Pagada' if is_paid else 'No Pagada', 'color': 'success' if is_paid else 'warning'},
                {'label': 'Tipo', 'value': novelty_type.upper() if novelty_type else 'LICENCIA', 'color': 'primary'},
            ]
        }

        # Agregar detalles de líneas individuales para incapacidades
        if is_incapacity_with_variation:
            computation_data['lineas_detalle'] = [
                {
                    'fecha': str(nov.get('date', '')),
                    'secuencia': nov.get('sequence', 0),
                    'rate': nov.get('rate_applied', 100),
                    'monto': nov.get('amount', 0),
                    'ibc_day': nov.get('ibc_day', 0),
                }
                for nov in additional_novelties
            ]

        result[result_item] = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': rule.name,
            'salary_rule_id': rule.id,
            'contract_id': localdict['contract'].id,
            'employee_id': localdict['employee'].id,
            'entity_id': concept['partner_id'],
            'loan_id': concept['loan_id'],
            'amount': amount_per_day,
            'quantity': days,
            'rate': 100,
            'total': round(tot_rule),  # Asegurar redondeo en ausencias
            'slip_id': self.id,
            'leave_id': concept['leave_id'].id,
            'initial_accrual_date': concept['date_from'],
            'final_accrual_date': concept['date_to'],
            'business_units': concept['days_work'],
            'holiday_units': concept['days_holiday'],
            'business_31_units': concept['days_31'],
            'holiday_31_units': concept['days_holiday_31'],
            'computation': json.dumps(computation_data, default=json_serial),
        }

        if leave.holiday_status_id.is_vacation or leave.holiday_status_id.is_vacation_money:
            Vac = self.env['hr.vacation']
            
            if '_vacation_accrual_dates' not in localdict:
                localdict['_vacation_accrual_dates'] = {}
            
            employee_id = employee.id
            
            if employee_id in localdict['_vacation_accrual_dates']:
                start = localdict['_vacation_accrual_dates'][employee_id] + timedelta(days=1)
            else:
                last = Vac.search(
                    [('employee_id', '=', employee.id)],
                    order='final_accrual_date desc', limit=1
                )
                if last:
                    start = last.final_accrual_date
                    if start < contract.date_start:
                        start = contract.date_start
                else:
                    start = contract.date_start
            
            domain = [
                ('state', '=', 'validate'),
                ('employee_id', '=', employee.id),
                ('unpaid_absences', '=', True),
                ('date_from', '>=', start),
                ('date_to', '<=', self.date_to),
            ]
            dias_aus = sum(l.number_of_days_in_payslip for l in self.env['hr.leave'].search(domain))
            dias_aus += sum(h.days for h in self.env['hr.absence.history'].search([
                ('employee_id', '=', employee.id),
                ('leave_type_id.unpaid_absences', '=', True),
                ('star_date', '>=', start),
                ('end_date', '<=', self.date_to),
            ]))

            dias_hab = concept['days_work']
            dias_fest = concept['days_holiday']
            dias_31_hab = concept['days_31']
            dias_31_fest = concept['days_holiday_31']

            dias_equiv = ((Decimal(dias_hab) + Decimal(dias_31_hab)) * Decimal(365)) / Decimal(15)
            dias_equiv = int(dias_equiv.quantize(0, rounding=ROUND_HALF_UP))
            if not start:
                start = contract.date_start
            end = start + timedelta(days=(dias_equiv + dias_aus) +1 )
            
            localdict['_vacation_accrual_dates'][employee_id] = end

            disp = self.get_holiday_book(contract, start)['days_left']
            dias_rest = max(disp - dias_hab, 0)

            log_lines = [
                '<div class="vac-log" style="font-family:Arial,sans-serif;font-size:12px;">',
                f'<p><strong>Tipo de vacaciones:</strong> {"En Dinero" if is_money_vacation else "Disfrute"}</p>',
                f'<p><strong>Inicio causación:</strong> {start.strftime("%d/%m/%Y")}</p>',
                f'<p><strong>Fin causación:</strong> {end.strftime("%d/%m/%Y")}</p>',
                f'<p><strong>Días hábiles:</strong> {dias_hab}</p>',
                f'<p><strong>Días festivos:</strong> {dias_fest}</p>',
                f'<p><strong>Días "31" hábiles:</strong> {dias_31_hab}</p>',
                f'<p><strong>Días "31" festivos:</strong> {dias_31_fest}</p>',
                f'<p><strong>Equivalente calendario:</strong> {dias_equiv + dias_aus}</p>',
                f'<p><strong>Ausencias no pagadas:</strong> {dias_aus}</p>',
                f'<p><strong>Disponibles antes:</strong> {disp}</p>',
                f'<p><strong>Restantes:</strong> {dias_rest}</p>',
                '</div>',
            ]

            vacation_info = {
                'start_date': start,
                'end_date': end,
                'business_days': dias_hab,
                'holiday_days': dias_fest,
                'equivalent_days': dias_equiv,
                'unpaid_absences': dias_aus,
                'available_days': disp,
                'remaining_days': dias_rest,
                'base_value': amount_per_day * 30  # Base mensual
            }
            localdict[f"vacation_info-PCD{concept['leave_id']}"] = vacation_info

            vacation_values = {
                'amount_base': amount_per_day * 30,
                'object_type': 'vacation',
                'vacation_leave_id': leave.id,
                'vacation_departure_date': concept['date_from'],
                'vacation_return_date': concept['date_to'],
                'initial_accrual_date': start,
                'final_accrual_date': end,
                'business_units': dias_hab,
                'holiday_units': dias_fest,
                'business_31_units': dias_31_hab,
                'holiday_31_units': dias_31_fest,
                'days_count': days,
                'log_compute': ''.join(log_lines),
            }
            
            # if is_money_vacation:
            #     total_units = dias_hab + dias_fest
            #     vacation_values.update({
            #         'units_of_money': total_units,
            #         'money_value': tot_rule
            #     })
            # else:
            #     vacation_values.update({
            #         'value_business_days': amount_per_day * dias_hab,
            #         'holiday_value': amount_per_day * dias_fest
            #     })

            result[result_item].update(vacation_values)

        return localdict, result
        
    def action_update_vacation_data(self):
        """
        Actualiza los datos de vacaciones de una nómina ya confirmada,
        diferenciando entre vacaciones disfrutadas y vacaciones en dinero.
        """
        self.ensure_one()
        
        if self.state not in ('done', 'paid'):
            raise UserError(_("Solo se pueden actualizar datos de vacaciones en nóminas confirmadas."))
        
        vacation_lines = self.line_ids.filtered(lambda line: 
            line.code in ['VACATIONS_MONEY', 'VACDISFRUTADAS'] or 
            (line.leave_id and (line.leave_id.holiday_status_id.is_vacation or 
                            line.leave_id.holiday_status_id.is_vacation_money))
        )
        
        if not vacation_lines:
            raise UserError(_("No se encontraron líneas de vacaciones para actualizar."))
        
        leave_periods = [(line.leave_id.date_from, line.leave_id.date_to, line.leave_id.name) 
                        for line in vacation_lines if line.leave_id]
        leave_periods.sort()  
        
        for i in range(1, len(leave_periods)):
            if leave_periods[i-1][1] >= leave_periods[i][0]:
                raise UserError(_(
                    "Se detectó un solapamiento entre períodos de vacaciones: %s (%s - %s) y %s (%s - %s). "
                    "Por favor, corrija las fechas antes de actualizar."
                ) % (
                    leave_periods[i-1][2], leave_periods[i-1][0].strftime('%d/%m/%Y'), leave_periods[i-1][1].strftime('%d/%m/%Y'),
                    leave_periods[i][2], leave_periods[i][0].strftime('%d/%m/%Y'), leave_periods[i][1].strftime('%d/%m/%Y')
                ))
        
        last_accrual_end = {}
        
        vacation_lines_sorted = sorted(
            [line for line in vacation_lines if line.leave_id], 
            key=lambda line: line.leave_id.date_from
        )
        
        for line in vacation_lines_sorted:
            employee = self.employee_id
            contract = self.contract_id
            leave = line.leave_id
            
            is_money_vacation = line.code == 'VACATIONS_MONEY' or (leave.holiday_status_id.is_vacation_money if leave else False)
            
            concept = {
                'leave_id': leave,
                'date_from': leave.date_from,
                'date_to': leave.date_to,
                'days_work': line.business_units,
                'days_holiday': line.holiday_units,
                'days_31': line.business_31_units,
                'days_holiday_31': line.holiday_31_units,
            }
            
            Vac = self.env['hr.vacation']
            
            if employee.id in last_accrual_end:
                start = last_accrual_end[employee.id] + timedelta(days=1)
            else:
                last_vacation = Vac.search(
                    [
                        ('employee_id', '=', employee.id),
                        ('payslip', '!=', self.id),
                    ],
                    order='final_accrual_date desc', limit=1
                )
                
                if last_vacation:
                    start = last_vacation.final_accrual_date + timedelta(days=1)
                    if start < contract.date_start:
                        start = contract.date_start
                else:
                    start = contract.date_start
            
            domain = [
                ('state', '=', 'validate'),
                ('employee_id', '=', employee.id),
                ('unpaid_absences', '=', True),
                ('date_from', '>=', start),
                ('date_to', '<=', self.date_to),
            ]
            
            dias_aus = sum(l.number_of_days for l in self.env['hr.leave'].search(domain))
            dias_aus += sum(h.days for h in self.env['hr.absence.history'].search([
                ('employee_id', '=', employee.id),
                ('leave_type_id.unpaid_absences', '=', True),
                ('star_date', '>=', start),
                ('end_date', '<=', self.date_to),
            ]))
            
            dias_hab = concept['days_work']
            dias_fest = concept['days_holiday']
            dias_31_hab = concept['days_31']
            dias_31_fest = concept['days_holiday_31']
            
            from decimal import Decimal, ROUND_HALF_UP
            dias_equiv = ((Decimal(dias_hab) + Decimal(dias_31_hab)) * Decimal(365)) / Decimal(15)
            dias_equiv = int(dias_equiv.quantize(0, rounding=ROUND_HALF_UP))
            
            end = start + timedelta(days=(dias_equiv + dias_aus) - 1)
            
            last_accrual_end[employee.id] = end
            
            disp = self.get_holiday_book(contract, start)['days_left']
            dias_rest = max(disp - dias_hab, 0)
            
            amount_per_day = line.amount if line.amount else 0
            total_amount = line.total if line.total else 0
            
            # Estilos para el log de vacaciones (Inline para compatibilidad Odoo)
            style_container = "background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); overflow: hidden; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; max-width: 500px; margin: 0 auto;"
            style_header = "background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between;"
            style_row = "border-bottom: 1px solid #f1f5f9;"
            style_label = "padding: 12px 8px; color: #64748b; font-weight: 500; font-size: 0.9rem; width: 40%; vertical-align: middle;"
            style_value = "padding: 12px 8px; color: #1e293b; font-weight: 600; font-size: 0.95rem; text-align: right; vertical-align: middle;"
            style_footer = "background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center;"
            
            type_label = "En Dinero" if is_money_vacation else "Disfrute"
            
            log_lines = [
                f'<div class="vac-log-container" style="{style_container}">',
                    f'<div style="{style_header}">',
                        '<h3 style="font-size: 1.1rem; font-weight: 600; margin: 0; display: flex; align-items: center; gap: 10px;">',
                            '<i class="fa fa-plane"></i> Detalle de Vacaciones',
                        '</h3>',
                        f'<span style="background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 500;">{type_label}</span>',
                    '</div>',
                    '<div style="padding: 20px;">',
                        '<table style="width: 100%; margin-bottom: 0; border-collapse: collapse;">',
                            # Periodo
                            f'<tr><td style="{style_label} {style_row}"><i class="fa fa-calendar" style="color:#3b82f6; margin-right:8px;"></i>Periodo</td><td style="{style_value} {style_row}">{concept["date_from"].strftime("%d/%m/%Y")} - {concept["date_to"].strftime("%d/%m/%Y")}</td></tr>',
                            # Causación
                            f'<tr><td style="{style_label} {style_row}"><i class="fa fa-clock-o" style="color:#0ea5e9; margin-right:8px;"></i>Causación</td><td style="{style_value} {style_row} color: #64748b; font-size: 0.85rem;">{start.strftime("%d/%m/%Y")} - {end.strftime("%d/%m/%Y")}</td></tr>',
                            # Días Hábiles
                            f'<tr><td style="{style_label} {style_row}">Días Hábiles</td><td style="{style_value} {style_row}">{dias_hab}</td></tr>',
                            # Días Festivos
                            f'<tr><td style="{style_label} {style_row}">Días Festivos</td><td style="{style_value} {style_row}"><span style="background: rgba(22,163,74,0.1); color: #16a34a; padding: 2px 10px; border-radius: 12px; font-size: 0.85rem;">{dias_fest}</span></td></tr>',
                            # Días 31
                            f'<tr><td style="{style_label} {style_row}">Días 31</td><td style="{style_value} {style_row}">',
                                f'<span style="background: rgba(234,179,8,0.1); color: #ca8a04; padding: 2px 10px; border-radius: 12px; font-size: 0.85rem; margin-right: 4px;" title="Hábiles">{dias_31_hab} H</span>',
                                f'<span style="background: rgba(234,179,8,0.1); color: #ca8a04; padding: 2px 10px; border-radius: 12px; font-size: 0.85rem;" title="Festivos">{dias_31_fest} F</span>',
                            '</td></tr>',
                            # Equivalente
                            f'<tr><td style="{style_label} {style_row}">Equivalente Calendario</td><td style="{style_value} {style_row}">{dias_equiv} días</td></tr>',
                            # Ausencias
                            f'<tr><td style="{style_label} {style_row} color: #ef4444;">Ausencias No Pagadas</td><td style="{style_value} {style_row} color: #ef4444;">{dias_aus} días</td></tr>',
                            # Saldo
                            f'<tr><td style="{style_label}">Saldo Restante</td><td style="{style_value}">{dias_rest} días</td></tr>',
                        '</table>',
                    '</div>',
                    f'<div style="{style_footer}">',
                        '<div>',
                            '<div style="color: #64748b; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">Valor Total</div>',
                            f'<div style="font-size: 0.8rem; color: #94a3b8;">Base diaria: ${amount_per_day:,.2f}</div>',
                        '</div>',
                        f'<div style="color: #059669; font-size: 1.4rem; font-weight: 700;">$ {total_amount:,.2f}</div>',
                    '</div>',
                '</div>'
            ]
            
            line.write({
                'initial_accrual_date': start,
                'final_accrual_date': end,
                'vacation_departure_date': concept['date_from'],
                'vacation_return_date': concept['date_to'],
                'log_compute': ''.join(log_lines),
                'business_units': dias_hab,
                'holiday_units': dias_fest,
                'business_31_units': dias_31_hab,
                'holiday_31_units': dias_31_fest,
            })
            
            vacation_values = {
                'employee_id': employee.id,
                'employee_identification': employee.identification_id,
                'leave_id': leave.id,
                'payslip': self.id,
                'initial_accrual_date': start,
                'final_accrual_date': end,
                'departure_date': concept['date_from'],
                'return_date': concept['date_to'],
                'business_units': dias_hab,
                'holiday_units': dias_fest,
                'days_returned': 0,
                'contract_id': contract.id,
                'ibc_pila': self.env['hr.payslip.line'].search([
                    ('slip_id', '=', self.id),
                    ('code', '=', 'IBD')
                ], limit=1).total or 0,
            }
            
            if is_money_vacation:
                vacation_values.update({
                    'base_value_money': round(amount_per_day * 30),  # Base mensual
                    'units_of_money': dias_hab + dias_fest,   # Total días
                    'money_value': round(total_amount),       # Valor pagado
                    'total': round(total_amount),             # Redondear total
                    'description': 'Vacaciones en Dinero'
                })
            else:
                vacation_values.update({
                    'base_value': round(amount_per_day * 30),        # Base mensual
                    'value_business_days': round(amount_per_day * dias_hab),
                    'holiday_value': round(amount_per_day * dias_fest),
                    'total': round(total_amount),             # Redondear total
                    'description': 'Vacaciones Disfrutadas'
                })
            
            vacation_records = Vac.search([
                ('employee_id', '=', employee.id),
                ('payslip', '=', self.id)
            ])
            
            if vacation_records:
                for vac_record in vacation_records:
                    vac_record.write(vacation_values)
            else:
                Vac.create(vacation_values)
        
        self.message_post(
            body=_("Se actualizaron los datos de %d períodos de vacaciones (%d disfrutadas, %d en dinero).") % (
                len(vacation_lines_sorted),
                len([l for l in vacation_lines_sorted if l.code == 'VACDISFRUTADAS' or 
                    (l.leave_id and l.leave_id.holiday_status_id.is_vacation and not l.leave_id.holiday_status_id.is_vacation_money)]),
                len([l for l in vacation_lines_sorted if l.code == 'VACATIONS_MONEY' or 
                    (l.leave_id and l.leave_id.holiday_status_id.is_vacation_money)])
            ),
            subject=_("Actualización de Datos de Vacaciones")
        )
        
        # Mensaje de éxito
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Datos de vacaciones actualizados correctamente.'),
                'sticky': False,
            }
        }
        
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
                rules = rules.filtered(lambda r: r.struct_id.process != 'nomina')
            if self.no_days_worked:
                rules = rules.filtered(lambda r: r.category_id.code not in ('BASIC','AUX'))
            if not self.novelties_payroll_concepts:
                rules = rules.filtered(lambda r: r.type_concepts != 'novedad')
        else:
            rules = self.struct_id.rule_ids

        return rules | common_rules

    def _no_round(self, amount):
        return amount

    def _round1(self, amount: Decimal | float) -> Decimal:
        """Redondea al entero más cercano usando *Decimal* sin decimales."""
        from decimal import Decimal, ROUND_HALF_UP
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _round100(self, amount):
        return int(math.ceil(amount / 100.0)) * 100

    def _round1000(self, amount):
        return round(amount, -3)

    def _round2d(self, amount):
        return round(amount, 2)

    @api.depends('line_ids')
    def _compute_concepts_category(self):
        category_mapping = {
            'EARNINGS': ['BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO', 'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC', 'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD', 'LICENCIA_REMUNERADA', 'LICENCIA_NO_REMUNERADA', 'AUSENCIA_NO_PAGO', 'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'],
            'DEDUCTIONS': ['DED', 'DEDUCCIONES', 'SANCIONES', 'DESCUENTO_AFC', 'SSOCIAL', 'TOTALDED'],
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

    def get_increase(self):
        return True

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
            if not contracts or not contracts[0].structure_type_id.default_struct_id:
                self.contract_id = False
                self.struct_id = False
                return
            self.contract_id = contracts[0]
            self.struct_id = contracts[0].structure_type_id.default_struct_id
        period_type = self._infer_period_type(date_from, date_to, self.contract_id)
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
        month_name = self.env['hr.birthday.list'].get_name_month(mes)
        
        date_name = month_name + ' ' + str(self.date_from.year)
        self.name = '%s - %s - %s' % (payslip_name, self.employee_id.name or '', date_name)
        self.analytic_account_id = self.contract_id.analytic_account_id
        
        # NOTA: En Odoo 19 el campo warning_message fue removido de hr.payslip.
        # Se elimina el bloque que escribia ese campo para evitar AttributeError
        # al cambiar la estructura del recibo (p. ej. seleccionar Liquidacion).

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
            payslip.not_line_ids.unlink()
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
        """
        Define campos clave para cada modelo de historial
        """
        key_fields = {
            'hr.vacation': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date', 'leave_id'],
            'hr.history.cesantias': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date'],
            'hr.history.prima': ['employee_id', 'contract_id', 'initial_accrual_date', 'final_accrual_date'],
        }
        return key_fields.get(model_name, [])
    
    def _create_or_update_history(self, model_name, values):
        """
        Crea o actualiza cualquier historial basado en campos clave
        """
        Model = self.env[model_name]
        key_fields = self._get_history_key_fields(model_name)
        
        domain = [(field, '=', values.get(field)) for field in key_fields if values.get(field) is not False]
        
        if domain:
            existing = Model.search(domain, limit=1)
            if existing:
                existing.write(values)
                return existing
        
        return Model.create(values)
    
    def _get_vacation_values(self, record, line):
        """
        Obtiene valores de vacaciones según el código de línea
        """
        base_values = {
            'employee_id': record.employee_id.id,
            'contract_id': record.contract_id.id,
            'initial_accrual_date': line.initial_accrual_date,
            'final_accrual_date': line.final_accrual_date,
            'payslip': record.id,
        }
        
        vacation_configs = {
            'VACDISFRUTADAS': {
                'departure_date': line.vacation_departure_date or record.date_from,
                'return_date': line.vacation_return_date or record.date_to,
                'business_units': line.business_units + line.business_31_units,
                'value_business_days': line.business_units * line.amount,
                'holiday_units': line.holiday_units + line.holiday_31_units,
                'holiday_value': round(line.holiday_units * line.amount),
                'base_value': line.amount_base,
                'total': round((line.business_units * line.amount) + (line.holiday_units * line.amount)),
                'leave_id': line.vacation_leave_id.id if line.vacation_leave_id else False
            },
            'VACREMUNERADAS': {
                'departure_date': record.date_from,
                'return_date': record.date_to,
                'units_of_money': line.quantity,
                'money_value': line.total,
                'base_value_money': line.amount_base,
                'total': line.total,
            },
            'VACATIONS_MONEY': {
                'departure_date': record.date_from,
                'return_date': record.date_to,
                'units_of_money': line.quantity,
                'business_units': line.quantity,
                'money_value': line.total,
                'base_value_money': line.amount_base,
                'total': line.total,
                'leave_id': line.vacation_leave_id.id if line.vacation_leave_id else False
            },
            'VACCONTRATO': {
                'departure_date': record.date_liquidacion,
                'return_date': record.date_liquidacion,
                'units_of_money': line.quantity,  # Total días (hábiles + festivos)
                'business_units': line.business_units or 0,  # Días hábiles
                'holiday_units': line.holiday_units or 0,  # Domingos/festivos
                'money_value': line.total,
                'base_value_money': line.amount,  # Promedio diario
                'total': line.total,
                'type': 'settlement',  # Tipo liquidación
            },
            'VAC_LIQ': {
                'departure_date': record.date_liquidacion,
                'return_date': record.date_liquidacion,
                'units_of_money': line.quantity,  # Total días (hábiles + festivos)
                'business_units': line.business_units or 0,  # Días hábiles
                'holiday_units': line.holiday_units or 0,  # Domingos/festivos
                'money_value': line.total,
                'base_value_money': line.amount,  # Promedio diario
                'total': line.total,
                'type': 'settlement',  # Tipo liquidación
            }
        }
        
        if line.code in vacation_configs:
            base_values.update(vacation_configs[line.code])
            return base_values
        
        return None
    
    def _get_severance_values(self, record, line_cesantias=None, line_interes=None):
        """
        Obtiene valores consolidados de cesantías e intereses
        """
        values = {}
        
        if record.struct_id.process == 'contrato':
            date_from = record.date_cesantias
            date_to = record.date_liquidacion
        else:
            date_from = record.date_cesantias
            date_to = record.date_to
        
        if line_cesantias and not line_cesantias.is_history_reverse:
            values.update({
                'employee_id': record.employee_id.id,
                'contract_id': record.contract_id.id,
                'type_history': 'cesantias',
                'initial_accrual_date': date_from,
                'final_accrual_date': date_to,
                'settlement_date': date_to,
                'time': line_cesantias.quantity,
                'base_value': line_cesantias.amount_base,
                'severance_value': line_cesantias.total,
                'payslip': record.id
            })
        
        if line_interes and not line_interes.is_history_reverse:
            if record.struct_id.process in ('cesantias', 'intereses_cesantias'):
                values.update({
                    'type_history': 'intcesantias',
                    'severance_interest_value': line_interes.total,
                })
            else:
                values.update({'severance_interest_value': line_interes.total})
        
        return values
    
    def _process_history_lines(self, record):
        """
        Procesa todas las líneas de historial en un solo método

        Incluye:
        - Vacaciones (nómina regular y liquidaciones)
        - Cesantías e intereses
        - Prima
        """
        process_type = record.struct_id.process
        is_liquidacion = process_type == 'contrato' and record.date_liquidacion

        lines_by_code = {line.code: line for line in record.line_ids}

        # VACACIONES: Para nómina regular
        vacation_codes = ['VACDISFRUTADAS', 'VACREMUNERADAS', 'VACATIONS_MONEY']
        for code in vacation_codes:
            line = lines_by_code.get(code)
            if line and line.initial_accrual_date:
                values = self._get_vacation_values(record, line)
                if values:
                    # Agregar campo 'type' para identificar operación
                    values['type'] = 'normal'  # Tipo: normal (no es liquidación)

                    if record.pay_vacations_in_payroll:
                        self._create_or_update_history('hr.vacation', values)
                    else:
                        self.env['hr.vacation'].create(values)

        # VACACIONES LIQUIDACIÓN: Para liquidaciones de contrato
        if is_liquidacion:
            vacation_liq_codes = ['VAC_LIQ', 'VACCONTRATO']
            for code in vacation_liq_codes:
                line = lines_by_code.get(code)
                if line and line.total > 0:
                    values = self._get_vacation_values(record, line)
                    if values:
                        # Asegurar fechas de causación
                        if not values.get('initial_accrual_date'):
                            values['initial_accrual_date'] = record.date_vacaciones or record.contract_id.date_start
                        if not values.get('final_accrual_date'):
                            values['final_accrual_date'] = record.date_liquidacion

                        self.env['hr.vacation'].create(values)
                        _logger.info(f"Creado historial de vacaciones liquidación: {line.quantity} días, ${line.total:,.0f}")

        # CESANTÍAS E INTERESES: Solo para provisiones/procesos específicos (NO liquidaciones)
        if process_type in ('cesantias', 'intereses_cesantias', 'nomina'):
            ces_line = lines_by_code.get('CESANTIAS')
            int_line = lines_by_code.get('INTCESANTIAS')

            if ces_line or int_line:
                values = self._get_severance_values(record, ces_line, int_line)
                if values:
                    # Agregar campo 'type' para identificar operación
                    values['type'] = 'normal'  # Tipo: normal (no es liquidación)
                    self._create_or_update_history('hr.history.cesantias', values)

        # PRIMA: Solo para provisiones/procesos específicos (NO liquidaciones)
        if process_type in ('prima', 'nomina'):
            prima_line = lines_by_code.get('PRIMA')
            if prima_line:
                date_from = record.date_prima
                date_to = record.date_to
                settlement_date = record.date_liquidacion if hasattr(record, 'date_liquidacion') else None

                values = {
                    'employee_id': record.employee_id.id,
                    'contract_id': record.contract_id.id,
                    'initial_accrual_date': date_from,
                    'final_accrual_date': date_to,
                    'settlement_date': settlement_date,
                    'time': prima_line.quantity,
                    'base_value': prima_line.amount_base,
                    'bonus_value': prima_line.total,
                    'payslip': record.id,
                    'type': 'normal',  # Tipo: normal (no es liquidación)
                }
                self._create_or_update_history('hr.history.prima', values)
    
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

        # v19: hr.payslip.state es draft/validated/paid/cancel ('done' ya no existe).
        # hr.payslip.run no tiene action_close() en v19; se setea state directo.
        self.write({'state': 'validated'})
        runs = self.mapped('payslip_run_id')
        if runs:
            runs.write({'state': '02_close'})
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
        payslips_without_period = self.env['hr.payslip'].search([
            ('state', 'in', ['verify', 'done', 'paid']),
            ('period_id', '=', False),
        ])
        
        if payslips_without_period:
            message = f"Se encontraron {len(payslips_without_period)} nóminas en estados avanzados sin período asignado."
            
            if len(payslips_without_period) <= 10:
                slip_details = []
                for slip in payslips_without_period:
                    details = f"- {slip.name} ({slip.employee_id.name}), Estado: {slip.state}, Fechas: {slip.date_from} - {slip.date_to}"
                    slip_details.append(details)
                
                message += "\n\nDetalles:\n" + "\n".join(slip_details)
            
            
            admin_user = self.env.ref('base.user_admin')
            model_id = self.env['ir.model'].search([('model', '=', 'hr.payslip')], limit=1).id
            
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'note': message,
                'user_id': admin_user.id,
                'res_model_id': model_id,
                'res_id': payslips_without_period[0].id if payslips_without_period else False,
                'summary': "Nóminas sin período asignado",
            })
        
        return payslips_without_period

    def assign_periods_to_draft_payslips(self):
        draft_slips = self.env['hr.payslip'].search([
            ('period_id', '=', False),
        ])
        
        if not draft_slips:
            return 0
        
        years_to_check = set(slip.date_from.year for slip in draft_slips)
        
        for year in years_to_check:
            for period_type in ['monthly', 'bi-monthly']:
                existing_periods = self.env['hr.period'].search([
                    ('year', '=', year),
                    ('type_period', '=', period_type),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
                
                if not existing_periods:
                    self.env.cr.commit()
                    self.env['hr.period'].create_periods_for_year(
                        year, schedule_pays=[period_type], company_id=self.env.company.id
                    )
                    self.env.cr.commit()
        
        updated_count = 0
        batch_size = 100
        period_obj = self.env['hr.period']
        for i in range(0, len(draft_slips), batch_size):
            batch = draft_slips[i:i+batch_size]
            
            for slip in batch:
                period_type = slip._infer_period_type(slip.date_from, slip.date_to, slip.contract_id)
                
                period = period_obj.get_period(
                slip.date_from, 
                slip.date_to, 
                period_type,
                slip.company_id.id)
            
                if period:
                    slip.write({"period_id": period.id})
                    updated_count += 1
            
            self.env.cr.commit()
        
        return updated_count

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
        
        Esta función verifica que los tipos de ausencia utilizados en las nóminas
        tengan correctamente configurados los campos que determinan su comportamiento
        en el cálculo de días trabajados.
        
        Returns:
            bool: True si todos los tipos están correctamente configurados
            
        Raises:
            UserError: Si algún tipo de ausencia no está correctamente configurado
        """
        if not self.leave_ids:
            return True
            
        valid_novelty_types = [
            'sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi', 
            'vre', 'lr', 'lnr', 'lt', 'p'
        ]
        
        leave_status_list = self.leave_ids.leave_id.mapped('holiday_status_id')
        missing_config = []
        
        for leave_status in leave_status_list:
            if not leave_status.novelty:
                missing_config.append(f"{leave_status.name}: Sin tipo PILA configurado")
            elif leave_status.novelty not in valid_novelty_types:
                missing_config.append(f"{leave_status.name}: Tipo PILA '{leave_status.novelty}' no válido")
                
            if leave_status.novelty in ['vco', 'p'] and leave_status.sub_wd:
                missing_config.append(f"{leave_status.name}: Tipo '{leave_status.novelty}' no debe restar días trabajados (sub_wd)")
                
            if not leave_status.work_entry_type_id:
                missing_config.append(f"{leave_status.name}: Falta tipo de entrada de trabajo (work_entry_type_id)")
        
        if missing_config:
            raise UserError(_(f"Configuración incorrecta en tipos de ausencia:\n{chr(10).join(missing_config)}"))
        
        return True
    
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
        
        Este método determina los días trabajados, días de ausencia, y otros ajustes
        necesarios para el cálculo correcto de la nómina.
        
        Returns:
            list: Lista de diccionarios con la información de cada línea de días trabajados
        """
        res = []
        
        def format_number(number: float) -> float:
            """ Convierte un número a formato decimal. y devuelve como float """
            return float(Decimal(number))
            
        for rec in self:
            contract = rec.contract_id
            date_from = rec.date_from
            date_to = rec.date_to
            wage_changes_sorted = sorted(contract.change_wage_ids, key=lambda x: x.date_start)
            last_wage_change = max((change for change in wage_changes_sorted if change.date_start < date_from), default=None)
            current_wage_day = last_wage_change.wage / DAYS_MONTH if last_wage_change else contract.wage / DAYS_MONTH
            leaves_worked_lines = {}
            worked_days = 0
            worked_aux_days = 0
            aux_transport_days = 0
            worked30 = 0
            hp_type = rec.struct_process
            annual_parameters = self.env['hr.annual.parameters'].search([('year', '=', date_to.year)], limit=1)
            w_hours_base = annual_parameters.hours_daily or HOURS_PER_DAY
            # Ajustar horas para contratos de tiempo parcial
            partial_factor = contract.factor if contract.parcial and contract.factor else 1.0
            w_hours = w_hours_base * partial_factor
            types = self._get_entry_types()
            days31 = types['days31']
            outdays = types['outdays']
            wdays = types['wdays']
            wdayst = types['wdayst']
            prevdays = types['prevdays']
            ps_types = ['nomina', 'contrato']
            if not rec.company_id.fragment_vac:
                ps_types.append('Vacaciones')
            adjustments = []
            if hp_type in ps_types:
                lab_days = rec.days_between(date_from, date_to)
                res.append({
                    'work_entry_type_id': wdayst.id,
                    'name': 'Total días del período',
                    'sequence': 1,
                    'code': 'TOTAL_DIAS',
                    'symbol': '',
                    'number_of_days': format_number(lab_days),
                    'number_of_hours': format_number(w_hours * lab_days),
                    'contract_id': contract.id
                })
                query = """
                    SELECT
                        SUM(wd.number_of_days) AS number_of_days,
                        wd.symbol,
                        hw.code
                    FROM hr_payslip_worked_days wd
                    INNER JOIN hr_payslip hp ON hp.id = wd.payslip_id
                    LEFT JOIN hr_work_entry_type hw ON hw.id = wd.work_entry_type_id
                    WHERE hp.date_from >= %s
                        AND hp.date_to <= %s
                        AND hp.contract_id = %s
                        AND hp.id != %s
                        AND hw.code NOT IN ('WORK_D', 'LICENCIA_REMUNERADA')
                        AND hp.struct_process IN ('vacaciones', 'nomina', 'contrato')
                        AND hp.state IN ('done', 'paid')
                    GROUP BY wd.symbol, hw.code
                """
                params = (date_from, date_to, contract.id, rec.id)
                self._cr.execute(query, params)
                wd_other_data = self._cr.fetchall()
                wd_other = 0
                wd_prev = 0
                wd_minus = 0
                
                for number_of_days, symbol, code in wd_other_data:
                    if code == 'WORK_D':
                        wd_other += number_of_days
                    else:
                        if code in ('PREV_AUS', 'PREV_PAYS'):
                            wd_prev += number_of_days
                        elif symbol in ('-', '') and code not in ('OUT', 'VAC', 'VACDISFRUTADAS'):
                            wd_minus += number_of_days

                sum_wdo = wd_minus - wd_prev
                wd_other = sum_wdo
                if wd_other > 0:
                    adjustments.append(f"(-{wd_other} D previos)")

                # Inicializar con días totales del período (sistema 360)
                worked_days = lab_days
                worked_aux_days = lab_days

                date_tmp = date_from
                out_of_contract_days = 0
                while date_tmp <= date_to:
                    is_absence_day = any(
                        leave.date_from.date() <= date_tmp <= leave.date_to.date() and 
                        leave.holiday_status_id.novelty not in ['vco', 'p'] and
                        leave.holiday_status_id.sub_wd
                        for leave in rec.leave_ids.leave_id
                    )
                    
                    is_within_contract = contract.date_start <= date_tmp <= (contract.date_end or date_tmp)
                    
                    wage_change_today = next((change for change in wage_changes_sorted if change.date_start == date_tmp), None)
                    if wage_change_today:
                        current_wage_day = wage_change_today.wage / DAYS_MONTH
                    if is_within_contract:
                        if is_absence_day:
                            # Buscar la ausencia CORRECTA que cubre este día específico
                            leave = next(
                                (lv for lv in rec.leave_ids.leave_id
                                 if lv.date_from.date() <= date_tmp <= lv.date_to.date()
                                 and lv.holiday_status_id.novelty not in ['vco', 'p']
                                 and lv.holiday_status_id.sub_wd),
                                None
                            )

                            if leave:
                                key = (leave.holiday_status_id.id, '-')
                                absence_line = next((line for line in leave.line_ids if line.date == date_tmp), None)

                                # Si hay línea de ausencia, usar sus valores
                                # Si no hay línea, usar valores por defecto (1 día, horas según jornada)
                                if absence_line:
                                    days_to_subtract = absence_line.days_payslip
                                    hour_to_subtract = absence_line.hours
                                    amount = absence_line.amount
                                else:
                                    # FALLBACK: Si no hay línea, usar 1 día calendario
                                    days_to_subtract = 1.0
                                    hour_to_subtract = w_hours
                                    amount = current_wage_day

                                # Solo procesar si hay días a restar
                                if days_to_subtract > 0:
                                    if key not in leaves_worked_lines:
                                        leaves_worked_lines[key] = {
                                            'work_entry_type_id': leave.holiday_status_id.work_entry_type_id.id if leave.holiday_status_id.work_entry_type_id else False,
                                            'name': f"Días {leave.holiday_status_id.name.capitalize()}",
                                            'sequence': 5,
                                            'code': leave.holiday_status_id.code or 'nocode',
                                            'symbol': '-',
                                            'amount': amount,
                                            'number_of_days': days_to_subtract,
                                            'number_of_hours': hour_to_subtract,
                                            'contract_id': contract.id,
                                        }
                                    else:
                                        leaves_worked_lines[key]['number_of_days'] += days_to_subtract
                                        leaves_worked_lines[key]['number_of_hours'] += hour_to_subtract
                                        leaves_worked_lines[key]['amount'] += amount

                                    # SIEMPRE restar días de ausencia de worked_days (afecta salario)
                                    worked_days -= days_to_subtract

                                    # Para auxilio de transporte:
                                    # - Si pay_transport_allowance=True: NO restar de worked_aux_days
                                    # - Si pay_transport_allowance=False: restar de worked_aux_days
                                    if leave.holiday_status_id.pay_transport_allowance:
                                        aux_transport_days += days_to_subtract
                                    else:
                                        worked_aux_days -= days_to_subtract

                            # NOTA: No se ajustan días de febrero porque days360 ya normaliza

                        else:
                            # Verificar día 31
                            if date_tmp.day == 31:
                                # Día 31: ya está ajustado en days360, verificar si hay ausencia especial
                                if any(leave.date_from.date() <= date_tmp <= leave.date_to.date()
                                      and leave.apply_day_31 for leave in rec.leave_ids.leave_id):
                                    worked_days -= 1
                                    worked_aux_days -= 1
                                    worked30 = 0
                                else:
                                    # No hacer nada: día 31 ya NO está contado en days360
                                    worked30 = 1
                                    # adjustments.append("(-1 D día 31)") - Ya no es necesario, days360 lo maneja
                    
                    else:
                        out_of_contract_days += 1
                    date_tmp += timedelta(days=1)

                if out_of_contract_days > 0:
                    description = 'Deducción por inicio de contrato' if date_from < contract.date_start else 'Deducción por fin de contrato'
                    res.append({
                        'work_entry_type_id': outdays.id,
                        'name': description,
                        'sequence': 2,
                        'code': 'OUT',
                        'symbol': '-',
                        'number_of_days': format_number(out_of_contract_days),
                        'number_of_hours': format_number(w_hours * out_of_contract_days),
                        'contract_id': contract.id,
                    })
                    adjustments.append(f"(-{out_of_contract_days} D fuera contrato)")
                    # IMPORTANTE: Restar dias fuera de contrato de los dias trabajados
                    worked_days -= out_of_contract_days
                    worked_aux_days -= out_of_contract_days
                    # Asegurar que no sean negativos
                    worked_days = max(0, worked_days)
                    worked_aux_days = max(0, worked_aux_days)

                for key, line_data in leaves_worked_lines.items():
                    line_data['number_of_days'] = format_number(line_data['number_of_days'])
                    line_data['number_of_hours'] = format_number(line_data['number_of_hours'])
                    res.append(line_data)

                # Calcular días de ausencias que NO pagan auxilio pero NO restan días trabajados
                # (ej: VACDISFRUTADAS con sub_wd=False, pay_transport_allowance=False)
                # Según Decreto 1250/2017: No se paga auxilio durante vacaciones
                days_without_aux_transport = 0
                for leave in rec.leave_ids.leave_id:
                    status = leave.holiday_status_id
                    # Solo ausencias que NO restan días (sub_wd=False) y NO pagan auxilio
                    if status.sub_wd:
                        continue  # Ya procesado arriba
                    if status.pay_transport_allowance:
                        continue  # Paga auxilio, no restar
                    if status.novelty in ['vco', 'p']:
                        continue  # Vacaciones compensadas o permisos especiales

                    # Calcular días de esta ausencia dentro del período de nómina
                    overlap_start = max(leave.date_from.date(), date_from)
                    overlap_end = min(leave.date_to.date(), date_to)
                    if overlap_start <= overlap_end:
                        # Usar days_between para cálculo comercial 360
                        days_without_aux = rec.days_between(overlap_start, overlap_end)
                        days_without_aux_transport += days_without_aux

                worked_aux_days = worked_days + aux_transport_days - days_without_aux_transport
                worked_days_name = 'Días Trabajados'
                if adjustments:
                    worked_days_name += " " + " ".join(adjustments)
                res.append({
                    'work_entry_type_id': wdays.id,
                    'name': worked_days_name,
                    'sequence': 6,
                    'code': 'WORK100',
                    'symbol': '+',
                    'amount': current_wage_day * worked_days,
                    'number_of_days': format_number(worked_days),
                    'number_of_hours': format_number(worked_days * w_hours),
                    'number_of_days_aux': format_number(worked_aux_days),
                    'number_of_hours_aux': format_number(worked_aux_days * w_hours),
                    'contract_id': contract.id
                })
                if rec.struct_id.regular_31:
                    res.append({
                        'work_entry_type_id': days31.id,
                        'name': 'Día 31',
                        'sequence': 6,
                        'code': 'WORK131',
                        'symbol': '+',
                        'amount': current_wage_day * worked30,
                        'number_of_days': format_number(worked30),
                        'number_of_hours': format_number(worked30 * w_hours),
                        'number_of_days_aux': format_number(worked30),
                        'number_of_hours_aux': format_number(worked30 * w_hours),
                        'contract_id': contract.id
                    })
                if wd_other:
                    res.append({
                        'work_entry_type_id': prevdays.id,
                        'name': 'Días Previos',
                        'sequence': 7,
                        'code': 'PREV_PAYS',
                        'symbol': '-',
                        'number_of_days': format_number(wd_other),
                        'number_of_hours': format_number(wd_other * w_hours),
                        'contract_id': contract.id
                    })
        return res
    
    def compute_sheet_leave(self):
        """
        Calcula y asigna las ausencias para la nómina con detalle mejorado
        de días usados y no utilizados, respetando la estructura de campos existente.

        OPTIMIZACIÓN: Si existe payroll_batch_context, usa leaves pre-cargados.
        """
        for rec in self:
            # Limpiar cualquier línea de ausencia previamente asociada al slip.
            # Si la ausencia cambió de estado (p. ej. rechazada), la línea queda "pegada"
            # y vuelve a entrar en el cálculo.
            rec.leave_days_ids.write({'payslip_id': False})
            rec.leave_ids.unlink()
            rec.payslip_day_ids.unlink()
            date_from = datetime.combine(rec.date_from, DATETIME_MIN)
            date_to = datetime.combine(rec.date_to, DATETIME_MAX)
            employee_id = rec.employee_id.id

            # OPTIMIZACIÓN: Usar batch context si está disponible
            batch_ctx = self.env.context.get('payroll_batch_context')
            if batch_ctx:
                # Filtrar las leaves pre-cargadas por fechas
                all_leaves = batch_ctx.get_employee_leaves(employee_id)
                leaves = all_leaves.filtered(
                    lambda l: l.date_to >= date_from and l.date_from <= date_to
                )
            else:
                leaves = self.env['hr.leave'].search([
                    ('state', 'in', ['validate', 'validate1', 'validate2']),
                    ('date_to', '>=', date_from),
                    ('date_from', '<=', date_to),
                    ('employee_id', '=', employee_id),
                ])
            self._validate_leave_types()
            
            if not leaves:
                rec.compute_worked_days()
                return True
            
            absence_records = []
            
            for leave in leaves:
                leave_start = max(leave.date_from.date(), rec.date_from)
                leave_end = min(leave.date_to.date(), rec.date_to)
                days_in_payslip = (leave_end - leave_start).days + 1
                days_in_other_payslips = sum(
                    line.days_payslip 
                    for line in leave.line_ids 
                    if line.payslip_id and line.payslip_id.id != rec.id
                )
                affects_payroll = leave.holiday_status_id.novelty not in ['vco', 'p'] and leave.holiday_status_id.sub_wd
                days_to_use = days_in_payslip if affects_payroll else 0
                days_not_used = leave.number_of_days_in_payslip - days_to_use - days_in_other_payslips
                absence_data = {
                    'leave_id': leave.id,
                    'leave_type': leave.holiday_status_id.name,
                    'employee_id': employee_id,
                    'payroll_id': rec.id,
                    'total_days': leave.number_of_days_in_payslip,
                    'days_used': days_to_use,
                    'days': days_in_other_payslips,
                    'days_unused': days_not_used,
                    'total': leave.number_of_days_in_payslip - days_in_other_payslips,
                    'is_interrupted': False,
                }
                
                absence_records.append(absence_data)
            if absence_records:
                leave_records = self.env['hr.absence.days'].create(absence_records)
                all_lines = leave_records.mapped('leave_id.line_ids').filtered(
                    lambda l: l.state in ('validated', 'paid')
                    and l.leave_id
                    and l.leave_id.state in ('validate', 'validate1', 'validate2')
                )
                if rec.struct_id.process == 'vacaciones' or rec.pay_vacations_in_payroll:
                    vacation_lines = all_lines.filtered(lambda l: l.leave_id.holiday_status_id.is_vacation)
                    if vacation_lines:
                        money_lines = vacation_lines.filtered(
                            lambda l: l.leave_id.holiday_status_id.is_vacation_money
                        )
                        time_lines = vacation_lines - money_lines
                        
                        relevant_lines = money_lines
                        if rec.company_id.fragment_vac:
                            relevant_lines |= time_lines.filtered(
                                lambda l: rec.date_from <= l.date <= rec.date_to
                            )
                        else:
                            relevant_lines |= time_lines
                        
                        relevant_lines.write({
                            'payslip_id': rec.id,
                        })
                    
                    other_lines = all_lines - vacation_lines
                    if other_lines:
                        other_lines.filtered(
                            lambda l: rec.date_from <= l.date <= rec.date_to
                        ).write({
                            'payslip_id': rec.id
                        })
                
                else:
                    relevant_lines = all_lines.filtered(
                        lambda l: (
                            rec.date_from <= l.date <= rec.date_to and
                            not l.leave_id.holiday_status_id.is_vacation and 
                            not l.leave_id.holiday_status_id.is_vacation_money
                        )
                    )
                    if relevant_lines:
                        relevant_lines.write({
                            'payslip_id': rec.id
                        })
            rec.compute_worked_days()
        return True

    def compute_worked_days(self):
        """
        Calcula los días trabajados para la nómina.
        Incluye manejo especial para febrero, día 31, días de descanso, sábados y feriados.
        """
        for rec in self:
            payslip_day_ids = []
            rec._validate_leave_types()
            wage_changes_sorted = sorted(rec.contract_id.change_wage_ids, key=lambda x: x.date_start)
            last_wage_change_before_payslip = max((change for change in wage_changes_sorted 
                                                if change.date_start < rec.date_from), default=None)
            current_wage_day = last_wage_change_before_payslip.wage / DAYS_MONTH if last_wage_change_before_payslip else rec.contract_id.wage / DAYS_MONTH
            has_day_31 = False
            holiday_service = self.env['lavish.holidays']
            date_tmp = rec.date_from
            while date_tmp <= rec.date_to:
                absence_line = None
                permission_line = None
                permission_leaves = [
                    leave for leave in rec.leave_ids.leave_id.line_ids 
                    if leave.date <= date_tmp <= leave.date and 
                    leave.leave_id.holiday_status_id.novelty == 'p'
                ]
                is_permission_day = bool(permission_leaves)
                if is_permission_day:
                    permission_leave = permission_leaves[0]
                    permission_line = next(
                        (line for line in permission_leave 
                        if line.date == date_tmp and line.state in ['paid','validated']), 
                        None
                    )
                absence_leaves = [
                    leave for leave in rec.leave_ids.leave_id.line_ids  
                    if leave.date <= date_tmp <= leave.date and 
                    leave.leave_id.holiday_status_id.novelty not in ['vco', 'p'] and
                    leave.leave_id.holiday_status_id.sub_wd
                ]
                
                is_absence_day = bool(absence_leaves)
                
                if is_absence_day:
                    absence_leave = absence_leaves[0]
                    absence_line = next(
                        (line for line in absence_leaves
                        if line.date == date_tmp and line.state in ['paid','validated']), 
                        None
                    )
                
                is_within_contract = rec.contract_id.date_start <= date_tmp <= (rec.contract_id.date_end or date_tmp)
                is_holiday = holiday_service.ensure_holidays(date_tmp)
                is_sunday = date_tmp.weekday() == 6
                is_saturday = date_tmp.weekday() == 5 and not rec.employee_id.sabado
                is_day_31 = date_tmp.day == 31
                wage_change_today = next((change for change in wage_changes_sorted if change.date_start == date_tmp), None)
                if wage_change_today:
                    current_wage_day = wage_change_today.wage / DAYS_MONTH
                if is_within_contract:
                    if is_absence_day:
                        day_type = 'A'  # Ausencia
                    elif is_permission_day:
                        day_type = 'P'  # Permiso (informativo, no resta días)
                    elif is_holiday:
                        day_type = 'H'  # Feriado
                    elif is_sunday:
                        day_type = 'D'  # Día de descanso (domingo)
                    elif is_saturday:
                        day_type = 'S'  # Sábado
                    else:
                        day_type = 'W'  # Trabajado
                    payslip_day_data = {
                        'payslip_id': rec.id, 
                        'day': date_tmp.day, 
                        'day_type': day_type,
                        'is_holiday': is_holiday,
                        'is_sunday': is_sunday,
                        'is_saturday': is_saturday,
                        'is_permission': is_permission_day,
                        'is_absence': is_absence_day
                    }
                    
                    if absence_line:
                        payslip_day_data['leave_line_id'] = absence_line.id
                    elif permission_line:
                        payslip_day_data['leave_line_id'] = permission_line.id
                    if is_day_31:
                        has_day_31 = True
                        apply_day_31 = any(
                            leave.date_from.date() <= date_tmp <= leave.date_to.date() and 
                            leave.apply_day_31 
                            for leave in rec.leave_ids.leave_id
                        )
                        
                        if not apply_day_31:
                            payslip_day_data['is_day_31'] = True
                    if date_tmp.month == 2:
                        last_day_of_february = calendar.monthrange(date_tmp.year, 2)[1]
                        if date_tmp.day == last_day_of_february:
                            payslip_day_data['is_feb_last'] = True
                    
                            if date_tmp.day == 28:
                                payslip_day_data['feb_adjust'] = 2  
                            else:  # día 29
                                payslip_day_data['feb_adjust'] = 1  
                    if day_type not in ['A', 'X']:
                        payslip_day_data['subtotal'] = current_wage_day
                    payslip_day_ids.append(payslip_day_data)
                else:
                    payslip_day_ids.append({
                        'payslip_id': rec.id, 
                        'day': date_tmp.day, 
                        'day_type': 'X',
                        'is_holiday': is_holiday,
                        'is_sunday': is_sunday,
                        'is_saturday': is_saturday
                    })
                date_tmp += timedelta(days=1)
            if rec.period_id.type_period == "monthly" and not has_day_31:
                last_day = calendar.monthrange(rec.date_to.year, rec.date_to.month)[1]
                if last_day < 31:
                    payslip_day_ids.append({
                        'payslip_id': rec.id,
                        'day': 31,
                        'day_type': 'V',
                        'is_virtual': True,
                        'is_day_31': True
                    })
            rec.payslip_day_ids.create(payslip_day_ids)

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

