# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, SUPERUSER_ID, tools, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round, date_utils, format_amount
from odoo.tools.misc import format_date
from odoo.tools.safe_eval import safe_eval
from collections import defaultdict, Counter, OrderedDict
from functools import partial, lru_cache
from datetime import datetime, timedelta, date, time
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from psycopg2 import sql
from psycopg2.extras import Json
from typing import Dict, List, Tuple, Any, Optional, Union, TypedDict
import ast
import re
import json
import logging
import math
import pytz
import calendar
import base64
import io

from .hr_slip_data_structures import (
    RuleData, CategoryData, CategoryCollection,
    LineDetail, ChangeRecord,
    ensure_category_data, ensure_rule_data
)

_logger = logging.getLogger(__name__)

# ===============================================================================
# CONSTANTES GLOBALES
# ===============================================================================

DAYS_YEAR = 360
DAYS_YEAR_NATURAL = 365
DAYS_MONTH = 30
PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 0
DATETIME_MIN = datetime.min.time()
DATETIME_MAX = datetime.max.time()
HOURS_PER_DAY = 8
UTC = pytz.UTC

# Códigos especiales
TPCT = 'total_previous_categories'
TPCP = 'total_previous_concepts'
NCI = 'non_constitutive_income'

# Tabla de retención en la fuente (en UVT)
TABLA_RETENCION = [
    (0, 95, 0, 0, 0),
    (95, 150, 19, 95, 0),
    (150, 360, 28, 150, 10),
    (360, 640, 33, 360, 69),
    (640, 945, 35, 640, 162),
    (945, 2300, 37, 945, 268),
    (2300, float('inf'), 39, 2300, 770)
]

CATEGORY_MAPPINGS = {
    'EARNINGS': [
        'BASIC', 'AUX', 'AUS', 'ALW', 'ACCIDENTE_TRABAJO',
        'DEV_NO_SALARIAL', 'DEV_SALARIAL', 'TOTALDEV', 'HEYREC',
        'COMISIONES', 'INCAPACIDAD', 'LICENCIA_MATERNIDAD',
        'LICENCIA_NO_REMUNERADA', 'LICENCIA_REMUNERADA',
        'PRESTACIONES_SOCIALES', 'PRIMA', 'VACACIONES'
    ],
    'DEDUCTIONS': [
        'DED', 'DEDUCCIONES', 'TOTALDED', 'SANCIONES',
        'DESCUENTO_AFC'
    ],
    'SOCIAL_SECURITY': ['SSOCIAL'],
    'PROVISIONS': ['PROV'],
    'BASES': ['IBC', 'IBD', 'IBC_R'],
    'OUTCOME': ['NET']
}

# Tipos de novedad válidos para PILA (lista simple)
VALID_NOVELTY_TYPES = [
    'sln', 'ige', 'irl', 'lma', 'lpa', 'vco', 'vdi',
    'vre', 'lr', 'lnr', 'lt', 'p'
]

# -------------------------------------------------------------------------
# TIPOS DE NOVEDAD PILA - Selection para campos
# Usado en: hr.leave.type.novelty
# -------------------------------------------------------------------------
NOVELTY_TYPE_SELECTION = [
    ('sln', 'Suspension temporal del contrato de trabajo'),
    ('ige', 'Incapacidad EPS'),
    ('irl', 'Incapacidad por accidente de trabajo o Enfermedad laboral'),
    ('lma', 'Licencia de Maternidad'),
    ('lpa', 'Licencia de Paternidad'),
    ('vco', 'Vacaciones Compensadas (Dinero)'),
    ('vdi', 'Vacaciones Disfrutadas'),
    ('vre', 'Vacaciones por Retiro'),
    ('lr', 'Licencia remunerada'),
    ('lnr', 'Licencia no Remunerada'),
    ('lt', 'Licencia de Luto'),
    ('p', 'Permisos no remunerados D/H (No se envia en pila)'),
]

# -------------------------------------------------------------------------
# TIPO DE LIQUIDACION DE VALORES - Selection para campos
# Usado en: hr.leave.type.liquidacion_value
# Define como se calcula el valor base de la ausencia
# -------------------------------------------------------------------------
LIQUIDATION_VALUE_SELECTION = [
    ('IBC', 'IBC Mes Anterior'),
    ('YEAR', 'Promedio Ano Anterior'),
    ('WAGE', 'Sueldo Actual'),
    ('MIN', 'Parametros minimos de ley'),
]

# -------------------------------------------------------------------------
# CONFIGURACION DE NOVEDADES PILA - Diccionario con comportamiento
# Usado en: calculos de IBC, seguridad social, auxilio transporte
# -------------------------------------------------------------------------
NOVELTY_TYPES_CONFIG = {
    'sln': {
        'name': 'Suspension temporal del contrato',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,  # Resta dias trabajados
        'paga_salario': False,
        'paga_auxilio': False,
    },
    'ige': {
        'name': 'Incapacidad EPS',
        'descuenta_ss': False,      # Mantiene IBC
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
        'tramos': True,             # Tiene porcentajes por rangos
    },
    'irl': {
        'name': 'Incapacidad ARL',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
        'tramos': True,
    },
    'lma': {
        'name': 'Licencia de Maternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'lpa': {
        'name': 'Licencia de Paternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vco': {
        'name': 'Vacaciones Compensadas (Dinero)',
        'descuenta_ss': False,
        'descuenta_trabajo': False,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vdi': {
        'name': 'Vacaciones Disfrutadas',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'vre': {
        'name': 'Vacaciones por Retiro',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': False,
    },
    'lr': {
        'name': 'Licencia remunerada',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': True,       # Segun configuracion
    },
    'lnr': {
        'name': 'Licencia no Remunerada',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio': False,
    },
    'lt': {
        'name': 'Licencia de Luto',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio': True,
    },
    'p': {
        'name': 'Permisos no remunerados D/H',
        'descuenta_ss': True,       # NO suma al IBC
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio': False,
        'no_pila': True,            # No se reporta en PILA
    },
}

def get_novelty_config(novelty_code):
    """
    Obtiene la configuracion de una novedad segun su codigo PILA.
    
    Args:
        novelty_code: Codigo de la novedad (sln, ige, irl, lma, lpa, etc.)
    
    Returns:
        dict con la configuracion de la novedad, o None si no existe
    
    Ejemplo:
        config = get_novelty_config('ige')
        if config and not config['descuenta_ss']:
            # Mantiene IBC
    """
    return NOVELTY_TYPES_CONFIG.get(novelty_code)

TYPE_PERIOD = [
    ('monthly', 'Mensual'),
    ('bi-monthly', 'Quincenal'),
    ('weekly', 'Semanal'),
    ('dualmonth', 'Cada 2 Meses'),
    ('quarterly', 'Cada Cuatro meses'),
    ('semi-annually', 'Cada 6 Meses'),
    ('annually', 'Anual'),
]

TYPE_BIWEEKLY = [
    ('first', 'Primera Quincena'),
    ('second', 'Segunda Quincena')
]

MOVE_TYPE_SELECTION = [
    ('payroll', 'Nomina'),
    ('prima', 'Prima'),
    ('cesantias', 'Cesantias'),
    ('vacaciones', 'Vacaciones'),
    ('liquidacion', 'Liquidacion Final'),
    ('otros', 'Otros'),
    ('r_payroll', 'Reversion de Nomina'),
    ('r_prima', 'Reversion Prima'),
    ('r_cesantias', 'Reversion Cesantias'),
    ('r_vacaciones', 'Reversion Vacaciones'),
    ('r_liquidacion', 'Reversion Liquidacion'),
    ('r_otros', 'Reversion Otros')
]

COMPUTATION_STATUS_SELECTION = [
    ('draft', 'Borrador'),
    ('computing', 'Calculando'),
    ('computed', 'Calculado'),
    ('error', 'Error'),
]

RIBBON_COLOR_SELECTION = [
    ('warning', 'Advertencia'),
    ('info', 'Información'),
    ('success', 'Éxito'),
    ('danger', 'Peligro')
]

# ===============================================================================
# FUNCIONES AUXILIARES GLOBALES
# ===============================================================================

def days360(start_date, end_date, method_eu=False):
    """
    Calcula el numero de dias entre dos fechas considerando todos los meses como de 30 dias.
    Metodo comercial colombiano (360 dias/año, 30 dias/mes).
    Febrero tambien se trata como 30 dias (28 o 29 de febrero = dia 30).

    Args:
        start_date: Fecha de inicio
        end_date: Fecha de fin
        method_eu: Ignorado, se usa siempre metodo colombiano

    Returns:
        int: Numero de dias calculados con metodo 360
    """
    start_day = start_date.day
    end_day = end_date.day

    if start_day == 31 or (start_date.month == 2 and start_day >= 28):
        start_day = 30
    else:
        start_day = min(start_day, 30)

    if end_day == 31 or (end_date.month == 2 and end_day >= 28):
        end_day = 30
    else:
        end_day = min(end_day, 30)

    return (
        (end_date.year - start_date.year) * 360 +
        (end_date.month - start_date.month) * 30 +
        (end_day - start_day) + 1
    )

def round_1_decimal(value):
    """Redondea a 1 decimal usando ROUND_HALF_UP."""
    return float(Decimal(str(value)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def json_serial(obj):
    """Función auxiliar para serializar objetos de Odoo y tipos básicos.
    Compatible con Odoo 19 (usa display_name en lugar de name_get).
    """
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, '_name'):
        # Objeto de Odoo - usar display_name (Odoo 19 compatible)
        return {
            'id': getattr(obj, 'id', None),
            'name': getattr(obj, 'display_name', '') or getattr(obj, 'name', ''),
            'model': getattr(obj, '_name', '')
        }
    elif hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items()
                if not k.startswith('_') and not callable(v)}
    raise TypeError(f"Type {type(obj)} not serializable")

# ===============================================================================
# CLASE ACUMULADOR DE LÍNEAS
# ===============================================================================

class PayslipLineAccumulator:
    """Clase para acumular líneas de nómina de forma eficiente."""
    
    def __init__(self):
        self.lines = defaultdict(lambda: {
            'amount': 0,
            'quantity': 0,
            'rate': 100,
            'total': 0,
            'details': [],
            'metadata': {}
        })
    
    def add(self, code, amount=0, quantity=1, rate=100, total=None, detail=None, **metadata):
        """Agrega o acumula valores para un código de línea."""
        line = self.lines[code]
        line['rate'] = rate
        line['amount'] += amount
        line['quantity'] += quantity
        
        if total is None:
            total = amount * quantity * rate / 100.0
        line['total'] += total
        
        if detail:
            line['details'].append(detail)
        
        line['metadata'].update(metadata)
        return dict(line)
    
    def get(self, code):
        """Obtiene los valores acumulados para un código."""
        return dict(self.lines.get(code, {}))
    
    def get_all(self):
        """Obtiene todas las líneas acumuladas."""
        return dict(self.lines)

# ===============================================================================
# CONTEXTO DE CÁLCULO
# ===============================================================================

class PayslipCalculationContext:
    """Contexto de cálculo de nómina con datos optimizados."""
    
    def __init__(self, payslip):
        self.payslip = payslip
        self.employee = payslip.employee_id
        self.contract = payslip.contract_id
        self.company = payslip.company_id
        self._cache = {}
    
    @property
    def annual_parameters(self):
        """Obtiene parámetros anuales con cache."""
        if 'annual_parameters' not in self._cache:
            params = self.payslip.env['hr.annual.parameters'].search([
                ('year', '=', self.payslip.date_to.year)
            ], limit=1)
            if not params:
                raise ValidationError(
                    f'Faltan parámetros anuales para {self.payslip.date_to.year}'
                )
            self._cache['annual_parameters'] = params
        return self._cache['annual_parameters']
    
    @property
    def current_wage(self):
        """Obtiene el salario actual considerando cambios."""
        if 'current_wage' not in self._cache:
            wage = self.contract.wage
            wage_changes = self.payslip.env['hr.contract.change.wage'].search([
                ('contract_id', '=', self.contract.id),
                ('date_start', '<=', self.payslip.date_to)
            ], order='date_start desc', limit=1)
            
            if wage_changes and wage_changes.wage > 0:
                wage = wage_changes.wage
            
            self._cache['current_wage'] = wage
        return self._cache['current_wage']
    
    @property
    def days_in_period(self):
        """Calcula días en el período usando método 360."""
        if 'days_in_period' not in self._cache:
            self._cache['days_in_period'] = self.payslip.days_between(
                self.payslip.date_from, 
                self.payslip.date_to
            )
        return self._cache['days_in_period']

# ===============================================================================
# MODELO PRINCIPAL - HR.PAYSLIP
# ===============================================================================
class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'sequence.mixin']
    _description = 'Nómina de Empleado - Colombia'
    _sequence_index = 'sequence_prefix'
    _sequence_field = 'number'
    _sequence_fixed_regex = r'^(?P<prefix1>.*?)(?P<seq>\d*)(?P<suffix>\D*?)$'
    _order = 'date_from desc, number desc'

    # ==============================
    # CAMPOS DE SECUENCIA Y CONTROL
    # ==============================
    # NOTA: Los campos number, sequence_prefix, sequence_number y move_type
    # estan definidos en hr_payslip_number.py para centralizar la logica de secuenciacion.
    # NO duplicar aqui.

    # ==============================
    # CAMPOS DE PERIODO Y FECHAS
    # ==============================
    period_id = fields.Many2one(
        'hr.period', 
        string='Periodo de Nómina',
        domain="[('closed', '=', False)]",
        index=True
    )
    # v19: el core hr.payslip define date_from/date_to como computed con
    # precompute=True. Lavish los hace editables (compute=False). Hay que
    # forzar precompute=False explicitamente para evitar el warning:
    # "precompute attribute doesn't make any sense on non computed field"
    date_from = fields.Date(
        string='From',
        readonly=False,
        required=True,
        tracking=True,
        store=True,
        compute=False,
        precompute=False,
    )
    date_to = fields.Date(
        string='To',
        readonly=False,
        required=True,
        tracking=True,
        store=True,
        compute=False,
        precompute=False,
    )
    periodo = fields.Char('Periodo', compute="_compute_periodo", store=True)

    # Manejo avanzado de fechas reales
    is_real_date = fields.Boolean(
        string='Usar fechas reales para ausencias',
        help='Marque si las ausencias deben calcularse en un período diferente al de pago.',
        default=False
    )
    date_from_real = fields.Datetime(string='Fecha real ausencias desde')
    date_to_real = fields.Datetime(string='Fecha real ausencias hasta')

    use_manual_days = fields.Boolean(
        string='Usar días manuales',
        default=False,
        help='Activa esta opción para usar únicamente los días ingresados manualmente en lugar del cálculo automático'
    )
    manual_days = fields.Float(
        string='Días manuales',
        help='Días a considerar en el cálculo de la nómina. Este campo solo se usa cuando "Usar días manuales" está activado.'
    )

    # ==============================
    # CAMPOS DE TIPO Y PROCESO
    # ==============================
    # NOTA: move_type esta definido en hr_payslip_number.py

    struct_process = fields.Selection(
        related='struct_id.process', 
        string='Proceso', 
        store=True,
        index=True
    )

    # ==============================
    # CONFIGURACIÓN
    # ==============================
    use_natural_days = fields.Boolean(
        string='Usar días naturales',
        help='Si está activo, calcula con 365 días al año. Si no, usa 360 días (comercial)',
        default=False
    )
    enable_rule_overrides = fields.Boolean(
        string='Habilitar ajustes manuales',
        help='Permite modificar manualmente los valores de las reglas salariales',
        default=False
    )
    annual_severance_liquidation = fields.Boolean(
        string='Liquidación anual de cesantías',
        default=False
    )
    provisiones = fields.Boolean('Provisiones')

    # ==============================
    # CONTROL DE CÁLCULO
    # ==============================
    is_first_compute = fields.Boolean(default=True, copy=False)
    computation_status = fields.Selection(
        selection=COMPUTATION_STATUS_SELECTION,
        default='draft',
        string='Estado de Cálculo'
    )
    computation_log = fields.Text(string='Log de Cálculo')

    # ==============================
    # RIBBONS Y ALERTAS
    # ==============================
    warning_ribbon = fields.Char(compute='_compute_ribbon_messages')
    info_ribbon = fields.Char(compute='_compute_ribbon_messages')
    success_ribbon = fields.Char(compute='_compute_ribbon_messages')
    ribbon_color = fields.Selection(
        selection=RIBBON_COLOR_SELECTION,
        compute='_compute_ribbon_messages'
    )
    show_ribbon = fields.Boolean(compute='_compute_ribbon_messages')

    computation_notes = fields.Html(string='Notas de Cálculo')
    alerts = fields.Text(compute='_compute_alerts')
    has_alerts = fields.Boolean(compute='_compute_alerts')

    # ==============================
    # ENTIDADES DE SEGURIDAD SOCIAL
    # ==============================
    eps_entity_id = fields.Many2one(
        'hr.employee.entities', string='EPS',
        domain="[('types_entities', '=', 'eps')]",
        compute='_compute_social_entities', store=True
    )
    pension_entity_id = fields.Many2one(
        'hr.employee.entities', string='Fondo de Pensión',
        domain="[('types_entities', '=', 'pension')]",
        compute='_compute_social_entities', store=True
    )
    arl_entity_id = fields.Many2one(
        'hr.employee.entities', string='ARL',
        domain="[('types_entities', '=', 'arl')]",
        compute='_compute_social_entities', store=True
    )
    ccf_entity_id = fields.Many2one(
        'hr.employee.entities', string='Caja de Compensación',
        domain="[('types_entities', '=', 'ccf')]",
        compute='_compute_social_entities', store=True
    )

    # ==============================
    # CAMPOS RELACIONADOS
    # ==============================
    leave_ids = fields.One2many('hr.absence.days', 'payroll_id', string='Ausencias')
    leave_days_ids = fields.One2many('hr.leave.line', 'payslip_id', string='Detalle de Ausencia')
    payslip_day_ids = fields.One2many('hr.payslip.day', 'payslip_id', string='Días de Nómina')
    rule_override_ids = fields.One2many('hr.payslip.rule.override', 'payslip_id', string='Ajustes de Reglas')
    has_overrides = fields.Boolean(compute='_compute_has_overrides', store=True)

    # ==============================
    # CATEGORÍAS
    # ==============================
    earnings_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Devengos')
    deductions_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Deducciones')
    bases_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Bases')
    provisions_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Provisiones (conceptos)')
    outcome_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Totales')

    # ==============================
    # LIQUIDACIONES
    # ==============================
    pay_cesantias_in_payroll = fields.Boolean(
        string='¿Liquidar Intereses de cesantía periodo anterior en nómina?',
        default=False,
        help='Activa el pago de intereses de cesantías del año anterior en esta nómina. '
             'Solo aplica para empleados que trabajaron el año anterior completo.'
    )
    pay_primas_in_payroll = fields.Boolean(
        string='¿Liquidar Primas en nómina?',
        default=False,
        help='Activa el pago de prima de servicios en esta nómina. '
             'Calcula la prima proporcional al semestre trabajado.'
    )
    pay_vacations_in_payroll = fields.Boolean(
        string='¿Liquidar vacaciones en nómina?',
        default=False,
        help='Activa el pago de vacaciones en esta nómina. '
             'Calcula las vacaciones pendientes por disfrutar.'
    )
    pay_rest_days_in_liquidation = fields.Boolean(
        string='¿Pagar descansos dominicales?',
        default=True,
        help='Si está activo, paga los domingos (y sábados si no trabaja sábados) '
             'proporcionales a los días trabajados en la liquidación.'
    )

    # Porcentajes para pago en nómina (los días ya se calculan en days_to_pay_prima/cesantias)
    prima_percentage_to_pay = fields.Float(
        string='% Prima a pagar',
        digits=(16, 2),
        default=100.0,
        help='Porcentaje de la prima causada a pagar (100% = todo lo causado)'
    )
    cesantias_percentage_to_pay = fields.Float(
        string='% Cesantías a pagar',
        digits=(16, 2),
        default=100.0,
        help='Porcentaje de las cesantías (intereses) causadas a pagar (100% = todo lo causado)'
    )

    date_liquidacion = fields.Date('Fecha liquidación de contrato')
    date_prima = fields.Date('Fecha liquidación de prima')

    # ==============================
    # CESANTÍAS, PRIMA, VACACIONES
    # ==============================
    severance_payments_reverse = fields.Many2many('hr.history.cesantias')
    prima_run_reverse_id = fields.Many2one('hr.payslip.run')
    prima_payslip_reverse_id = fields.Many2one('hr.payslip')
    paid_vacation_ids = fields.One2many('hr.payslip.paid.vacation', 'slip_id')
    date_cesantias = fields.Date('Fecha liquidación de cesantías')
    date_vacaciones = fields.Date('Fecha liquidación de vacaciones')
    refund_date = fields.Date(string='Fecha reintegro')


    # Dias trabajados hasta fechas de liquidacion
    days_to_liquidacion = fields.Integer(
        string='Días hasta liquidación',
        compute='_compute_days_to_liquidacion',
        store=True,
        help='Días trabajados desde inicio de contrato hasta fecha de liquidación (método 360)'
    )
    days_to_prima = fields.Integer(
        string='Días hasta liquidación prima',
        compute='_compute_days_to_liquidacion',
        store=True,
        help='Días trabajados para cálculo de prima (método 360)'
    )
    days_to_cesantias = fields.Integer(
        string='Días hasta liquidación cesantías',
        compute='_compute_days_to_liquidacion',
        store=True,
        help='Días trabajados para cálculo de cesantías (método 360)'
    )
    days_to_vacaciones = fields.Integer(
        string='Días hasta liquidación vacaciones',
        compute='_compute_days_to_liquidacion',
        store=True,
        help='Días trabajados para cálculo de vacaciones (método 360)'
    )

    # Días finales a pagar (después de ajustes)
    days_to_pay_prima = fields.Float(
        string='Días a pagar prima',
        compute='_compute_proportional_days_to_pay',
        store=True,
        digits=(16, 2),
        help='Días proporcionales a pagar de prima: (días trabajados / 180) * 15 días por semestre'
    )
    days_to_pay_cesantias = fields.Float(
        string='Días a pagar cesantías',
        compute='_compute_proportional_days_to_pay',
        store=True,
        digits=(16, 2),
        help='Días proporcionales a pagar de cesantías: (días trabajados / 360) * 30 días por año'
    )
    interest_cesantias_percentage = fields.Float(
        string='% Intereses cesantías',
        compute='_compute_proportional_days_to_pay',
        store=True,
        digits=(16, 4),
        help='Porcentaje de intereses sobre cesantías: (días trabajados / 360) * 12% anual'
    )

    # Campos manuales para ajuste de vacaciones
    manual_vacation_days = fields.Float(
        string='Días de vacaciones (manual)',
        digits=(16, 2),
        help='Permite ingresar manualmente los días de vacaciones disponibles. Si se llena, este valor se usa en lugar del cálculo automático.'
    )
    use_manual_vacation_days = fields.Boolean(
        string='Usar días manuales (vacaciones)',
        default=False,
        help='Activar para usar el valor manual de días de vacaciones en lugar del cálculo automático'
    )
    include_holidays_in_vacation_settlement = fields.Boolean(
        string='Incluir festivos en liquidación de vacaciones',
        default=False,
        help='Si está activo, los días festivos del período se incluyen en la liquidación de vacaciones'
    )
    computed_vacation_days = fields.Float(
        string='Días de vacaciones calculados',
        compute='_compute_vacation_days_for_settlement',
        store=True,
        digits=(16, 2),
        help='Días de vacaciones calculados automáticamente o ingresados manualmente'
    )
    computed_date_vacaciones = fields.Date(
        string='Fecha vacaciones sugerida',
        compute='_compute_suggested_vacation_date',
        store=False,
        help='Fecha de corte de vacaciones calculada automáticamente basándose en los días manuales ingresados'
    )

    # ==============================
    # CAMPOS DIVERSOS
    # ==============================
    observation = fields.Text()
    definitive_plan = fields.Boolean()
    analytic_account_id = fields.Many2one('account.analytic.account')
    journal_struct_id = fields.Many2one('account.journal', domain="[('company_id', '=', company_id)]")
    extrahours_ids = fields.One2many('hr.overtime', 'payslip_run_id')
    novedades_ids = fields.One2many('hr.novelties.different.concepts', 'payslip_id')
    payslip_old_ids = fields.Many2many(
        'hr.payslip',
        'hr_payslip_rel',
        'current_payslip_id',
        'old_payslip_id',
        string='Nominas relacionadas'
    )
    worked_days_line_ids = fields.One2many(
        'hr.payslip.worked_days',
        'payslip_id',
        string='Días Trabajados',
        compute=False
    )

    # ==============================
    # RESULTADOS Y TOTALES
    # ==============================
    payslip_detail = fields.Html(compute='_compute_payslip_detail')
    prestaciones_sociales_report = fields.Html(
        string="Reporte de Prestaciones Sociales",
        compute='_compute_prestaciones_sociales_report'
    )
    resulados_op = fields.Html()
    resulados_rt = fields.Html()
    ret_line_ids = fields.One2many('lavish.retencion.reporte', 'payslip_id')
    histori_vacation_ids = fields.One2many('hr.vacation', 'payslip')
    not_line_ids = fields.One2many('hr.payslip.not.line', 'slip_id')
    reversed_slip_id = fields.Many2one('hr.payslip')

    total_earnings = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))
    total_deductions = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))
    total_provisions = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))
    net_amount = fields.Float(compute='_compute_totals', store=True, digits=(16, 2))

    # Campos adicionales para vista de liquidacion
    social_security_ids = fields.One2many('hr.payslip.line', compute="_compute_concepts_category", string='Seguridad Social')
    total_seguridad_social = fields.Float(compute='_compute_liquidation_totals', store=True, digits=(16, 2), string='Total Seguridad Social')
    total_devengos = fields.Float(compute='_compute_liquidation_totals', store=True, digits=(16, 2), string='Total Devengos')
    total_deducciones = fields.Float(compute='_compute_liquidation_totals', store=True, digits=(16, 2), string='Total Deducciones')
    count_earnings = fields.Integer(compute='_compute_liquidation_totals', store=True, string='Cantidad Devengos')
    count_deductions = fields.Integer(compute='_compute_liquidation_totals', store=True, string='Cantidad Deducciones')

    salary_efficiency = fields.Float(compute='_compute_salary_efficiency')
    days_worked_count = fields.Integer(compute='_compute_days_summary', store=True)
    days_absence_count = fields.Integer(compute='_compute_days_summary', store=True)
    absence_percentage = fields.Float(compute='_compute_days_summary', store=True)
    reason_retiro = fields.Many2one('hr.departure.reason', string='Motivo de retiro')
    has_prestaciones = fields.Boolean(compute='_compute_has_prestaciones_retencion', store=True)
    has_retencion = fields.Boolean(compute='_compute_has_prestaciones_retencion', store=True)
    have_compensation = fields.Boolean('Indemnización', default=False)
    settle_payroll_concepts = fields.Boolean('Liquida conceptos de nómina', default=True)
    novelties_payroll_concepts = fields.Boolean('Liquida conceptos de novedades', default=True)
    pagar_cesantias_ano_anterior = fields.Boolean('Liquida conceptos de Cesantia periodo anterior', default=True)
    no_days_worked = fields.Boolean('Sin días laborados', default=False, help='Aplica unicamente cuando la fecha de inicio es igual a la fecha de finalización.')

    # Campos de opciones avanzadas
    is_advance_severance = fields.Boolean(string='Es avance de cesantías')
    value_advance_severance = fields.Float(string='Valor a pagar avance')
    employee_severance_pay = fields.Boolean(string='Pago cesantías al empleado')
    partner_computed_id = fields.Many2one('res.partner', compute='_compute_partner_computed', store=True)
    process_settlement_loans = fields.Boolean(default=True)
    worked_hours = fields.Float(
        string='Horas trabajadas',
        compute='_compute_worked_hours',
        store=True
    )
    warning_ribbon = fields.Char(
        string='Warning Message',
        compute='_compute_ribbon_messages',
        store=False
    )
    info_ribbon = fields.Char(
        string='Info Message',
        compute='_compute_ribbon_messages',
        store=False
    )
    success_ribbon = fields.Char(
        string='Success Message',
        compute='_compute_ribbon_messages',
        store=False
    )
    resultados_op = fields.Html(string='Resultados Operativos')
    resultados_rt = fields.Html(string='Resultados Retención')
    loan_installment_ids = fields.One2many('hr.loan.installment', 'payslip_id', string='Prestamos')
    process_loans = fields.Boolean(string='Procesar Préstamos', default=True)
    double_installment = fields.Boolean(string='Procesar Doble Cuota', help='Permite procesar dos cuotas en este período')
    process_settlement_loans = fields.Boolean(
        string='Descontar Préstamos en Liquidación',
        help='Permite descontar los saldos de préstamos marcados para liquidación'
    )

    @api.depends('line_ids.category_id.code', 'provisions_ids', 'ret_line_ids')
    def _compute_has_prestaciones_retencion(self):
        """Calcula si la nómina tiene prestaciones o retención."""
        for record in self:
            prestaciones_codes = ['PRESTACIONES_SOCIALES', 'PRIMA', 'CESANTIAS', 'INTERESES_CESANTIAS']
            has_prestaciones = any(
                line.category_id.code in prestaciones_codes 
                for line in record.line_ids
            ) or bool(record.provisions_ids)
            
            has_retencion = bool(record.ret_line_ids) or any(
                line.salary_rule_id.code == 'RETENCION' 
                for line in record.line_ids
            )
            
            record.has_prestaciones = has_prestaciones
            record.has_retencion = has_retencion

    @api.depends('employee_id')
    def _compute_partner_computed(self):
        """Calcula el tercero para conceptos según el empleado."""
        for record in self:
            employee = record.employee_id
            if not employee:
                record.partner_computed_id = False
                continue

            # Odoo 19: hr.employee no tiene address_home_id. Usar work_contact_id o el partner del usuario.
            record.partner_computed_id = employee.work_contact_id or employee.user_id.partner_id or False

    @api.depends('contract_id', 'date_liquidacion', 'date_prima', 'date_cesantias', 'date_vacaciones')
    def _compute_days_to_liquidacion(self):
        """
        Calcular días por liquidar desde fechas de corte hasta fecha de liquidación.

        Los días se calculan DESDE cada fecha de corte HASTA la fecha de liquidación.
        Esto representa cuántos días del período se están liquidando.
        """
        for record in self:
            if record.contract_id and record.date_liquidacion:
                # Días por liquidar de prima (desde fecha corte prima hasta liquidación)
                if record.date_prima:
                    if hasattr(record.contract_id, 'dias360'):
                        record.days_to_prima = record.contract_id.dias360(record.date_prima, record.date_liquidacion)
                    else:
                        delta = record.date_liquidacion - record.date_prima
                        record.days_to_prima = delta.days + 1
                else:
                    record.days_to_prima = 0

                # Días por liquidar de cesantías (desde fecha corte cesantías hasta liquidación)
                if record.date_cesantias:
                    if hasattr(record.contract_id, 'dias360'):
                        record.days_to_cesantias = record.contract_id.dias360(record.date_cesantias, record.date_liquidacion)
                    else:
                        delta = record.date_liquidacion - record.date_cesantias
                        record.days_to_cesantias = delta.days + 1
                else:
                    record.days_to_cesantias = 0

                # Días por liquidar de vacaciones (desde fecha corte vacaciones hasta liquidación)
                if record.date_vacaciones:
                    if hasattr(record.contract_id, 'dias360'):
                        record.days_to_vacaciones = record.contract_id.dias360(record.date_vacaciones, record.date_liquidacion)
                    else:
                        delta = record.date_liquidacion - record.date_vacaciones
                        record.days_to_vacaciones = delta.days + 1
                else:
                    record.days_to_vacaciones = 0

                # Días totales desde inicio de contrato hasta liquidación
                if record.contract_id.date_start:
                    if hasattr(record.contract_id, 'dias360'):
                        record.days_to_liquidacion = record.contract_id.dias360(record.contract_id.date_start, record.date_liquidacion)
                    else:
                        delta = record.date_liquidacion - record.contract_id.date_start
                        record.days_to_liquidacion = delta.days + 1
                else:
                    record.days_to_liquidacion = 0
            else:
                record.days_to_liquidacion = 0
                record.days_to_prima = 0
                record.days_to_cesantias = 0
                record.days_to_vacaciones = 0

    @api.depends('days_to_prima', 'days_to_cesantias')
    def _compute_proportional_days_to_pay(self):
        """
        Calcular días proporcionales a pagar según legislación colombiana.

        Fórmulas:
        - Prima: (días trabajados / 180 días semestre) * 15 días = días a pagar
        - Cesantías: (días trabajados / 360 días año) * 30 días = días a pagar
        - Intereses cesantías: (días trabajados / 360) * 12% anual = % a pagar

        Ejemplos:
        - 180 días prima: (180/180) * 15 = 15 días
        - 360 días cesantías: (360/360) * 30 = 30 días
        - 180 días intereses: (180/360) * 12% = 6%
        """
        for record in self:
            # Prima: 15 días por semestre (180 días)
            if record.days_to_prima > 0:
                record.days_to_pay_prima = round((record.days_to_prima / 180.0) * 15.0, 2)
            else:
                record.days_to_pay_prima = 0.0

            # Cesantías: 30 días por año (360 días)
            if record.days_to_cesantias > 0:
                record.days_to_pay_cesantias = round((record.days_to_cesantias / 360.0) * 30.0, 2)
                # Intereses: 12% anual proporcional
                record.interest_cesantias_percentage = round((record.days_to_cesantias / 360.0) * 0.12, 4)
            else:
                record.days_to_pay_cesantias = 0.0
                record.interest_cesantias_percentage = 0.0

    @api.depends('contract_id', 'date_liquidacion', 'date_to', 'date_vacaciones', 'manual_vacation_days', 'use_manual_vacation_days', 'include_holidays_in_vacation_settlement')
    def _compute_vacation_days_for_settlement(self):
        """
        Calcular días de vacaciones pendientes por disfrutar para liquidación.

        Flujo:
        1. Si use_manual_vacation_days está activo, usa el valor manual
        2. Si no, calcula días pendientes usando calculate_remaining_days del contrato
        3. La fecha de cálculo es: date_liquidacion > date_to > hoy
        4. Si include_holidays_in_vacation_settlement está activo, se incluyen festivos
        """
        for record in self:
            if record.use_manual_vacation_days and record.manual_vacation_days is not None:
                # Usar valor manual
                record.computed_vacation_days = record.manual_vacation_days
            elif record.contract_id and hasattr(record.contract_id, 'calculate_remaining_days'):
                # Determinar fecha de cálculo: prioridad date_liquidacion > date_to > hoy
                date_calc = record.date_liquidacion or record.date_to or fields.Date.today()

                # Temporalmente ajustar retirement_date del contrato para el cálculo
                original_retirement = record.contract_id.retirement_date
                try:
                    # Establecer fecha de retiro temporal para cálculo
                    record.contract_id.retirement_date = date_calc

                    # Calcular días pendientes (esto ya considera vacaciones causadas vs consumidas)
                    remaining_days = record.contract_id.calculate_remaining_days(
                        ignore_payslip_id=record.id if record.id else None
                    )

                    record.computed_vacation_days = round(remaining_days, 2)
                finally:
                    # Restaurar fecha de retiro original
                    record.contract_id.retirement_date = original_retirement
            else:
                record.computed_vacation_days = 0.0

    @api.onchange('use_manual_vacation_days')
    def _onchange_use_manual_vacation_days(self):
        """
        Al activar/desactivar el uso de días manuales, copiar el valor calculado
        al campo manual para facilitar ajustes.
        """
        if self.use_manual_vacation_days and not self.manual_vacation_days:
            # Si se activa y no hay valor manual, copiar el calculado
            if self.contract_id and hasattr(self.contract_id, 'calculate_remaining_days'):
                date_calc = self.date_liquidacion or self.date_to or fields.Date.today()

                # Temporalmente ajustar retirement_date para cálculo
                original_retirement = self.contract_id.retirement_date
                try:
                    self.contract_id.retirement_date = date_calc
                    remaining_days = self.contract_id.calculate_remaining_days(
                        ignore_payslip_id=self.id if self.id else None
                    )
                    self.manual_vacation_days = round(remaining_days, 2)
                finally:
                    self.contract_id.retirement_date = original_retirement

    @api.depends('use_manual_vacation_days', 'manual_vacation_days', 'date_liquidacion', 'computed_vacation_days')
    def _compute_suggested_vacation_date(self):
        """
        Calcular fecha de corte de vacaciones sugerida basándose en los días manuales.

        Si el usuario ingresa manualmente días de vacaciones, este campo muestra
        qué fecha de corte correspondería a esos días.

        Ejemplo: Si ingresa 2 días y la fecha de liquidación es 20-11-2025,
        la fecha sugerida sería aproximadamente 18-11-2025 (retrocediendo 2 días).
        """
        for record in self:
            if record.use_manual_vacation_days and record.manual_vacation_days and record.date_liquidacion:
                # Calcular fecha retrocediendo los días manuales desde la fecha de liquidación
                days_to_subtract = int(record.manual_vacation_days)

                # Usar método 360 si está disponible
                if record.contract_id and hasattr(record.contract_id, 'add_days360'):
                    # add_days360 con valor negativo retrocede en el tiempo
                    record.computed_date_vacaciones = record.contract_id.add_days360(
                        record.date_liquidacion,
                        -days_to_subtract
                    )
                else:
                    # Aproximación usando días naturales
                    from datetime import timedelta
                    record.computed_date_vacaciones = record.date_liquidacion - timedelta(days=days_to_subtract)
            else:
                record.computed_date_vacaciones = False

    @api.onchange('manual_vacation_days')
    def _onchange_manual_vacation_days(self):
        """
        Al cambiar los días manuales de vacaciones, ajustar automáticamente
        la fecha de corte de vacaciones para que coincida con esos días.

        FÓRMULA LEGAL: días_vacaciones = (15/360) × días_trabajados
        INVERSA: días_trabajados = días_vacaciones × 24
        """
        if self.use_manual_vacation_days and self.manual_vacation_days and self.date_liquidacion:
            # Fórmula: días_trabajados = días_vacaciones × 24
            # (porque 360 días trabajados generan 15 días de vacaciones: 360/15 = 24)
            days_trabajados = self.manual_vacation_days * 24

            # Convertir días trabajados a meses y días (método 360: 1 mes = 30 días)
            meses = int(days_trabajados // 30)
            dias_restantes = int(days_trabajados % 30)

            # Calcular fecha desde hacia atrás
            from dateutil.relativedelta import relativedelta
            suggested_date = self.date_liquidacion
            if meses > 0:
                suggested_date = suggested_date - relativedelta(months=meses)
            if dias_restantes > 0:
                suggested_date = suggested_date - relativedelta(days=dias_restantes)

            # Actualizar la fecha de vacaciones automáticamente
            self.date_vacaciones = suggested_date

    # ===============================================================================
    # MÉTODOS DE RIBBON Y ALERTAS
    # ===============================================================================
    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.is_paid')
    def _compute_worked_hours(self):
        for payslip in self:
            payslip.sum_worked_hours = sum([line.number_of_hours for line in payslip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')])
            
    @api.depends('state', 'computation_status', 'has_overrides', 'line_ids', 'period_id')
    def _compute_ribbon_messages(self):
        """Calcula mensajes para mostrar en el ribbon de la vista."""
        for record in self:
            record.warning_ribbon = False
            record.info_ribbon = False
            record.success_ribbon = False
            record.show_ribbon = False
            record.ribbon_color = False
            
            # Verificar estado de cálculo
            if record.state == 'draft' and record.computation_status == 'error':
                record.warning_ribbon = "Error en el último cálculo. Revise el log de errores."
                record.ribbon_color = 'danger'
                record.show_ribbon = True
            
            # Verificar ajustes manuales
            elif record.has_overrides and record.state not in ['done', 'paid']:
                record.info_ribbon = "Esta nómina tiene ajustes manuales aplicados"
                record.ribbon_color = 'info'
                record.show_ribbon = True
            
            # Verificar período
            elif not record.period_id and record.state in ['verify', 'done']:
                record.warning_ribbon = "Nómina sin período asignado"
                record.ribbon_color = 'warning'
                record.show_ribbon = True
            
            # Verificar nómina calculada exitosamente
            elif record.computation_status == 'computed' and record.state in ('draft', 'validated'):
                record.success_ribbon = "Nómina calculada exitosamente"
                record.ribbon_color = 'success'
                record.show_ribbon = True
            
            # Advertencia de fechas futuras
            elif record.date_to and record.date_to > fields.Date.today():
                days_future = (record.date_to - fields.Date.today()).days
                record.info_ribbon = f"Esta nómina es para {days_future} días en el futuro"
                record.ribbon_color = 'info'
                record.show_ribbon = True
    
    @api.depends('line_ids', 'leave_ids', 'contract_id', 'employee_id')
    def _compute_alerts(self):
        """Calcula alertas y advertencias para la nómina."""
        for record in self:
            alerts = []
            
            # Verificar entidades de seguridad social
            if not record.eps_entity_id:
                alerts.append("• No tiene EPS asignada")
            if not record.pension_entity_id:
                alerts.append("• No tiene fondo de pensión asignado")
            if not record.arl_entity_id:
                alerts.append("• No tiene ARL asignada")
            
            # Verificar salario mínimo
            if record.contract_id and record.contract_id.wage and record.date_to:
                annual_params = self.env['hr.annual.parameters'].search([
                    ('year', '=', record.date_to.year)
                ], limit=1)
                if annual_params and record.contract_id.wage < annual_params.smmlv_monthly:
                    alerts.append("• El salario está por debajo del mínimo legal vigente")
            
            # Verificar ausencias sin pagar
            unpaid_leaves = record.leave_ids.filtered(
                lambda l: l.leave_id.holiday_status_id.unpaid_absences
            )
            if unpaid_leaves:
                total_days = sum(l.days_used for l in unpaid_leaves)
                alerts.append(f"• Tiene {total_days} días de ausencias no remuneradas")
            
            # Verificar conceptos con valores negativos
            negative_lines = record.line_ids.filtered(
                lambda l: l.total < 0
                and l.category_id
                and l.category_id.code not in ['DED', 'DEDUCCIONES', 'SSOCIAL']
                and l.category_id.category_type != 'totals'
            )
            if negative_lines:
                alerts.append("• Hay conceptos de devengos con valores negativos")
            
            # Verificar días trabajados
            if record.days_worked_count == 0 and record.state != 'draft':
                alerts.append("• No hay días trabajados registrados")
            
            # Asignar resultados
            record.alerts = '\n'.join(alerts) if alerts else False
            record.has_alerts = bool(alerts)

    @api.depends('alerts', 'has_alerts', 'computation_status', 'line_ids')
    def _compute_warning_message(self):
        """Computa mensaje de advertencia para mostrar en la vista."""
        for record in self:
            warning_msgs = []
            
            # Si hay alertas, incluirlas
            if record.has_alerts and record.alerts:
                warning_msgs.append(record.alerts)
            
            # Si hay errores de cálculo
            if record.computation_status == 'error':
                warning_msgs.append('Error en el cálculo de la nómina')
            
            # Si no hay líneas de nómina calculadas
            if not record.line_ids and record.state not in ['draft', 'cancel']:
                warning_msgs.append('No se han calculado conceptos de nómina')
            
            record.warning_message = '\n'.join(warning_msgs) if warning_msgs else False
    
    # ===============================================================================
    # METODOS DE INICIALIZACION Y CONFIGURACION
    # ===============================================================================
    # NOTA: El metodo init() para indices de secuenciacion esta en hr_payslip_number.py

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para manejar secuencias y validaciones."""
        for vals in vals_list:
            if vals.get('number', '/') == '/':
                vals['number'] = '/'
            
            # Agregar nota de creación
            if 'computation_notes' not in vals:
                vals['computation_notes'] = f"""
                <div class="alert alert-info">
                    <strong>Nómina creada:</strong> {fields.Datetime.now()}<br/>
                    <strong>Usuario:</strong> {self.env.user.name}
                </div>
                """
        
        return super().create(vals_list)
    
    def write(self, vals):
        """Override write para agregar validaciones y notas."""
        # Agregar nota de modificación si se cambian campos importantes
        important_fields = ['date_from', 'date_to', 'struct_id', 'contract_id', 'enable_rule_overrides']
        if any(field in vals for field in important_fields):
            for record in self:
                current_notes = record.computation_notes or ""
                new_note = f"""
                <div class="alert alert-warning mt-2">
                    <strong>Modificación:</strong> {fields.Datetime.now()}<br/>
                    <strong>Usuario:</strong> {self.env.user.name}<br/>
                    <strong>Campos modificados:</strong> {', '.join([f for f in important_fields if f in vals])}
                </div>
                """
                vals['computation_notes'] = current_notes + new_note
        
        return super().write(vals)
    
    # ===============================================================================
    # CAMPOS COMPUTADOS
    # ===============================================================================
    
    @api.depends('date_to')
    def _compute_periodo(self):
        """Calcula el período en formato YYYYMM."""
        for rec in self:
            if rec.date_to:
                rec.periodo = rec.date_to.strftime("%Y%m")
            else:
                rec.periodo = ''
    
    # NOTA: _compute_sequence_prefix y _compute_move_type estan definidos
    # en hr_payslip_number.py para centralizar la logica de secuenciacion.
    # NO duplicar aqui.

    @api.depends('employee_id', 'state')
    def _compute_social_entities(self):
        """Calcula las entidades de seguridad social del empleado."""
        for payslip in self:
            entities = payslip.employee_id.social_security_entities
            
            # Resetear valores
            payslip.eps_entity_id = False
            payslip.pension_entity_id = False
            payslip.arl_entity_id = False
            payslip.ccf_entity_id = False
            
            for entity in entities:
                if entity.contrib_id and entity.contrib_id.type_entities:
                    entity_type = entity.contrib_id.type_entities

                    if entity.partner_id:
                        partner_id = entity.partner_id.id
                    else:
                        continue
                    
                    if entity_type == 'eps':
                        payslip.eps_entity_id = partner_id
                    elif entity_type == 'pension':
                        payslip.pension_entity_id = partner_id
                    elif entity_type == 'riesgo':  
                        payslip.arl_entity_id = partner_id
                    elif entity_type in ['caja', 'ccf']: 
                        payslip.ccf_entity_id = partner_id
                    
    @api.depends('rule_override_ids.active')
    def _compute_has_overrides(self):
        """Verifica si tiene ajustes manuales activos."""
        for record in self:
            record.has_overrides = bool(record.rule_override_ids.filtered('active'))

    @api.depends('line_ids', 'line_ids.total', 'line_ids.category_id')
    def _compute_concepts_category(self):
        """Categoriza las lineas de nomina de forma optimizada."""
        PayslipLine = self.env['hr.payslip.line']
        empty_lines = PayslipLine

        for payslip in self:
            # Inicializar todos los campos con recordsets vacios
            earnings = empty_lines
            deductions = empty_lines
            social_security = empty_lines
            provisions = empty_lines
            bases = empty_lines
            outcome = empty_lines

            # Categorizar lineas
            for line in payslip.line_ids:
                cat_code = line.category_id.code or ''
                parent_code = line.category_id.parent_id.code if line.category_id.parent_id else ''

                if cat_code in CATEGORY_MAPPINGS.get('EARNINGS', []) or parent_code in CATEGORY_MAPPINGS.get('EARNINGS', []):
                    earnings |= line
                elif cat_code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []) or parent_code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []):
                    social_security |= line
                elif cat_code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []) or parent_code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []):
                    deductions |= line
                elif cat_code in CATEGORY_MAPPINGS.get('PROVISIONS', []) or parent_code in CATEGORY_MAPPINGS.get('PROVISIONS', []):
                    provisions |= line
                elif cat_code in CATEGORY_MAPPINGS.get('OUTCOME', []) or parent_code in CATEGORY_MAPPINGS.get('OUTCOME', []):
                    outcome |= line
                else:
                    bases |= line

            # Asignar todos los campos - SIEMPRE asignar todos
            payslip.earnings_ids = earnings
            payslip.deductions_ids = deductions
            payslip.social_security_ids = social_security
            payslip.provisions_ids = provisions
            payslip.bases_ids = bases
            payslip.outcome_ids = outcome

    @api.depends('line_ids', 'line_ids.total', 'line_ids.category_id')
    def _compute_totals(self):
        """Calcula los totales por categoría."""
        for payslip in self:
            earnings = sum(line.total for line in payslip.line_ids.filtered(lambda l: l.category_id.code not in ['TOTALDEV', ]))
            deductions = sum(line.total for line in payslip.line_ids.filtered(lambda l: l.category_id.code not in ['TOTALDED',]))
            provisions = sum(line.total for line in payslip.line_ids.filtered(lambda l: l.category_id.code not in ['PROV','TOTALPROV','PROVISIONES']))
            net = sum(line.total for line in payslip.line_ids.filtered(lambda l: l.category_id.code not in ['NET', ]))
            payslip.total_earnings = earnings
            payslip.total_deductions = abs(deductions)  # Mostrar valor absoluto
            payslip.total_provisions = provisions
            payslip.net_amount = net

    @api.depends('total_earnings', 'total_deductions')
    def _compute_salary_efficiency(self):
        for payslip in self:
            if payslip.total_earnings > 0:
                net_amount = payslip.total_earnings - payslip.total_deductions
                payslip.salary_efficiency = (net_amount / payslip.total_earnings) * 100
            else:
                payslip.salary_efficiency = 0.0

    @api.depends('line_ids', 'line_ids.total', 'line_ids.category_id')
    def _compute_liquidation_totals(self):
        """Calcula totales para la vista de liquidacion."""
        for payslip in self:
            # Contadores
            earnings_lines = payslip.line_ids.filtered(
                lambda l: l.category_id.code in CATEGORY_MAPPINGS.get('EARNINGS', []) or
                (l.category_id.parent_id and l.category_id.parent_id.code in CATEGORY_MAPPINGS.get('EARNINGS', []))
            )
            deductions_lines = payslip.line_ids.filtered(
                lambda l: l.category_id.code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []) or
                (l.category_id.parent_id and l.category_id.parent_id.code in CATEGORY_MAPPINGS.get('DEDUCTIONS', []))
            )
            ss_lines = payslip.line_ids.filtered(
                lambda l: l.category_id.code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []) or
                (l.category_id.parent_id and l.category_id.parent_id.code in CATEGORY_MAPPINGS.get('SOCIAL_SECURITY', []))
            )

            payslip.count_earnings = len(earnings_lines.filtered(lambda l: l.total != 0))
            payslip.count_deductions = len(deductions_lines.filtered(lambda l: l.total != 0))

            # Totales - buscar lineas TOTALDEV y TOTALDED
            total_dev_line = payslip.line_ids.filtered(lambda l: l.category_id.code == 'TOTALDEV')
            total_ded_line = payslip.line_ids.filtered(lambda l: l.category_id.code == 'TOTALDED')

            payslip.total_devengos = sum(total_dev_line.mapped('total')) if total_dev_line else sum(
                l.total for l in earnings_lines if l.total > 0
            )
            payslip.total_deducciones = abs(sum(total_ded_line.mapped('total'))) if total_ded_line else abs(sum(
                l.total for l in deductions_lines
            ))
            payslip.total_seguridad_social = abs(sum(l.total for l in ss_lines))

    @api.depends('payslip_day_ids', 'payslip_day_ids.day_type')
    def _compute_days_summary(self):
        """Calcula resumen de días trabajados y ausencias."""
        for payslip in self:
            if payslip.payslip_day_ids:
                worked_days = len(payslip.payslip_day_ids.filtered(lambda d: d.day_type == 'W'))
                absence_days = len(payslip.payslip_day_ids.filtered(lambda d: d.day_type == 'A'))
                total_days = len(payslip.payslip_day_ids)
                
                payslip.days_worked_count = worked_days
                payslip.days_absence_count = absence_days
                payslip.absence_percentage = (absence_days / total_days * 100) if total_days > 0 else 0
            else:
                payslip.days_worked_count = 0
                payslip.days_absence_count = 0
                payslip.absence_percentage = 0

    # NOTA: _compute_split_sequence esta definido en hr_payslip_number.py

    @api.depends('line_ids', 'leave_ids', 'worked_days_line_ids')
    def _compute_payslip_detail(self):
        """Calcula el detalle de la nómina con información mejorada."""
        for payslip in self:
            detail_html = f"""
            <div class="payslip-detail-container">
                <h3>Resumen de Nómina</h3>
                <div class="row">
                    <div class="col-md-6">
                        <strong>Empleado:</strong> {payslip.employee_id.name}<br/>
                        <strong>Período:</strong> {payslip.date_from} - {payslip.date_to}<br/>
                        <strong>Tipo:</strong> {dict(payslip._fields['move_type'].selection).get(payslip.move_type, '')}
                    </div>
                    <div class="col-md-6">
                        <strong>Total Devengos:</strong> ${payslip.total_earnings:,.2f}<br/>
                        <strong>Total Deducciones:</strong> ${payslip.total_deductions:,.2f}<br/>
                        <strong>Neto a Pagar:</strong> ${payslip.net_amount:,.2f}
                    </div>
                </div>
            </div>
            """
            payslip.payslip_detail = detail_html
