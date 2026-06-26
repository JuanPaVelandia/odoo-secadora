
"""
IMPORTANTE - MIGRACIÓN ODOO 18:
================================
Este módulo contiene referencias a 'rules_multi' y 'result_rules_co' que fueron
ELIMINADOS en la migración a Odoo 19 nativo.

ESTRUCTURA ANTIGUA (Odoo 15):
- rules_multi: Dict con múltiples períodos de la misma regla
- result_rules_co: Dict con info de bases (prima, cesantías, etc.)

ESTRUCTURA NUEVA (Odoo 19):
- rules: DefaultDictPayroll con estructura nativa
  - rules[code]['rule'] = objeto completo con campos base_*
  - rules[code]['total'] = total acumulado

Para acceder a campos base_*:
  ANTES: result_rules_co[code]['base_prima']
  AHORA: rules[code]['rule'].base_prima

Las referencias a rules_multi en este archivo retornarán valores vacíos ({})
hasta que se implemente la nueva lógica usando métodos SQL de acumulación
del módulo lavish_hr_payroll (hr_slip_acumulacion.py).
"""

from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
from odoo.exceptions import UserError, ValidationError
import time
from odoo.tools.safe_eval import safe_eval
import json
from odoo.tools.float_utils import float_round
import logging
_logger = logging.getLogger(__name__)
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import defaultdict
from odoo.tools import format_date, formatLang, frozendict, date_utils,format_amount

from decimal import Decimal, getcontext,ROUND_HALF_UP
from odoo.addons.lavish_hr_payroll.models.hr_slip_constante import (
    DAYS_YEAR, DAYS_YEAR_NATURAL, DAYS_MONTH, PRECISION_TECHNICAL, PRECISION_DISPLAY,
    DATETIME_MIN, DATETIME_MAX, HOURS_PER_DAY, TABLA_RETENCION, days360, round_1_decimal
)
getcontext().prec = 10

class ParamLoader:
    _CACHE: Dict[int, Dict[str, float]] = {}

    @classmethod
    def _read(cls, env, year: int) -> Dict[str, float]:
        rec = env['hr.annual.parameters'].search([('year', '=', year)], limit=1)
        if not rec:
            raise UserError(_('Faltan parámetros anuales para %s') % year)
        return {
            'SMMLV_DAILY':   rec.smmlv_daily,
            'TOPE_25_SMMLV': rec.top_twenty_five_smmlv,
            'TOPE_40':       rec.value_porc_statute_1395 / 100,
            'INT_FACTOR':    rec.porc_integral_salary / 100,  # 0.70
        }

    @classmethod
    def for_date(cls, env, d: date) -> Dict[str, float]:
        if d.year not in cls._CACHE:
            cls._CACHE[d.year] = cls._read(env, d.year)
        return cls._CACHE[d.year]

def monthrange(year=None, month=None):
    today = datetime.today()
    y = year or today.year
    m = month or today.month
    return y, m, calendar.monthrange(y, m)[1]

def get_days_in_months():
    """
    Genera una lista con el número de días en cada mes, considerando los años bisiestos.
    
    Returns:
        list: Lista con el número de días en cada mes.
    """
    days_in_months = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    
    # Ajustar el número de días en febrero para años bisiestos
    days_in_months[2] = 29 if calendar.isleap(datetime.now().year) else 28
    
    return days_in_months

def format_currency(value):
    """
    Formatea un número como una cadena de texto con formato de moneda.
    """
    return "${:,.2f}".format(value)


class hr_salary_rule(models.Model):
    _name = 'hr.salary.rule'
    _inherit = ['hr.salary.rule','mail.thread', 'mail.activity.mixin']

    #Trazabilidad
    struct_id = fields.Many2one(tracking=True)
    active = fields.Boolean(tracking=True)
    sequence = fields.Integer(tracking=True)
    condition_select = fields.Selection(tracking=True)
    amount_select = fields.Selection(tracking=True)
    amount_python_compute = fields.Text(tracking=True)
    appears_on_payslip = fields.Boolean(tracking=True)
    proyectar_nom = fields.Boolean('Proyectar en nomina')
    proyectar_ret = fields.Boolean('Proyectar en Retencion')
    #Campos lavish
    types_employee = fields.Many2many('hr.types.employee',string='Tipos de Empleado', tracking=True)
    dev_or_ded = fields.Selection([('devengo', 'Devengo'),
                                     ('deduccion', 'Deducción')],'Naturaleza', tracking=True)
    type_concepts = fields.Selection([('contrato', 'Fijo Contrato'),
                                     ('ley', 'Por Ley'),
                                     ('novedad', 'Novedad Variable'),
                                     ('prestacion', 'Prestación Social'),
                                     ('tributaria', 'Deducción Tributaria')],'Tipo', required=True, default='contrato', tracking=True)
    aplicar_cobro = fields.Selection([('15','Primera quincena'),
                                        ('30','Segunda quincena'),
                                        ('0','Siempre')],'Aplicar cobro', tracking=True)
    modality_value = fields.Selection([('fijo', 'Valor fijo'),
                                       ('diario', 'Valor diario'),
                                       ('diario_efectivo', 'Valor diario del día efectivamente laborado')],'Modalidad de valor', tracking=True)
    deduction_applies_bonus = fields.Boolean('Aplicar deducción en Prima', tracking=True)
    account_tax_id = fields.Many2one("account.tax", "Impuesto de Retefuente Laboral")
    #Es incapacidad / deducciones
    amount_select = fields.Selection(
        selection_add=[
            ('concept', 'Concept Code')
        ], 
        ondelete={
            'concept': 'set default'
        }
    )
    is_leave = fields.Boolean('Es Ausencia', tracking=True)
    is_recargo = fields.Boolean('Es Recargos', tracking=True)
    deduct_deductions = fields.Selection([('all', 'Todas las deducciones'),
                                          ('law', 'Solo las deducciones de ley')],'Tener en cuenta al descontar', default='all', tracking=True)
    rounding_method = fields.Selection([
        ('no_round', 'Sin redondeo'),
        ('round1', 'Redondear a entero'),
        ('round100', 'Redondear al 100 más cercano'),
        ('round1000', 'Redondear al 1000 más cercano'),
        ('round2d', 'Redondear a 2 decimales')
    ], string='Método de redondeo', default='no_round', 
       help="Seleccione el método de redondeo para aplicar al resultado de esta regla salarial.")




    restart_one_month_prima = fields.Boolean('Restar 1 mes al promedio de los acumulados en prima', tracking=True)
    liquidar_con_base = fields.Boolean('Liquidar con IBC mes anterior', tracking=True)
    base_prima = fields.Boolean('Para prima', tracking=True)
    base_cesantias = fields.Boolean('Para cesantías', tracking=True)
    base_vacaciones = fields.Boolean('Para vacaciones tomadas', tracking=True)
    base_vacaciones_dinero = fields.Boolean('Para vacaciones dinero', tracking=True)
    base_intereses_cesantias = fields.Boolean('Para intereses de cesantías', tracking=True)
    base_auxtransporte_tope = fields.Boolean('Para tope de auxilio de transporte', tracking=True)
    base_compensation = fields.Boolean('Para liquidación de indemnización', tracking=True)

    # Contadores para prestaciones sociales
    prima_rules_count = fields.Integer('Reglas Prima', compute='_compute_prestaciones_counts', store=False)
    cesantias_rules_count = fields.Integer('Reglas Cesantías', compute='_compute_prestaciones_counts', store=False)
    vacaciones_rules_count = fields.Integer('Reglas Vacaciones', compute='_compute_prestaciones_counts', store=False)
    intereses_cesantias_rules_count = fields.Integer('Reglas Int. Cesantías', compute='_compute_prestaciones_counts', store=False)

    #Base de Seguridad Social
    base_seguridad_social = fields.Boolean('Para seguridad social', tracking=True)
    base_arl = fields.Boolean('Para seguridad social', tracking=True)
    base_parafiscales = fields.Boolean('Para parafiscales', tracking=True)
    excluir_ret = fields.Boolean('excluir de Calculo retefuente', tracking=True)
    is_projectable_rtf = fields.Boolean(
        string='Proyectable para Retención / Fondos',
        default=False,
        help='Indica si este concepto debe ser proyectado en el cálculo de retención en la fuente'
    )

    descontar_suspensiones = fields.Boolean('Descontar Licencia No remuneradas', tracking=True)
    salary_rule_accounting = fields.One2many('hr.salary.rule.accounting', 'salary_rule', string="Contabilización", tracking=True)
    #Reportes
    display_days_worked = fields.Boolean(string='Mostrar la cantidad de días trabajados en los formatos de impresión', tracking=True)
    short_name = fields.Char(string='Nombre corto/reportes')
    process = fields.Selection([('nomina', 'Nónima'),
                                ('vacaciones', 'Vacaciones'),
                                ('prima', 'Prima'),
                                ('cesantias', 'Cesantías'),
                                ('intereses_cesantias', 'Intereses de cesantías'),
                                ('contrato', 'Liq. de Contrato'),
                                ('otro', 'Otro')], string='Proceso')
    novedad_ded = fields.Selection([('cont', 'Contrato'),
                                    ('Noved', 'Novedad'),
                                    ('0', 'No'),],'Opcion de Novedad', tracking=True)
    not_include_flat_payment_file = fields.Boolean(string='No incluir en archivo plano de pagos')
    #Empleados publicos
    account_id_cxp = fields.Many2one('account.account',string='Cuenta CXP', company_dependent=True)
    state_budget_item = fields.Char(string='Rubro')
    state_budget_resource = fields.Char(string='Recurso')

    @api.depends_context('company')
    def _compute_prestaciones_counts(self):
        """Calcula el número de reglas marcadas para prima, cesantías y vacaciones"""
        for rule in self:
            # Obtener estructura asociada a la regla
            struct = rule.struct_id

            if struct:
                # Buscar todas las reglas de la misma estructura
                all_rules = self.search([('struct_id', '=', struct.id), ('active', '=', True)])

                # Contar reglas para cada concepto
                rule.prima_rules_count = len(all_rules.filtered('base_prima'))
                rule.cesantias_rules_count = len(all_rules.filtered('base_cesantias'))
                rule.vacaciones_rules_count = len(all_rules.filtered(lambda r: r.base_vacaciones or r.base_vacaciones_dinero))
                rule.intereses_cesantias_rules_count = len(all_rules.filtered('base_intereses_cesantias'))
            else:
                # Si no hay estructura, contar en toda la compañía
                all_rules = self.search([('company_id', '=', rule.company_id.id), ('active', '=', True)])

                rule.prima_rules_count = len(all_rules.filtered('base_prima'))
                rule.cesantias_rules_count = len(all_rules.filtered('base_cesantias'))
                rule.vacaciones_rules_count = len(all_rules.filtered(lambda r: r.base_vacaciones or r.base_vacaciones_dinero))
                rule.intereses_cesantias_rules_count = len(all_rules.filtered('base_intereses_cesantias'))

    def _compute_rule(self, localdict):
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate)
        :rtype: (float, float, float)
        """
        self.ensure_one()
        res = 0,0,0,0,0,[]#monto:float, cantidad:float, tasa:float, nombre:str, log:Xml, data:dict
        if self.amount_select == 'fix':
            try:
                return
            except Exception as e:
                self._raise_error(localdict, _("Wrong quantity defined for:"), e)
        if self.amount_select == 'percentage':
            try:
                return (float(safe_eval(self.amount_percentage_base, localdict)),
                        float(safe_eval(self.quantity, localdict)),
                        self.amount_percentage or 0.0, self.name,False,False)
            except Exception as e:
                self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e)
        if self.amount_select == 'code':
            try:
                safe_eval(self.amount_python_compute or 0.0, localdict, mode='exec')
                return float(localdict['result']), localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0), self.name,False,False
            except Exception as e:
                self._raise_error(localdict, _("Wrong python code defined for:"), e)
        if self.amount_select == 'concept':
            try:
                method = getattr(self, '_' + str(self.code).lower(), None)
                if method:
                    res = method(localdict)
                    return float(res[0]), res[1], res[2], res[3],res[4],res[5]
                return float(res[0]), res[1], res[2] , res[3],res[4],res[5]
            except Exception as e:
                self._raise_error(localdict, _("Wrong python code defined for:"), e)



    def _compute_rule_lavish(self, localdict):
        """
        :param localdict: dictionary containing the current computation environment
        :return: returns a tuple (amount, qty, rate)
        :rtype: (float, float, float)
        """
        self.ensure_one()
        res = 0,0,0,0,0,[]
        try:
            if self.amount_select == 'fix':
                try:
                    return self.amount_fix or 0.0, float(safe_eval(self.quantity, localdict)), 100.0,False,False,False
                except Exception as e:
                    self._raise_error(localdict, _("Wrong quantity defined for:"), e, "amount_fix calculation")
                    
            if self.amount_select == 'percentage':
                try:
                    return (float(safe_eval(self.amount_percentage_base, localdict)),
                            float(safe_eval(self.quantity, localdict)),
                            self.amount_percentage or 0.0,False,False,False)
                except Exception as e:
                    self._raise_error(localdict, _("Wrong percentage base or quantity defined for:"), e, "percentage calculation")
                    
            if self.amount_select == 'code':
                try:
                    safe_eval(self.amount_python_compute or 0.0, localdict, mode='exec')
                    return float(localdict['result']), localdict.get('result_qty', 1.0), localdict.get('result_rate', 100.0),False,False,False
                except Exception as e:
                    error_context = {
                        'code': self.amount_python_compute,
                        'location': 'Python code evaluation'
                    }
                    self._raise_error(localdict, _("Wrong python code defined for:"), e, "code evaluation", error_context)
                    
            if self.amount_select == 'concept':
                try:
                    method = getattr(self, '_' + str(self.code).lower(), None)
                    if method:
                        res = method(localdict)
                        return float(res[0]), res[1], res[2], res[3], res[4], res[5]
                    return float(res[0]), res[1], res[2], res[3], res[4], res[5]
                except Exception as e:
                    error_context = {
                        'method_name': f'_{str(self.code).lower()}',
                        'location': 'Concept method execution'
                    }
                    self._raise_error(localdict, _("Wrong python code defined for:"), e, "concept execution", error_context)
                    
        except Exception as e:
            self._raise_error(localdict, _("Unexpected error in rule computation:"), e, "general computation")
            
    def _raise_error(self, localdict, error_type, e, error_location=None, error_context=None):
        """
        Raise a detailed error message with context information
        Args:
            localdict: The local dictionary with computation context
            error_type: Type of error that occurred
            e: The exception object
            error_location: Where the error occurred
            error_context: Additional context about the error (optional)
        """
        import traceback
        import sys
        
        # Get the full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        trace_details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        # Get relevant code if available
        code_context = ""
        if error_context and 'code' in error_context:
            code_context = f"\n\nRelevant code:\n{error_context['code']}"
        
        # Get specific error details
        error_details = f"\n\nError Location: {error_location}"
        if error_context:
            for key, value in error_context.items():
                if key != 'code':  # Skip code as it's already included above
                    error_details += f"\n{key}: {value}"
        
        # Build the complete error message
        error_message = _("""%s
    - Employee: %s
    - Contract: %s
    - Payslip: %s
    - Salary rule: %s (%s)
    - Error type: %s
    - Error message: %s
    %s
    %s

    Traceback:
    %s""",
            error_type,
            localdict['employee'].name,
            localdict['contract'].name,
            localdict['payslip'].name,
            self.name,
            self.code,
            type(e).__name__,
            str(e),
            error_details,
            code_context,
            trace_details)
        
        raise UserError(error_message)

    def _compute_overtime_generic(self, localdict, rule_code, percentage, field_name):
        """
        Método genérico para cálculo de horas extras y recargos.

        Args:
            localdict: Diccionario de contexto de nómina
            rule_code: Código de la regla (HEYREC001, HEYREC002, etc.)
            percentage: Porcentaje de recargo (125.0, 200.0, 175.0, 110.0, 35.0)
            field_name: Campo en hr.overtime que contiene las horas

        Returns:
            Tuple: (rate, quantity, percentage, name, False, {})
        """
        contract = localdict['contract']
        employee = localdict['employee']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')

        # Validar si el contrato permite pago de horas extras
        if hasattr(contract, 'not_pay_overtime') and contract.not_pay_overtime:
            return 0, 0, 0, f'HE {rule_code}', False, {}

        # Buscar registros de horas extras en el período
        overtime_records = self.env['hr.overtime'].search([
            ('employee_id', '=', employee.id),
            ('date', '>=', slip.date_from),
            ('date', '<=', slip.date_to)
        ])

        total_hours = 0
        total_value = 0

        # Calcular tasa horaria base
        if hasattr(annual_parameters, 'hours_monthly') and annual_parameters.hours_monthly > 0:
            base_hours = annual_parameters.hours_monthly
        else:
            base_hours = 240  # 30 días × 8 horas

        hourly_rate = Decimal(contract.wage) / Decimal(base_hours)

        # Procesar cada registro de horas extras
        for overtime in overtime_records:
            # Obtener horas del campo específico
            hours = getattr(overtime, field_name, 0) if hasattr(overtime, field_name) else 0

            if hours > 0:
                # Calcular valor con porcentaje de recargo
                hours_decimal = Decimal(str(hours))
                percentage_decimal = Decimal(str(percentage)) / Decimal('100')
                value = hourly_rate * percentage_decimal * hours_decimal

                total_hours += float(hours)
                total_value += float(value)

        # Si no hay horas, retornar 0
        if total_hours == 0:
            return 0, 0, percentage, f'HE {rule_code}', False, {}

        # Calcular tasa promedio
        rate = total_value / total_hours if total_hours > 0 else 0

        return rate, total_hours, percentage, f'HE {rule_code}', False, {}

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PARA OBTENER DATOS DEL PERÍODO ACTUAL (MES EN PROCESO)
    # ══════════════════════════════════════════════════════════════════════════

    def _get_current_period_data(self, localdict, filters=None):
        """
        Obtiene datos del período ACTUAL (mes en proceso) desde localdict['rules'].
        Compatible con Odoo 19 - usa estructura nativa.

        Args:
            localdict: Diccionario de contexto de nómina
            filters: Dict con filtros a aplicar
                {
                    'rules': ['BASIC', 'HE001'],           # Códigos de reglas específicas
                    'categories': ['BASIC', 'DEV_SALARIAL'],  # Códigos de categorías
                    'exclude_rules': ['BASIC'],            # Excluir reglas
                    'exclude_categories': ['DED'],         # Excluir categorías
                    'base_prima': True,                    # Solo reglas con base_prima=True
                    'base_cesantias': True,                # Solo reglas con base_cesantias=True
                    'base_ss': True,                       # Solo reglas con base_seguridad_social=True
                    'base_vacaciones': True,               # Solo reglas con base_vacaciones=True
                    'min_amount': 1000,                    # Monto mínimo
                    'conditions': lambda rule: rule.code.startswith('HE')  # Condición custom
                }

        Returns:
            dict: {
                'total': float,
                'quantity': float,
                'by_rule': {code: {'total': X, 'quantity': Y, 'rule': obj}},
                'by_category': {code: {'total': X, 'quantity': Y}}
            }
        """
        filters = filters or {}

        # Inicializar resultado
        result = {
            'total': 0.0,
            'quantity': 0.0,
            'by_rule': {},
            'by_category': {}
        }

        # Obtener rules desde localdict (Odoo 19 nativo)
        rules = localdict.get('rules', {})

        if not rules:
            return result

        # Procesar cada regla
        for code, rule_data in rules.items():
            rule_obj = rule_data.rule
            total = rule_data.total
            quantity = rule_data.quantity

            if not rule_obj:
                continue

            # Aplicar filtros
            if not self._passes_current_period_filters(rule_obj, filters):
                continue

            # Agregar a totales
            result['total'] += total
            result['quantity'] += quantity

            # Agregar por regla
            result['by_rule'][code] = {
                'total': total,
                'quantity': quantity,
                'rule': rule_obj
            }

            # Agregar por categoría
            if rule_obj.category_id:
                cat_code = rule_obj.category_id.code
                if cat_code not in result['by_category']:
                    result['by_category'][cat_code] = {'total': 0.0, 'quantity': 0.0}

                result['by_category'][cat_code]['total'] += total
                result['by_category'][cat_code]['quantity'] += quantity

        return result

    def _passes_current_period_filters(self, rule_obj, filters):
        """
        Verifica si una regla pasa todos los filtros especificados.

        Args:
            rule_obj: Objeto hr.salary.rule
            filters: Dict con filtros

        Returns:
            bool: True si pasa todos los filtros
        """
        if not filters:
            return True

        # Filtro de reglas específicas
        if 'rules' in filters:
            rules_filter = filters['rules'] if isinstance(filters['rules'], list) else [filters['rules']]
            if rule_obj.code not in rules_filter:
                return False

        # Filtro de reglas excluidas
        if 'exclude_rules' in filters:
            excluded = filters['exclude_rules'] if isinstance(filters['exclude_rules'], list) else [filters['exclude_rules']]
            if rule_obj.code in excluded:
                return False

        # Filtro de categorías
        if 'categories' in filters and rule_obj.category_id:
            categories = filters['categories'] if isinstance(filters['categories'], list) else [filters['categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if not (cat_code in categories or parent_code in categories):
                return False

        # Filtro de categorías excluidas
        if 'exclude_categories' in filters and rule_obj.category_id:
            excluded = filters['exclude_categories'] if isinstance(filters['exclude_categories'], list) else [filters['exclude_categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if cat_code in excluded or parent_code in excluded:
                return False

        # Filtros de base
        if 'base_prima' in filters and filters['base_prima']:
            if not rule_obj.base_prima:
                return False

        if 'base_cesantias' in filters and filters['base_cesantias']:
            if not rule_obj.base_cesantias:
                return False

        if 'base_ss' in filters and filters['base_ss']:
            if not rule_obj.base_seguridad_social:
                return False

        if 'base_vacaciones' in filters and filters['base_vacaciones']:
            if not rule_obj.base_vacaciones:
                return False

        # Filtro de condiciones custom
        if 'conditions' in filters and callable(filters['conditions']):
            if not filters['conditions'](rule_obj):
                return False

        return True

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE PRESTACIONES SOCIALES
    # ══════════════════════════════════════════════════════════════════════════

    def _int_cesantias(self, localdict):
        """Cálculo de intereses de cesantías"""
        result = self._calculate_prestacion_generic(localdict, 'int_ces', 'base_cesantias')

        # Ajustar para intereses (12% anual)
        val_prest = result[0]
        dias = result[1]

        porcentaje = (0.12 * dias) / DAYS_YEAR
        val_prest_ajustado = val_prest * porcentaje

        return val_prest_ajustado, dias, 100, result[3], result[4], result[5]

    def _calculate_prestacion_generic(self, localdict, tipo_prestacion, param_base):
        """
        Método genérico para calcular prestaciones sociales.
        Usa acumulación de hr_slip_acumulacion.py y datos del período actual.

        Args:
            localdict: Diccionario de contexto
            tipo_prestacion: 'prima', 'ces', 'int_ces'
            param_base: 'base_prima', 'base_cesantias'

        Returns:
            tuple: (valor, días, porcentaje, nombre, log_data, extra_data)
        """
        contract = localdict['contract']
        slip = localdict['slip']
        employee = localdict['employee']
        annual_parameters = localdict.get('annual_parameters')

        # Validar contrato
        if contract.modality_salary == 'integral':
            return 0, 0, 0, f'{tipo_prestacion.upper()} - No aplica salario integral', {}, {}

        if employee.tipo_coti_id and employee.tipo_coti_id.code in ['12', '19']:
            return 0, 0, 0, f'{tipo_prestacion.upper()} - No aplica aprendiz', {}, {}

        # Determinar período según tipo de prestación
        if tipo_prestacion in ['ces', 'int_ces']:
            # Cesantías: Año completo (1 enero - 31 diciembre)
            d0 = date(slip.date_to.year, 1, 1)
            d1 = date(slip.date_to.year, 12, 31)
            if contract.date_start and contract.date_start > d0:
                d0 = contract.date_start
        elif tipo_prestacion == 'prima':
            # Prima: Semestre (1 enero - 30 junio) o (1 julio - 31 diciembre)
            mes = slip.date_to.month
            if mes <= 6:
                d0 = date(slip.date_to.year, 1, 1)
                d1 = date(slip.date_to.year, 6, 30)
            else:
                d0 = date(slip.date_to.year, 7, 1)
                d1 = date(slip.date_to.year, 12, 31)

            if contract.date_start and contract.date_start > d0:
                d0 = contract.date_start
        else:
            d0 = slip.date_from
            d1 = slip.date_to

        # Calcular días totales (360 días comerciales)
        dias_totales = days360(d0, d1)

        # Obtener ausencias no remuneradas desde acumulación
        dias_suspension = slip._get_leave_days_no_pay(d0, d1, contract.id)

        # Días efectivos
        dias_efectivos = max(dias_totales - dias_suspension, 0)

        if dias_efectivos == 0:
            return 0, 0, 0, f'{tipo_prestacion.upper()} - Sin días efectivos', {}, {}

        # ===== OBTENER BASE DE CÁLCULO =====

        # 1. Salario base contractual
        salario_base = contract.wage

        # 2. Auxilio de transporte (si aplica)
        auxilio_transporte = 0
        if contract.modality_aux == 'basico' and annual_parameters:
            # Validar si aplica auxilio según salario
            salary_validation = self._get_salary_base_for_tope(localdict)
            if salary_validation <= 2 * annual_parameters.smmlv_monthly:
                auxilio_transporte = annual_parameters.transportation_assistance_monthly

        # 3. Componentes variables del PERÍODO ACTUAL (mes en proceso)
        total_variables_mes = 0
        current_data = self._get_current_period_data(localdict, {param_base: True})
        total_variables_mes = current_data.get('total', 0)

        # 4. Componentes variables ACUMULADOS (períodos anteriores)
        total_variables_acumulado = 0
        # Obtener conceptos con base_prima o base_cesantias del período
        accumulated = slip._get_concepts_accumulated_by_payslip(d0, d1)
        for concept_code, concept_data in accumulated.items():
            # Verificar si el concepto tiene el atributo base correspondiente
            concept_rule = self.env['hr.salary.rule'].search([('code', '=', concept_code)], limit=1)
            if concept_rule and getattr(concept_rule, param_base, False):
                if isinstance(concept_data, dict):
                    total_variables_acumulado += concept_data.get('total', 0)
                else:
                    total_variables_acumulado += concept_data

        # Total componentes variables
        total_variables = total_variables_mes + total_variables_acumulado

        # Promedio diario de variables
        promedio_variables_dia = (total_variables / dias_efectivos * 30) if dias_efectivos > 0 else 0

        # Base total
        base_mensual = salario_base + auxilio_transporte + promedio_variables_dia
        base_diaria = base_mensual / DAYS_YEAR  # 360 días comerciales

        # Valor de la prestación
        valor_prestacion = base_diaria * dias_efectivos

        # Preparar datos de log
        prestacion_data = {
            'tipo': tipo_prestacion,
            'periodo': {'desde': str(d0), 'hasta': str(d1)},
            'dias': {
                'totales': dias_totales,
                'suspension': dias_suspension,
                'efectivos': dias_efectivos
            },
            'base': {
                'salario': salario_base,
                'auxilio': auxilio_transporte,
                'variables_mes': total_variables_mes,
                'variables_acumulado': total_variables_acumulado,
                'variables_total': total_variables,
                'promedio_diario_variables': promedio_variables_dia,
                'total_mensual': base_mensual,
                'diaria': base_diaria
            },
            'valor': valor_prestacion
        }

        # Guardar en localdict para uso posterior
        localdict[f'{tipo_prestacion}_data'] = prestacion_data

        nombre = f'{tipo_prestacion.upper()} - {dias_efectivos} días'

        return valor_prestacion, dias_efectivos, 100, nombre, prestacion_data, {}

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE TOTALES
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_total_from_categories(self, localdict, category_codes):
        """
        Calcula totales desde localdict['categories'] directamente.
        Más eficiente - usa totales ya acumulados en vez de iterar reglas.

        Args:
            localdict: Diccionario de contexto
            category_codes: Lista de códigos de categorías a sumar

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        categories = localdict.get('categories', {})

        total = 0
        category_totals = {}
        details = {}

        # Iterar por los códigos de categoría solicitados
        for cat_code in category_codes:
            cat_data = categories.get(cat_code)

            # Verificar si la categoría existe y tiene datos
            if cat_data:
                cat_total = cat_data.total
                total += cat_total
                category_totals[cat_code] = cat_total

                # Agregar detalles de reglas que contribuyeron
                rules = localdict.get('rules')
                for rule_code in cat_data.rule_codes:
                    if rules and rule_code in rules:
                        rule_data = rules.get(rule_code)
                        details[rule_code] = rule_data.total if rule_data else 0

        return total, 1, 100, False, category_totals, details

    def _calculate_total_from_rules(self, localdict, categories, exclude_not_in_net=True):
        """
        MÉTODO ANTIGUO - Mantener para compatibilidad.
        Usa _calculate_total_from_categories() que es más eficiente.

        Calcula totales desde localdict['rules'] por categorías.
        Compatible con Odoo 19 - usa estructura nativa.

        Args:
            localdict: Diccionario de contexto
            categories: Lista de códigos de categorías a sumar
            exclude_not_in_net: Si True, excluye reglas con not_computed_in_net=True

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        # Usar el método más eficiente que lee directamente de categories
        return self._calculate_total_from_categories(localdict, categories)

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE RETENCIÓN EN LA FUENTE
    # ══════════════════════════════════════════════════════════════════════════

    def _calculate_retention_generic(self, localdict, tipo='nomina'):
        """
        Método genérico para retención en la fuente.

        Soporta tres procedimientos:
        - Ordinario (procedimiento 1): Cálculo con tabla de retención
        - Fijo (procedimiento fixed): Monto fijo definido en contrato
        - Extranjero no residente: 20% sobre ingresos totales

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

        # Inicializar diccionario de datos
        retention_data = {
            'tipo': tipo,
            'year': slip.date_to.year,
            'month': slip.date_to.month,
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'document': employee.identification_id if hasattr(employee, 'identification_id') else ''
            }
        }

        # Validación aprendices - no aplica retención
        if contract.contract_type == 'aprendizaje':
            retention_data['status'] = 'no_applicable'
            retention_data['reason'] = 'contract_type_apprentice'
            localdict['retention_data'] = retention_data
            return 0, 0, 0, 'No aplica para aprendices', retention_data, {}

        # Determinar método según procedimiento configurado en contrato
        if hasattr(contract, 'retention_procedure'):
            if contract.retention_procedure == 'extranjero_no_residente':
                return self._calculate_retention_foreigner(localdict, retention_data)
            elif contract.retention_procedure == 'fixed':
                return self._calculate_retention_fixed(localdict, retention_data)

        # Por defecto: procedimiento ordinario
        return self._calculate_retention_ordinary(localdict, retention_data, tipo)

    def _calculate_retention_ordinary(self, localdict, retention_data, tipo_especial=None):
        """
        Cálculo ordinario de retención en la fuente (Procedimiento 1).

        Proceso:
        1. Obtener ingresos del período (salario + devengados)
        2. Proyectar a 30 días si es quincenal
        3. Restar aportes obligatorios (salud, pensión)
        4. Aplicar deducciones y rentas exentas
        5. Calcular base gravable en UVT
        6. Aplicar tabla de retención
        7. Restar retención anterior del mes

        Args:
            localdict: Diccionario de contexto
            retention_data: Dict con datos de retención
            tipo_especial: Tipo especial de retención ('prima', etc.)

        Returns:
            Tuple: (rate, quantity, percentage, name, log_data_dict, extra_data_dict)
        """
        contract = localdict['contract']
        slip = localdict['slip']
        annual_parameters = localdict.get('annual_parameters')

        if not annual_parameters:
            retention_data['status'] = 'error'
            retention_data['reason'] = 'no_annual_parameters'
            return 0, 0, 0, 'Error: Faltan parámetros anuales', retention_data, {}

        # ===== PASO 1: Días trabajados =====
        dias_trabajados = 30
        worked_days = localdict.get('worked_days', {})
        # ODOO 18: worked_days es dict de recordsets
        work100 = worked_days.get('WORK100')
        if work100:
            dias_trabajados = work100.number_of_days

        retention_data['dias_trabajados'] = dias_trabajados

        # ===== PASO 2: Verificar si debe proyectar =====
        debe_proyectar = False
        if hasattr(contract, 'proyectar_ret'):
            debe_proyectar = contract.proyectar_ret and slip.date_from.day <= 15

        retention_data['es_proyectado'] = debe_proyectar

        # ===== PASO 3: Obtener ingresos según tipo =====
        if tipo_especial == 'prima':
            # Para prima, solo tomar el valor de la prima
            ingresos_total = self._get_totalizar_reglas(
                localdict, 'PRIMA',
                incluir_current=True,
                incluir_before=False,
                incluir_multi=True
            )

            ingresos = {
                'total': ingresos_total,
                'salario': 0,
                'dev_salarial': ingresos_total,
                'dev_no_salarial': 0
            }
        else:
            # Ingresos normales por categorías
            salario, _ = self._get_totalizar_categorias(
                localdict,
                categorias=['BASIC'],
                incluir_current=True,
                incluir_before=False,
                incluir_multi=True
            )

            dev_salarial, _ = self._get_totalizar_categorias(
                localdict,
                categorias=['DEV_SALARIAL'],
                incluir_current=True,
                incluir_before=False,
                incluir_multi=True
            )

            dev_no_salarial, _ = self._get_totalizar_categorias(
                localdict,
                categorias=['DEV_NO_SALARIAL'],
                incluir_current=True,
                incluir_before=False,
                incluir_multi=True
            )

            ingresos = {
                'salario': salario,
                'dev_salarial': dev_salarial,
                'dev_no_salarial': dev_no_salarial,
                'total': salario + dev_salarial + dev_no_salarial
            }

        retention_data['ingresos'] = ingresos

        # ===== PASO 4: Proyectar si es necesario =====
        if debe_proyectar and dias_trabajados > 0:
            factor = 30.0 / dias_trabajados
            for key in ingresos:
                ingresos[key] *= factor
            retention_data['factor_proyeccion'] = factor

        # ===== PASO 5: Obtener aportes obligatorios =====
        salud = self._get_totalizar_reglas(
            localdict, 'SSOCIAL001',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        pension = self._get_totalizar_reglas(
            localdict, 'SSOCIAL002',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        solidaridad = self._get_totalizar_reglas(
            localdict, 'SSOCIAL003',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        subsistencia = self._get_totalizar_reglas(
            localdict, 'SSOCIAL004',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        aportes = {
            'salud': abs(salud),
            'pension': abs(pension),
            'solidaridad': abs(solidaridad),
            'subsistencia': abs(subsistencia)
        }

        aportes['total_pension'] = aportes['pension'] + aportes['solidaridad'] + aportes['subsistencia']
        retention_data['aportes'] = aportes

        # ===== PASO 6: Calcular base gravable =====
        ing_no_gravados = aportes['total_pension'] + aportes['salud']
        ing_base = ingresos['total'] - ing_no_gravados

        # Deducciones y rentas exentas (simplificado - se puede expandir)
        deducciones = {'total': 0}
        rentas_exentas = {'total': 0, 'renta_exenta_25': 0}

        # Subtotales
        subtotal_ibr1 = ing_base - deducciones['total']
        subtotal_ibr2 = subtotal_ibr1 - rentas_exentas['total']

        # ===== PASO 7: Renta exenta 25% =====
        renta_exenta_25 = min(
            subtotal_ibr2 * 0.25,
            annual_parameters.value_uvt * (790.0 / 12.0)
        )

        # ===== PASO 8: Total beneficios y límites =====
        total_beneficios = deducciones['total'] + rentas_exentas['total'] + renta_exenta_25
        limite_40 = ing_base * 0.4
        limite_uvt = annual_parameters.value_uvt * (1340.0 / 12.0)
        beneficios_limitados = min(total_beneficios, limite_40, limite_uvt)

        # ===== PASO 9: Base gravable final en UVT =====
        subtotal_ibr3 = ing_base - beneficios_limitados
        ibr_uvts = subtotal_ibr3 / annual_parameters.value_uvt if annual_parameters.value_uvt > 0 else 0

        retention_data['subtotales'] = {
            'ibr1': subtotal_ibr1,
            'ibr2': subtotal_ibr2,
            'ibr3': subtotal_ibr3,
            'ibr_uvts': ibr_uvts
        }

        retention_data['beneficios'] = {
            'renta_exenta_25': renta_exenta_25,
            'total': total_beneficios,
            'limitados': beneficios_limitados
        }

        # ===== PASO 10: Aplicar tabla de retención =====
        retencion = 0
        rate = 0

        # Verificar si usa procedimiento 102 (tarifa fija)
        if hasattr(contract, 'retention_procedure') and contract.retention_procedure == '102':
            if hasattr(contract, 'rtf_rate'):
                retencion = subtotal_ibr3 * (contract.rtf_rate / 100.0)
                rate = contract.rtf_rate
        else:
            # Aplicar tabla de retención estándar
            for desde, hasta, tarifa, resta_uvt, suma_uvt in TABLA_RETENCION:
                if desde <= ibr_uvts < hasta:
                    if desde > 0:
                        retencion = (((ibr_uvts - resta_uvt) * (tarifa / 100.0)) + suma_uvt) * annual_parameters.value_uvt
                        rate = tarifa
                    break

        # ===== PASO 11: Restar retención anterior del mes =====
        retencion_anterior = self._get_totalizar_reglas(
            localdict, 'RT_MET_01',
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        retencion_def = max(0, retencion - abs(retencion_anterior))

        # ===== PASO 12: Ajustar por proyección =====
        if debe_proyectar:
            retencion_def = retencion_def / 2.0

        retention_data['retencion_calculada'] = retencion
        retention_data['retencion_anterior'] = retencion_anterior
        retention_data['retencion_definitiva'] = retencion_def
        retention_data['tarifa'] = rate
        retention_data['status'] = 'calculated'

        # Guardar en localdict para otros usos
        localdict['retention_data'] = retention_data

        nombre = f'Retención - Base: ${subtotal_ibr3:,.0f}'

        return retencion_def, -1, rate, nombre, retention_data, {}

    def _calculate_retention_fixed(self, localdict, retention_data):
        """
        Retención con monto fijo definido en contrato.

        Args:
            localdict: Diccionario de contexto
            retention_data: Dict con datos de retención

        Returns:
            Tuple: (rate, quantity, percentage, name, log_data_dict, extra_data_dict)
        """
        contract = localdict['contract']

        valor_fijo = 0
        if hasattr(contract, 'fixed_value_retention_procedure'):
            valor_fijo = contract.fixed_value_retention_procedure

        retention_data['tipo'] = 'monto_fijo'
        retention_data['valor'] = valor_fijo
        retention_data['status'] = 'calculated'

        localdict['retention_data'] = retention_data

        return valor_fijo, -1, 100, f'Retención Fijo: ${valor_fijo:,.0f}', retention_data, {}

    def _calculate_retention_foreigner(self, localdict, retention_data):
        """
        Retención para extranjero no residente - 20% sobre ingresos totales.

        Args:
            localdict: Diccionario de contexto
            retention_data: Dict con datos de retención

        Returns:
            Tuple: (rate, quantity, percentage, name, log_data_dict, extra_data_dict)
        """
        # Obtener ingresos totales por categorías
        basic, _ = self._get_totalizar_categorias(
            localdict,
            categorias=['BASIC'],
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        dev_salarial, _ = self._get_totalizar_categorias(
            localdict,
            categorias=['DEV_SALARIAL'],
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        dev_no_salarial, _ = self._get_totalizar_categorias(
            localdict,
            categorias=['DEV_NO_SALARIAL'],
            incluir_current=True,
            incluir_before=False,
            incluir_multi=True
        )

        base = basic + dev_salarial + dev_no_salarial
        retencion = base * 0.20

        retention_data['tipo'] = 'extranjero_no_residente'
        retention_data['base'] = base
        retention_data['tarifa'] = 20
        retention_data['retencion'] = retencion
        retention_data['status'] = 'calculated'

        localdict['retention_data'] = retention_data

        return retencion, -1, 20, f'Retención Extranjero - Base: ${base:,.0f}', retention_data, {}

    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS LEGACY - MANTIENEN COMPATIBILIDAD
    # ══════════════════════════════════════════════════════════════════════════

    def _get_context_name(self, concept, payslip):
        """
        Obtiene el nombre contextual del concepto según la nómina actual.
        Si el concepto ya tiene context_name, lo devuelve; de lo contrario, lo calcula.
        """
        base_parts = []
        if concept.input_id:
            base_parts.append(concept.input_id.name)
        
        if payslip:
            date_to = payslip.date_to
            fortnight = "1Q" if date_to.day <= 15 else "2Q"
            month_year = f"{date_to.strftime('%b').upper()}/{date_to.year}"
            base_parts.append(f"{fortnight} {month_year}")
        
        if concept.is_deduction and concept.is_earning:
            tipo = "D" if concept.is_deduction else "I" if concept.is_earning else "C"
            base_parts.append(f"[{tipo}]")
        
        return " - ".join(base_parts) if base_parts else ""

    def _obtener_otros_embargos(self, localdict, current_concept_id):
        """
        Obtiene otros embargos activos en la nómina para consideración de prioridades.
        Compatible con Odoo 19 - usa RulesCollection.

        Returns:
            List[Dict]: Lista de diccionarios con información de otros embargos
        """
        result = []
        rules = localdict.get('rules')  # RulesCollection

        if not rules:
            return result

        # Buscar todas las reglas de embargo activas (EMBARGO002, EMBARGO003, etc.)
        for rule_code in rules.get_codes():
            if rule_code.startswith('EMBARGO') and rule_code != 'EMBARGO001':
                rule_data = rules.get(rule_code)
                if rule_data:
                    total = rule_data.total
                    if total > 0:
                        # Determinar tipo de embargo de data extra si existe
                        extra_data = rule_data.extra_data
                        tipo = extra_data.get('tipo_embargo', 'OTRO')

                        result.append({
                            'name': rule_code,
                            'valor': total,
                            'type': tipo,
                            'priority': 1 if tipo == 'ECA' else 2,
                            'rule_code': rule_code
                        })

        # Ordenar: alimentarios primero (priority 1), luego generales (priority 2)
        return sorted(result, key=lambda x: x['priority'])

    def _format_money(self, value):
        """
        Formatea un valor numérico como moneda con punto como separador de miles
        y coma como separador decimal, siempre con 2 decimales.
        """
        if value is None:
            return "$0,00"
        # Formatear con punto como separador de miles y coma como decimal
        return f"${value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def _format_number(self, value):
        """
        Formatea un valor numérico con punto como separador de miles
        y coma como separador decimal, siempre con 2 decimales.
        """
        if value is None:
            return "0,00"
        # Formatear con punto como separador de miles y coma como decimal
        return f"{value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    def need_compute_salary_average(self, contract, date_from, date_to):
        date_3_months_before = date_to - relativedelta(months=3)
        if date_from > date_3_months_before:
            date_3_months_before = date_from
        return contract.has_change_salary(date_3_months_before, date_to)
    

    def _get_periodo(self, slip) -> str:
        """
        Devuelve la etiqueta de periodo basada en payslip:
          - "Vacaciones MM-YY" para struct_process='vacaciones'
          - "Primera Q1 MM-YY" o "Segunda Q2 MM-YY" en nóminas ordinarias
        """
        date_to = slip.date_to
        etiqueta_fecha = date_to.strftime('%m-%y')
        tipo = slip.struct_process
        if tipo == 'vacaciones':
            label = 'Vacaciones'
        else:
            label = 'Q1' if date_to.day <= 15 else 'Q2'
        return f"{self.name} {label} {etiqueta_fecha}".capitalize()

    def _get_tipo_ausencia(self, tipo_novedad):
        """Retorna el nombre legible del tipo de ausencia según el código"""
        tipos = {
            'vac': 'VACACIONES',
            'ige': 'Incapacidad EPS',
            'irl': 'Incapacidad ARL',
            'lnr': 'Licencia no Remunerada',
            'lma': 'Licencia de Maternidad',
            'lpa': 'Licencia de Paternidad',
            'vdi': 'Vacaciones Disfrutadas',
            'p': 'Permisos no remunerados D/H (No se envia en pila)',
            'sln': 'Suspensión',
        }
        return tipos.get(tipo_novedad, tipo_novedad.upper() if tipo_novedad else 'OTRO')
    @api.model
    def compute_payslip_2_values(self, localdict):
        """
        - Incluye reglas DEV_SALARIAL y DEV_NO_SALARIAL.
        - Para DEV_SALARIAL exige base_seguridad_social=True.
        - Ignora líneas de ausencia.
        - Extrae montos de localdict['rules'] para el payslip actual (ODOO 18).
        - Agrupa por categoría padre (si existe) o categoría.
        - Mantiene rest_of_period calculado por línea.
        """
        data_ibc = {
            'rest_of_period': {
                'year_month': False,
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'current_slip': {
                'year_month': False,
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'grand_totals': {
                'total_salary': 0.0,
                'total_no_salary': 0.0,
            },
            'events': [],
            'line_ids': [],  # IDs de líneas de nómina consultadas
        }
        slip = localdict['slip']

        # Usar método de acumulación para obtener datos del mes hasta el slip anterior
        start_date = slip.date_from.replace(day=1)
        end_date = slip.date_from - timedelta(days=1)

        # Obtener categorías acumuladas del período (CategoryCollection)
        accumulated_cats = slip._get_categories_accumulated_by_payslip(start_date, end_date)

        # Procesar DEV_SALARIAL acumulado
        dev_salarial = accumulated_cats.get('DEV_SALARIAL')
        if dev_salarial:
            # Para dev_salarial solo sumamos si tiene base_seguridad_social
            lines = self.env['hr.payslip.line'].browse(dev_salarial.line_ids)
            for ln in lines.filtered(lambda l: l.salary_rule_id.base_seguridad_social and not l.leave_id):
                data_ibc['rest_of_period']['total_salary'] += ln.total
                data_ibc['line_ids'].append(ln.id)  # Guardar ID de línea
                data_ibc['events'].append({
                    'date': ln.date_to,
                    'origin': 'MES ACTUAL',
                    'foce_min': '',
                    'sequence': ln.sequence,
                    'factor': ln.rate,
                    'days': ln.quantity,
                    'base_daily': 0.0,
                    'calc_value': ln.amount,
                    'slip_value': ln.total,
                    'rule_id': ln.salary_rule_id,
                    'novelty': 'NOM-ANT',
                })

        # Procesar DEV_NO_SALARIAL acumulado
        dev_no_salarial = accumulated_cats.get('DEV_NO_SALARIAL')
        if dev_no_salarial:
            lines = self.env['hr.payslip.line'].browse(dev_no_salarial.line_ids)
            for ln in lines.filtered(lambda l: not l.leave_id and l.salary_rule_id.category_id.code != 'AUX'):
                data_ibc['rest_of_period']['total_no_salary'] += ln.total
                data_ibc['line_ids'].append(ln.id)  # Guardar ID de línea
                data_ibc['events'].append({
                    'date': ln.date_to,
                    'origin': 'MES ACTUAL',
                    'foce_min': '',
                    'sequence': ln.sequence,
                    'factor': ln.rate,
                    'days': ln.quantity,
                    'base_daily': 0.0,
                    'calc_value': ln.amount,
                    'slip_value': ln.total,
                    'rule_id': ln.salary_rule_id,
                    'novelty': 'NOM-ANT',
                })

        # Procesar DEDUCCIONES acumuladas que estén marcadas como base SS.
        # Se suman en valor absoluto para que impacten (incrementen) el IBC.
        for ded_code in ('DED', 'DEDUCCIONES'):
            ded_cat = accumulated_cats.get(ded_code)
            if not ded_cat:
                continue
            lines = self.env['hr.payslip.line'].browse(ded_cat.line_ids)
            for ln in lines.filtered(lambda l: l.salary_rule_id.base_seguridad_social and not l.leave_id):
                ded_total = abs(ln.total or 0.0)
                if ded_total == 0.0:
                    continue
                data_ibc['rest_of_period']['total_salary'] += ded_total
                data_ibc['line_ids'].append(ln.id)
                data_ibc['events'].append({
                    'date': ln.date_to,
                    'origin': 'MES ACTUAL',
                    'foce_min': '',
                    'sequence': ln.sequence,
                    'factor': ln.rate,
                    'days': ln.quantity,
                    'base_daily': 0.0,
                    'calc_value': abs(ln.amount or 0.0),
                    'slip_value': ded_total,
                    'rule_id': ln.salary_rule_id,
                    'novelty': 'NOM-ANT',
                })
        # Usar estructura Odoo 19 nativa localdict['rules'] en lugar de rules_multi
        rules = localdict.get('rules', {})
        for code, rule_data in rules.items():
            rule = rule_data.rule
            if not rule:
                continue

            cat = rule.category_id
            amount = rule_data.total
            unitario = rule_data.amount
            cantidad = rule_data.quantity
            porcentaje = rule_data.rate

            # Verificar si es ausencia o auxilio
            if amount == 0.0 or rule.category_id.code in ('AUX'):
                continue

            # Filtrar DEV_SALARIAL y DEV_NO_SALARIAL
            if cat.code == 'DEV_SALARIAL' or (cat.parent_id and cat.parent_id.code == 'DEV_SALARIAL'):
                if rule.base_seguridad_social:
                    # Si el valor viene negativo (p.ej. sanciones/deducciones
                    # configuradas para IBC), se toma en absoluto para que
                    # incremente la base.
                    if amount < 0:
                        amount = abs(amount)
                        unitario = abs(unitario or 0.0)
                    data_ibc['current_slip']['total_salary'] += amount
                else:
                    continue
            elif cat.code == 'DEV_NO_SALARIAL' or (cat.parent_id and cat.parent_id.code == 'DEV_NO_SALARIAL'):
                data_ibc['current_slip']['total_no_salary'] += amount
            elif cat.code in ('DED', 'DEDUCCIONES') or (cat.parent_id and cat.parent_id.code in ('DED', 'DEDUCCIONES')):
                # Deducciones marcadas como base SS entran al IBC como valor absoluto.
                if rule.base_seguridad_social:
                    data_ibc['current_slip']['total_salary'] += abs(amount or 0.0)
                    unitario = abs(unitario or 0.0)
                    amount = abs(amount or 0.0)
                else:
                    continue
            else:
                continue

            data_ibc['events'].append({
                'date':       slip.date_to,
                'origin':     'NOM ACTUAL',
                'foce_min':  '',
                'sequence':   rule.sequence,
                'factor':     porcentaje,
                'days':       cantidad,
                'base_daily': 0.0,
                'calc_value': unitario,
                'slip_value': amount,
                'rule_id':    rule,
                'novelty':    'NOM',
            })

        data_ibc['grand_totals']['total_salary'] += data_ibc['current_slip']['total_salary'] + data_ibc['rest_of_period']['total_salary']
        data_ibc['grand_totals']['total_no_salary'] += data_ibc['current_slip']['total_no_salary'] + data_ibc['rest_of_period']['total_no_salary']

        return data_ibc

    @api.model
    def compute_absences(self, localdict):
        """
        1) Toma de localdict:
           - slip            : hr.payslip actual
           - before_month    : "YYYY-MM" del mes anterior
           - current_month   : "YYYY-MM" del mes en curso
           - payslip_data    : {
                 'before_month': [ { 'payslip_ids': [...], ... }, ... ],
                 'current_month': [ { 'payslip_ids': [...], ... }, ... ]
             }
           - previous_ibc    : IBC calculado del mes anterior (float)
           - use_previous_ibc: bool, si debe usar ibc anterior
           - year_avg        : promedio anual (float, opcional)
        2) Extrae **todos** los payslip_ids de cada lista.
        3) Divide en previous_ids, rest_ids y current_id.
        4) Para cada grupo acumula líneas de hr.leave.line según la lógica descrita.
        """
        slip           = localdict['slip']
        before_month   = localdict.get('before_month', [])
        current_month  = localdict.get('current_month', [])
        annual_params = localdict['annual_parameters']
        prev_ids = []
        for rec in before_month:
            prev_ids.extend(rec.get('payslip_ids', []))
        curr_ids = []
        for rec in current_month:
            curr_ids.extend(rec.get('payslip_ids', []))

        rest_ids = [pid for pid in curr_ids if pid != slip.id]

        Line = self.env['hr.leave.line']
        validated_leave_domain = [('leave_id.state', 'in', ('validate', 'validate1'))]
        groups = {
            'previous': Line.search([('payslip_id', 'in', prev_ids)] + validated_leave_domain),
            'rest':     Line.search([('payslip_id', 'in', rest_ids)] + validated_leave_domain),
            'current':  Line.search([('payslip_id', '=', slip.id)] + validated_leave_domain),
        }
        def _dias_in(d):
            return slip.date_from.year  == d.year and slip.date_to.month == d.month
        
        def _accumulate(lines, origin, slip_ids, period):
            data = {
                'year_month':  period,
                'slip_ids':    slip_ids,
                'total_days':  0.0,
                'total_value': 0.0,
                'events':      [],
            }
            for ln in lines.filtered(lambda ln: ln.rule_id.base_seguridad_social):
                if not ln.leave_id or ln.leave_id.state not in ('validate', 'validate1'):
                    continue
                lt = ln.leave_id
                typ = lt.holiday_status_id.novelty
                factor, _ = lt.holiday_status_id.get_rate_concept_id(ln.sequence)
                dias_en_periodo = ln.days_payslip
                if not _dias_in(ln.date) and origin != 'previous' and typ != 'vdi':
                    continue
                if ln.date.day == 31:
                    continue
                if origin == 'previous' and not typ == 'vdi':
                    continue
                base_month = slip.contract_id.wage
                calc_value = self._obtener_ibc_diario_previo(slip.contract_id, slip.date_from)
                base_daily = base_month / 30.0
                calc_value = base_daily * factor * ln.days_payslip
                valor_smlv = annual_params.smmlv_monthly /30

                if ln.rule_id.liquidar_con_base:
                    slip_val = self._set_limits_ibc(calc_value, valor_minimo=valor_smlv) if typ in ('lnr','p') else  ln.amount
                else:
                    slip_val = 0.0 if typ in ('lnr','p') else  ln.amount
                
                data['total_days']  += ln.days_payslip
                data['total_value'] += slip_val
                data['events'].append({
                    'date':       ln.date,
                    'origin':     origin,
                    'foce_min': ln.rule_id.liquidar_con_base,
                    'sequence':   ln.sequence,
                    'factor':     factor,
                    'days':       dias_en_periodo,
                    'base_daily': base_daily,
                    'calc_value': calc_value,
                    'slip_value': slip_val,
                    'rule_id':    ln.rule_id,
                    'novelty':    typ,
                })
            return data

        prev_data = _accumulate(groups['previous'], 'previous', prev_ids, before_month)
        rest_data = _accumulate(groups['rest'],     'rest',     rest_ids, current_month)
        curr_data = _accumulate(groups['current'],  'current',  [slip.id], current_month)

        return {
            'previous_period': prev_data,
            'rest_of_period': rest_data,
            'current_slip': curr_data,
            'total_days': rest_data['total_days'] + curr_data['total_days'] + prev_data['total_days'],
            'total_value': rest_data['total_value'] + curr_data['total_value'] + prev_data['total_value'],
        }
        
    def _set_limits_ibc(self, ibc, valor_minimo):
        if ibc < valor_minimo:
            return valor_minimo
        else:
            return ibc
        
    def category_code(self,rule):
        cat = rule.category_id
        while cat:
            if cat.code in ('DEV_SALARIAL', 'DEV_NO_SALARIAL'):
                return cat.code
            if cat.code in ('INDEM', 'PRESTACIONES_SOCIALES', 'AUX'):
                return None
            cat = cat.parent_id
        return None
    
    def _obtener_ibc_diario_previo(self, contract, ref_date):
        """
        Obtiene el IBC diario del mes anterior.
        """
        # 1. Intentar obtener desde seguridad social
        ini = ref_date.replace(day=1) - relativedelta(months=1)
        fin = ref_date.replace(day=1) - timedelta(days=1)
        
        ss = self.env['hr.executing.social.security'].search([
            ('employee_id', '=', contract.employee_id.id),
            ('contract_id', '=', contract.id),
            ('k_start', '>=', ini), ('k_start', '<=', fin),
        ])
        
        if ss:
            base = sum(l.nValorBaseSalud for l in ss)
            dias = sum((l.nDiasLiquidados or 0) + (l.nDiasVacaciones or 0) + 
                       (l.nDiasLicenciaRenumerada or 0) + (l.nDiasMaternidad or 0) + 
                       (l.nDiasIncapacidadEPS or 0) + (l.nDiasIncapacidadARP or 0)  for l in ss)
            
            if dias:
                return base / dias
        
        # 2. Si no hay en seguridad social, calcular desde nómina
        lines = self.env['hr.payslip.line'].search([
            ('state_slip', 'in', ['done', 'paid']),
            ('contract_id', '=', contract.id),
            ('date_from', '>=', ini),
            ('date_to', '<=', fin),
        ])
        
        if lines:
            base = sum(abs(l.total) for l in lines if l.salary_rule_id.base_seguridad_social)
            nos = sum(abs(l.total) for l in lines if self.category_code(l.salary_rule_id) == 'DEV_NO_SALARIAL')
            
            params = ParamLoader.for_date(self.env, fin)
            extra = max(0.0, nos - (base + nos) * params['TOPE_40'])
            ibc_mes = min(base + extra, params['TOPE_25_SMMLV'])
            
            if ibc_mes > 0:
                return ibc_mes / DAYS_MONTH
        
        return contract.wage / DAYS_MONTH
    

    def _get_totalizar_other_reglas(
        self,
        liquidacion_data: Dict[str, Any],
        codigos_regla: Optional[Union[str, List[str]]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,
        incluir_before: bool = False,
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        devolver_cantidad: bool = False,
        solo_con_ausencias: bool = False,
        excluir_con_ausencias: bool = False
        ) -> Union[float, int]:
        """
        Totaliza reglas de nómina según los criterios especificados.

        Args:
            liquidacion_data: Diccionario con datos de liquidación
            codigos_regla: Códigos de reglas a totalizar (None = todas)
            filtros: Diccionario con funciones de filtrado
            incluir_current: No usado en Odoo 19 (se mantiene por compatibilidad)
            incluir_before: No usado en Odoo 19 (se mantiene por compatibilidad)
            incluir_multi: Obsoleto en Odoo 19 (se mantiene por compatibilidad)
            devolver_cantidad: Si se devuelve la cantidad en lugar del valor
            solo_con_ausencias: Si se incluyen solo las reglas con ausencias
            excluir_con_ausencias: Si se excluyen las reglas con ausencias

        Returns:
            float o int: Total acumulado según los criterios
        """
        # Validamos que los parámetros de ausencia no sean contradictorios
        if solo_con_ausencias and excluir_con_ausencias:
            raise ValueError("No se pueden activar solo_con_ausencias y excluir_con_ausencias simultáneamente")

        if codigos_regla is None:
            codigos = list(liquidacion_data.get('rules', {}).keys())
        else:
            codigos = codigos_regla if isinstance(codigos_regla, list) else [codigos_regla]

        filtros = filtros or {}
        def pasa_filter(obj: Any):
            """Evalúa si un objeto pasa todos los filtros especificados"""
            for attr_name, condition_func in filtros.items():
                if attr_name == 'object':
                    if not condition_func(obj):
                        return False
                else:
                    attr_value = getattr(obj, attr_name, None)
                    if callable(condition_func):
                        if not condition_func(attr_value):
                            return False
                    else:
                        if bool(attr_value) != bool(condition_func):
                            return False
            return True

        entradas: List[Dict[str, Any]] = []

        # ODOO 18 NATIVO: Usar estructura 'rules'
        for code in codigos:
            rule_data = liquidacion_data.get('rules', {}).get(code)
            if rule_data:
                rule_obj = rule_data.rule
                if rule_obj:
                    entradas.append({
                        'object': rule_obj,
                        'total': rule_data.total,
                        'quantity': rule_data.quantity,
                        'leave': {},
                    })

        total_valor = 0.0
        total_entradas = 0
        for item in entradas:
            obj = item.get('object')
            if not obj or not pasa_filter(obj):
                continue

            # Filtramos por ausencias
            tiene_ausencias = bool(item.get('leave', {}))
            if solo_con_ausencias and not tiene_ausencias:
                continue
            if excluir_con_ausencias and tiene_ausencias:
                continue

            if devolver_cantidad:
                total_entradas += item.get('quantity', 0)
            else:
                total_valor += item.get('total', 0.0)

        return total_entradas if devolver_cantidad else total_valor

    def _trae_totalizar_categorias(
        self,
        localdict: Dict[str, Any],
        categorias: Optional[Union[List[str], str]] = None,
        categorias_excluir: Optional[Union[List[str], str]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before: bool = False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_subcategorias: bool = True,
        solo_con_ausencias: bool = False,
        excluir_con_ausencias: bool = False
        ) -> Tuple[float, float]:
        """
        Totaliza categorías de nómina en Odoo 19.

        Args:
            localdict: Diccionario local con datos de nómina
            categorias: Categorías a incluir (None = todas)
            categorias_excluir: Categorías a excluir
            filtros: Diccionario con funciones de filtrado
            incluir_subcategorias: Si se incluyen subcategorías
            solo_con_ausencias: Si se incluyen solo las reglas con ausencias
            excluir_con_ausencias: Si se excluyen las reglas con ausencias

        Returns:
            Tuple[float, float]: (valor total, total de entradas)
        """
        # Validamos que los parámetros de ausencia no sean contradictorios
        if solo_con_ausencias and excluir_con_ausencias:
            raise ValueError("No se pueden activar solo_con_ausencias y excluir_con_ausencias simultáneamente")
        
        def _to_list(x: Optional[Union[List[str], str]]) -> Optional[List[str]]:
            if x is None:
                return None
            return x if isinstance(x, list) else [x]

        categorias = _to_list(categorias)
        categorias_excluir = _to_list(categorias_excluir)
        filtros = filtros or {}

        def _pasa_filtros(obj: Any):
            """Evalúa si un objeto pasa todos los filtros especificados"""
            for attr_name, condition_func in filtros.items():
                if attr_name == 'object':
                    if not condition_func(obj):
                        return False
                else:
                    attr_value = getattr(obj, attr_name, None)
                    if callable(condition_func):
                        if not condition_func(attr_value):
                            return False
                    else:
                        if bool(attr_value) != bool(condition_func):
                            return False
            return True

        fuente: List[Dict[str, Any]] = []
        # ODOO 18: Usar estructura nativa 'rules'
        for code, rule_data in localdict.get('rules', {}).items():
            rule_obj = rule_data.rule
            if rule_obj:
                fuente.append({
                    'code': code,
                    'object': rule_obj,
                    'total': rule_data.total,
                    'quantity': rule_data.quantity,
                    'leave': {},
                })

        reglas_por_cat: Dict[str, set] = {} 
        padres: Dict[str, str] = {}
        for item in fuente:
            obj = item['object']
            if not obj.category_id:
                continue
            cat = obj.category_id.code
            reglas_por_cat.setdefault(cat, set()).add(item['code'])
            if obj.category_id.parent_id:
                padres.setdefault(cat, obj.category_id.parent_id.code)

        hijos: Dict[str, set] = {}
        for cat, p in padres.items():
            hijos.setdefault(p, set()).add(cat)

        if categorias is None:
            cats = set(reglas_por_cat)
        else:
            cats = set(categorias)
            if incluir_subcategorias:
                cola = list(cats)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in cats:
                            cats.add(h)
                            cola.append(h)

        if categorias_excluir:
            ex = set(categorias_excluir)
            if incluir_subcategorias:
                cola = list(ex)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in ex:
                            ex.add(h)
                            cola.append(h)
            cats -= ex
            
        total_valor = 0.0
        total_entradas = 0
        for item in fuente:
            obj = item['object']
            cat = obj.category_id.code if obj.category_id else None
            if cat not in cats or not _pasa_filtros(obj):
                continue
                
            # Filtramos por ausencias
            tiene_ausencias = bool(item.get('leave', {}))
            if solo_con_ausencias and not tiene_ausencias:
                continue
            if excluir_con_ausencias and tiene_ausencias:
                continue
            valor = item.get('total', 0.0)
            total_valor += item.get('total', 0.0)
            total_entradas += item.get('quantity', 0)

        return total_valor, total_entradas

    
    def _get_totalizar_reglas(
        self,
        liquidacion_data: Dict[str, Any],
        codigos_regla: Optional[Union[str, List[str]]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before: bool = False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        devolver_cantidad: bool = False,
        ) -> Union[float, int]:
        """
        Totaliza reglas de nómina en Odoo 19.

        Args:
            liquidacion_data: Diccionario con datos de liquidación
            codigos_regla: Códigos de reglas a totalizar (None = todas)
            filtros: Diccionario con funciones de filtrado
            devolver_cantidad: Si se devuelve la cantidad en lugar del valor

        Returns:
            float o int: Total acumulado
        """
        if codigos_regla is None:
            codigos = list(liquidacion_data.get('rules', {}).keys())
        else:
            codigos = codigos_regla if isinstance(codigos_regla, list) else [codigos_regla]

        filtros = filtros or {}
        def pasa_filter(obj: Any):
            cond = filtros.get('object')
            return cond(obj) if cond else True

        entradas: List[Dict[str, Any]] = []

        # ODOO 18 NATIVO: Usar estructura 'rules'
        for code in codigos:
            rule_data = liquidacion_data.get('rules', {}).get(code)
            if rule_data:
                rule_obj = rule_data.rule
                if rule_obj:
                    entradas.append({
                        'object': rule_obj,
                        'total': rule_data.total,
                        'quantity': rule_data.quantity,
                    })

        total_valor = 0.0
        total_entradas = 0
        for item in entradas:
            obj = item.get('object')
            if not obj or not pasa_filter(obj):
                continue

            if devolver_cantidad:
                total_entradas += item.get('quantity', 0)
            else:
                total_valor += item.get('total', 0.0)

        return total_entradas if devolver_cantidad else total_valor

    def _get_totalizar_categorias(
        self,
        localdict: Dict[str, Any],
        categorias: Optional[Union[List[str], str]] = None,
        categorias_excluir: Optional[Union[List[str], str]] = None,
        filtros: Optional[Dict[str, Callable[[Any], bool]]] = None,
        incluir_current: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_before: bool = False,  # Obsoleto - se mantiene por compatibilidad
        incluir_multi: bool = True,  # Obsoleto - se mantiene por compatibilidad
        incluir_subcategorias: bool = True,
        ) -> Tuple[float, float]:
        """
        Totaliza categorías de nómina en Odoo 19.

        Args:
            localdict: Diccionario local con datos de nómina
            categorias: Categorías a incluir (None = todas)
            categorias_excluir: Categorías a excluir
            filtros: Diccionario con funciones de filtrado
            incluir_subcategorias: Si se incluyen subcategorías

        Returns:
            Tuple[float, float]: (total_valor, total_entradas)
        """
        def _to_list(x: Optional[Union[List[str], str]]) -> Optional[List[str]]:
            if x is None:
                return None
            return x if isinstance(x, list) else [x]

        categorias = _to_list(categorias)
        categorias_excluir = _to_list(categorias_excluir)
        filtros = filtros or {}

        def _pasa_filtros(obj: Any):
            for clave, cond in filtros.items():
                if clave == 'object':
                    if not cond(obj):
                        return False
                else:
                    val = getattr(obj, clave, None)
                    if callable(cond):
                        if not cond(val):
                            return False
                    else:
                        if bool(val) != bool(cond):
                            return False
            return True

        fuente: List[Dict[str, Any]] = []

        # ODOO 18 NATIVO: Usar estructura 'rules'
        for code, rule_data in localdict.get('rules', {}).items():
            rule_obj = rule_data.rule
            if rule_obj:
                fuente.append({
                    'code': code,
                    'object': rule_obj,
                    'total': rule_data.total,
                    'quantity': rule_data.quantity,
                })

        reglas_por_cat: Dict[str, set] = {} # construir mapeos categoría ← reglas y padre ← hijo
        padres: Dict[str, str] = {}
        for item in fuente:
            obj = item['object']
            if not obj.category_id:
                continue
            cat = obj.category_id.code
            reglas_por_cat.setdefault(cat, set()).add(item['code'])
            if obj.category_id.parent_id:
                padres.setdefault(cat, obj.category_id.parent_id.code)

        hijos: Dict[str, set] = {}
        for cat, p in padres.items():
            hijos.setdefault(p, set()).add(cat)

        if categorias is None:
            cats = set(reglas_por_cat)
        else:
            cats = set(categorias)
            if incluir_subcategorias:
                cola = list(cats)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in cats:
                            cats.add(h)
                            cola.append(h)

        if categorias_excluir:
            ex = set(categorias_excluir)
            if incluir_subcategorias:
                cola = list(ex)
                while cola:
                    c = cola.pop()
                    for h in hijos.get(c, ()):
                        if h not in ex:
                            ex.add(h)
                            cola.append(h)
            cats -= ex
        total_valor = 0.0
        total_entradas = 0
        for item in fuente:
            obj = item['object']
            cat = obj.category_id.code if obj.category_id else None
            if cat not in cats or not _pasa_filtros(obj):
                continue

            total_valor += item.get('total', 0.0)
            total_entradas += item.get('quantity', 0)

        return total_valor, total_entradas
    

    def _ssocial001(self, liquidacion_data):
        """
        Calcula la deducción de salud del empleado
        """
        porcentaje_salud = liquidacion_data['annual_parameters'].value_porc_health_employee / 100
        slip = liquidacion_data['slip']
        periodo = self._get_periodo(slip).upper()
        empleado = liquidacion_data['employee']

        # Verificar si el empleado no contribuye a EPS
        if empleado.subtipo_coti_id.not_contribute_eps:
            return 0, 0, 0, 0, False, {}

        # Verificar si no es contrato de aprendizaje
        if liquidacion_data['contract'].contract_type != 'aprendizaje':
            # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
            ibd_rule = liquidacion_data.get('rules', {}).get('IBD')
            ibc_full = ibd_rule.extra_data.get('ibc_final', 0) if ibd_rule else 0
            ingreso_base_cotizacion = ibd_rule.total if ibd_rule else 0
            ibc = ibc_full - ingreso_base_cotizacion

            # Obtener valor acumulado del mes anterior
            valor_mes_anterior = self._get_totalizar_reglas(
                liquidacion_data, 'SSOCIAL001',
                incluir_current=True, incluir_before=False, incluir_multi=False,
                devolver_cantidad=False
            )
            vac = ibd_rule.extra_data.get('vac_monto', 0) if ibd_rule else 0
            vac_dias = ibd_rule.extra_data.get('vac_dias', 0) if ibd_rule else 0
            ibc_anterior = valor_mes_anterior / porcentaje_salud if porcentaje_salud else 0
            ibc_adjustado = ibc + ibc_anterior - vac
            base_calculo = ingreso_base_cotizacion + ibc_adjustado

            porcentaje_salud = liquidacion_data['annual_parameters'].value_porc_health_employee

            # Verificar si aplica según la quincena de cobro
            if ((self.aplicar_cobro == '15' and slip.date_from.day >= 15) or
                (self.aplicar_cobro == '30' and slip.date_from.day < 15)):
                return 0, 0, porcentaje_salud, '', False, {}
            else:
                return base_calculo, -1, porcentaje_salud, periodo, False, {}
        else:
            return 0, 0, 0, 0, False, {}

    def _ssocial002(self, liquidacion_data):
        """
        Calcula la deducción de pensión del empleado
        """
        porcentaje_pension = liquidacion_data['annual_parameters'].value_porc_pension_employee / 100
        slip = liquidacion_data['slip']
        periodo = self._get_periodo(slip).upper()
        empleado = liquidacion_data['employee']

        if empleado.subtipo_coti_id.not_contribute_pension:
            return 0, 0, 0, 0, False, {}

        if liquidacion_data['contract'].contract_type != 'aprendizaje':
            # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
            ibd_rule = liquidacion_data.get('rules', {}).get('IBD')
            ibc_full = ibd_rule.extra_data.get('ibc_final', 0) if ibd_rule else 0
            ingreso_base_cotizacion = ibd_rule.total if ibd_rule else 0
            ibc = ibc_full - ingreso_base_cotizacion

            valor_mes_anterior = self._get_totalizar_reglas(
                liquidacion_data, 'SSOCIAL002',
                incluir_current=True, incluir_before=False, incluir_multi=False,
                devolver_cantidad=False
            )
            vac = ibd_rule.extra_data.get('vac_monto', 0) if ibd_rule else 0
            vac_dias = ibd_rule.extra_data.get('vac_dias', 0) if ibd_rule else 0
            ibc_anterior = valor_mes_anterior / porcentaje_pension if porcentaje_pension else 0
            ibc_adjustado = ibc + ibc_anterior - vac
            base_calculo = ingreso_base_cotizacion + ibc_adjustado

            porcentaje_pension = liquidacion_data['annual_parameters'].value_porc_pension_employee

            if ((self.aplicar_cobro == '15' and slip.date_from.day >= 15) or
                (self.aplicar_cobro == '30' and slip.date_from.day < 15)):
                return 0, 0, porcentaje_pension, '', False, {}
            else:
                return base_calculo, -1, porcentaje_pension, periodo, False, {}
        else:
            return 0, 0, 0, 0, False, {}
          
    def _ssocial003(self, liquidacion_data):
        """
        Calcula el aporte a fondo de solidaridad
        """
        porcentaje_fsp = 0.5
        slip = liquidacion_data['slip']
        periodo = self._get_periodo(slip).upper()
        parametros_anuales = liquidacion_data['annual_parameters']
        contrato = liquidacion_data['contract']

        # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
        ibd_rule = liquidacion_data.get('rules', {}).get('IBD')

        debe_proyectar = (contrato.proyectar_fondos and slip.date_from.day <= 15)

        if debe_proyectar:
            total, qty_days = self._get_totalizar_categorias(
                liquidacion_data, categorias=['BASIC'],
                incluir_current=False, incluir_before=False, incluir_multi=True
            )
            total_dev, _ = self._get_totalizar_categorias(
                liquidacion_data, categorias=['DEV_SALARIAL'], categorias_excluir="BASIC",
                incluir_current=False, incluir_before=False, incluir_multi=True
            )

            if liquidacion_data['slip'].struct_type_id.wage_type == "hourly" and qty_days > 0:
                hours_daily = parametros_anuales.hours_daily
                qty_days = qty_days / hours_daily

            total_basic = total / qty_days if qty_days > 0 else 0
            days_project =  qty_days + 15
            BASIC = total_basic * days_project
            ingreso_base_cotizacion = (BASIC + total_dev)
        else:
            ingreso_base_cotizacion = ibd_rule.total if ibd_rule else 0

        if (round_1_decimal(ingreso_base_cotizacion) <= round_1_decimal(parametros_anuales.top_four_fsp_smmlv) or
            contrato.contract_type == 'aprendizaje'):
            return 0, 0, porcentaje_fsp, '', False, {}

        empleado = liquidacion_data['employee']
        es_pensionado = empleado.subtipo_coti_id.code not in ['00', False]

        if es_pensionado:
            return 0, 0, porcentaje_fsp, '', False, {}

        valor_mes_anterior = self._get_totalizar_reglas(
            liquidacion_data, 'SSOCIAL003',
            incluir_current=True
        )

        if valor_mes_anterior != 0:
            base_mes_anterior = valor_mes_anterior / (porcentaje_fsp / 100)
        else:
            base_mes_anterior = 0

        base_calculo = ingreso_base_cotizacion - abs(base_mes_anterior)

        if ((self.aplicar_cobro == '15' and slip.date_from.day >= 15) or
            (self.aplicar_cobro == '30' and slip.date_from.day < 15)):
            return 0, 0, porcentaje_fsp, '', False, {}
        if debe_proyectar and base_calculo > 0:
            base_calculo = base_calculo / 2

        # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
        ibd_rule = liquidacion_data.get('rules', {}).get('IBD')
        vac = ibd_rule.extra_data.get('vac_monto', 0) if ibd_rule else 0
        if  self._get_totalizar_reglas(liquidacion_data, 'SSOCIAL003',  incluir_before=True) == 0:
            vac = 0.0
        return base_calculo - vac, -1, porcentaje_fsp, periodo, False, {}

    def _ssocial004(self, liquidacion_data):
        """
        Calcula el aporte al fondo de subsistencia
        """
        def calcular_porcentaje_subsistencia(ingreso_base, salario_minimo):
            """Determina el porcentaje según el rango de IBC"""
            if ingreso_base <= 4 * salario_minimo:
                return 0.0
            elif ingreso_base <= 16 * salario_minimo:
                return 0.5
            elif ingreso_base <= 17 * salario_minimo:
                return 0.7
            elif ingreso_base <= 18 * salario_minimo:
                return 0.9
            elif ingreso_base <= 19 * salario_minimo:
                return 1.1
            elif ingreso_base <= 20 * salario_minimo:
                return 1.3
            else:
                return 1.5

        parametros_anuales = liquidacion_data['annual_parameters']
        salario_minimo = parametros_anuales.smmlv_monthly
        slip = liquidacion_data['payslip']
        periodo = self._get_periodo(slip).upper()
        contrato = liquidacion_data['contract']

        # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
        ibd_rule = liquidacion_data.get('rules', {}).get('IBD')

        # Verificar si debe proyectar
        debe_proyectar = (contrato.proyectar_fondos and slip.date_from.day <= 15)

        if debe_proyectar:
            total, qty_days = self._get_totalizar_categorias(
                liquidacion_data, categorias=['BASIC'],
                incluir_current=False, incluir_before=False, incluir_multi=True
            )
            total_dev, _ = self._get_totalizar_categorias(
                liquidacion_data, categorias=['DEV_SALARIAL'], categorias_excluir="BASIC",
                incluir_current=False, incluir_before=False, incluir_multi=True
            )

            if liquidacion_data['slip'].struct_type_id.wage_type == "hourly" and qty_days > 0:
                hours_daily = parametros_anuales.hours_daily
                qty_days = qty_days / hours_daily

            total_basic = total / qty_days if qty_days > 0 else 0
            days_project =  qty_days + 15
            BASIC = total_basic * days_project
            ingreso_base_cotizacion = (BASIC + total_dev)
        else:
            ingreso_base_cotizacion = ibd_rule.total if ibd_rule else 0

        empleado = liquidacion_data['employee']
        es_pensionado = empleado.subtipo_coti_id.code not in ['00', False]

        # Verificar condiciones iniciales
        if (es_pensionado or
            contrato.contract_type == 'aprendizaje' or
            round_1_decimal(ingreso_base_cotizacion) <= round_1_decimal(parametros_anuales.top_four_fsp_smmlv)):
            return 0.0, 1, 0.0, '', False, {}

        # Calcular porcentaje según rango
        multiples_sm = ingreso_base_cotizacion / salario_minimo
        porcentaje = calcular_porcentaje_subsistencia(round_1_decimal(ingreso_base_cotizacion), round_1_decimal(salario_minimo))

        if porcentaje != 0.0:
            valor_mes_anterior = self._get_totalizar_reglas(
                liquidacion_data, 'SSOCIAL004',
                incluir_current=True
            )

            if valor_mes_anterior != 0:
                base_mes_anterior = valor_mes_anterior / (porcentaje / 100)
            else:
                base_mes_anterior = 0

            base_calculo = ingreso_base_cotizacion - abs(base_mes_anterior)

            if ((self.aplicar_cobro == '15' and slip.date_from.day >= 15) or
                (self.aplicar_cobro == '30' and slip.date_from.day < 15)):
                return 0, 0, porcentaje, '', False, {}

            if debe_proyectar and base_calculo > 0:
                base_calculo = base_calculo / 2

            # ODOO 18: Acceder a IBD desde rules (guardado por hr_slip.py línea 1263)
            ibd_rule = liquidacion_data.get('rules', {}).get('IBD')
            vac = ibd_rule.extra_data.get('vac_monto', 0) if ibd_rule else 0
            if  self._get_totalizar_reglas(liquidacion_data, 'SSOCIAL004',  incluir_before=True) == 0:
                vac = 0
            return base_calculo - vac, -1, porcentaje, periodo, False, {}
        else:
            return 0.0, 1, 0.0, '', False, {}
        


    # Implementación de los métodos principales

    def get_holiday_book(self, contract, date_from=False, date_ref=False):
        """
        Calcula los días de vacaciones acumulados y disponibles para un empleado
        
        Args:
            contract: Contrato del empleado
            date_ref: Fecha de referencia para el cálculo (por defecto, fecha actual)
            
        Returns:
            dict: Diccionario con información de días trabajados, disponibles, disfrutados, etc.
        """
        date_ref = date_ref or contract.date_ref_holiday_book or datetime.now()
        prestaciones_service = self.env['prestaciones.sociales.service']
        worked_days = days360(date_from, date_ref)
        
        days_enjoyed, days_paid, days_suspension = 0, 0, 0
        
        for holiday_book in contract.vacaciones_ids:
            days_enjoyed += holiday_book.business_units
        
        leave_lines = self.env["hr.leave.line"].search([
            ("leave_id.employee_id", "=", contract.employee_id.id),
            ("leave_id.state", "=", "validate"),
            ("leave_id.unpaid_absences", "=", True),
            ("date", ">=", date_from),
            ("date", "<=", date_ref),
        ])
        
        days_suspension = sum(line.days_payslip for line in leave_lines)
        
        worked_days_adjusted = worked_days - days_suspension
        
        days_left = (worked_days_adjusted * 15 / DAYS_YEAR) #- days_enjoyed
        return {
            'worked_days': round_1_decimal(worked_days),
            'worked_days_adjusted': round_1_decimal(worked_days_adjusted),
            'days_left': round_1_decimal(days_left),
            'days_enjoyed': round_1_decimal(days_enjoyed),
            'days_paid': round_1_decimal(days_paid),
            'days_suspension': round_1_decimal(days_suspension),
        }

    def _round1(self, amount: Decimal | float) -> Decimal:
        """Redondea al entero más cercano (sin decimales) usando Decimal."""
        from decimal import Decimal, ROUND_HALF_UP
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _label_vac_liq(
        self,
        days_pending: Decimal | float,
        days_enjoyed: Decimal | float,
        ) -> str:
        """Construye la etiqueta *VACACIONES LIQ.* con acrónimos y emojis. 
        """
        icon_pending = '$' 
        icon_enjoyed = "" 
        dpp = f"D.P.P=({icon_pending} {round(days_pending,2)})"
        ddf = f"D.D.F=({icon_enjoyed} {round(days_enjoyed,2)})"
        return f"VACACIONES LIQ. DE CONTRATO {dpp} {ddf}"

    def _rtf_prima(self, liquidacion_data):
        """
        Retención en la fuente para prima de servicios.
        Usa el método genérico de retención con tipo='prima'.
        """
        # Usar el método genérico de retención con tipo especial 'prima'
        return self._calculate_retention_generic(liquidacion_data, tipo='prima')

    def get_last_year(self, data_payslip, date_to):
        date_from = date_to - relativedelta(years=1)
        if date_from < data_payslip['contract'].date_start:
            date_from = data_payslip['contract'].date_start
        days = days360(date_from, date_to)
        dias_ausencias =  sum([i.number_of_days for i in self.env['hr.leave'].search([('date_from','>=',data_payslip['slip'].date_vacaciones),('date_to','<=',data_payslip['slip'].date_liquidacion),('state','=','validate'),('employee_id','=',data_payslip['slip'].employee_id.id),('unpaid_absences','=',True)])])
        dias_ausencias += sum([i.days for i in self.env['hr.absence.history'].search([('star_date', '>=', data_payslip['slip'].date_vacaciones), ('end_date', '<=', data_payslip['slip'].date_liquidacion),('employee_id', '=', data_payslip['slip'].employee_id.id), ('leave_type_id.unpaid_absences', '=', True)])])
        wd = days - dias_ausencias
        data = {}
        values_base_compensation = 0.0
        rules = data_payslip.get('rules', {})
        for rule_code, rule_data in rules.items():
            total = rule_data.get('total', 0)
            rule_obj = rule_data.get('rule')
            # Acceder a base_prima desde el objeto regla
            if rule_code != 'BASIC' and rule_code != 'AUX000' and rule_obj and getattr(rule_obj, 'base_prima', False):
                values_base_compensation += total
        acumulatdo = self.get_accumulated_compensation(data_payslip, date_from, date_to, values_base_compensation)
        return acumulatdo# / 30
    
    def get_accumulated_compensation(self, data_payslip, date_start, date_end, values_base_compensation):
        date_start = date_end-relativedelta(years=1)
        date_start = data_payslip['contract'].date_start if date_start <= data_payslip['contract'].date_start else date_start
        dias_trabajados = days360(date_start, date_end)
        # formatear fechas
        date_start = str(date_start.year) + '-' + str(date_start.month) + '-' + str(date_start.day)
        date_end = str(date_end.year) + '-' + str(date_end.month) + '-' + str(date_end.day)

        self.env.cr.execute("""Select Sum(accumulated) as accumulated
                                From
                                (
                                    Select COALESCE(sum(pl.total),0) as accumulated 
                                        From hr_payslip as hp 
                                        Inner Join hr_payslip_line as pl on  hp.id = pl.slip_id 
                                        Inner Join hr_salary_rule hc on pl.salary_rule_id = hc.id and hc.base_compensation = true
                                        Inner Join hr_salary_rule_category hsc on hc.category_id = hsc.id and (hsc.code != 'BASIC' or hc.code='BASICTURNOS')
                                        WHERE hp.state = 'done' and hp.contract_id = %s
                                        AND (hp.date_from between %s and %s
                                            or
                                            hp.date_to between %s and %s )
                                    Union 
                                    Select COALESCE(sum(pl.amount),0) as accumulated
                                        From hr_accumulated_payroll as pl
                                        Inner Join hr_salary_rule hc on pl.salary_rule_id = hc.id and hc.base_compensation = true
                                        Inner Join hr_salary_rule_category hsc on hc.category_id = hsc.id and (hsc.code != 'BASIC' or hc.code='BASICTURNOS')
                                        WHERE pl.employee_id = %s and pl.date between %s and %s
                                ) As A""",
                            (data_payslip['contract'].id, date_start, date_end, date_start, date_end, data_payslip['contract'].employee_id.id,
                             date_start, date_end))
        res = self.env.cr.fetchone()
        if res and res[0]:
            return ((res[0]+values_base_compensation) / dias_trabajados) * DAYS_YEAR
        else:
            return 0.0
        
    def _indem(self, data_payslip):
        """
        Calcula la indemnización por terminación de contrato sin justa causa.
        Incluye cálculo proporcional para fracciones de año.
        
        Args:
            data_payslip (dict): Diccionario con datos de liquidación
            
        Returns:
            tuple: (valor_diario, días, porcentaje, nombre, log_html, datos_para_visualización)
        """

        
        def to_decimal(value):
            """Convierte un valor a Decimal de manera segura."""
            if isinstance(value, Decimal):
                return value
            elif value is None:
                return Decimal("0")
            return Decimal(str(value))
        
        def decimal_round(value, precision=2):
            """Redondea un valor Decimal al número de decimales especificado."""
            value = to_decimal(value)
            decimal_precision = Decimal(f'0.{"0" * precision}1')
            return value.quantize(decimal_precision, rounding=ROUND_HALF_UP)
        
        def fmt_money(val):
            """Formatea un valor monetario."""
            if isinstance(val, Decimal):
                val_float = float(val)
            elif val is None:
                val_float = 0.0
            else:
                try:
                    val_float = float(val)
                except (ValueError, TypeError):
                    val_float = 0.0
            return format_amount(self.env, val_float, self.env.company.currency_id)
        

        
        def generar_html_indemnizacion(tipo_contrato, date_start, settlement_date, duration_days, 
                                    years_worked, salario_basico, salario_variable, salario_total,
                                    explicaciones, pasos, dias_indemnizacion, valor_diario, valor_total):
            """Genera directamente el HTML para la visualización."""
            tipos_contrato = {
                'fijo': _('Término Fijo'),
                'indefinido': _('Término Indefinido'),
                'obra': _('Obra o Labor')
            }
            tipo_contrato_mostrar = tipos_contrato.get(tipo_contrato, tipo_contrato.capitalize())
            
            html = [
                '<div class="p-3 border rounded bg-light">',
                f'<h5 class="text-primary">{_("Cálculo de Indemnización")} - {tipo_contrato_mostrar}</h5>'
            ]
            
            html.append(
                f'<div class="mb-3">'
                f'<small><strong>{_("Periodo")}:</strong> {date_start.strftime("%d/%m/%Y")} – {settlement_date.strftime("%d/%m/%Y")}</small><br/>'
                f'<small><strong>{_("Días trabajados")}:</strong> {duration_days} ({years_worked:.2f} años)</small>'
                f'</div><hr/>'
            )
            
            html.append('<div class="mb-3 p-2 bg-white rounded shadow-sm border-start border-primary border-4">')
            html.append(f'<h6 class="mb-2">{_("Componentes del Salario")}:</h6>')
            
            html.append(
                f'<div><strong>{_("Salario básico")}:</strong> '
                f'<span class="text-primary">{fmt_money(salario_basico)}</span></div>'
            )
            
            html.append(
                f'<div><strong>{_("Promedio variable")}:</strong> '
                f'<span class="text-primary">{fmt_money(salario_variable)}</span></div>'
            )
            
            html.append(
                f'<div><strong>{_("Salario total")}:</strong> '
                f'<span class="text-primary font-weight-bold">{fmt_money(salario_total)}</span></div>'
            )
            
            html.append('</div>')
            
            if explicaciones and len(explicaciones) > 0:
                html.append('<div class="mt-3 mb-3 p-2 bg-white rounded shadow-sm">')
                html.append(f'<h6 class="mb-2">{_("Criterios del Cálculo")}:</h6>')
                
                html.append('<ul class="mb-0">')
                for explicacion in explicaciones:
                    html.append(f'<li>{explicacion}</li>')
                html.append('</ul>')
                
                html.append('</div>')
            
            if pasos and len(pasos) > 0:
                html.append('<div class="mt-3 mb-3">')
                html.append(f'<h6 class="mb-2">{_("Detalle del Cálculo")}:</h6>')
                
                html.append('<div class="table-responsive">')
                html.append('<table class="table table-sm table-bordered">')
                html.append(f'<thead class="table-light"><tr><th>{_("Concepto")}</th><th>{_("Detalle")}</th><th class="text-end">{_("Valor")}</th></tr></thead>')
                html.append('<tbody>')
                
                for paso in pasos:
                    detalle = paso.get('detalle', '')
                    calculo = paso.get('calculo', '')
                    valor = paso.get('valor', 0)
                    
                    html.append('<tr>')
                    html.append(f'<td><strong>{detalle}</strong></td>')
                    html.append(f'<td>{calculo}</td>')
                    html.append(f'<td class="text-end">{fmt_money(valor) if "diario" not in detalle.lower() else valor}</td>')
                    html.append('</tr>')
                
                html.append('</tbody></table>')
                html.append('</div>')
                html.append('</div>')
            
            html.append('<div class="mt-3 p-3 bg-light rounded shadow-sm border border-success">')
            html.append(f'<h6 class="mb-2 text-success">{_("Resultado Final")}:</h6>')
            
            html.append(
                f'<div><strong>{_("Días de indemnización")}:</strong> '
                f'<span class="text-success fw-bold">{dias_indemnizacion:.2f}</span></div>'
            )
            
            html.append(
                f'<div><strong>{_("Valor diario")}:</strong> '
                f'<span class="text-success fw-bold">{fmt_money(valor_diario)}</span></div>'
            )
            
            html.append(
                f'<div><strong>{_("Valor total indemnización")}:</strong> '
                f'<span class="text-success fw-bold">{fmt_money(valor_total)}</span></div>'
            )
            
            html.append('</div>')
            
            html.append('</div>')
            
            return ''.join(html)
        
        annual_params = data_payslip['annual_parameters']
        slip = data_payslip.get('slip')
        contract = data_payslip.get('contract')
        
        if not slip or not contract or not slip.reason_retiro or not slip.have_compensation:
            return 0, 0, 0, 0, "", {}
        
        settlement_date = slip.date_liquidacion
        if not settlement_date:
            return 0, 0, 0, 0, "", {}
        
        date_start = contract.date_start
        if not date_start:
            return 0, 0, 0, 0, "", {}
        
        
        salario_variable = to_decimal(0)
        if contract.modality_salary == 'variable':
            salario_variable = to_decimal(self.get_last_year(data_payslip, settlement_date))

        
        salario_basico = to_decimal(contract.wage)
        salario_total = salario_basico + salario_variable
        
        duration_days = days360(date_start, settlement_date)
        years_worked = to_decimal(duration_days) / to_decimal(DAYS_YEAR)
        
        smmlv = to_decimal(annual_params.smmlv_monthly)
        
        pasos = []
        explicaciones = []
        
        dias_indemnizacion = to_decimal(0)
        
        if contract.contract_type in ['fijo', 'obra']:
            date_end = contract.date_end
            if not date_end:
                return 0, 0, 0, 0, "", {}
            
            if settlement_date > date_end:
                return 0, 0, 0, 0, "", {}
            
            days_not_pay = days360(settlement_date, date_end) - 1
            
            explicaciones.append(
                f"Contrato a término {contract.contract_type}. "
                f"Se calcula indemnización por los días faltantes para terminar el contrato."
            )
            
            if days_not_pay <= 0:
                return 0, 0, 0, 0, "", {}
            
            dias_indemnizacion = to_decimal(days_not_pay)
            
            if contract.contract_type == 'obra' and dias_indemnizacion < 15:
                pasos.append({
                    'detalle': 'Ajuste mínimo para contrato por obra',
                    'calculo': f"Días faltantes: {float(dias_indemnizacion)}. "
                            f"Como es menor a 15 días, se ajusta al mínimo legal.",
                    'valor': 15.0
                })
                dias_indemnizacion = to_decimal(15)
            else:
                pasos.append({
                    'detalle': 'Días faltantes para terminar el contrato',
                    'calculo': f"Desde {settlement_date.strftime('%d/%m/%Y')} "
                            f"hasta {date_end.strftime('%d/%m/%Y')}",
                    'valor': float(dias_indemnizacion)
                })
        
        else:
            explicaciones.append(
                f"Contrato a término indefinido. "
                f"El salario total es {fmt_money(salario_total)} y el límite de 10 SMMLV es {fmt_money(smmlv * 10)}."
            )
            
            if salario_total < smmlv * 10:
                explicaciones.append(
                    f"El salario es menor a 10 SMMLV. "
                    f"Se aplica: 30 días por el primer año + 20 días por cada año adicional hasta el 5to año "
                    f"+ 13.33 días por cada año después del 5to."
                )
                
                if years_worked <= 1:
                    dias_primer_anio = to_decimal(DAYS_MONTH) * years_worked
                    pasos.append({
                        'detalle': 'Primer año o fracción',
                        'calculo': f"30 días × {float(years_worked):.2f} años = {float(dias_primer_anio):.2f} días",
                        'valor': float(dias_primer_anio)
                    })
                    dias_indemnizacion = dias_primer_anio
                else:
                    pasos.append({
                        'detalle': 'Primer año completo',
                        'calculo': f"30 días por el primer año completo",
                        'valor': DAYS_MONTH
                    })
                    dias_indemnizacion = to_decimal(DAYS_MONTH)
                    
                    if years_worked <= 6:
                        anios_adicionales = years_worked - 1
                        dias_anios_2_a_5 = anios_adicionales * to_decimal(20)
                        
                        pasos.append({
                            'detalle': 'Años 2 al 5 o fracción',
                            'calculo': f"{float(anios_adicionales):.2f} años × 20 días = {float(dias_anios_2_a_5):.2f} días",
                            'valor': float(dias_anios_2_a_5)
                        })
                        dias_indemnizacion += dias_anios_2_a_5
                    else:
                        dias_anios_2_a_5 = to_decimal(5) * to_decimal(20)
                        pasos.append({
                            'detalle': 'Años 2 al 5 completos',
                            'calculo': f"5 años × 20 días = {float(dias_anios_2_a_5)} días",
                            'valor': float(dias_anios_2_a_5)
                        })
                        dias_indemnizacion += dias_anios_2_a_5
                        
                        anios_despues_6 = years_worked - 6
                        dias_anios_6_adelante = anios_despues_6 * to_decimal('13.33')
                        
                        pasos.append({
                            'detalle': 'Años posteriores al 5to',
                            'calculo': f"{float(anios_despues_6):.2f} años × 13.33 días = {float(dias_anios_6_adelante):.2f} días",
                            'valor': float(dias_anios_6_adelante)
                        })
                        dias_indemnizacion += dias_anios_6_adelante
            else:
                explicaciones.append(
                    f"El salario es igual o mayor a 10 SMMLV. "
                    f"Se aplica: 20 días por el primer año + 15 días por cada año adicional."
                )
                
                if years_worked <= 1:
                    dias_primer_anio = to_decimal(20) * years_worked
                    pasos.append({
                        'detalle': 'Primer año o fracción',
                        'calculo': f"20 días × {float(years_worked):.2f} años = {float(dias_primer_anio):.2f} días",
                        'valor': float(dias_primer_anio)
                    })
                    dias_indemnizacion = dias_primer_anio
                else:
                    pasos.append({
                        'detalle': 'Primer año completo',
                        'calculo': f"20 días por el primer año completo",
                        'valor': 20.0
                    })
                    dias_indemnizacion = to_decimal(20)
                    
                    anios_adicionales = years_worked - 1
                    dias_anios_adicionales = anios_adicionales * to_decimal(15)
                    
                    pasos.append({
                        'detalle': 'Años adicionales o fracción',
                        'calculo': f"{float(anios_adicionales):.2f} años × 15 días = {float(dias_anios_adicionales):.2f} días",
                        'valor': float(dias_anios_adicionales)
                    })
                    dias_indemnizacion += dias_anios_adicionales
        
        valor_diario = salario_total / DAYS_MONTH
        valor_total = valor_diario * dias_indemnizacion
        
        dias_indemnizacion = decimal_round(dias_indemnizacion, 2)
        valor_diario = decimal_round(valor_diario, 2)
        valor_total = decimal_round(valor_total, 2)
        
        pasos.append({
            'detalle': 'Cálculo del valor diario',
            'calculo': f"Salario total {fmt_money(salario_total)} ÷ 30 días = {fmt_money(valor_diario)}",
            'valor': float(valor_diario)
        })
        
        pasos.append({
            'detalle': 'Cálculo del valor total',
            'calculo': f"Valor diario {fmt_money(valor_diario)} × {float(dias_indemnizacion)} días = {fmt_money(valor_total)}",
            'valor': float(valor_total)
        })
        
        html_log = generar_html_indemnizacion(
            contract.contract_type,
            date_start, 
            settlement_date, 
            duration_days, 
            float(years_worked),
            float(salario_basico),
            float(salario_variable),
            float(salario_total),
            explicaciones,
            pasos,
            float(dias_indemnizacion),
            float(valor_diario),
            float(valor_total)
        )
        
        contract_type = contract.contract_type
        contract_name = dict(contract._fields['contract_type'].selection).get(contract_type, "")
        
        nombre = f"INDEMNIZACIÓN CONTRATO {contract_name.upper()}"
        
        visual_data = {
            'employee': {
                'name': contract.employee_id.name,
                'id': contract.employee_id.identification_id,
            },
            'contract': {
                'type': contract_name,
                'start_date': contract.date_start.strftime('%Y-%m-%d'),
                'end_date': contract.date_end.strftime('%Y-%m-%d') if contract.date_end else 'N/A',
                'salary': float(salario_total),
                'avg': float(salario_variable),
            },
            'calculation': {
                'years_worked': float(years_worked),
                'days_first_year': float(dias_indemnizacion),
                'total_indem': float(valor_total),
                'steps': pasos,
                'explanation': explicaciones,
            },
            'params': {
                'smmlv': float(smmlv),
            }
        }
        
        return float(valor_diario), float(dias_indemnizacion), 100, nombre, html_log, visual_data

class hr_types_faults(models.Model):
    _name = 'hr.types.faults'
    _description = 'Tipos de faltas'

    name = fields.Char('Nombre', required=True)
    description = fields.Text('Descripción')
