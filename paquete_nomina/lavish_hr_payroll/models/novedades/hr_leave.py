from odoo import api, fields, models, SUPERUSER_ID, tools, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare
from odoo.fields import Domain as expression
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from datetime import datetime, time, timedelta, date
from pytz import UTC
from odoo.fields import Domain
AND = Domain.AND
from odoo.tools import format_date
from operator import itemgetter
import pytz
UTC = pytz.UTC

from odoo.addons.lavish_hr_employee.models.payroll.hr_payslip_constants import days360
STATE = [
    ('draft', 'Borrador'),
    ('validated', 'Validada'),
    ('paid', 'Pagada')
]

import logging
HOURS_PER_DAY = 8
import logging
_logger = logging.getLogger(__name__)
import calendar
from collections import namedtuple
_nt_holiday_stock = namedtuple("Holiday", ["day", "days_to_sum", "celebration"])

EASTER_WEEK_HOLIDAYS = [
    _nt_holiday_stock(day=-3, days_to_sum=None, celebration="Jueves Santo"),
    _nt_holiday_stock(day=-2, days_to_sum=None, celebration="Viernes Santo"),
    _nt_holiday_stock(day=39, days_to_sum=calendar.MONDAY, celebration="Ascensión del Señor"),
    _nt_holiday_stock(day=60, days_to_sum=calendar.MONDAY, celebration="Corphus Christi"),
    _nt_holiday_stock(day=68, days_to_sum=calendar.MONDAY, celebration="Sagrado Corazón de Jesús")
]

HOLIDAYS = [
    _nt_holiday_stock(day="01-01", days_to_sum=None, celebration="Año Nuevo"),
    _nt_holiday_stock(day="05-01", days_to_sum=None, celebration="Día del Trabajo"),
    _nt_holiday_stock(day="07-20", days_to_sum=None, celebration="Día de la Independencia"),
    _nt_holiday_stock(day="08-07", days_to_sum=None, celebration="Batalla de Boyacá"),
    _nt_holiday_stock(day="12-08", days_to_sum=None, celebration="Día de la Inmaculada Concepción"),
    _nt_holiday_stock(day="12-25", days_to_sum=None, celebration="Día de Navidad"),
    _nt_holiday_stock(day="01-06", days_to_sum=calendar.MONDAY, celebration="Día de los Reyes Magos"),
    _nt_holiday_stock(day="03-19", days_to_sum=calendar.MONDAY, celebration="Día de San José"),
    _nt_holiday_stock(day="06-29", days_to_sum=calendar.MONDAY, celebration="San Pedro y San Pablo"),
    _nt_holiday_stock(day="08-15", days_to_sum=calendar.MONDAY, celebration="La Asunción de la Virgen"),
    _nt_holiday_stock(day="10-12", days_to_sum=calendar.MONDAY, celebration="Día de la Raza"),
    _nt_holiday_stock(day="11-01", days_to_sum=calendar.MONDAY, celebration="Todos los Santos"),
    _nt_holiday_stock(day="11-11", days_to_sum=calendar.MONDAY, celebration="Independencia de Cartagena")
]

# Diccionario de tipos de novedades PILA con sus caracteristicas
# Usado para determinar comportamiento segun tipo de ausencia
NOVELTY_TYPES = {
    'sln': {
        'name': 'Suspension temporal del contrato',
        'descuenta_ss': True,
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio_transporte': False,
    },
    'ige': {
        'name': 'Incapacidad EPS',
        'descuenta_ss': False,  # IBC se mantiene
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
        'tramos': True,  # Tiene tramos de porcentaje
    },
    'irl': {
        'name': 'Incapacidad por accidente de trabajo o enfermedad laboral',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
        'tramos': True,
    },
    'lma': {
        'name': 'Licencia de Maternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
    },
    'lpa': {
        'name': 'Licencia de Paternidad',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
    },
    'vco': {
        'name': 'Vacaciones Compensadas (Dinero)',
        'descuenta_ss': False,
        'descuenta_trabajo': False,  # No resta dias trabajados
        'paga_salario': True,
        'paga_auxilio_transporte': False,
    },
    'vdi': {
        'name': 'Vacaciones Disfrutadas',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
    },
    'vre': {
        'name': 'Vacaciones por Retiro',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': False,
    },
    'lr': {
        'name': 'Licencia remunerada',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': True,  # Segun configuracion
    },
    'lnr': {
        'name': 'Licencia no Remunerada',
        'descuenta_ss': True,
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio_transporte': False,
    },
    'lt': {
        'name': 'Licencia de Luto',
        'descuenta_ss': False,
        'descuenta_trabajo': True,
        'paga_salario': True,
        'paga_auxilio_transporte': True,
    },
    'p': {
        'name': 'Permisos no remunerados D/H',
        'descuenta_ss': True,
        'descuenta_trabajo': True,
        'paga_salario': False,
        'paga_auxilio_transporte': False,
        'no_pila': True,  # No se reporta en PILA
    },
}

def get_novelty_config(novelty_code):
    """
    Obtiene la configuracion de una novedad segun su codigo PILA.

    Args:
        novelty_code: Codigo de la novedad (sln, ige, irl, lma, lpa, vco, vdi, vre, lr, lnr, lt, p)

    Returns:
        dict con la configuracion de la novedad, o None si no existe
    """
    return NOVELTY_TYPES.get(novelty_code)

def next_weekday(d, weekday):
    """ https://stackoverflow.com/a/6558571 """
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0: # Target day already happened this week
        days_ahead += 7
    return d + timedelta(days_ahead)

def calc_easter(year):
    """ Returns Easter as a date object.

    upstream: http://code.activestate.com/recipes/576517-calculate-easter-western-given-a-year/

    :type year: integer

    :raises:
    :rtype: ValueError if year is not integer
    """
    year = int(year)
    a = year % 19
    b = year // 100
    c = year % 100
    d = (19 * a + b - b // 4 - ((b - (b + 8) // 25 + 1) // 3) + 15) % 30
    e = (32 + 2 * (b % 4) + 2 * (c // 4) - d - (c % 4)) % 7
    f = d + e - 7 * ((a + 11 * d + 22 * e) // 451) + 114
    month = f // 31
    day = f % 31 + 1
    return date(year, month, day)

def get_colombia_holidays_by_year(year):
    try:
        year = int(year)
    except ValueError:
        raise TypeError("El año debe ser un entero")

    if year < 1970 or year > 99999:
        raise ValueError("El año debe ser mayor a 1969 y menor a 100000")

    nt_holiday = namedtuple("Holiday", ["date", "celebration"])
    normal_holidays = []
    for holiday in HOLIDAYS:
        holiday_date = datetime.strptime("%s-%d" % (holiday.day, year), "%m-%d-%Y").date()
        if holiday.days_to_sum is not None and holiday_date.weekday() != holiday.days_to_sum:
            holiday_date = next_weekday(holiday_date, holiday.days_to_sum)
        normal_holidays.append(nt_holiday(date=holiday_date, celebration=holiday.celebration))

    sunday_date = calc_easter(year)
    easter_holidays = []
    for holiday in EASTER_WEEK_HOLIDAYS:
        holiday_date = sunday_date + timedelta(days=holiday.day)
        if holiday.days_to_sum is not None and holiday_date.weekday() != holiday.days_to_sum:
            holiday_date = next_weekday(holiday_date, holiday.days_to_sum)
        easter_holidays.append(nt_holiday(date=holiday_date, celebration=holiday.celebration))

    holiday_list = normal_holidays + easter_holidays
    holiday_list.sort(key=lambda holiday: holiday.date)
    return holiday_list

def is_holiday_date(d):
    if not isinstance(d, date):
        raise TypeError("Debe proporcionar un objeto tipo date")
    if isinstance(d, datetime):
        d = d.date()
    holiday_list = set([holiday.date for holiday in get_colombia_holidays_by_year(d.year)])
    return d in holiday_list

_logger = logging.getLogger(__name__)

# NOTA: La clase HrWorkEntryType con los campos deduct_deductions, not_contribution_base y short_name
# esta definida en lavish_hr_employee/models/hr_leave.py - NO duplicar aqui

class HolidaysRequest(models.Model):    
    _inherit = "hr.leave"
    _order = 'date_from desc'

    number_of_vac_money_days = fields.Float( 'Duracion (Dias Compensadas)', store=True, tracking=True, help='Number of days of the time off request. Used in the calculation.')
    sequence = fields.Char('Numero')
    employee_identification = fields.Char('Identificación empleado')
    unpaid_absences = fields.Boolean(related='holiday_status_id.unpaid_absences', string='Ausencia no remunerada',store=True)
    discounting_bonus_days = fields.Boolean(related='holiday_status_id.discounting_bonus_days', string='Descontar días en prima',store=True,tracking=True)
    contract_id = fields.Many2one(comodel_name='hr.contract', string='Contrato', compute='_inverse_get_contract',store=True)
    employee_company_id = fields.Many2one('res.company', string='Compañía del empleado', related='employee_id.company_id', store=True)

    # Campos relacionados para mostrar info del empleado en el formulario de ausencias
    emp_identification_type_id = fields.Many2one(
        'l10n_latam.identification.type',
        string='Tipo Documento',
        related='employee_id.l10n_latam_identification_type_id',
        readonly=True
    )
    emp_identification_id = fields.Char(
        string='Numero Documento',
        related='employee_id.identification_id',
        readonly=True
    )
    emp_contract_type_id = fields.Many2one(
        'hr.contract.type',
        string='Tipo Contrato',
        related='contract_id.contract_type_id',
        readonly=True
    )
    emp_risk_id = fields.Many2one(
        'hr.contract.risk',
        string='Nivel Riesgo ARL',
        related='contract_id.risk_id',
        readonly=True
    )
    emp_sabado = fields.Boolean(
        string='Trabaja Sabados',
        related='employee_id.sabado',
        readonly=True
    )
    emp_currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='contract_id.currency_id',
        readonly=True
    )
    emp_wage = fields.Monetary(
        string='Salario',
        related='contract_id.wage',
        currency_field='emp_currency_id',
        readonly=True
    )

    payslip_state = fields.Selection(
        selection_add=[
            ('normal', 'Normal'),
            ('blocked', 'Bloqueado'),
            ('done', 'Procesado'),
        ],
        ondelete={'normal': 'cascade', 'blocked': 'cascade', 'done': 'cascade'},
        string='Estado en nómina', default='normal', tracking=True)
    #Campos para vacaciones
    is_vacation = fields.Boolean(related='holiday_status_id.is_vacation', string='Es vacaciones',store=True)
    is_vacation_money = fields.Boolean(related='holiday_status_id.is_vacation_money', string='Es vacaciones en Dinero',store=True)
    business_days = fields.Float(compute='_compute_number_of_days', string='Días habiles', store=True)
    holidays = fields.Float(compute='_compute_number_of_days', string='Días festivos', store=True, help='Total de días festivos en la ausencia')
    days_31_business = fields.Float(compute='_compute_number_of_days', string='Días 31 habiles', store=True, help='Este día no se tiene encuenta para el calculo del pago pero si afecta su historico de vacaciones.')
    days_31_holidays = fields.Float(compute='_compute_number_of_days', string='Días 31 festivos', store=True, help='Este día no se tiene encuenta para el calculo del pago ni afecta su historico de vacaciones.')
    
    # Campos de valores para festivos (store=True para persistir)
    holiday_value = fields.Float(
        string='Valor Días Festivos',
        compute='_compute_holiday_values',
        store=True,
        digits=(16, 2),
        help='Valor monetario total de los días festivos en esta ausencia'
    )
    holiday_31_value = fields.Float(
        string='Valor Días 31 Festivos',
        compute='_compute_holiday_values',
        store=True,
        digits=(16, 2),
        help='Valor monetario total de los días 31 festivos en esta ausencia'
    )
    total_holiday_value = fields.Float(
        string='Valor Total Festivos',
        compute='_compute_holiday_values',
        store=True,
        digits=(16, 2),
        help='Valor total de festivos (incluye días 31 festivos)'
    )
    alert_days_vacation = fields.Boolean(string='Alerta días vacaciones')
    accumulated_vacation_days = fields.Float(string='Días acumulados de vacaciones')
    #Creación de ausencia
    type_of_entity = fields.Many2one('hr.contribution.register', 'Tipo de Entidad',tracking=True)
    entity = fields.Many2one('hr.employee.entities', 'Entidad',tracking=True)
    diagnostic = fields.Many2one('hr.leave.diagnostic', 'Diagnóstico',tracking=True)
    radicado = fields.Char('Radicado #',tracking=True)
    is_recovery = fields.Boolean('Es recobro',tracking=True)
    
    # -------------------------------------------------------------------------
    # OPCIONES AVANZADAS DE CALCULO
    # Permiten sobrescribir configuracion del tipo de ausencia.
    # Por defecto heredan valor del tipo seleccionado.
    # -------------------------------------------------------------------------
    evaluates_day_off = fields.Boolean(
        string='Evalua festivos',
        compute='_compute_leave_config_defaults',
        store=True,
        readonly=False,
        tracking=True,
        help='OPCION AVANZADA - Evaluar dias festivos\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO:\n'
             '  [x] Marcado .... Festivos tienen tratamiento especial\n'
             '  [ ] Desmarcado . Todos los dias se tratan igual\n'
             '------------------------------------------------------------\n'
             'DEFAULT: Heredado del tipo de ausencia\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Vacaciones 1-10 enero (festivo el 6):\n'
             '  + Con evaluacion --> 9 dias habiles + 1 festivo\n'
             '  + Sin evaluacion --> 10 dias corridos'
    )
    apply_day_31 = fields.Boolean(
        string='Aplica dia 31',
        compute='_compute_leave_config_defaults',
        store=True,
        readonly=False,
        tracking=True,
        help='OPCION AVANZADA - Incluir dia 31 en calculo\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO:\n'
             '  [x] Marcado .... Dia 31 se cuenta y paga\n'
             '  [ ] Desmarcado . Dia 31 NO se paga (mes 30 dias)\n'
             '------------------------------------------------------------\n'
             'BASE LEGAL: Mes nomina Colombia = 30 dias\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Incapacidad 25-31 enero:\n'
             '  + Con dia 31 --> 7 dias pagados\n'
             '  + Sin dia 31 --> 6 dias pagados'
    )
    discount_rest_day = fields.Boolean(
        string='Descontar dia de descanso',
        compute='_compute_leave_config_defaults',
        store=True,
        readonly=False,
        tracking=True,
        help='OPCION AVANZADA - Descontar domingos/festivos\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO:\n'
             '  [x] Marcado .... Dias descanso NO se pagan\n'
             '  [ ] Desmarcado . Se pagan todos los dias\n'
             '------------------------------------------------------------\n'
             'USO TIPICO:\n'
             '  + Vacaciones ............. NO descuenta\n'
             '  + Licencia no remunerada . SI descuenta\n'
             '  + Incapacidad ............ Segun EPS\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Lunes a domingo (7 dias):\n'
             '  + Con descuento --> 6 dias pagados\n'
             '  + Sin descuento --> 7 dias pagados'
    )
    payroll_value = fields.Float('Valor a pagado',tracking=True)
    ibc = fields.Float('IBL',tracking=True)
    force_ibc = fields.Boolean('Forzar IBL ausencia', tracking=True,
                               help='Permite ingresar manualmente el valor del IBL')
    force_porc = fields.Float('Forzar Porcentaje', tracking=True,
                              help='Si es diferente de 0, usa este porcentaje en lugar del configurado en el tipo de ausencia')
    force_wage_incapacity = fields.Boolean('No validar mínimo', tracking=True,
                                           help='Si está marcado, NO valida que el pago sea al menos el salario mínimo diario')
    force_min_wage = fields.Boolean('Forzar Salario Mínimo', tracking=True,
                                    help='Si está marcado, usa el SMMLV como base de liquidación')
    force_base_amount = fields.Float('Forzar Base', tracking=True,
                                     help='Si es mayor a 0, usa este valor como base de liquidación en lugar del IBC calculado')
    
    # -------------------------------------------------------------------------
    # AJUSTES MANUALES DE VALOR
    # -------------------------------------------------------------------------
    valor_adicional_manual = fields.Float(
        string='Valor Adicional Manual',
        tracking=True,
        help='VALOR ADICIONAL PARA AJUSTAR EL TOTAL\n'
             '------------------------------------------------------------\n'
             'USO:\n'
             '  + Permite agregar un monto extra al valor calculado\n'
             '  + Se suma al valor final (EPS + Complemento + Adicional)\n'
             '  + Util para ajustes o bonificaciones especiales\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Incapacidad:\n'
             '  + Valor EPS: $500,000\n'
             '  + Complemento: $150,000\n'
             '  + Valor Adicional: $50,000\n'
             '  + TOTAL A PAGAR: $700,000\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Vacaciones en Dinero:\n'
             '  + Valor calculado: $1,200,000\n'
             '  + Valor Adicional: $300,000 (bonificacion)\n'
             '  + TOTAL A PAGAR: $1,500,000'
    )
    
    # -------------------------------------------------------------------------
    # VACACIONES EN DINERO - CONFIGURACION ESPECIAL
    # -------------------------------------------------------------------------
    dias_a_liquidar = fields.Float(
        string='Días a Liquidar',
        tracking=True,
        help='DIAS ESPECIFICOS A LIQUIDAR\n'
             '------------------------------------------------------------\n'
             'USO:\n'
             '  + Solo aplica para VACACIONES EN DINERO\n'
             '  + Permite definir cuantos dias liquidar\n'
             '  + Si es 0, usa los dias calculados del periodo\n'
             '------------------------------------------------------------\n'
             'EJEMPLO:\n'
             '  + Empleado tiene 30 dias acumulados\n'
             '  + Solo quiere liquidar 15 dias\n'
             '  + Poner 15 en este campo\n'
             '------------------------------------------------------------\n'
             'NOTA: Los dias restantes quedan disponibles'
    )
    incluir_festivos_liquidacion = fields.Boolean(
        string='Incluir Festivos en Liquidación',
        tracking=True,
        default=True,
        help='INCLUIR FESTIVOS EN LIQUIDACION DE VACACIONES\n'
             '------------------------------------------------------------\n'
             'COMPORTAMIENTO:\n'
             '  [x] Marcado .... Los festivos del periodo SE PAGAN\n'
             '  [ ] Desmarcado . Solo se pagan dias habiles\n'
             '------------------------------------------------------------\n'
             'EJEMPLO - Liquidar 15 dias (3 festivos en periodo):\n'
             '  + Con festivos --> 15 dias pagados\n'
             '  + Sin festivos --> 12 dias habiles pagados\n'
             '------------------------------------------------------------\n'
             'NOTA: Aplica cuando se usa "Dias a Liquidar" o quincenas'
    )
    
    # Campo calculado para total a pagar (incluyendo adicionales)
    total_a_pagar = fields.Float(
        string='Total a Pagar',
        compute='_compute_total_a_pagar',
        store=True,
        tracking=True,
        help='Valor total incluyendo: EPS/ARL + Complemento Empresa + Valor Adicional'
    )
    
    # Resumen para vacaciones en dinero
    resumen_vacaciones_dinero = fields.Html(
        string='Resumen Vacaciones Dinero',
        compute='_compute_resumen_vacaciones_dinero',
        help='Detalle del calculo de vacaciones en dinero'
    )
    
    leave_ids = fields.One2many('hr.absence.days', 'leave_id', string='Novedades', readonly=True)
    line_ids = fields.One2many(comodel_name='hr.leave.line', inverse_name='leave_id', readonly=True, string='Lineas de Ausencia')
    eps_value = fields.Float('Valor pagado por la EPS',tracking=True)
    payment_date = fields.Date ('Fecha de pago',tracking=True)
    return_date = fields.Date ('Fecha de regreso',tracking=True)
    #Prorroga
    payroll_value_with_extension = fields.Float('Valor pagado en nómina con prorrogas',  store=True, tracking=True)
    eps_value_with_extension = fields.Float('Valor pagado por la EPS  con prorrogas', store=True, tracking=True)
    is_extension = fields.Boolean(string='Es prórroga', default=False)
    extension_id = fields.Many2one(
        comodel_name='hr.leave',
        domain="[('state', '=', 'validate'),('holiday_status_id', '=', holiday_status_id), ('employee_id', '=', employee_id),]",
        string='Prórroga')
    payroll_id = fields.Many2one('hr.payslip')
    days_used = fields.Float(string='Dias a usar',compute="_days_used")

    #####################
    state = fields.Selection(selection_add=[
        ('paid', 'Pagada'),
        ('validate1',),
    ], string='Estado', readonly=True)
    approve_date = fields.Datetime('Aprobación', readonly=True,)
    payed_vac = fields.Float('Vacaciones en dinero')
    special_vac_base = fields.Boolean('Disfrutadas con todo')
    #####################
    number_of_days_temp = fields.Float(compute='_compute_number_of_days', string='Días de licencia', readonly=True, store=True)
    number_of_days_in_payslip = fields.Float(compute='_compute_number_of_days', string='Días en la nómina')
    number_of_hours_in_payslip = fields.Float(compute='_compute_number_of_days', string='Horas en nómina')
    number_of_hours = fields.Float(compute='_compute_number_of_days', string='Horas de licencia')
    dummy = fields.Boolean('Actualizar')
    apply_payslip_pay_31 = fields.Boolean('Pagar el 31 en la Nomina')
    # NOTA: payed_vac ya definido arriba (linea ~424), eliminado duplicado
    pay_out_slip = fields.Boolean('Pagar fuera de periodo', help="Permite que el sistema calcule los días")
    type_name = fields.Char(related='holiday_status_id.name', string='Nombre del tipo de permiso')
    payroll_code = fields.Char(string="Código de nómina", related="holiday_status_id.code")
    # Campos para interrupciones de vacaciones
    is_vacation_interrupted = fields.Boolean('Vacaciones interrumpidas', default=False, help='Indica si estas vacaciones fueron interrumpidas')
    vacation_interruption_date = fields.Date('Fecha de interrupción')
    vacation_interruption_reason_id = fields.Many2one('hr.vacation.interruption.reason', 'Motivo de interrupción')
    vacation_interruption_detail = fields.Text('Detalle de interrupción')
    vacation_days_returned = fields.Float('Días devueltos', digits=(16, 4), help='Días de vacaciones devueltos por interrupción')
    vacation_will_return = fields.Boolean('Volverá a vacaciones', default=False)
    vacation_return_date = fields.Date('Fecha para retomar vacaciones')
    # Campos para mostrar advertencias
    min_payment_warning = fields.Boolean('Advertencia pago mínimo', compute='_compute_warnings')
    min_payment_message = fields.Char('Mensaje pago mínimo', compute='_compute_warnings')
    holiday_warning = fields.Boolean('Advertencia festivo', compute='_compute_warnings')
    holiday_warning_message = fields.Char('Mensaje festivo', compute='_compute_warnings')
    # Campo para días disponibles
    available_vacation_days = fields.Float('Días de vacaciones disponibles', digits=(16, 4), compute='_compute_available_vacation_days')

    # Campos para cálculos de IBC
    ibc_pila = fields.Float('IBC PILA', tracking=True)

    IBC_ORIGIN = [
        ('ibc', 'IBC Mes Anterior'),
        ('wage', 'Sueldo Actual'),
        ('year', 'Promedio Año'),
        ('min', 'Salario Mínimo'),
        ('manual', 'Valor Manual'),
    ]
    ibc_ss_origin = fields.Selection(
        IBC_ORIGIN,
        string='Origen IBC Seguridad Social',
        default='ibc',
        tracking=True,
        help='Define de donde se toma el valor para el IBC de seguridad social. '
             'Por defecto usa el IBC del mes anterior.'
    )
    ibc_ss_value = fields.Float(
        string='IBC Seguridad Social',
        compute='_compute_ibc_ss_value',
        store=True,
        digits=(16, 2),
        tracking=True,
        help='Valor del IBC usado para el calculo de seguridad social'
    )
    ibc_ss_manual = fields.Float(
        string='IBC Manual SS',
        digits=(16, 2),
        tracking=True,
        help='Valor manual para IBC de seguridad social cuando origen es Manual'
    )
    ibc_ss_provisional = fields.Boolean(
        string='Valor Provisional',
        default=True,
        tracking=True,
        help='Indica si el valor del IBC es provisional (antes de liquidacion de SS)'
    )
    ibc_daily_rate = fields.Float(
        string='IBC Diario',
        compute='_compute_ibc_daily_rate',
        store=True,
        digits=(16, 2),
        help='Ingreso Base de Cotización diario para seguridad social'
    )
    ibc_ss_resumen = fields.Html(
        string='Resumen Calculo IBC SS',
        compute='_compute_ibc_ss_resumen',
        store=True,
        help='Muestra el detalle de como se calculo el IBC para seguridad social'
    )

    # Campos para incapacidad durante vacaciones
    disability_during_vacation = fields.Boolean(
        string='Incapacidad durante vacaciones',
        default=False,
        tracking=True,
        help='Marca si el empleado tuvo incapacidad durante el periodo de vacaciones'
    )
    disability_start_date = fields.Date(
        string='Fecha inicio incapacidad en vacaciones',
        tracking=True,
        help='Fecha en que inició la incapacidad durante las vacaciones'
    )
    disability_days = fields.Float(
        string='Días de incapacidad en vacaciones',
        digits=(16, 2),
        tracking=True,
        help='Días de incapacidad durante las vacaciones que se deben devolver al empleado'
    )
    extended_vacation_days = fields.Float(
        string='Días extendidos por incapacidad',
        compute='_compute_extended_vacation_days',
        store=True,
        digits=(16, 2),
        help='Días adicionales de vacaciones otorgados por la incapacidad durante el periodo'
    )
    
    ibl_total = fields.Float('IBL Total', compute='_compute_ibl_total', store=True)
    diferencia_ibc = fields.Float('Diferencia a cargo de empresa', compute='_compute_ibl_total', store=True)
    use_ibc_pila = fields.Boolean('Usar IBC PILA para todos los cálculos', default=False)
    
    days_work_count = fields.Float('Días laborables', compute='_compute_days_count', store=True)
    days_rest_count = fields.Float('Días de descanso', compute='_compute_days_count', store=True)
    
    resumen_calculo = fields.Html('Resumen de cálculo', compute='_compute_resumen_calculo', store=True)

    # -------------------------------------------------------------------------
    # HTML DETALLADO: Explica el IBL segun configuracion liquidacion_value
    # -------------------------------------------------------------------------
    ibl_detalle_html = fields.Html(
        string='Detalle IBL (Pago)',
        compute='_compute_ibl_detalle_html',
        store=True,
        help='Explicacion detallada del Ingreso Base de Liquidacion (IBL) '
             'para el PAGO de la ausencia, segun la configuracion del tipo de ausencia.'
    )

    def _get_hours_per_day(self, date_ref=None, company_id=None):
        """
        Obtiene las horas por dia desde hr.company.working.hours.
        Si no existe configuracion, usa HOURS_PER_DAY (8) por defecto.

        Args:
            date_ref: Fecha de referencia para buscar el periodo (default: date_from)
            company_id: ID de la empresa (default: empresa del empleado)

        Returns:
            float: Horas por dia laborable
        """
        if not date_ref:
            date_ref = self.date_from.date() if self.date_from else fields.Date.today()
        if not company_id:
            company_id = self.employee_id.company_id.id if self.employee_id else self.env.company.id

        # Buscar configuracion de horas para el mes/ano
        working_hours = self.env['hr.company.working.hours'].search([
            ('company_id', '=', company_id),
            ('year', '=', date_ref.year),
            ('month', '=', date_ref.month),
        ], limit=1)

        if working_hours and working_hours.hours_per_day > 0:
            return working_hours.hours_per_day

        # Fallback: buscar en parametros anuales
        annual_params = self.env['hr.annual.parameters'].get_for_year(
            date_ref.year,
            company_id=company_id,
            raise_if_not_found=False,
        )
        if annual_params and annual_params.working_hours_ids:
            wh = annual_params.working_hours_ids.filtered(
                lambda w: w.month == date_ref.month and (not w.company_id or w.company_id.id == company_id)
            )
            if wh and wh[0].hours_per_day > 0:
                return wh[0].hours_per_day

        # Fallback final: constante por defecto
        return HOURS_PER_DAY

    @api.depends('line_ids', 'line_ids.amount', 'ibc', 'ibc_pila')
    def _compute_ibl_total(self):
        for leave in self:
            leave.ibl_total = sum(line.amount for line in leave.line_ids)
            
            if leave.holiday_status_id.completar_salario and leave.holiday_status_id.novelty in ['ige', 'irl']:
                if leave.request_unit_hours:
                    annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                        leave.date_from.year,
                        company_id=(leave.company_id.id or (leave.contract_id.company_id.id if leave.contract_id else None)),
                        raise_if_not_found=True,
                    )
                    hours_monthly = annual_parameters.hours_monthly or 240
                    valor_base = (leave.contract_id.wage / hours_monthly) * leave.number_of_hours_display
                else:
                    valor_base = leave.contract_id.wage / 30 * leave.number_of_days
                    
                leave.diferencia_ibc = max(0, valor_base - leave.ibl_total)
            else:
                leave.diferencia_ibc = 0

    @api.depends('ibc_ss_origin', 'ibc', 'ibc_pila', 'ibc_ss_manual', 'contract_id', 'contract_id.wage', 'date_from')
    def _compute_ibc_ss_value(self):
        """Calcula el valor del IBC para seguridad social segun el origen seleccionado"""
        for leave in self:
            origin = leave.ibc_ss_origin or 'ibc'
            value = 0

            if origin == 'ibc':
                value = leave.ibc_pila or leave.ibc or (leave.contract_id.wage if leave.contract_id else 0)
            elif origin == 'wage':
                value = leave.contract_id.wage if leave.contract_id else 0
            elif origin == 'year':
                if leave.contract_id and leave.date_from:
                    payslips = self.env['hr.payslip'].search([
                        ('employee_id', '=', leave.contract_id.employee_id.id),
                        ('state', 'in', ['done', 'paid']),
                        ('date_from', '>=', leave.date_from - relativedelta(years=1)),
                        ('date_to', '<', leave.date_from)
                    ])
                    if payslips:
                        total_ibc = 0
                        for payslip in payslips:
                            ibc_line = payslip.line_ids.filtered(lambda l: l.code == 'IBD')
                            if ibc_line:
                                total_ibc += abs(ibc_line[0].total)
                            else:
                                total_ibc += payslip.contract_id.wage if payslip.contract_id else 0
                        value = total_ibc / len(payslips) if payslips else 0
                    else:
                        value = leave.contract_id.wage
                else:
                    value = 0
            elif origin == 'min':
                if leave.date_from:
                    company_id = leave.employee_company_id.id if leave.employee_company_id else None
                    annual_params = self.env['hr.annual.parameters'].get_for_year(
                        leave.date_from.year, company_id=company_id, raise_if_not_found=False
                    )
                    value = annual_params.smmlv_monthly if annual_params else 0
            elif origin == 'manual':
                value = leave.ibc_ss_manual or 0

            leave.ibc_ss_value = value

    @api.depends('ibc_ss_value', 'ibc', 'contract_id', 'contract_id.wage')
    def _compute_ibc_daily_rate(self):
        """Calcula el IBC diario para seguridad social"""
        for leave in self:
            if leave.ibc_ss_value:
                leave.ibc_daily_rate = leave.ibc_ss_value / 30
            elif leave.ibc:
                leave.ibc_daily_rate = leave.ibc / 30
            elif leave.contract_id and leave.contract_id.wage:
                leave.ibc_daily_rate = leave.contract_id.wage / 30
            else:
                leave.ibc_daily_rate = 0

    @api.depends('ibc_ss_origin', 'ibc_ss_value', 'ibc_ss_provisional', 'ibc_ss_manual',
                 'ibc', 'ibc_pila', 'contract_id', 'contract_id.wage', 'date_from',
                 'number_of_days', 'ibc_daily_rate')
    def _compute_ibc_ss_resumen(self):
        """Genera el resumen HTML de como se calculo el IBC para seguridad social"""
        origen_labels = {
            'ibc': 'IBC Mes Anterior',
            'wage': 'Sueldo Actual',
            'year': 'Promedio Año',
            'min': 'Salario Minimo (SMMLV)',
            'manual': 'Valor Manual',
        }

        for leave in self:
            if not leave.ibc_ss_origin:
                leave.ibc_ss_resumen = "<div class='text-muted'>Sin calculo de IBC</div>"
                continue

            origin = leave.ibc_ss_origin
            origin_label = origen_labels.get(origin, origin)

            # Construir detalle segun el origen
            detalle_origen = ""
            valores_usados = []

            if origin == 'ibc':
                if leave.ibc_pila:
                    valores_usados.append(f"IBC PILA: ${leave.ibc_pila:,.2f}")
                    detalle_origen = f"Se usa el IBC PILA registrado: <strong>${leave.ibc_pila:,.2f}</strong>"
                elif leave.ibc and leave.contract_id and leave.date_to:
                    # Obtener detalle de nominas del mes anterior
                    date_to = leave.date_to.date()
                    from_date = (date_to.replace(day=1) - relativedelta(months=1))
                    to_date = (date_to.replace(day=1) - relativedelta(days=1))

                    # Buscar nominas del periodo
                    payslips = self.env['hr.payslip'].search([
                        ('state', 'in', ['done', 'paid']),
                        ('contract_id', '=', leave.contract_id.id),
                        ('date_from', '<=', to_date),
                        ('date_to', '>=', from_date),
                    ])

                    if payslips:
                        detalle_nominas = "<table class='table table-sm table-bordered mb-2'>"
                        detalle_nominas += "<thead class='table-light'><tr><th>Nomina</th><th>Periodo</th><th class='text-end'>Base SS</th></tr></thead><tbody>"

                        total_base_ss = 0
                        for slip in payslips:
                            # Obtener lineas base seguridad social
                            lines_ss = slip.line_ids.filtered(lambda l: l.salary_rule_id.base_seguridad_social)
                            base_ss = sum(abs(l.total) for l in lines_ss)
                            total_base_ss += base_ss

                            slip_ref = slip.number or f"ID:{slip.id}"
                            periodo = f"{slip.date_from.strftime('%d/%m')} - {slip.date_to.strftime('%d/%m/%Y')}"
                            detalle_nominas += f"<tr><td><code>{slip_ref}</code></td><td>{periodo}</td><td class='text-end'>${base_ss:,.2f}</td></tr>"

                        detalle_nominas += "</tbody></table>"

                        promedio = total_base_ss / len(payslips) if payslips else 0
                        valores_usados.append(f"Nominas encontradas: {len(payslips)}")
                        valores_usados.append(f"Total Base SS: ${total_base_ss:,.2f}")
                        valores_usados.append(f"Promedio: ${promedio:,.2f}")

                        detalle_origen = f"""
                        <div class='mb-2'><strong>Calculo IBC mes anterior ({from_date.strftime('%m/%Y')}):</strong></div>
                        {detalle_nominas}
                        <div class='row mb-2'>
                            <div class='col-6'>Total Base SS: <strong>${total_base_ss:,.2f}</strong></div>
                            <div class='col-6 text-end'>Promedio: <strong>${promedio:,.2f}</strong></div>
                        </div>
                        <div class='alert alert-success py-1 mb-0'>
                            <strong>IBC Calculado: ${leave.ibc:,.2f}</strong>
                        </div>
                        """
                    else:
                        # Sin nominas del mes anterior, mostrar de donde viene el valor
                        wage = leave.contract_id.wage if leave.contract_id else 0
                        valores_usados.append(f"Sueldo contrato: ${wage:,.2f}")
                        valores_usados.append(f"IBC SS Value: ${leave.ibc_ss_value:,.2f}")

                        detalle_origen = f"""
                        <div class='mb-2'><strong>Calculo IBC mes anterior ({from_date.strftime('%m/%Y')}):</strong></div>
                        <div class='alert alert-warning py-2 mb-2'>
                            <i class='fa fa-exclamation-triangle'></i> Sin nominas confirmadas en {from_date.strftime('%m/%Y')}
                        </div>
                        <table class='table table-sm table-borderless mb-2'>
                            <tr>
                                <td class='text-muted'>Sueldo del contrato:</td>
                                <td class='text-end'><strong>${wage:,.2f}</strong></td>
                            </tr>
                            <tr>
                                <td class='text-muted'>IBC SS Configurado:</td>
                                <td class='text-end'><strong>${leave.ibc_ss_value:,.2f}</strong></td>
                            </tr>
                        </table>
                        <div class='alert alert-info py-1 mb-0'>
                            <strong>IBC Aplicado: ${leave.ibc:,.2f}</strong>
                        </div>
                        """
                else:
                    detalle_origen = "<span class='text-warning'>No hay IBC disponible</span>"

            elif origin == 'wage':
                wage = leave.contract_id.wage if leave.contract_id else 0
                valores_usados.append(f"Sueldo: ${wage:,.2f}")
                detalle_origen = f"Se usa el sueldo actual del contrato: <strong>${wage:,.2f}</strong>"

            elif origin == 'year':
                if leave.contract_id and leave.date_from:
                    payslips = self.env['hr.payslip'].search([
                        ('employee_id', '=', leave.contract_id.employee_id.id),
                        ('state', 'in', ['done', 'paid']),
                        ('date_from', '>=', leave.date_from - relativedelta(years=1)),
                        ('date_to', '<', leave.date_from)
                    ], order='date_from')

                    if payslips:
                        detalle_nominas = "<ul class='mb-0'>"
                        total_ibc = 0
                        for payslip in payslips[:12]:  # Mostrar max 12
                            ibc_line = payslip.line_ids.filtered(lambda l: l.code == 'IBD')
                            ibc_val = abs(ibc_line[0].total) if ibc_line else payslip.contract_id.wage
                            total_ibc += ibc_val
                            periodo = payslip.date_from.strftime('%m/%Y') if payslip.date_from else 'N/A'
                            detalle_nominas += f"<li>{periodo}: ${ibc_val:,.2f}</li>"
                        detalle_nominas += "</ul>"

                        promedio = total_ibc / len(payslips)
                        valores_usados.append(f"Total nominas: {len(payslips)}")
                        valores_usados.append(f"Suma IBC: ${total_ibc:,.2f}")
                        valores_usados.append(f"Promedio: ${promedio:,.2f}")

                        detalle_origen = f"""
                        <div>Se calcula el promedio de {len(payslips)} nominas del ultimo año:</div>
                        {detalle_nominas}
                        <div class='mt-2'><strong>Promedio: ${promedio:,.2f}</strong></div>
                        """
                    else:
                        wage = leave.contract_id.wage
                        detalle_origen = f"<span class='text-warning'>Sin nominas anteriores, se usa sueldo: ${wage:,.2f}</span>"
                else:
                    detalle_origen = "<span class='text-danger'>Falta contrato o fecha</span>"

            elif origin == 'min':
                if leave.date_from:
                    company_id = leave.employee_company_id.id if leave.employee_company_id else None
                    annual_params = self.env['hr.annual.parameters'].get_for_year(
                        leave.date_from.year, company_id=company_id, raise_if_not_found=False
                    )
                    smmlv = annual_params.smmlv_monthly if annual_params else 0
                    valores_usados.append(f"SMMLV {leave.date_from.year}: ${smmlv:,.2f}")
                    detalle_origen = f"Se usa el salario minimo del año {leave.date_from.year}: <strong>${smmlv:,.2f}</strong>"
                else:
                    detalle_origen = "<span class='text-danger'>Falta fecha de inicio</span>"

            elif origin == 'manual':
                valores_usados.append(f"Valor manual: ${leave.ibc_ss_manual:,.2f}")
                detalle_origen = f"Valor ingresado manualmente: <strong>${leave.ibc_ss_manual:,.2f}</strong>"

            # Estado provisional
            estado_class = 'warning' if leave.ibc_ss_provisional else 'success'
            estado_text = 'Provisional' if leave.ibc_ss_provisional else 'Confirmado'
            estado_icon = '&#9888;' if leave.ibc_ss_provisional else '&#10004;'

            # Calculos finales
            dias = leave.number_of_days or 0
            ibc_diario = leave.ibc_daily_rate or 0
            valor_ss = ibc_diario * dias

            # Construir HTML
            html = f"""
            <div class="card">
                <div class="card-header bg-light">
                    <strong>Calculo IBC Seguridad Social</strong>
                    <span class="badge bg-{estado_class} float-end">{estado_icon} {estado_text}</span>
                </div>
                <div class="card-body">
                    <table class="table table-sm table-borderless mb-3">
                        <tr>
                            <td class="text-muted" style="width:40%">Origen:</td>
                            <td><strong>{origin_label}</strong></td>
                        </tr>
                        <tr>
                            <td class="text-muted">IBC Mensual:</td>
                            <td><strong>${leave.ibc_ss_value:,.2f}</strong></td>
                        </tr>
                        <tr>
                            <td class="text-muted">IBC Diario:</td>
                            <td>${ibc_diario:,.2f} <small class="text-muted">(IBC / 30)</small></td>
                        </tr>
                        <tr>
                            <td class="text-muted">Dias ausencia:</td>
                            <td>{dias:.2f}</td>
                        </tr>
                        <tr class="border-top">
                            <td class="text-muted">Valor para SS:</td>
                            <td><strong>${valor_ss:,.2f}</strong> <small class="text-muted">(IBC Diario x Dias)</small></td>
                        </tr>
                    </table>

                    <div class="alert alert-info mb-0 py-2">
                        <small><strong>Detalle del calculo:</strong></small><br/>
                        <small>{detalle_origen}</small>
                    </div>
                </div>
            </div>
            """

            leave.ibc_ss_resumen = html

    @api.depends('disability_during_vacation', 'disability_days')
    def _compute_extended_vacation_days(self):
        """Calcula los días adicionales de vacaciones por incapacidad durante el periodo"""
        for leave in self:
            if leave.disability_during_vacation and leave.disability_days > 0:
                leave.extended_vacation_days = leave.disability_days
            else:
                leave.extended_vacation_days = 0

    @api.depends('date_from', 'date_to', 'contract_id', 'holiday_status_id', 'line_ids')
    def _compute_days_count(self):
        for leave in self:
            days_work = days_rest = 0
            
            if leave.line_ids:
                days_work = sum(line.days_work for line in leave.line_ids)
                days_rest = sum(line.days_holiday for line in leave.line_ids)
                days_rest += sum(line.days_holiday_31 for line in leave.line_ids)
            elif leave.date_from and leave.date_to:
                current_date = leave.date_from.date()
                while current_date <= leave.date_to.date():
                    is_rest_day = (
                        current_date.weekday() == 6 or
                        self._is_holiday(current_date) or
                        (current_date.weekday() == 5 and not leave.employee_id.sabado)
                    )
                    
                    if is_rest_day:
                        days_rest += 1
                    else:
                        days_work += 1
                    
                    current_date += timedelta(days=1)
            
            leave.days_work_count = days_work
            leave.days_rest_count = days_rest
    
    # -------------------------------------------------------------------------
    # CALCULO TOTAL A PAGAR (incluye adicionales)
    # -------------------------------------------------------------------------
    @api.depends('payroll_value', 'diferencia_ibc', 'valor_adicional_manual', 'is_vacation_money')
    def _compute_total_a_pagar(self):
        """Calcula el total a pagar incluyendo todos los componentes."""
        for leave in self:
            # Base: valor pagado (EPS/ARL o valor directo)
            total = leave.payroll_value or 0
            
            # Sumar complemento empresa (diferencia_ibc)
            if leave.diferencia_ibc and leave.diferencia_ibc > 0:
                total += leave.diferencia_ibc
            
            # Sumar valor adicional manual
            if leave.valor_adicional_manual and leave.valor_adicional_manual > 0:
                total += leave.valor_adicional_manual
            
            leave.total_a_pagar = total
    
    # -------------------------------------------------------------------------
    # RESUMEN VACACIONES EN DINERO
    # -------------------------------------------------------------------------
    @api.depends('is_vacation_money', 'payroll_value', 'valor_adicional_manual', 
                 'total_a_pagar', 'dias_a_liquidar', 'number_of_days', 'contract_id',
                 'incluir_festivos_liquidacion', 'business_days', 'holidays')
    def _compute_resumen_vacaciones_dinero(self):
        """Genera resumen detallado para vacaciones en dinero."""
        for leave in self:
            if not leave.is_vacation_money:
                leave.resumen_vacaciones_dinero = ""
                continue
            
            # Datos del calculo
            dias_solicitados = leave.dias_a_liquidar or leave.number_of_days or 0
            dias_habiles = leave.business_days or 0
            dias_festivos = leave.holidays or 0
            incluir_festivos = leave.incluir_festivos_liquidacion
            
            # Dias efectivos a pagar
            if incluir_festivos:
                dias_a_pagar = dias_solicitados
                nota_festivos = "Festivos INCLUIDOS en el pago"
            else:
                dias_a_pagar = dias_habiles
                nota_festivos = f"Festivos NO incluidos ({dias_festivos} dias)"
            
            # Valores
            valor_calculado = leave.payroll_value or 0
            valor_adicional = leave.valor_adicional_manual or 0
            total = leave.total_a_pagar or 0
            
            # Base diaria
            base_diaria = valor_calculado / dias_a_pagar if dias_a_pagar > 0 else 0
            
            # Construir HTML
            html = f"""
            <div class="card border-primary">
                <div class="card-header bg-primary text-white">
                    <i class="fa fa-money"></i> <strong>VACACIONES EN DINERO</strong>
                </div>
                <div class="card-body">
                    <table class="table table-sm table-borderless mb-2">
                        <tr>
                            <td class="text-muted" style="width:50%">Días solicitados:</td>
                            <td><strong>{dias_solicitados:.2f}</strong></td>
                        </tr>
                        <tr>
                            <td class="text-muted">Días hábiles:</td>
                            <td>{dias_habiles:.2f}</td>
                        </tr>
                        <tr>
                            <td class="text-muted">Días festivos:</td>
                            <td>{dias_festivos:.2f}</td>
                        </tr>
                        <tr class="border-top">
                            <td class="text-muted">Días a pagar:</td>
                            <td><strong>{dias_a_pagar:.2f}</strong></td>
                        </tr>
                    </table>
                    
                    <div class="alert alert-info py-1 mb-2">
                        <small><i class="fa fa-info-circle"></i> {nota_festivos}</small>
                    </div>
                    
                    <table class="table table-sm mb-0">
                        <tr>
                            <td class="text-muted" style="width:50%">Base diaria:</td>
                            <td class="text-end">${base_diaria:,.2f}</td>
                        </tr>
                        <tr>
                            <td class="text-muted">Valor calculado:</td>
                            <td class="text-end">${valor_calculado:,.2f}</td>
                        </tr>
            """
            
            if valor_adicional > 0:
                html += f"""
                        <tr class="text-success">
                            <td><i class="fa fa-plus-circle"></i> Valor adicional:</td>
                            <td class="text-end">+ ${valor_adicional:,.2f}</td>
                        </tr>
                """
            
            html += f"""
                        <tr class="border-top bg-light">
                            <td><strong>TOTAL A PAGAR:</strong></td>
                            <td class="text-end"><strong>${total:,.2f}</strong></td>
                        </tr>
                    </table>
                </div>
            </div>
            """
            
            leave.resumen_vacaciones_dinero = html
    
    @api.depends('date_from', 'date_to', 'contract_id', 'holiday_status_id', 'line_ids', 
                'ibc', 'ibc_pila', 'ibl_total', 'diferencia_ibc')
    def _compute_resumen_calculo(self):
        for leave in self:
            if not leave.line_ids:
                leave.resumen_calculo = "<div>Sin líneas de ausencia calculadas</div>"
                continue
                
            dias_laborables = leave.days_work_count
            dias_descanso = leave.days_rest_count
            total_dias = dias_laborables + dias_descanso
            valor_ibc = leave.ibc
            valor_ibc_pila = leave.ibc_pila
            valor_ibl = leave.ibl_total
            diferencia = leave.diferencia_ibc
            tipo_liquidacion = leave.holiday_status_id.liquidacion_value
            valores_dict = dict([
                ('IBC', 'IBC Mes Anterior'),
                ('YEAR', 'Promedio Año Anterior'),
                ('WAGE', 'Sueldo Actual'),
                ('MIN', 'Parámetros mínimos de ley')
            ])
            tipo_texto = valores_dict.get(tipo_liquidacion, 'No definido')
            
            desglose_tramos = ""
            if leave.holiday_status_id.novelty in ['ige', 'irl']:
                tramos = {
                    'iniciales': [],
                    'hasta_90': [],
                    'hasta_180': [],
                    'mas_180': []
                }
                
                for line in leave.line_ids:
                    if line.sequence <= leave.holiday_status_id.num_days_no_assume:
                        tramos['iniciales'].append(line)
                    elif line.sequence <= 90:
                        tramos['hasta_90'].append(line)
                    elif line.sequence <= 180:
                        tramos['hasta_180'].append(line)
                    else:
                        tramos['mas_180'].append(line)
                
                desglose_tramos = """
                <div class="mt-3">
                    <strong>Desglose por tramos:</strong>
                    <ul>
                """
                
                if tramos['iniciales']:
                    dias = len(tramos['iniciales'])
                    valor = sum(line.amount for line in tramos['iniciales'])
                    desglose_tramos += f"<li>Primeros {dias} días (Empresa): {valor:.2f}</li>"
                
                if tramos['hasta_90']:
                    dias = len(tramos['hasta_90'])
                    valor = sum(line.amount for line in tramos['hasta_90'])
                    desglose_tramos += f"<li>Días 3-90 (EPS/ARL 66.67%): {valor:.2f}</li>"
                
                if tramos['hasta_180']:
                    dias = len(tramos['hasta_180'])
                    valor = sum(line.amount for line in tramos['hasta_180'])
                    desglose_tramos += f"<li>Días 91-180 (EPS/ARL 50%): {valor:.2f}</li>"
                
                if tramos['mas_180']:
                    dias = len(tramos['mas_180'])
                    valor = sum(line.amount for line in tramos['mas_180'])
                    desglose_tramos += f"<li>Días +180 (EPS/ARL 50%): {valor:.2f}</li>"
                
                desglose_tramos += """
                    </ul>
                </div>
                """
            
            completar_info = ""
            if leave.holiday_status_id.completar_salario and diferencia > 0:
                completar_info = f"""
                <div class="alert alert-info mt-3">
                    <strong>Complemento salarial:</strong> La empresa asumirá {diferencia:.2f} 
                    para completar hasta el 100% del salario actual.
                </div>
                """
            
            resumen = f"""
            <div class="row">
                <div class="col-6">
                    <strong>Detalles de Días:</strong>
                    <ul>
                        <li>Días laborables: {dias_laborables}</li>
                        <li>Días de descanso: {dias_descanso}</li>
                        <li>Total días: {total_dias}</li>
                    </ul>
                </div>
                <div class="col-6">
                    <strong>Valores:</strong>
                    <ul>
                        <li>IBC Base: {valor_ibc:.2f}</li>
                        <li>IBC PILA: {valor_ibc_pila:.2f}</li>
                        <li>IBL Total (Pago al empleado): {valor_ibl:.2f}</li>
                    </ul>
                </div>
            </div>
            <div class="row">
                <div class="col-12">
                    <strong>Tipo de liquidación:</strong> {tipo_texto}
                </div>
            </div>
            {desglose_tramos}
            {completar_info}
            """
            
            leave.resumen_calculo = resumen

    # -------------------------------------------------------------------------
    # COMPUTE: Detalle IBL segun liquidacion_value
    # -------------------------------------------------------------------------
    @api.depends('holiday_status_id', 'holiday_status_id.liquidacion_value', 'contract_id',
                 'contract_id.wage', 'date_from', 'date_to', 'ibc', 'ibc_pila',
                 'force_base_amount', 'force_min_wage', 'force_porc', 'force_wage_incapacity',
                 'line_ids', 'line_ids.amount', 'line_ids.base_type', 'line_ids.ibc_base',
                 'payroll_value', 'number_of_days')
    def _compute_ibl_detalle_html(self):
        """
        Genera HTML detallado explicando el IBL (Ingreso Base de Liquidacion)
        segun la configuracion del tipo de ausencia (liquidacion_value).

        TIPOS DE LIQUIDACION:
            - IBC:  Usa IBC del mes anterior (para incapacidades)
            - YEAR: Usa promedio del año anterior (vacaciones)
            - WAGE: Usa sueldo actual del contrato
            - MIN:  Usa SMMLV vigente

        NOTA: Este campo es para el PAGO al empleado, diferente al IBC de SS.
        """
        LIQUIDACION_LABELS = {
            'IBC': ('IBC Mes Anterior', 'fa-calendar-check-o', 'primary'),
            'YEAR': ('Promedio Año Anterior', 'fa-history', 'info'),
            'WAGE': ('Sueldo Actual', 'fa-money', 'success'),
            'MIN': ('Salario Mínimo (SMMLV)', 'fa-legal', 'warning'),
        }

        for leave in self:
            if not leave.holiday_status_id or not leave.contract_id:
                leave.ibl_detalle_html = "<div class='text-muted'>Sin datos suficientes para calcular IBL</div>"
                continue

            tipo_liq = leave.holiday_status_id.liquidacion_value or 'WAGE'
            liq_label, liq_icon, liq_color = LIQUIDACION_LABELS.get(tipo_liq, ('No definido', 'fa-question', 'secondary'))

            # Obtener parametros anuales
            annual_params = None
            smmlv = 0
            if leave.date_from:
                company_id = leave.employee_company_id.id if leave.employee_company_id else None
                annual_params = self.env['hr.annual.parameters'].get_for_year(
                    leave.date_from.year, company_id=company_id, raise_if_not_found=False
                )
                smmlv = annual_params.smmlv_monthly if annual_params else 0

            salario_contrato = leave.contract_id.wage or 0

            # ═══════════════════════════════════════════════════════════════
            # DETERMINAR IBL SEGUN CONFIGURACION Y VALORES FORZADOS
            # ═══════════════════════════════════════════════════════════════
            ibl_usado = 0
            origen_ibl = ""
            detalle_origen = ""
            tiene_forzado = False

            # 1. Verificar si hay valores forzados (tienen prioridad)
            if leave.force_base_amount and leave.force_base_amount > 0:
                tiene_forzado = True
                ibl_usado = leave.force_base_amount
                origen_ibl = "VALOR FORZADO"
                detalle_origen = f"""
                <div class='alert alert-warning py-2'>
                    <i class='fa fa-exclamation-triangle'></i>
                    <strong>Base forzada manualmente:</strong> ${leave.force_base_amount:,.2f}
                    <br/><small class='text-muted'>El tipo de liquidacion ({liq_label}) fue ignorado</small>
                </div>
                """
            elif leave.force_min_wage:
                tiene_forzado = True
                ibl_usado = smmlv
                origen_ibl = "SMMLV FORZADO"
                detalle_origen = f"""
                <div class='alert alert-warning py-2'>
                    <i class='fa fa-exclamation-triangle'></i>
                    <strong>Forzado a Salario Minimo:</strong> ${smmlv:,.2f}
                    <br/><small class='text-muted'>El tipo de liquidacion ({liq_label}) fue ignorado</small>
                </div>
                """

            # 2. Si no hay forzado, usar segun liquidacion_value
            elif tipo_liq == 'IBC':
                origen_ibl = "IBC MES ANTERIOR"
                ibl_usado = leave.ibc or leave.ibc_pila or salario_contrato

                # Buscar nominas del mes anterior para detallar
                if leave.date_from and leave.contract_id:
                    from_date = (leave.date_from.replace(day=1) - relativedelta(months=1))
                    to_date = (leave.date_from.replace(day=1) - relativedelta(days=1))

                    payslips = self.env['hr.payslip'].search([
                        ('state', 'in', ['done', 'paid']),
                        ('contract_id', '=', leave.contract_id.id),
                        ('date_from', '<=', to_date),
                        ('date_to', '>=', from_date),
                    ], order='date_from')

                    if payslips:
                        detalle_origen = f"""
                        <div class='mb-2'><strong>Nominas del periodo {from_date.strftime('%m/%Y')}:</strong></div>
                        <table class='table table-sm table-bordered'>
                            <thead class='table-light'>
                                <tr><th>Nomina</th><th>Periodo</th><th class='text-end'>Base</th></tr>
                            </thead>
                            <tbody>
                        """
                        total_base = 0
                        for slip in payslips:
                            # Buscar linea IBD o calcular base
                            ibd_line = slip.line_ids.filtered(lambda l: l.code == 'IBD')
                            base_slip = abs(ibd_line[0].total) if ibd_line else slip.contract_id.wage
                            total_base += base_slip
                            slip_ref = slip.number or f"#{slip.id}"
                            periodo = f"{slip.date_from.strftime('%d/%m')} - {slip.date_to.strftime('%d/%m/%Y')}"
                            detalle_origen += f"<tr><td><code>{slip_ref}</code></td><td>{periodo}</td><td class='text-end'>${base_slip:,.2f}</td></tr>"

                        promedio = total_base / len(payslips)
                        detalle_origen += f"""
                            </tbody>
                            <tfoot class='table-light'>
                                <tr><td colspan='2'><strong>Promedio</strong></td><td class='text-end'><strong>${promedio:,.2f}</strong></td></tr>
                            </tfoot>
                        </table>
                        """
                        ibl_usado = promedio
                    else:
                        detalle_origen = f"""
                        <div class='alert alert-info py-2'>
                            <i class='fa fa-info-circle'></i>
                            Sin nominas confirmadas en {from_date.strftime('%m/%Y')}.
                            <br/>Se usa el IBC registrado: <strong>${ibl_usado:,.2f}</strong>
                        </div>
                        """

            elif tipo_liq == 'YEAR':
                origen_ibl = "PROMEDIO AÑO ANTERIOR"
                if leave.date_from and leave.contract_id:
                    # Buscar nominas del ultimo ano
                    fecha_inicio = leave.date_from - relativedelta(years=1)
                    payslips = self.env['hr.payslip'].search([
                        ('employee_id', '=', leave.contract_id.employee_id.id),
                        ('state', 'in', ['done', 'paid']),
                        ('date_from', '>=', fecha_inicio),
                        ('date_to', '<', leave.date_from)
                    ], order='date_from')

                    if payslips:
                        detalle_origen = f"""
                        <div class='mb-2'><strong>Promedio de {len(payslips)} nominas ({fecha_inicio.strftime('%m/%Y')} - {leave.date_from.strftime('%m/%Y')}):</strong></div>
                        <table class='table table-sm table-bordered'>
                            <thead class='table-light'>
                                <tr><th>Periodo</th><th class='text-end'>Base</th></tr>
                            </thead>
                            <tbody>
                        """
                        total_ibc = 0
                        for slip in payslips[-12:]:  # Mostrar max 12 meses
                            ibd_line = slip.line_ids.filtered(lambda l: l.code == 'IBD')
                            base_slip = abs(ibd_line[0].total) if ibd_line else slip.contract_id.wage
                            total_ibc += base_slip
                            periodo = slip.date_from.strftime('%m/%Y') if slip.date_from else 'N/A'
                            detalle_origen += f"<tr><td>{periodo}</td><td class='text-end'>${base_slip:,.2f}</td></tr>"

                        promedio = total_ibc / len(payslips)
                        detalle_origen += f"""
                            </tbody>
                            <tfoot class='table-light'>
                                <tr><td><strong>PROMEDIO ({len(payslips)} meses)</strong></td><td class='text-end'><strong>${promedio:,.2f}</strong></td></tr>
                            </tfoot>
                        </table>
                        """
                        ibl_usado = promedio
                    else:
                        ibl_usado = salario_contrato
                        detalle_origen = f"""
                        <div class='alert alert-warning py-2'>
                            <i class='fa fa-exclamation-triangle'></i>
                            Sin nominas del año anterior. Se usa sueldo actual: <strong>${salario_contrato:,.2f}</strong>
                        </div>
                        """
                else:
                    ibl_usado = salario_contrato

            elif tipo_liq == 'MIN':
                origen_ibl = "SMMLV"
                ibl_usado = smmlv
                detalle_origen = f"""
                <div class='alert alert-info py-2'>
                    <i class='fa fa-legal'></i>
                    SMMLV {leave.date_from.year if leave.date_from else ''}: <strong>${smmlv:,.2f}</strong>
                </div>
                """

            else:  # WAGE
                origen_ibl = "SUELDO CONTRATO"
                ibl_usado = salario_contrato
                detalle_origen = f"""
                <div class='alert alert-success py-2'>
                    <i class='fa fa-file-text-o'></i>
                    Sueldo segun contrato: <strong>${salario_contrato:,.2f}</strong>
                </div>
                """

            # ═══════════════════════════════════════════════════════════════
            # COMPARACION CON SALARIO ACTUAL
            # ═══════════════════════════════════════════════════════════════
            comparacion_html = ""
            if ibl_usado != salario_contrato and salario_contrato > 0:
                diferencia = salario_contrato - ibl_usado
                porcentaje = (diferencia / salario_contrato * 100) if salario_contrato else 0
                color_dif = 'success' if diferencia > 0 else 'danger'
                icono_dif = 'fa-arrow-up' if diferencia > 0 else 'fa-arrow-down'
                comparacion_html = f"""
                <div class='row mb-3'>
                    <div class='col-12'>
                        <div class='alert alert-{color_dif} py-2 mb-0'>
                            <i class='fa {icono_dif}'></i>
                            <strong>Comparacion con salario actual:</strong>
                            <br/>IBL usado: ${ibl_usado:,.2f} vs Sueldo: ${salario_contrato:,.2f}
                            <br/>Diferencia: <strong>${diferencia:+,.2f}</strong> ({porcentaje:+.1f}%)
                        </div>
                    </div>
                </div>
                """

            # ═══════════════════════════════════════════════════════════════
            # DESGLOSE POR TRAMOS (para incapacidades)
            # ═══════════════════════════════════════════════════════════════
            tramos_html = ""
            if leave.holiday_status_id.novelty in ['ige', 'irl'] and leave.line_ids:
                num_dias_empresa = leave.holiday_status_id.num_days_no_assume or 2

                tramos = {
                    'empresa': [],
                    'eps_66': [],
                    'eps_50_180': [],
                    'eps_50_plus': [],
                }

                for line in leave.line_ids.filtered(lambda l: not l.is_complement):
                    seq = line.sequence or 0
                    if seq <= num_dias_empresa:
                        tramos['empresa'].append(line)
                    elif seq <= 90:
                        tramos['eps_66'].append(line)
                    elif seq <= 180:
                        tramos['eps_50_180'].append(line)
                    else:
                        tramos['eps_50_plus'].append(line)

                tramos_html = """
                <div class='mb-3'>
                    <strong><i class='fa fa-list'></i> Desglose por Tramos:</strong>
                    <table class='table table-sm table-bordered mt-2'>
                        <thead class='table-light'>
                            <tr><th>Tramo</th><th>Dias</th><th>%</th><th>Quien Paga</th><th class='text-end'>Valor</th></tr>
                        </thead>
                        <tbody>
                """

                if tramos['empresa']:
                    dias = len(tramos['empresa'])
                    valor = sum(l.amount for l in tramos['empresa'])
                    porc = tramos['empresa'][0].rate_applied if tramos['empresa'] else 100
                    tramos_html += f"<tr class='table-success'><td>Dias 1-{num_dias_empresa}</td><td>{dias}</td><td>{porc:.0f}%</td><td>EMPRESA</td><td class='text-end'>${valor:,.2f}</td></tr>"

                if tramos['eps_66']:
                    dias = len(tramos['eps_66'])
                    valor = sum(l.amount for l in tramos['eps_66'])
                    tramos_html += f"<tr class='table-info'><td>Dias {num_dias_empresa+1}-90</td><td>{dias}</td><td>66.67%</td><td>EPS/ARL</td><td class='text-end'>${valor:,.2f}</td></tr>"

                if tramos['eps_50_180']:
                    dias = len(tramos['eps_50_180'])
                    valor = sum(l.amount for l in tramos['eps_50_180'])
                    tramos_html += f"<tr class='table-warning'><td>Dias 91-180</td><td>{dias}</td><td>50%</td><td>EPS/ARL</td><td class='text-end'>${valor:,.2f}</td></tr>"

                if tramos['eps_50_plus']:
                    dias = len(tramos['eps_50_plus'])
                    valor = sum(l.amount for l in tramos['eps_50_plus'])
                    tramos_html += f"<tr class='table-danger'><td>Dias 181+</td><td>{dias}</td><td>50%</td><td>EPS/ARL</td><td class='text-end'>${valor:,.2f}</td></tr>"

                tramos_html += """
                        </tbody>
                    </table>
                </div>
                """

            # ═══════════════════════════════════════════════════════════════
            # DETALLE DE DIAS (31, festivos, etc.)
            # ═══════════════════════════════════════════════════════════════
            dias_html = ""
            if leave.line_ids:
                dias_31 = sum(l.days_31 for l in leave.line_ids)
                dias_festivos = sum(l.days_holiday for l in leave.line_ids)
                dias_31_fest = sum(l.days_holiday_31 for l in leave.line_ids)
                dias_trabajo = sum(l.days_work for l in leave.line_ids)

                if dias_31 > 0 or dias_festivos > 0 or dias_31_fest > 0:
                    dias_html = f"""
                    <div class='mb-3'>
                        <strong><i class='fa fa-calendar'></i> Detalle de Dias:</strong>
                        <div class='row mt-2'>
                            <div class='col-6'>
                                <ul class='mb-0'>
                                    <li>Dias laborables: <strong>{dias_trabajo:.0f}</strong></li>
                                    <li>Dias festivos: <strong>{dias_festivos:.0f}</strong></li>
                                </ul>
                            </div>
                            <div class='col-6'>
                                <ul class='mb-0'>
                                    <li>Dias 31 (laborables): <strong>{dias_31:.0f}</strong></li>
                                    <li>Dias 31 festivos: <strong>{dias_31_fest:.0f}</strong></li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    """

            # ═══════════════════════════════════════════════════════════════
            # PORCENTAJE FORZADO
            # ═══════════════════════════════════════════════════════════════
            porc_forzado_html = ""
            if leave.force_porc and leave.force_porc != 0:
                porc_forzado_html = f"""
                <div class='alert alert-warning py-2 mb-3'>
                    <i class='fa fa-percent'></i>
                    <strong>Porcentaje forzado:</strong> {leave.force_porc:.2f}%
                    <br/><small>El porcentaje configurado en el tipo de ausencia fue ignorado</small>
                </div>
                """

            # ═══════════════════════════════════════════════════════════════
            # NO VALIDAR MINIMO
            # ═══════════════════════════════════════════════════════════════
            no_minimo_html = ""
            if leave.force_wage_incapacity:
                no_minimo_html = f"""
                <div class='alert alert-danger py-2 mb-3'>
                    <i class='fa fa-exclamation-circle'></i>
                    <strong>Sin validacion de minimo:</strong> El pago puede ser inferior al SMMLV diario (${smmlv/30:,.2f})
                </div>
                """

            # ═══════════════════════════════════════════════════════════════
            # FORMULA FINAL
            # ═══════════════════════════════════════════════════════════════
            ibl_diario = ibl_usado / 30 if ibl_usado else 0
            dias_total = leave.number_of_days or 0
            valor_calculado = leave.payroll_value or 0

            formula_html = f"""
            <div class='card mt-3'>
                <div class='card-header bg-dark text-white'>
                    <strong><i class='fa fa-calculator'></i> Formula de Calculo</strong>
                </div>
                <div class='card-body'>
                    <table class='table table-sm table-borderless mb-0'>
                        <tr>
                            <td class='text-muted' style='width:40%'>IBL Mensual:</td>
                            <td><strong>${ibl_usado:,.2f}</strong></td>
                        </tr>
                        <tr>
                            <td class='text-muted'>IBL Diario:</td>
                            <td>${ibl_diario:,.2f} <small class='text-muted'>(IBL / 30)</small></td>
                        </tr>
                        <tr>
                            <td class='text-muted'>Dias a liquidar:</td>
                            <td><strong>{dias_total:.2f}</strong></td>
                        </tr>
                        <tr class='border-top'>
                            <td class='text-muted'>Total a Pagar:</td>
                            <td><strong class='text-success fs-5'>${valor_calculado:,.2f}</strong></td>
                        </tr>
                    </table>
                </div>
            </div>
            """

            # ═══════════════════════════════════════════════════════════════
            # ENSAMBLAR HTML FINAL
            # ═══════════════════════════════════════════════════════════════
            html = f"""
            <div class='ibl-detalle'>
                <!-- Encabezado con tipo de liquidacion -->
                <div class='card mb-3'>
                    <div class='card-header bg-{liq_color} {"text-white" if liq_color in ["primary", "info", "success", "danger"] else ""}'>
                        <i class='fa {liq_icon}'></i>
                        <strong>Tipo de Liquidacion: {liq_label}</strong>
                        {f"<span class='badge bg-warning text-dark float-end'>FORZADO</span>" if tiene_forzado else ""}
                    </div>
                    <div class='card-body'>
                        <div class='row'>
                            <div class='col-6'>
                                <small class='text-muted'>Origen IBL:</small>
                                <div><strong>{origen_ibl}</strong></div>
                            </div>
                            <div class='col-6 text-end'>
                                <small class='text-muted'>IBL Aplicado:</small>
                                <div><strong class='fs-5'>${ibl_usado:,.2f}</strong></div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Detalle del origen -->
                {detalle_origen}

                <!-- Comparacion con salario actual -->
                {comparacion_html}

                <!-- Alertas de forzados -->
                {porc_forzado_html}
                {no_minimo_html}

                <!-- Desglose por tramos -->
                {tramos_html}

                <!-- Detalle de dias -->
                {dias_html}

                <!-- Formula final -->
                {formula_html}
            </div>
            """

            leave.ibl_detalle_html = html

    @api.depends('date_from', 'date_to', 'resource_calendar_id', 'holiday_status_id.request_unit', 'number_of_vac_money_days')
    def _compute_duration(self):
        for holiday in self:
            if holiday.number_of_vac_money_days:
                days = holiday.number_of_vac_money_days
                hours = days * holiday._get_hours_per_day()
            else:
                # Usar _get_duration() (singular) de Odoo 17, no _get_durations()
                days, hours = holiday._get_duration()
            holiday.number_of_hours = hours
            holiday.number_of_days = days

    @api.depends('line_ids', 'apply_payslip_pay_31')
    def _compute_number_of_days(self):
        for leave in self:
            lines = leave.line_ids
            if not lines:
                leave.update({
                    'number_of_days_temp': 0,
                    'number_of_days_in_payslip': 0,
                    'number_of_hours_in_payslip': 0,
                    'number_of_hours': 0,
                    'business_days': 0,
                    'holidays': 0,
                    'days_31_business': 0,
                    'days_31_holidays': 0,
                })
                continue
            leave.number_of_days_temp = sum(lines.mapped('days_assigned'))
            leave.number_of_days_in_payslip = sum(lines.mapped('days_payslip'))
            leave.number_of_hours_in_payslip = sum(lines.mapped('hours'))
            leave.number_of_hours = sum(lines.mapped('hours_assigned'))
            leave.holidays = sum(lines.mapped('days_holiday'))
            leave.days_31_business = sum(lines.mapped('days_31'))
            leave.days_31_holidays = sum(lines.mapped('days_holiday_31'))
            leave.business_days = leave.number_of_days_in_payslip - leave.holidays
    
    @api.depends('line_ids.holiday_amount', 'line_ids.holiday_31_amount', 'line_ids.days_holiday', 'line_ids.days_holiday_31')
    def _compute_holiday_values(self):
        """Calcula valores monetarios de días festivos"""
        for leave in self:
            # Valor de días festivos normales
            leave.holiday_value = sum(leave.line_ids.mapped('holiday_amount'))
            
            # Valor de días 31 festivos
            leave.holiday_31_value = sum(leave.line_ids.mapped('holiday_31_amount'))
            
            # Valor total (festivos normales + festivos 31)
            leave.total_holiday_value = leave.holiday_value + leave.holiday_31_value

    # -------------------------------------------------------------------------
    # COMPUTE: Valores por defecto desde tipo de ausencia
    # -------------------------------------------------------------------------
    @api.depends('holiday_status_id')
    def _compute_leave_config_defaults(self):
        """
        Hereda configuracion del tipo de ausencia como valores por defecto.
        Estos campos son editables (readonly=False) permitiendo override manual.
        
        FLUJO:
          1. Usuario selecciona tipo de ausencia
          2. Sistema carga valores por defecto del tipo
          3. Usuario puede modificar para casos especiales
        
        CAMPOS AFECTADOS:
          - evaluates_day_off: Evaluar festivos
          - apply_day_31: Incluir dia 31
          - discount_rest_day: Descontar dias descanso
        """
        for leave in self:
            if leave.holiday_status_id:
                # Heredar configuracion del tipo de ausencia
                leave.evaluates_day_off = leave.holiday_status_id.evaluates_day_off
                leave.apply_day_31 = leave.holiday_status_id.apply_day_31
                leave.discount_rest_day = leave.holiday_status_id.discount_rest_day
            else:
                # Valores por defecto si no hay tipo seleccionado
                leave.evaluates_day_off = False
                leave.apply_day_31 = False
                leave.discount_rest_day = False
            
    @api.depends('holiday_status_id', 'date_from', 'date_to', 'line_ids', 'line_ids.amount')
    def _compute_warnings(self):
        """Calcular advertencias sobre pagos mínimos y festivos"""
        for leave in self:
            leave.min_payment_warning = False
            leave.min_payment_message = ""
            leave.holiday_warning = False
            leave.holiday_warning_message = ""
            if not leave.holiday_status_id.is_vacation and not leave.holiday_status_id.is_vacation_money:
                continue
            if leave.line_ids:
                company_id = leave.employee_company_id.id if leave.employee_company_id else None
                annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                    leave.date_from.year, company_id=company_id, raise_if_not_found=False
                )

                if annual_parameters:
                    smmlv_daily = annual_parameters.smmlv_monthly / 30
                    work_lines = leave.line_ids.filtered(lambda l: l.days_work > 0)
                    if work_lines:
                        total_work_days = sum(line.days_work for line in work_lines)
                        total_amount = sum(line.amount for line in work_lines)

                        if total_work_days > 0:
                            avg_daily = total_amount / total_work_days
                            if avg_daily < smmlv_daily and not leave.force_wage_incapacity:
                                leave.min_payment_warning = True
                                leave.min_payment_message = f"El pago diario ({avg_daily:.2f}) es menor al mínimo legal ({smmlv_daily:.2f})"
            if leave.date_from and leave.date_to:
                current_date = leave.date_from.date()
                holidays_found = []
                while current_date <= leave.date_to.date():
                    is_holiday = self.env['lavish.holidays'].ensure_holidays(current_date)
                    if is_holiday:
                        holidays_found.append(current_date.strftime('%d/%m/%Y'))
                    current_date += timedelta(days=1)
                
                if holidays_found:
                    leave.holiday_warning = True
                    leave.holiday_warning_message = f"⚠️ Festivos detectados: {', '.join(holidays_found)}"
    
    @api.depends('employee_id', 'contract_id', 'date_from')
    def _compute_available_vacation_days(self):
        """Calcular días de vacaciones disponibles"""
        for leave in self:
            leave.available_vacation_days = 0
            if (leave.holiday_status_id.is_vacation or leave.holiday_status_id.is_vacation_money) and \
               leave.employee_id and leave.contract_id:
                date_end = leave.date_from.date() if leave.date_from else fields.Date.today()
                date_start = leave.contract_id.date_start
                days_contracted = leave.contract_id.dias360(date_start, date_end)
                days_unpaid = self._get_unpaid_absence_days(date_start, date_end, leave.employee_id)
                days_vacation = ((days_contracted - days_unpaid) * 15) / 360
                days_vacation = round(days_vacation, 4)
                days_enjoyed = self._get_enjoyed_vacation_days(leave.contract_id.id, leave.employee_id.id)
                leave.available_vacation_days = days_vacation - days_enjoyed
    
    def _get_enjoyed_vacation_days(self, contract_id, employee_id):
        """Obtener días de vacaciones ya disfrutados"""
        vacations = self.env['hr.vacation'].search([
            ('contract_id', '=', contract_id),
            ('employee_id', '=', employee_id)
        ])
        enjoyed_days = 0
        for vacation in vacations:
            if vacation.vacation_type == 'enjoy':
                enjoyed_days += vacation.business_units
            elif vacation.vacation_type == 'money':
                enjoyed_days += vacation.units_of_money
            if vacation.is_interrupted and vacation.days_returned > 0:
                enjoyed_days -= vacation.days_returned
        return enjoyed_days
    
    def action_draft(self):
        """Resetear ausencia a estado inicial (confirm en Odoo 18)"""
        for record in self:
            record._clean_leave()
        self.write({
            'state': 'confirm',
            'first_approver_id': False,
            'second_approver_id': False,
        })
        self.activity_update()
        return True

    def action_reset_confirm(self):
        """Resetear ausencia a confirmado - Odoo 18"""
        for record in self:
            record._clean_leave()
        return super(HolidaysRequest, self).action_reset_confirm()

    @api.depends('employee_id','date_from')
    def _inverse_get_contract(self):
        for record in self:
            if not record.employee_id or not record.date_from or not record.date_to:
                record.contract_id = False
                continue
            # Add a default contract if not already defined or invalid
            if record.contract_id and record.employee_id == record.contract_id.employee_id:
                continue
            contracts = record.employee_id._get_contracts(record.date_from.date(), record.date_to.date())
            record.contract_id = contracts[0] if contracts else False

    @api.constrains('date_from', 'date_to', 'employee_id')
    def _check_contract(self):
        for record in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', record.employee_id.id),('state', 'in', ['open', 'finished'])])
    
    @api.depends('leave_ids', 'leave_ids.days_used')
    def _days_used(self):
        for rec in self:
            rec.days_used += sum(value for value in rec.leave_ids.mapped('days_used') if isinstance(value, (int, float)))
    @api.onchange('ibc','force_ibc', 'number_of_days', 'date_from', 'date_to',)
    def force_ibc_amt(self):
        for record in self:
            if record.force_ibc and record.ibc != 0:
                record.payroll_value = (record.ibc / 30) * record.number_of_days
            else:
                record._compute_amount_license()
                
    def interrupt_vacation(self, interruption_date, reason_id, detail, days_returned, will_return=False, return_date=None):
        """Interrumpir vacaciones"""
        self.ensure_one()
        if not self.holiday_status_id.is_vacation:
            raise UserError(_("Solo se pueden interrumpir ausencias de tipo vacaciones."))
        if not interruption_date or interruption_date < self.date_from.date() or interruption_date > self.date_to.date():
            raise UserError(_("La fecha de interrupción debe estar dentro del período de vacaciones."))
        if days_returned <= 0:
            raise UserError(_("Debe indicar cuántos días se devuelven por la interrupción."))
        self.write({
            'is_vacation_interrupted': True,
            'vacation_interruption_date': interruption_date,
            'vacation_interruption_reason_id': reason_id,
            'vacation_interruption_detail': detail,
            'vacation_days_returned': days_returned,
            'vacation_will_return': will_return,
            'vacation_return_date': return_date,
            'date_to': datetime.combine(interruption_date, datetime.max.time())
        })
        if self.payroll_id and self.payroll_id.state in ['done', 'paid']:
            credit_note_vals = {
                'name': f"R{self.payroll_id.sequence_prefix}{self.employee_id.name}",
                'employee_id': self.employee_id.id,
                'date_from': self.date_from.date(),
                'date_to': interruption_date,
                'contract_id': self.contract_id.id,
                'struct_id': self.payroll_id.struct_id.id,
                'credit_note': True,
                'leave_id': self.id,
                'worked_days_line_ids': []  # Se calculará después
            }
            credit_note = self.env['hr.payslip'].create(credit_note_vals)
            message = _(f"""
            Vacaciones interrumpidas:
            - Fecha: {interruption_date}
            - Motivo: {self.vacation_interruption_reason_id.name}
            - Días devueltos: {days_returned}
            - Nota crédito: {credit_note.name}
            """)
            self.message_post(body=message)
            return {
                'name': _('Nota Crédito por Interrupción'),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip',
                'view_mode': 'form',
                'res_id': credit_note.id,
                'target': 'current'
            }
        return True
       
    @api.onchange('date_from', 'date_to', 'employee_id', 'holiday_status_id', 'number_of_days')
    def _compute_amount_license(self):
        for record in self:
            contracts = record.env['hr.contract'].search([('employee_id', '=', record.employee_id.id),('state', 'in', ['open', 'finished'])])
            ibc = 0.0
            amount = 0.0
            if contracts and self.date_to:
                company_id = record.employee_company_id.id if record.employee_company_id else None
                annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                    record.date_to.date().year, company_id=company_id, raise_if_not_found=False
                )

                # FORZAR SUELDO BASE SI ES TIEMPO PARCIAL
                if record.contract_id and record.contract_id.parcial:
                    # Si el contrato es tiempo parcial, siempre usar el sueldo como base
                    record.ibc = record.contract_id.wage
                elif record.holiday_status_id.liquidacion_value == 'IBC':
                    record.ibc = self._get_ibc_last_month(record.date_to.date(), record.contract_id)
                elif record.holiday_status_id.liquidacion_value in ['WAGE', 'MIN']:
                    record.ibc = self._get_wage_in_date(record.date_to.date(), record.contract_id)
                elif record.holiday_status_id.liquidacion_value == 'YEAR':
                    record.ibc = self._get_average_last_year(record.contract_id)
                else:
                    record.ibc = record.contract_id.wage
                if record.line_ids:
                    record.payroll_value = sum(x.amount for x in record.line_ids)
                else:
                    if record.request_unit_hours:
                        record.payroll_value = (record.ibc / annual_parameters.hours_monthly) * record.number_of_hours_display
                    else:
                        record.payroll_value = (record.ibc / 30) * record.number_of_days

    def _get_wage_in_date(self, process_date, contract):
        wage_in_date = contract.wage
        for change in sorted(contract.change_wage_ids, key=lambda x: x.date_start):
            if process_date >= change.date_start:
                wage_in_date = change.wage
        return wage_in_date

    def _get_ibc_last_month(self, date_to, contract):
        """
        Obtiene el IBC del mes anterior considerando las reglas de seguridad social.
        """
        from_date = (date_to.replace(day=1) - relativedelta(months=1))
        to_date = (date_to.replace(day=1) - relativedelta(days=1))
        company_id = contract.company_id.id if contract and contract.company_id else None
        annual_parameters = self.env['hr.annual.parameters'].get_for_year(
            date_to.year, company_id=company_id, raise_if_not_found=True
        )
        payslip_lines = self.env['hr.payslip.line'].search([
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.contract_id', '=', contract.id),
            ('date_from', '>=', from_date),
            ('date_from', '<=', to_date),
        ])
        lines_by_type = {
            'base_ss': [],
            'no_salarial': [],
        }

        for line in payslip_lines:
            if line.salary_rule_id.base_seguridad_social:
                lines_by_type['base_ss'].append(line)
            
            if (line.salary_rule_id.category_id.code == 'DEV_NO_SALARIAL' or
                (line.salary_rule_id.category_id.parent_id and 
                line.salary_rule_id.category_id.parent_id.code == 'DEV_NO_SALARIAL')):
                lines_by_type['no_salarial'].append(line)

        value_base_ss = sum(abs(line.total) for line in lines_by_type['base_ss'])
        value_no_salarial = sum(abs(line.total) for line in lines_by_type['no_salarial'])

        gran_total = value_base_ss + value_no_salarial
        statute_value = gran_total * (annual_parameters.value_porc_statute_1395 / 100)
        total_statute = value_no_salarial - statute_value
        base_40 = max(total_statute, 0)
        ibc = value_base_ss + base_40
        calculo_detalle = {
            'periodo': {
                'desde': from_date,
                'hasta': to_date
            },
            'valores': {
                'base_seguridad_social': value_base_ss,
                'no_salarial': value_no_salarial,
                'total': gran_total
            },
            'estatuto_1395': {
                'porcentaje': annual_parameters.value_porc_statute_1395,
                'valor': statute_value
            },
            'calculo_40': {
                'excedente_estatuto': total_statute,
                'base_aplicada': base_40
            },
            'ibc_final': ibc,
            'detalle_conceptos': {
                'base_ss': [{'code': line.salary_rule_id.code, 
                            'name': line.salary_rule_id.name,
                            'valor': line.total} 
                        for line in lines_by_type['base_ss']],
                'no_salarial': [{'code': line.salary_rule_id.code,
                            'name': line.salary_rule_id.name,
                            'valor': line.total} 
                            for line in lines_by_type['no_salarial']]
            }
        }
        if (contract.fecha_ibc and 
            from_date.year == contract.fecha_ibc.year and 
            from_date.month == contract.fecha_ibc.month):
            return contract.u_ibc

        return ibc if ibc else contract.wage

    def calculate_average_salary(self, contract_id, end_date, months=3):
        calculated_start = end_date - relativedelta(months=months)
        start_date = max(calculated_start, contract_id.date_start)
        query = """
            WITH RECURSIVE date_ranges AS (
                SELECT
                    %s::date as date_from,
                    CASE
                        WHEN date_trunc('month', %s::date) = date_trunc('month', %s::date)
                        THEN %s::date
                        ELSE (date_trunc('month', %s::date) + interval '1 month - 1 day')::date
                    END as date_to,
                    date_trunc('month', %s::date) as month_start
                
                UNION ALL
                
                SELECT
                    (month_start + interval '1 month')::date as date_from,
                    CASE
                        WHEN date_trunc('month', month_start + interval '1 month') = date_trunc('month', %s::date)
                        THEN %s::date
                        ELSE ((month_start + interval '2 month - 1 day'))::date
                    END as date_to,
                    month_start + interval '1 month' as month_start
                FROM date_ranges
                WHERE month_start < date_trunc('month', %s::date)
            ),
            period_data AS (
                SELECT
                    dr.date_from,
                    dr.date_to,
                    CASE
                        WHEN extract(day from dr.date_from) = 1 AND 
                            extract(day from dr.date_to) >= 30
                        THEN 30
                        ELSE LEAST(
                            extract(day from dr.date_to) - 
                            extract(day from dr.date_from) + 1,
                            30 - extract(day from dr.date_from) + 1
                        )
                    END as days,
                    COALESCE(
                        (
                            SELECT wage
                            FROM hr_contract_change_wage wcw
                            WHERE wcw.contract_id = %s
                            AND wcw.date_start <= dr.date_from
                            ORDER BY wcw.date_start DESC
                            LIMIT 1
                        ),
                        %s
                    ) as wage
                FROM date_ranges dr
            )
            SELECT
                date_from,
                date_to,
                days,
                wage,
                (wage / 30.0 * days) as amount
            FROM period_data
            ORDER BY date_from;
        """
        self.env.cr.execute(query, (
            start_date, start_date, end_date, end_date, start_date, start_date,
            end_date, end_date, end_date,
            contract_id.id, contract_id.wage
        ))
        periods = self.env.cr.dictfetchall()
        if not periods:
            return contract_id.wage
        total_amount = 0
        total_days = 0
        for period in periods:
            total_amount += period['amount']
            total_days += period['days']
        average_salary = round((total_amount / total_days) * 30, 2) if total_days > 0 else contract_id.wage
        return average_salary

    def _get_average_last_year(self, contract):
        import logging
        _logger = logging.getLogger(__name__)
        
        def formato_moneda(monto):
            return "{:,.2f}".format(monto)
        
        detalles_log = []
        
        # Verificación inicial de fechas
        if not self.date_to or not self.date_from:
            return 0
            
        date_to = self.date_from.date()
        date_from = (date_to - relativedelta(years=1))
        initial_process_date = max(contract.date_start, date_from)
        
        # Registro del análisis de períodos
        detalles_log.append(f"Análisis de Período:")
        detalles_log.append(f"- Fecha Desde: {date_from}")
        detalles_log.append(f"- Fecha Hasta: {date_to}")
        detalles_log.append(f"- Inicio de Contrato: {contract.date_start}")
        detalles_log.append(f"- Fecha Inicial de Proceso: {initial_process_date}")
        base_field = 'base_vacaciones'
        # Determinación del tipo de cálculo
        if self.is_vacation:
            base_field = 'base_vacaciones'
            detalles_log.append("Tipo: Cálculo de vacaciones (base_vacaciones)")
        if self.is_vacation_money:
            base_field = 'base_vacaciones_dinero'
            detalles_log.append("Tipo: Cálculo de dinero de vacaciones (base_vacaciones_dinero)")
        
        PayslipLine = self.env['hr.payslip.line']
        Payslip = self.env['hr.payslip']
        AccumulatedPayroll = self.env['hr.accumulated.payroll']
        
        def get_payslip_total(contract_id, date_start, date_end):
            # Usar base_field definido en el scope exterior
            # Consulta SQL para obtener el total de las nóminas
            query_total = """
                SELECT COALESCE(SUM(pl.total), 0) as total
                FROM hr_payslip_line pl
                INNER JOIN hr_payslip hp ON pl.slip_id = hp.id
                INNER JOIN hr_salary_rule sr ON pl.salary_rule_id = sr.id
                INNER JOIN hr_salary_rule_category src ON sr.category_id = src.id
                WHERE hp.state IN ('done', 'paid')
                AND hp.contract_id = %(contract_id)s
                AND sr.code != 'AUX000'
                AND sr.""" + base_field + """ = true
                AND src.code != 'BASIC'
                AND hp.date_from >= %(date_start)s
                AND hp.date_from <= %(date_end)s
            """
            self.env.cr.execute(query_total, {
                'contract_id': contract.id,
                'date_start': date_start,
                'date_end': date_end
            })
            return self.env.cr.fetchone()[0] or 0
        
        # Cálculo de totales de nómina
        payslip_total = get_payslip_total(contract, initial_process_date, self.date_to)
        detalles_log.append(f"\nAnálisis de Nómina:")
        detalles_log.append(f"- Total de nóminas: {formato_moneda(payslip_total)}")
        
        # Búsqueda de nóminas acumuladas
        accumulated_domain = [
            ('employee_id', '=', contract.employee_id.id),
            ('date', '>=', initial_process_date),
            ('date', '<=', self.date_to),
            ('salary_rule_id.code', '!=', 'AUX000'),
            ('salary_rule_id.' + base_field, '=', True),
            ('salary_rule_id.category_id.code', '!=', 'BASIC'),
        ]
        accumulated_payrolls = AccumulatedPayroll.search(accumulated_domain)
        accumulated_total = sum(accumulated_payrolls.mapped('amount'))
        detalles_log.append(f"- Total de nóminas acumuladas: {formato_moneda(accumulated_total)}")
        detalles_log.append(f"- Número de registros acumulados encontrados: {len(accumulated_payrolls)}")
        
        # Cálculo de días
        dias_trabajados = min(self._days360(initial_process_date, self.date_to), 360)
        dias_ausencias = self._get_unpaid_absence_days(initial_process_date, self.date_to, contract.employee_id)
        dias_liquidacion = dias_trabajados - dias_ausencias
        
        detalles_log.append(f"\nAnálisis de Días:")
        detalles_log.append(f"- Días trabajados totales (base 360): {dias_trabajados}")
        detalles_log.append(f"- Días de ausencia no pagados: {dias_ausencias}")
        detalles_log.append(f"- Días netos de liquidación: {dias_liquidacion}")
        
        # Cálculos finales
        wage_average = self.calculate_average_salary(contract, date_to, 12)
        amount = payslip_total + accumulated_total
        
        detalles_log.append(f"\nCálculos Finales:")
        detalles_log.append(f"- Salario base promedio: {formato_moneda(wage_average)}")
        detalles_log.append(f"- Monto total (nómina + acumulado): {formato_moneda(amount)}")
        
        result = 0
        if dias_liquidacion > 0:
            promedio_diario = amount/dias_liquidacion
            factor_mensual = promedio_diario * 30
            result = wage_average + factor_mensual
            detalles_log.append(f"- Promedio diario: {formato_moneda(promedio_diario)}")
            detalles_log.append(f"- Factor mensual (prom. diario * 30): {formato_moneda(factor_mensual)}")
            detalles_log.append(f"- Resultado final: {formato_moneda(result)}")
        else:
            detalles_log.append("- Resultado final: 0 (sin días de liquidación)")
        
        # Registro del análisis completo
        
        return result
    def _days360(self, start_date, end_date, method_eu=True):
        """
        Calcula días entre fechas usando método comercial 360.
        Usa la función estándar days360 de hr_payslip_constants.
        """
        return days360(start_date, end_date)

    def _get_unpaid_absence_days(self, start_date, end_date, employee):
        leaves = self.env['hr.leave'].search([
            ('date_from', '>=', start_date),
            ('date_to', '<=', end_date),
            ('state', '=', 'validate'),
            ('employee_id', '=', employee.id),
            ('unpaid_absences', '=', True)
        ])
        absence_histories = self.env['hr.absence.history'].search([
            ('star_date', '>=', start_date),
            ('end_date', '<=', end_date),
            ('employee_id', '=', employee.id),
            ('leave_type_id.unpaid_absences', '=', True)
        ])
        return sum(leave.number_of_days for leave in leaves) + sum(absence.days for absence in absence_histories)

    def _calculate_wage_average(self, start_date, end_date, contract):
        wage_average = 0
        current_date = start_date
        while current_date <= end_date:
            if current_date.day != 31:
                wage = self._get_wage_in_date(current_date, contract)
                if current_date.month == 2 and current_date.day == 28 and (current_date + timedelta(days=1)).day != 29:
                    wage_average += (wage / 30) * 3
                elif current_date.month == 2 and current_date.day == 29:
                    wage_average += (wage / 30) * 2
                else:
                    wage_average += wage / 30
            current_date += timedelta(days=1)
        return wage_average

    @api.onchange('is_extension')
    def _onchange_extension_id(self):
        for rec in self:
            if rec.date_to and rec.is_extension:
                last_leave = self.env['hr.leave'].search([('date_to', '<', rec.date_to),('state', '=', 'validate'),('holiday_status_id','=',rec.holiday_status_id.id),('employee_id','=',rec.employee_id.id)], order='date_to desc', limit=1)
                rec.extension_id = last_leave.id
            else:
                rec.extension_id = False

    @api.onchange('date_from', 'date_to', 'employee_id')
    def _onchange_leave_dates(self):
        if self.holiday_status_id.is_vacation == False:            
            if self.date_from and self.date_to:
                self.number_of_days = self._get_number_of_days(self.date_from, self.date_to, self.employee_id.id)['days']
            else:
                self.number_of_days = 0

    @api.onchange('disability_during_vacation', 'disability_start_date', 'disability_days')
    def _onchange_disability_during_vacation(self):
        """
        Al registrar incapacidad durante vacaciones, calcular nuevas fechas.
        Según legislación colombiana (Art. 186 CST), los días de incapacidad se devuelven al empleado.
        Solo aplica para ausencias de tipo vacaciones.
        """
        for leave in self:
            if leave.is_vacation and leave.disability_during_vacation and leave.disability_start_date and leave.disability_days > 0:
                # Validar que la fecha de inicio de incapacidad esté dentro del período de vacaciones
                if leave.date_from and leave.date_to:
                    disability_date_only = leave.disability_start_date
                    date_from_only = leave.date_from.date() if isinstance(leave.date_from, datetime) else leave.date_from
                    date_to_only = leave.date_to.date() if isinstance(leave.date_to, datetime) else leave.date_to

                    if date_from_only <= disability_date_only <= date_to_only:
                        # Sugerir nueva fecha de regreso (extendiendo por los días de incapacidad)
                        if leave.return_date:
                            new_return_date = leave.return_date + timedelta(days=int(leave.disability_days))
                            leave.vacation_return_date = new_return_date
                            leave.vacation_will_return = True
                        elif leave.date_to:
                            new_return_date = date_to_only + timedelta(days=int(leave.disability_days))
                            leave.vacation_return_date = new_return_date
                            leave.vacation_will_return = True
                    else:
                        raise ValidationError(
                            f'La fecha de inicio de incapacidad debe estar dentro del período de vacaciones '
                            f'({date_from_only.strftime("%d/%m/%Y")} - {date_to_only.strftime("%d/%m/%Y")})'
                        )

    @api.onchange('employee_id','holiday_status_id')
    def _onchange_info_entity(self):
        for record in self:
            if record.employee_id and record.holiday_status_id:
                record.type_of_entity = record.holiday_status_id.type_of_entity_association.id
                for entities in record.employee_id.social_security_entities:
                    if entities.contrib_id.id == record.holiday_status_id.type_of_entity_association.id:                        
                        record.entity = entities.partner_id.id
            else:
                record.type_of_entity = False
                record.entity = False
                record.diagnostic = False

    @api.constrains('date_from', 'date_to', 'employee_id')
    def _check_date(self):
        if self.env.context.get('leave_skip_date_check', False):
            return

        all_employees = self.employee_id
        all_leaves = self.search([
            ('date_from', '<', max(self.mapped('date_to'))),
            ('date_to', '>', min(self.mapped('date_from'))),
            ('employee_id', 'in', all_employees.ids),
            ('id', 'not in', self.ids),
            ('state', 'not in', ['cancel', 'refuse']),
        ])
        for holiday in self:
            if holiday.holiday_status_id.code == 'VAC_MONEY' or holiday.holiday_status_id.is_vacation_money:
                continue 
            domain = [
                ('date_from', '<', holiday.date_to),
                ('date_to', '>', holiday.date_from),
                ('id', '!=', holiday.id),
                ('state', 'not in', ['cancel', 'refuse']),
            ]

            employee_id = (holiday.employee_id | holiday.employee_id).ids
            search_domain = domain + [('employee_id', 'in', employee_id)]
            conflicting_holidays = all_leaves.filtered_domain(search_domain)

            # Filter out VAC_MONEY leaves from conflicting_holidays
            conflicting_holidays = conflicting_holidays.filtered(lambda h: h.holiday_status_id.code != 'VAC_MONEY' or h.holiday_status_id.is_vacation_money)

            if conflicting_holidays:
                conflicting_holidays_list = []
                # Do not display the name of the employee if the conflicting holidays have an employee_id.user_id equivalent to the user id
                holidays_only_have_uid = bool(holiday.employee_id)
                holiday_states = dict(conflicting_holidays.fields_get(allfields=['state'])['state']['selection'])
                for conflicting_holiday in conflicting_holidays:
                    conflicting_holiday_data = {}
                    conflicting_holiday_data['employee_name'] = conflicting_holiday.employee_id.name
                    conflicting_holiday_data['date_from'] = format_date(self.env, min(conflicting_holiday.mapped('date_from')))
                    conflicting_holiday_data['date_to'] = format_date(self.env, min(conflicting_holiday.mapped('date_to')))
                    conflicting_holiday_data['state'] = holiday_states[conflicting_holiday.state]
                    if conflicting_holiday.employee_id.user_id.id != self.env.uid:
                        holidays_only_have_uid = False
                    if conflicting_holiday_data not in conflicting_holidays_list:
                        conflicting_holidays_list.append(conflicting_holiday_data)
                if not conflicting_holidays_list:
                    return
                conflicting_holidays_strings = []
                if holidays_only_have_uid:
                    for conflicting_holiday_data in conflicting_holidays_list:
                        conflicting_holidays_string = _('From %(date_from)s To %(date_to)s - %(state)s',
                                                        date_from=conflicting_holiday_data['date_from'],
                                                        date_to=conflicting_holiday_data['date_to'],
                                                        state=conflicting_holiday_data['state'])
                        conflicting_holidays_strings.append(conflicting_holidays_string)
                    raise ValidationError(_('You can not set two time off that overlap on the same day.\nExisting time off:\n%s') %
                                          ('\n'.join(conflicting_holidays_strings)))
                for conflicting_holiday_data in conflicting_holidays_list:
                    conflicting_holidays_string = _('%(employee_name)s - From %(date_from)s To %(date_to)s - %(state)s',
                                                    employee_name=conflicting_holiday_data['employee_name'],
                                                    date_from=conflicting_holiday_data['date_from'],
                                                    date_to=conflicting_holiday_data['date_to'],
                                                    state=conflicting_holiday_data['state'])
                    conflicting_holidays_strings.append(conflicting_holidays_string)
                conflicting_employees = set(employee_id) - set(conflicting_holidays.employee_id.ids)
                # Only one employee has a conflicting holiday
                if len(conflicting_employees) == len(employee_id) - 1:
                    raise ValidationError(_('You can not set two time off that overlap on the same day for the same employee.\nExisting time off:\n%s') %
                                          ('\n'.join(conflicting_holidays_strings)))
                raise ValidationError(_('You can not set two time off that overlap on the same day for the same employees.\nExisting time off:\n%s') %
                                      ('\n'.join(conflicting_holidays_strings)))

    @api.constrains('date_from', 'date_to', 'employee_id')
    def _check_date_state(self):
        if self.env.context.get('leave_skip_state_check'):
            return
        for holiday in self:
            if holiday.state in ['cancel', 'refuse', 'validate1', 'validate']:
                raise ValidationError(_("This modification is not allowed in the current state."))

    @api.onchange('number_of_days', 'request_date_from')
    def onchange_number_of_days_vacations(self):
        """
        Calcula los días de vacaciones considerando días laborales, festivos y días 31.
        También valida contra los días acumulados disponibles.
        """
        for record in self:
            try:
                # Solo proceder si es vacaciones y tiene fecha inicial
                if not (record.holiday_status_id.is_vacation and record.request_date_from):
                    continue

                # Configuración inicial
                lst_days = [5, 6] if not record.employee_id.sabado else [6]
                date_to = record.request_date_from - timedelta(days=1)
                cant_days = record.number_of_days
                
                # Contadores
                holidays = business_days = days_31_b = days_31_h = 0
                
                # Calcular días
                while cant_days > 0:
                    date_add = date_to + timedelta(days=1)
                    if not date_add.weekday() in lst_days:
                        #Obtener dias festivos parametrizados
                        obj_holidays = self.env['lavish.holidays'].search([('date', '=', date_add)])
                        if obj_holidays:
                            holidays += 1
                            days_31_h += 1 if date_add.day == 31 else 0
                            date_to = date_add
                        else:
                            cant_days = cant_days - 1     
                            business_days += 1
                            days_31_b += 1 if date_add.day == 31 else 0
                            date_to = date_add
                    else:
                        holidays += 1
                        days_31_h += 1 if date_add.day == 31 else 0
                    
                    date_to = date_add
                
                # Verificar días acumulados disponibles
                contract_domain = [
                    ('employee_id', '=', record.employee_id.id),
                    ('state', 'in', ['open', 'finished']),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', fields.Date.today())
                ]
                
                contract = self.env['hr.contract'].search(contract_domain, limit=1)
                
                if contract:
                    accumulated_days = contract.get_accumulated_vacation_days()
                    
                    # Actualizar campos relacionados con días acumulados
                    record.write({
                        'accumulated_vacation_days': accumulated_days,
                        'alert_days_vacation': business_days > accumulated_days
                    })
                    
                    if business_days > accumulated_days:
                        return {
                            'warning': {
                                'title': _('Advertencia'),
                                'message': _(
                                    'Los días solicitados ({:.2f}) superan los días disponibles ({:.2f}).'
                                ).format(business_days, accumulated_days)
                            }
                        }
                else:
                    _logger.warning(f"No se encontró contrato activo para el empleado {record.employee_id.name}")
                    return {
                        'warning': {
                            'title': _('Advertencia'),
                            'message': _('El empleado {} no tiene un contrato activo.').format(
                                record.employee_id.name
                            )
                        }
                    }
                
            except Exception as e:
                _logger.error('Error en cálculo de días de vacaciones: %s', str(e))
                return {
                    'warning': {
                        'title': _('Error'),
                        'message': _('Error al calcular los días de vacaciones. Por favor, verifique la configuración.')
                    }
                }

    # @api.constrains('state', 'number_of_days', 'holiday_status_id')
    # def _check_holidays(self):
    #     mapped_days = self.mapped('holiday_status_id').get_employees_days(self.mapped('employee_id').ids)
    #     for holiday in self:
    #         if holiday.holiday_type != 'employee' or not holiday.employee_id or holiday.holiday_status_id.requires_allocation == 'no':
    #             continue
    #         leave_days = mapped_days[holiday.employee_id.id][holiday.holiday_status_id.id]
    #         if float_compare(leave_days['remaining_leaves'], 0, precision_digits=2) == -1 or float_compare(leave_days['virtual_remaining_leaves'], 0, precision_digits=2) == -1:
    #             continue
    #             # # Se comenta validación original de odoo
    #             # raise ValidationError(_('The number of remaining time off is not sufficient for this time off type.\n'
    #             #                         'Please also check the time off waiting for validation.'))

    def action_force_paid(self):
        #Validación adjunto
        for holiday in self:
            holiday.line_ids.write({'state': 'paid'})
    def action_confirm(self):
        obj = super(HolidaysRequest, self).action_confirm()
        #Creación registro en el historico de vacaciones cuando es una ausencia no remunerada
        for record in self:
            if not record.line_ids:
                record.compute_holiday()
            record.line_ids.write({'state': 'validated'})
        return obj
    def action_approve(self, check_state=True):
        #Validación adjunto
        for holiday in self:
            if not holiday.line_ids:
                holiday.compute_holiday()
            # Validacion compañia
            if self.env.company.id != holiday.employee_id.company_id.id:
                raise ValidationError(_('El empleado ' + holiday.employee_id.name + ' esta en la compañía ' + holiday.employee_id.company_id.name + ' por lo cual no se puede aprobar debido a que se encuentra ubicado en la compañía ' + self.env.company.name + ', seleccione la compañía del empleado para aprobar la ausencia.'))
            # Validación adjunto
            if holiday.holiday_status_id.obligatory_attachment:
                attachment = self.env['ir.attachment'].search([('res_model', '=', 'hr.leave'),('res_id','=',holiday.id)])    
                if not attachment:    
                    raise ValidationError(_('Es obligatorio agregar un adjunto para la ausencia '+holiday.display_name+'.'))
            holiday.line_ids.write({'state': 'validated'})
        #Ejecución metodo estandar
        
        obj = super(HolidaysRequest, self).action_approve(check_state)
        #Creación registro en el historico de vacaciones cuando es una ausencia no remunerada
        for record in self:
            if not record.line_ids:
                record.compute_holiday()
            if record.unpaid_absences:
                days_unpaid_absences = record.number_of_days
                days_vacation_represent = round((days_unpaid_absences * 15) / 365,0)
                if days_vacation_represent > 0:
                    # Obtener contrato y ultimo historico de vacaciones
                    obj_contract = self.env['hr.contract'].search([('employee_id','=',record.employee_id.id),('state', 'in', ['open', 'finished'])])
                    date_vacation = obj_contract.date_start
                    obj_vacation = self.env['hr.vacation'].search(
                        [('employee_id', '=', record.employee_id.id), ('contract_id', '=', obj_contract.id)])
                    if obj_vacation:
                        for history in sorted(obj_vacation, key=lambda x: x.final_accrual_date):
                            date_vacation = history.final_accrual_date + timedelta(
                                days=1) if history.final_accrual_date > date_vacation else date_vacation
                    #Fechas de causación
                    initial_accrual_date = date_vacation
                    final_accrual_date = date_vacation + timedelta(days=days_vacation_represent)

                    info_vacation = {
                        'employee_id': record.employee_id.id,
                        'contract_id': obj_contract.id,
                        'initial_accrual_date': initial_accrual_date,
                        'final_accrual_date': final_accrual_date,
                        'departure_date': record.request_date_from,
                        'return_date': record.request_date_to,
                        'business_units': days_vacation_represent,
                        'leave_id': record.id
                    }
                    self.env['hr.vacation'].create(info_vacation)

        return obj

    def action_refuse(self):
        obj = super(HolidaysRequest, self).action_refuse()
        for record in self:
            self.env['hr.vacation'].search([('leave_id','=',record.id)]).unlink()
        return obj

    def action_validate(self, check_state=True):
        for holiday in self:
            if not holiday.line_ids:
                holiday.compute_holiday()
            if holiday.holiday_status_id.obligatory_attachment:
                attachment = self.env['ir.attachment'].search([('res_model', '=', 'hr.leave'), ('res_id', '=', holiday.id)])
                if not attachment:
                    raise ValidationError(_('Es obligatorio agregar un adjunto para la ausencia ' + holiday.display_name + '.'))
            holiday.line_ids.write({'state': 'validated'})
        # Ejecución metodo estandar
        obj = super(HolidaysRequest, self).action_validate()
        # Enviar correo automático para vacaciones aprobadas
        for holiday in self:
            if holiday.holiday_status_id.is_vacation or holiday.holiday_status_id.is_vacation_money:
                holiday.action_send_vacation_email()
        return obj

    def action_send_vacation_email(self):
        """Envía correo de notificación de vacaciones aprobadas al empleado"""
        self.ensure_one()
        template = self.env.ref('lavish_hr_payroll.mail_template_vacation_approved', raise_if_not_found=False)
        if template and self.employee_id.work_email:
            template.send_mail(self.id, force_send=True)
            return True
        return False

    def action_print_vacation_certificate(self):
        """Genera el certificado de vacaciones en PDF"""
        self.ensure_one()
        if not (self.holiday_status_id.is_vacation or self.holiday_status_id.is_vacation_money):
            raise UserError(_('El certificado de vacaciones solo está disponible para ausencias de tipo vacaciones.'))
        return self.env.ref('lavish_hr_payroll.report_vacation_certificate_action').report_action(self)

    def action_send_vacation_certificate(self):
        """Envía el certificado de vacaciones por correo al empleado"""
        self.ensure_one()
        if not (self.holiday_status_id.is_vacation or self.holiday_status_id.is_vacation_money):
            raise UserError(_('El certificado de vacaciones solo está disponible para ausencias de tipo vacaciones.'))
        template = self.env.ref('lavish_hr_payroll.mail_template_vacation_approved', raise_if_not_found=False)
        if template:
            return template.send_mail(self.id, force_send=True)
        raise UserError(_('No se encontró la plantilla de correo para vacaciones.'))

    @api.model_create_multi
    def create(self, vals_list):
        IrSequence = self.env['ir.sequence']
        
        for vals in vals_list:
            # Generate sequence for each record
            vals['sequence'] = IrSequence.next_by_code('seq.hr.leave') or ''
            
            # Handle employee identification lookup
            if vals.get('employee_identification'):
                obj_employee = self.env['hr.employee'].search(
                    [('identification_id', '=', vals.get('employee_identification'))],
                    limit=1
                )
                if obj_employee:
                    vals['employee_id'] = obj_employee.id
            
            # Handle employee id lookup
            if vals.get('employee_id'):
                obj_employee = self.env['hr.employee'].search(
                    [('id', '=', vals.get('employee_id'))],
                    limit=1
                )
                if obj_employee:
                    vals['employee_identification'] = obj_employee.identification_id

        return super().create(vals_list)

    #############################################################################################
    #GET HR_LEAVE_LINE
    #############################################################################################

    def compute_line(self):
        self.compute_holiday()

    def _get_number_of_days_batch_co(self, date_from, date_to, employee_ids):
        """ Returns a float equals to the timedelta between two dates given as string."""
        employee = self.env['hr.employee'].browse(employee_ids)
        # We force the company in the domain as we are more than likely in a compute_sudo
        domain = [('time_type', '=', 'leave'),
                  ('company_id', 'in', self.env.company.ids + self.env.context.get('allowed_company_ids', []))]
        result = employee._get_work_days_data_batch(date_from, date_to, compute_leaves=False, calendar=False,  domain=domain)
        for employee_id in result:
            if self.request_unit_half and result[employee_id]['hours'] > 0:
                result[employee_id]['days'] = 0.5
        return result

    def _get_number_of_days(self, date_from, date_to, employee_id):
        """ Returns a float equals to the timedelta between two dates given as string."""
        if employee_id:
            return self._get_number_of_days_batch_co(date_from, date_to, employee_id)[employee_id]

        today_hours = self.env.company.resource_calendar_id.get_work_hours_count(
            datetime.combine(date_from.date(), time.min),
            datetime.combine(date_from.date(), time.max),
            False)

        hours = self.env.company.resource_calendar_id.get_work_hours_count(date_from, date_to)
        hours_per_day = self._get_hours_per_day(date_from.date()) if self else HOURS_PER_DAY
        days = hours / (today_hours or hours_per_day) if not self.request_unit_half else 0.5
        return {'days': days, 'hours': hours}

    def _get_leaves_on_public_holiday(self):
        return False #self.filtered(lambda l: l.employee_id and not l.number_of_days)

    def _clean_leave(self):
        self.line_ids.unlink()

    def _is_holiday(self, date):
        """Verifica si una fecha es festivo buscando en la tabla de festivos"""
        if not date:
            return False
        holiday = self.env['lavish.holidays'].search([('date', '=', date)], limit=1)
        return bool(holiday)

    def _should_apply_day_31(self, holiday):
        """
        Determina si se debe aplicar el día 31 para la ausencia dada.
        
        :param holiday: Registro de ausencia
        :return: True si se debe aplicar el día 31, False en caso contrario
        """
        return self.apply_day_31
    
    def _compute_return_date(self):
        self.ensure_one()
        if not self.date_to:
            return False
        end_date = self.date_to.date()
        next_day = end_date + timedelta(days=1)
        works_saturday = self.employee_id.sabado
        if self.holiday_status_id.evaluates_day_off:
            while True:
                is_saturday = next_day.weekday() == 5
                is_sunday = next_day.weekday() == 6
                is_holiday = self.env['lavish.holidays'].ensure_holidays(next_day)
                if (is_saturday and not works_saturday) or is_sunday or is_holiday:
                    next_day += timedelta(days=1)
                else:
                    break
        return next_day
    
    def calcular_valor_pago_incapacidad(self, day_data, current_date, sequence, is_rest_day, is_day_31):
        """
        Calcula el valor de pago para un día de ausencia.

        Returns:
            tuple: (amount_real, ibc_day, ibc_base, rate_applied, base_type, ibc_original)
                - amount_real: Valor a pagar por el día
                - ibc_day: IBC diario usado para el cálculo
                - ibc_base: Base mensual usada
                - rate_applied: Porcentaje aplicado (0-100)
                - base_type: Tipo de base usada ('ibc', 'wage', 'smmlv', 'year', 'forced')
                - ibc_original: IBC del mes anterior (para mostrar si es diferente a ibc_base)
        """
        holiday = self

        apply_day_31 = holiday.holiday_status_id.apply_day_31
        discount_rest_day = holiday.holiday_status_id.discount_rest_day
        pagar_festivos = holiday.evaluates_day_off
        liquidacion_type = holiday.holiday_status_id.liquidacion_value
        company_id = holiday.employee_company_id.id if holiday.employee_company_id else None
        annual_parameters = self.env['hr.annual.parameters'].get_for_year(
            holiday.date_from.year, company_id=company_id, raise_if_not_found=False
        )
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
        hours_monthly = annual_parameters.hours_monthly if annual_parameters else 240

        # Guardar el IBC del mes anterior (siempre disponible para comparación)
        ibc_original = holiday.ibc or 0

        if is_day_31 and not apply_day_31:
            return 0, 0, 0, 0, False, 0

        if is_rest_day and discount_rest_day and not pagar_festivos:
            return 0, 0, 0, 0, False, 0

        # DETERMINAR BASE SEGÚN PRIORIDAD DE FORZADOS
        # IMPORTANTE: Separar valor a PAGAR (pay_amount) del IBC para seguridad social (ibc_base)
        base_type = 'ibc'

        # 1. Si hay base forzada manualmente, usar esa para TODO
        if holiday.force_base_amount and holiday.force_base_amount > 0:
            pay_amount = holiday.force_base_amount
            ibc_base = holiday.force_base_amount
            base_type = 'forced'
        # 2. Si está marcado forzar salario mínimo
        elif holiday.force_min_wage:
            pay_amount = smmlv
            ibc_base = smmlv
            base_type = 'smmlv'
        # 3. Si es tiempo parcial, usar sueldo
        elif holiday.contract_id.parcial:
            pay_amount = holiday.contract_id.wage
            ibc_base = holiday.contract_id.wage
            base_type = 'wage'
        # 4. Según tipo de liquidación del tipo de ausencia
        elif liquidacion_type == 'IBC':
            # SEPARACIÓN: Pagar con sueldo, pero IBC con mes anterior
            # El empleado recibe su sueldo normal
            pay_amount = holiday.contract_id.wage
            # El IBC para seguridad social usa el mes anterior
            ibc_base = holiday.ibc or holiday.ibc_pila or holiday.contract_id.wage
            base_type = 'ibc'
        elif liquidacion_type == 'YEAR':
            pay_amount = holiday._get_average_last_year(holiday.contract_id)
            ibc_base = pay_amount
            base_type = 'year'
        elif liquidacion_type == 'MIN':
            pay_amount = smmlv
            ibc_base = smmlv
            base_type = 'smmlv'
        else:  # WAGE
            pay_amount = holiday.contract_id.wage
            ibc_base = holiday.contract_id.wage
            base_type = 'wage'

        # Calcular IBC diario (para seguridad social)
        ibc_day = ibc_base / 30 if ibc_base else 0

        rate, rule = holiday.holiday_status_id.get_rate_concept_id(sequence)
        rate_applied = (rate * 100) if rate else 100.0

        # Calcular valor a PAGAR usando pay_amount (sueldo del contrato para incapacidades)
        if holiday.holiday_status_id.code == 'EGA' and sequence <= holiday.holiday_status_id.num_days_no_assume:
            rate_applied = 100.0  # Empresa paga 100% en primeros días
            if holiday.request_unit_hours:
                amount_real = (pay_amount / hours_monthly) * day_data['hours']
            else:
                amount_real = pay_amount / 30
        elif holiday.holiday_status_id.novelty == 'irl' and sequence == 1:
            rate_applied = 100.0  # Primer día ARL paga 100%
            if holiday.request_unit_hours:
                amount_real = (pay_amount / hours_monthly) * day_data['hours']
            else:
                amount_real = pay_amount / 30
        else:
            if holiday.request_unit_hours:
                amount_real = (pay_amount / hours_monthly) * day_data['hours'] * rate
            else:
                amount_real = pay_amount * rate / 30

        # Aplicar porcentaje forzado si existe
        if holiday.force_porc != 0:
            rate_applied = holiday.force_porc
            if holiday.request_unit_hours:
                amount_real = (pay_amount / hours_monthly) * day_data['hours'] * holiday.force_porc / 100
            else:
                amount_real = (pay_amount / 30) * holiday.force_porc / 100

        # Validar contra salario mínimo (Ley colombiana: ninguna ausencia puede pagarse por debajo del SMMLV)
        if not holiday.force_wage_incapacity:
            if holiday.request_unit_hours:
                min_hourly = smmlv / hours_monthly
                amount_real = max(amount_real, min_hourly * day_data['hours'])
            else:
                min_daily = smmlv / 30
                amount_real = max(amount_real, min_daily)

        return amount_real, ibc_day, ibc_base, rate_applied, base_type, ibc_original

    def _generate_formula_html(self, base_type, ibc_base, rate_applied, amount_real,
                               is_rest_day, is_day_31, is_hours, day_data,
                               is_public_holiday=False, is_weekend=False, holiday_name=None):
        """Genera HTML explicativo de la formula de calculo para un dia de ausencia

        Args:
            is_public_holiday: True si es un festivo de la tabla lavish.holidays
            is_weekend: True si es sabado (no laboral) o domingo
            holiday_name: Nombre del festivo si aplica
        """
        BASE_TYPE_LABELS = {
            'ibc': 'IBC Mes Anterior',
            'wage': 'Sueldo',
            'smmlv': 'SMMLV',
            'year': 'Promedio Ano',
            'forced': 'Base Forzada',
        }

        base_label = BASE_TYPE_LABELS.get(base_type, 'Base')

        company_id = self.employee_company_id.id if self.employee_company_id else None
        annual_params = self.env['hr.annual.parameters'].get_for_year(
            self.date_from.year, company_id=company_id, raise_if_not_found=False
        )
        hours_monthly = annual_params.hours_monthly if annual_params else 240

        if is_hours:
            hours = day_data.get('hours', 8)
            divisor = hours_monthly
            units = f"{hours} horas"
            daily_value = ibc_base / divisor if ibc_base else 0
        else:
            divisor = 30
            units = "1 dia"
            daily_value = ibc_base / divisor if ibc_base else 0

        html_parts = []
        html_parts.append('<div class="formula-explanation" style="font-size: 11px; line-height: 1.4;">')

        html_parts.append(f'<div><b>Base:</b> {base_label}</div>')
        html_parts.append(f'<div><b>Valor Base:</b> ${ibc_base:,.0f}</div>')

        if is_hours:
            html_parts.append(f'<div><b>Calculo:</b> ${ibc_base:,.0f} / {divisor} h = ${daily_value:,.2f}/hora</div>')
            html_parts.append(f'<div><b>Horas:</b> {hours}</div>')
            subtotal = daily_value * hours
            html_parts.append(f'<div><b>Subtotal:</b> ${daily_value:,.2f} x {hours} = ${subtotal:,.2f}</div>')
        else:
            html_parts.append(f'<div><b>Calculo:</b> ${ibc_base:,.0f} / {divisor} = ${daily_value:,.2f}/dia</div>')

        if rate_applied != 100:
            html_parts.append(f'<div><b>Porcentaje:</b> {rate_applied:.0f}%</div>')

        # Todos los días de descanso (festivos y fines de semana) se muestran como "Día festivo"
        # porque en nómina colombiana todos cuentan como días festivos para reportes
        if is_public_holiday:
            if holiday_name:
                html_parts.append(f'<div style="color: #c9302c;"><i>Dia festivo: {holiday_name}</i></div>')
            else:
                html_parts.append('<div style="color: #c9302c;"><i>Dia festivo</i></div>')
        elif is_weekend:
            html_parts.append('<div style="color: #5bc0de;"><i>Dia festivo (fin de semana)</i></div>')

        if is_day_31:
            html_parts.append('<div style="color: #666;"><i>Dia 31</i></div>')

        html_parts.append(f'<div style="border-top: 1px solid #ccc; margin-top: 4px; padding-top: 4px;">')
        html_parts.append(f'<b>Total:</b> ${amount_real:,.2f}</div>')
        html_parts.append('</div>')

        return ''.join(html_parts)

    def compute_holiday(self):
        for holiday in self:
            if not holiday.contract_id:
                raise UserError(_('¡Error! La licencia no tiene contrato asignado.'))
            if not holiday.contract_id.resource_calendar_id:
                raise UserError(_('¡Error! El contrato no tiene un horario laboral definido.'))
            holiday.line_ids.unlink()
            sequence = 0

            # CORRECCIÓN: Detectar automáticamente si es prórroga de incapacidad
            # Si la incapacidad empieza el día después de terminar otra del mismo tipo,
            # es una prórroga y la secuencia debe continuar
            extension_leave = holiday.extension_id
            if not extension_leave and holiday.holiday_status_id.novelty in ('ige', 'irl'):
                # Buscar incapacidad anterior del mismo tipo que termine justo antes
                date_from = holiday.date_from.date()
                previous_leave = self.env['hr.leave'].search([
                    ('employee_id', '=', holiday.employee_id.id),
                    ('holiday_status_id', '=', holiday.holiday_status_id.id),
                    ('state', '=', 'validate'),
                    ('id', '!=', holiday.id),
                ], order='date_to desc', limit=1)

                if previous_leave:
                    prev_date_to = previous_leave.date_to.date()
                    # Si la incapacidad anterior terminó el día antes o el mismo día que empieza esta
                    days_between = (date_from - prev_date_to).days
                    if days_between <= 1:  # Mismo día o día siguiente = prórroga
                        extension_leave = previous_leave
                        holiday.is_extension = True
                        holiday.extension_id = previous_leave.id

            if extension_leave:
                last_sequence = extension_leave.line_ids.mapped('sequence')
                if last_sequence:
                    sequence = max(last_sequence)

            if holiday.holiday_status_id.is_vacation:
                holiday.return_date = self._compute_return_date()
            if holiday.holiday_status_id.is_vacation_money:
                self._compute_vacation_money(holiday, sequence)
            else:
                self._compute_regular_leave(holiday, sequence)
            self.validate_february_days(holiday)
            holiday.payroll_value = sum(x.amount for x in holiday.line_ids)
            holiday.number_of_days = sum(x.days_payslip for x in holiday.line_ids)
            
            # -------------------------------------------------------------------------
            # COMPLEMENTO DE SALARIO
            # Si completar_salario esta activo, crear linea adicional con la diferencia
            # La regla de complemento debe tener liquidar_con_base=False (usa salario actual)
            # -------------------------------------------------------------------------
            if (holiday.holiday_status_id.completar_salario and 
                holiday.holiday_status_id.novelty in ['ige', 'irl'] and
                holiday.holiday_status_id.company_complement_input_id):
                
                # Obtener dias realmente pagados (excluyendo lineas de complemento previas)
                lineas_normales = holiday.line_ids.filtered(lambda l: not l.is_complement)
                dias_pagados = sum(l.days_payslip for l in lineas_normales)
                valor_eps = sum(l.amount for l in lineas_normales)
                
                # Calcular diferencia entre salario completo y lo pagado por EPS
                # NOTA: Usa salario actual del contrato (liquidar_con_base=False en la regla)
                salario_diario = holiday.contract_id.wage / 30
                valor_base_completo = salario_diario * dias_pagados
                diferencia = max(0, valor_base_completo - valor_eps)
                
                # Solo crear linea si hay diferencia positiva
                if diferencia > 0.01:  # Tolerancia para evitar lineas de centavos
                    # Calcular porcentaje que representa el complemento
                    porcentaje_complemento = (diferencia / valor_base_completo * 100) if valor_base_completo else 0
                    
                    # Crear linea de complemento separada
                    complement_vals = {
                        'leave_id': holiday.id,
                        'sequence': 9999,  # Secuencia alta para que aparezca al final
                        'name': f'COMPLEMENTO ({porcentaje_complemento:.2f}%)',
                        'date': holiday.date_to.date(),
                        'hours_assigned': 0,
                        'days_assigned': dias_pagados,
                        'hours': 0,
                        'days_payslip': 0,  # No suma dias, solo valor
                        'day': '0',
                        'days_work': 0,
                        'days_holiday': 0,
                        'days_31': 0,
                        'days_holiday_31': 0,
                        'amount': diferencia,
                        'ibc_day': salario_diario,  # IBC diario = salario/30
                        'ibc_base': holiday.contract_id.wage,  # Base = salario actual
                        'ibc_original': valor_eps,  # Guardar valor EPS para referencia
                        'rate_applied': porcentaje_complemento,
                        'base_type': 'complemento',
                        'rule_id': holiday.holiday_status_id.company_complement_input_id.id,
                        'holiday_amount': 0.0,
                        'holiday_31_amount': 0.0,
                        'holiday_date': False,
                        'is_complement': True,
                    }
                    self.env['hr.leave.line'].create(complement_vals)
                    
                    # Actualizar valor total pagado
                    holiday.payroll_value = valor_eps + diferencia
                    holiday.diferencia_ibc = diferencia

            return True
    
    def _compute_vacation_money(self, holiday, sequence):
        """
        Calcula vacaciones en dinero.
        
        CAMPOS ESPECIALES:
        - dias_a_liquidar: Si > 0, usa este numero de dias en lugar del calculado
        - incluir_festivos_liquidacion: Si True, incluye festivos en el pago
        - valor_adicional_manual: Se suma al total final
        """
        # PRIORIDAD DIAS: dias_a_liquidar > number_of_vac_money_days > number_of_days
        if holiday.dias_a_liquidar and holiday.dias_a_liquidar > 0:
            days_to_process = int(holiday.dias_a_liquidar)
        else:
            days_to_process = int(holiday.number_of_vac_money_days or holiday.number_of_days or 0)
        
        current_date = holiday.date_from.date()
        incluir_festivos = holiday.incluir_festivos_liquidacion

        liquidacion_type = holiday.holiday_status_id.liquidacion_value
        company_id = holiday.employee_company_id.id if holiday.employee_company_id else None
        annual_parameters = self.env['hr.annual.parameters'].get_for_year(
            holiday.date_from.year, company_id=company_id, raise_if_not_found=False
        )
        smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0

        # Determinar base según prioridad de forzados
        base_type = 'ibc'
        if holiday.force_base_amount and holiday.force_base_amount > 0:
            amount = holiday.force_base_amount
            base_type = 'forced'
        elif holiday.force_min_wage:
            amount = smmlv
            base_type = 'smmlv'
        elif liquidacion_type == 'IBC':
            # CORRECCIÓN: Usar IBC con fallback a ibc_pila o salario del contrato
            amount = holiday.ibc or holiday.ibc_pila or holiday.contract_id.wage
            base_type = 'ibc'
        elif liquidacion_type == 'YEAR':
            amount = holiday._get_average_last_year(holiday.contract_id)
            base_type = 'year'
        elif liquidacion_type == 'MIN':
            amount = smmlv
            base_type = 'smmlv'
        else:
            amount = holiday.contract_id.wage
            base_type = 'wage'

        # IBC diario para vacaciones en dinero
        ibc_day = amount / 30 if amount else 0
        ibc_base = amount
        rate_applied = holiday.force_porc if holiday.force_porc != 0 else 100.0
        
        # Contadores para resumen
        dias_habiles_procesados = 0
        dias_festivos_procesados = 0
        total_valor = 0

        for day in range(days_to_process):
            sequence += 1

            day_from = datetime.combine(current_date, time.min).replace(tzinfo=UTC)
            day_to = datetime.combine(current_date, time.max).replace(tzinfo=UTC)
            day_data = holiday._get_number_of_days(day_from, day_to, holiday.employee_id.id)
            
            # Verificar si es festivo
            is_holiday = holiday._is_holiday(current_date)
            is_sunday = current_date.weekday() == 6
            is_saturday = current_date.weekday() == 5 and not holiday.employee_id.sabado
            is_rest_day = is_holiday or is_sunday or is_saturday
            
            # Si no incluye festivos y es dia de descanso, saltar (pero contar)
            if is_rest_day and not incluir_festivos:
                # Incrementar dias pero no crear linea de pago
                current_date += timedelta(days=1)
                dias_festivos_procesados += 1
                continue

            if holiday.force_porc != 0:
                amount_real = (amount / 30) * holiday.force_porc / 100
            else:
                amount_real = amount / 30

            # Validar contra salario mínimo
            if not holiday.force_wage_incapacity and smmlv:
                amount_real = max(amount_real, (smmlv/30))
            
            total_valor += amount_real
            dias_habiles_procesados += 1

            vals = {
                'leave_id': holiday.id,
                'sequence': sequence,
                'name': current_date.strftime('%Y-%m-%d'),
                'date': current_date,
                'hours_assigned': day_data['hours'],
                'days_assigned': 1,
                'hours': day_data['hours'],
                'days_payslip': 1,
                'day': str(current_date.weekday()),
                'days_work': 0 if is_rest_day else 1,
                'days_holiday': 1 if is_rest_day else 0,
                'days_31': 1 if current_date.day == 31 else 0,
                'days_holiday_31': 1 if current_date.day == 31 and is_rest_day else 0,
                'amount': amount_real,
                'ibc_day': ibc_day,
                'ibc_base': ibc_base,
                'rate_applied': rate_applied,
                'base_type': base_type,
                'rule_id': holiday.holiday_status_id.get_rate_concept_id(sequence)[1],
                'holiday_amount': amount_real if is_rest_day else 0.0,
                'holiday_31_amount': amount_real if current_date.day == 31 and is_rest_day else 0.0,
                'holiday_date': current_date if is_rest_day else False,
            }
            self.env['hr.leave.line'].create(vals)
            current_date += timedelta(days=1)
        
        # Actualizar valores totales incluyendo valor adicional manual
        holiday.payroll_value = total_valor
        if holiday.valor_adicional_manual and holiday.valor_adicional_manual > 0:
            # El total_a_pagar se calcula automaticamente por el compute
            pass
    
    def _compute_regular_leave(self, holiday, sequence):
        date_from = holiday.date_from.replace(tzinfo=UTC)
        date_to = holiday.date_to.replace(tzinfo=UTC)

        if holiday.request_unit_hours and (date_to.date() - date_from.date()).days > 0:
            raise UserError(_('Advertencia: Las solicitudes de licencia por horas no deben abarcar varios días.'))

        current_date = date_from.date()
        
        apply_day_31 = holiday.holiday_status_id.apply_day_31
        discount_rest_day = holiday.holiday_status_id.discount_rest_day
        pagar_festivos = holiday.evaluates_day_off
        
        while current_date <= date_to.date():
            sequence += 1
            
            day_from = datetime.combine(current_date, time.min).replace(tzinfo=UTC)
            day_to = datetime.combine(current_date, time.max).replace(tzinfo=UTC)
            if holiday.request_unit_hours:
                if current_date == date_from.date():
                    day_from = date_from
                if current_date == date_to.date():
                    day_to = date_to
            # Si use_calendar_days=True, usar todos los dias calendario (no solo habiles)
            # Esto es necesario para incapacidades y licencias que cuentan fines de semana
            # Obtener horas por dia desde hr.company.working.hours o usar default
            hours_per_day_config = holiday._get_hours_per_day(current_date)
            if holiday.holiday_status_id.use_calendar_days:
                day_data = {'days': 1.0, 'hours': hours_per_day_config}
            else:
                day_data = holiday._get_number_of_days(day_from, day_to, holiday.employee_id.id)

            is_day_31 = current_date.day == 31
            is_holiday = holiday._is_holiday(current_date)
            is_sunday = current_date.weekday() == 6
            is_saturday = current_date.weekday() == 5 and not holiday.employee_id.sabado
            is_rest_day = is_holiday or is_sunday or is_saturday

            days_payslip = day_data['days']
            days_work = day_data['days']
            hours_payslip = day_data['hours']

            # CORRECCION: Si es sabado y el empleado trabaja sabados pero el calendario
            # no incluye el sabado (day_data['days'] = 0), forzar como dia laboral
            is_saturday_workday = current_date.weekday() == 5 and holiday.employee_id.sabado
            if is_saturday_workday and day_data['days'] == 0:
                days_work = 1.0
                days_payslip = 1.0
                hours_payslip = hours_per_day_config
            days_holiday = 0
            days_holiday_31 = 0
            days_31 = 0
            
            if is_day_31:
                if apply_day_31:
                    if is_rest_day:
                        # CORRECCIÓN: Usar 1.0 si day_data['days'] es 0 para días de descanso
                        days_holiday_31 = 1.0 if day_data['days'] == 0 else day_data['days']
                        days_31 = 0
                    else:
                        days_31 = day_data['days']
                else:
                    days_payslip = 0
                    days_work = 0
                    hours_payslip = 0
                    days_holiday_31 = 0
                    days_31 = 0
            
            if is_rest_day:
                # CORRECCIÓN: Los días de descanso (sábados, domingos, festivos) SIEMPRE
                # cuentan como días de nómina (days_payslip = 1) para reportes.
                # days_work = 0 porque no son días laborables.
                # Se marcan como days_holiday = 1 para identificarlos como "festivos" en nómina.
                days_holiday = 1.0 if day_data['days'] == 0 else day_data['days']
                days_payslip = 1.0 if day_data['days'] == 0 else day_data['days']
                days_work = 0
                hours_payslip = day_data['hours'] if day_data['hours'] > 0 else hours_per_day_config
            amount_real, ibc_day, ibc_base, rate_applied, base_type, ibc_original = holiday.calcular_valor_pago_incapacidad(
                day_data, current_date, sequence, is_rest_day, is_day_31
            )
            _, rule = holiday.holiday_status_id.get_rate_concept_id(sequence)

            # Obtener nombre del festivo si aplica
            holiday_record = self.env['lavish.holidays'].search([('date', '=', current_date)], limit=1) if is_holiday else None
            holiday_name = holiday_record.name if holiday_record else None
            # Determinar si es fin de semana (sabado no laboral o domingo)
            is_weekend = (is_saturday or is_sunday) and not is_holiday

            # Generar HTML de formula
            formula_html = holiday._generate_formula_html(
                base_type, ibc_base, rate_applied, amount_real,
                is_rest_day, is_day_31, holiday.request_unit_hours, day_data,
                is_public_holiday=is_holiday, is_weekend=is_weekend, holiday_name=holiday_name
            )

            vals = {
                'leave_id': holiday.id,
                'sequence': sequence,
                'name': current_date.strftime('%Y-%m-%d'),
                'date': current_date,
                'hours_assigned': day_data['hours'],
                'days_assigned': day_data['days'],
                'hours': hours_payslip,
                'days_payslip': days_payslip,
                'day': str(current_date.weekday()),
                'days_work': days_work,
                'days_holiday': days_holiday,
                'days_31': days_31,
                'days_holiday_31': days_holiday_31,
                'amount': amount_real,
                'ibc_day': ibc_day,
                'ibc_base': ibc_base,
                'ibc_original': ibc_original,
                'rate_applied': rate_applied,
                'base_type': base_type,
                'rule_id': rule,
                'formula_html': formula_html,
            }
            
            # Calcular valores de festivos
            if is_rest_day and is_holiday:
                vals['holiday_date'] = current_date
                if is_day_31 and apply_day_31:
                    # Día 31 festivo
                    if days_holiday_31 > 0:
                        vals['holiday_31_amount'] = amount_real if days_holiday_31 == 1.0 else (amount_real * days_holiday_31)
                    else:
                        vals['holiday_31_amount'] = 0.0
                else:
                    # Festivo normal
                    if days_holiday > 0:
                        vals['holiday_amount'] = amount_real if days_holiday == 1.0 else (amount_real * days_holiday)
                    else:
                        vals['holiday_amount'] = 0.0
            else:
                vals['holiday_amount'] = 0.0
                vals['holiday_31_amount'] = 0.0
                vals['holiday_date'] = False
            
            self.env['hr.leave.line'].create(vals)
            current_date += timedelta(days=1)
    
    def validate_february_days(self, leave):
        if not leave.contract_id:
            return

        start_month = leave.date_from.month if leave.date_from else 0
        end_month = leave.date_to.month if leave.date_to else 0

        if not (start_month == 2 or end_month == 2):
            return

        year = leave.date_from.year
        feb_last_day = 29 if calendar.isleap(year) else 28

        if end_month == 2 and leave.date_to.day == feb_last_day:
            sequence = max(leave.line_ids.mapped('sequence')) if leave.line_ids else 0
            liquidacion_type = leave.holiday_status_id.liquidacion_value
            company_id = leave.employee_company_id.id if leave.employee_company_id else None
            annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                leave.date_from.year, company_id=company_id, raise_if_not_found=False
            )
            smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0

            # Determinar base según prioridad de forzados
            base_type = 'ibc'
            if leave.force_base_amount and leave.force_base_amount > 0:
                amount = leave.force_base_amount
                base_type = 'forced'
            elif leave.force_min_wage:
                amount = smmlv
                base_type = 'smmlv'
            elif liquidacion_type == 'IBC':
                # CORRECCIÓN: Usar IBC con fallback a ibc_pila o salario del contrato
                amount = leave.ibc or leave.ibc_pila or leave.contract_id.wage
                base_type = 'ibc'
            elif liquidacion_type == 'YEAR':
                amount = leave._get_average_last_year(leave.contract_id)
                base_type = 'year'
            elif liquidacion_type == 'MIN':
                amount = smmlv
                base_type = 'smmlv'
            else:
                amount = leave.contract_id.wage
                base_type = 'wage'

            # IBC diario y rate para días virtuales de febrero
            ibc_day = amount / 30 if amount else 0
            ibc_base = amount
            ibc_original = leave.ibc or 0  # IBC del mes anterior para comparación
            rate, _ = leave.holiday_status_id.get_rate_concept_id(sequence + 1)
            rate_applied = leave.force_porc if leave.force_porc != 0 else ((rate * 100) if rate else 100.0)

            for virtual_day in range(feb_last_day + 1, 31):
                sequence += 1

                virtual_date = date(year, 2, feb_last_day)

                if leave.force_porc != 0:
                    amount_real = (amount / 30) * leave.force_porc / 100
                else:
                    amount_real = amount / 30

                # Validar contra salario mínimo
                if not leave.force_wage_incapacity:
                    amount_real = max(amount_real, (smmlv/30))

                vals = {
                    'leave_id': leave.id,
                    'sequence': sequence,
                    'name': f'2-{virtual_day}-{year}',
                    'date': virtual_date,
                    'hours_assigned': 8,
                    'days_assigned': 1,
                    'hours': 8,
                    'days_payslip': 1,
                    'day': str(virtual_date.weekday()),
                    'days_work': 1,
                    'days_holiday': 0,
                    'days_31': 0,
                    'days_holiday_31': 0,
                    'amount': amount_real,
                    'ibc_day': ibc_day,
                    'ibc_base': ibc_base,
                    'ibc_original': ibc_original,
                    'rate_applied': rate_applied,
                    'base_type': base_type,
                    'holiday_amount': 0.0,
                    'holiday_31_amount': 0.0,
                    'holiday_date': False,
                    'rule_id': leave.holiday_status_id.eps_arl_input_id.id,
                    'is_virtual_day': True,
                    'virtual_day_number': virtual_day
                }
                self.env['hr.leave.line'].create(vals)

    def recompute_amounts(self):
        """Recomputar montos de las líneas no pagadas"""
        for holiday in self:
            if not holiday.contract_id:
                raise UserError(_('¡Error! La licencia no tiene contrato asignado.'))
            if not holiday.contract_id.resource_calendar_id:
                raise UserError(_('¡Error! El contrato no tiene un horario laboral definido.'))

            company_id = holiday.employee_company_id.id if holiday.employee_company_id else None
            annual_parameters = self.env['hr.annual.parameters'].get_for_year(
                holiday.date_from.year, company_id=company_id, raise_if_not_found=False
            )
            smmlv = annual_parameters.smmlv_monthly if annual_parameters else 0
            hours_monthly = annual_parameters.hours_monthly if annual_parameters else 240
            liquidacion_type = holiday.holiday_status_id.liquidacion_value

            # Determinar base según prioridad de forzados
            base_type = 'ibc'
            if holiday.force_base_amount and holiday.force_base_amount > 0:
                amount = holiday.force_base_amount
                base_type = 'forced'
            elif holiday.force_min_wage:
                amount = smmlv
                base_type = 'smmlv'
            elif holiday.contract_id.parcial:
                amount = holiday.contract_id.wage
                base_type = 'wage'
            elif liquidacion_type == 'IBC':
                # CORRECCIÓN: Usar IBC con fallback a ibc_pila o salario del contrato
                amount = holiday.ibc or holiday.ibc_pila or holiday.contract_id.wage
                base_type = 'ibc'
            elif liquidacion_type == 'YEAR':
                amount = holiday._get_average_last_year(holiday.contract_id)
                base_type = 'year'
            elif liquidacion_type == 'MIN':
                amount = smmlv
                base_type = 'smmlv'
            else:
                amount = holiday.contract_id.wage
                base_type = 'wage'

            ibc_day = amount / 30 if amount else 0
            ibc_base = amount
            ibc_original = holiday.ibc or 0  # IBC del mes anterior para comparación

            unpaid_lines = holiday.line_ids.filtered(lambda x: x.state != 'paid')
            for line in unpaid_lines:
                rate, rule = holiday.holiday_status_id.get_rate_concept_id(line.sequence)
                rate_applied = (rate * 100) if rate else 100.0

                if holiday.holiday_status_id.code == 'EGA' and line.sequence <= holiday.holiday_status_id.num_days_no_assume:
                    amount_real = amount / 30
                    rate_applied = 100.0
                elif holiday.holiday_status_id.novelty == 'irl' and line.sequence == 1:
                    amount_real = amount / 30
                    rate_applied = 100.0
                else:
                    amount_real = amount * rate / 30

                if holiday.force_porc != 0:
                    amount_real = (amount / 30) * holiday.force_porc / 100
                    rate_applied = holiday.force_porc

                if holiday.request_unit_hours:
                    daily_rate = amount / hours_monthly
                    amount_real = daily_rate * line.hours * (rate_applied / 100)

                # Validar contra salario mínimo
                if not holiday.force_wage_incapacity:
                    if holiday.request_unit_hours:
                        min_hourly = smmlv / hours_monthly
                        amount_real = max(amount_real, min_hourly * line.hours)
                    else:
                        amount_real = max(amount_real, smmlv / 30)

                is_day_31 = line.date.day == 31
                if is_day_31 and not self._should_apply_day_31(holiday):
                    amount_real = 0
                    line_ibc_day = 0
                    line_rate = 0
                    line_base_type = False
                else:
                    line_ibc_day = ibc_day
                    line_rate = rate_applied
                    line_base_type = base_type

                # Calcular valores de festivos si aplica
                holiday_amount = 0.0
                holiday_31_amount = 0.0
                holiday_date_val = None
                
                if line.is_holiday:
                    holiday_date_val = line.date
                    if line.days_holiday > 0:
                        # Calcular valor proporcional de festivos
                        if line.days_payslip > 0:
                            amount_per_day = amount_real / line.days_payslip
                            holiday_amount = amount_per_day * line.days_holiday
                        else:
                            holiday_amount = amount_real if line.days_holiday == 1.0 else 0.0
                    
                    if line.days_holiday_31 > 0:
                        # Calcular valor proporcional de días 31 festivos
                        if line.days_payslip > 0:
                            amount_per_day = amount_real / line.days_payslip
                            holiday_31_amount = amount_per_day * line.days_holiday_31
                        else:
                            holiday_31_amount = amount_real if line.days_holiday_31 == 1.0 else 0.0
                
                line.write({
                    'amount': amount_real,
                    'ibc_day': line_ibc_day,
                    'ibc_base': ibc_base,
                    'ibc_original': ibc_original,
                    'rate_applied': line_rate,
                    'base_type': line_base_type,
                    'holiday_amount': holiday_amount,
                    'holiday_31_amount': holiday_31_amount,
                    'holiday_date': holiday_date_val,
                    'rule_id': rule,
                })

            holiday.payroll_value = sum(x.amount for x in holiday.line_ids)

        return True

    def update_ibc_and_recompute(self, new_ibc):
        """Actualizar IBC y recomputar montos"""
        self.ensure_one()
        self.write({'ibc': new_ibc})
        return self.recompute_amounts() 
    
    def _cancel_work_entry_conflict(self):
        leaves_to_defer = self.filtered(lambda l: l.payslip_state == 'blocked')
        leaves_vco = self.filtered(lambda l: l.holiday_status_id.code == 'vco')  # Filtrar las ausencias de tipo 'vco'
        
        for leave in leaves_to_defer:
            leave.activity_schedule(
                'hr_payroll_holidays.mail_activity_data_hr_leave_to_defer',
                summary=_('Validated Time Off to Defer'),
                note=_(
                    'Please create manually the work entry for %s',
                    leave.employee_id._get_html_link()),
                user_id=leave.employee_id.company_id.deferred_time_off_manager.id or self.env.ref('base.user_admin').id)
        
        for leave in leaves_vco:
            leave.activity_schedule(
                'mail.mail_activity_data_todo', 
                summary=_('Compensación de vacaciones en dinero'),
                note=_(
                    'Compensación de vacaciones en dinero para %(employee)s.\n'
                    'Periodo de cobertura: desde %(start_date)s to %(end_date)s\n'
                    'Número de días: %(days)s'
                ) % {
                    'employee': leave.employee_id._get_html_link(),
                    'start_date': leave.date_from.date(),
                    'end_date': leave.date_to.date(),
                    'days': leave.number_of_days
                },
                user_id=leave.employee_id.company_id.deferred_time_off_manager.id or self.env.ref('base.user_admin').id
            )
            
        return super(HolidaysRequest, self - leaves_to_defer - leaves_vco)._cancel_work_entry_conflict()

class HrLeaveDiagnostic(models.Model):
    _name = "hr.leave.diagnostic"
    _description = "Diagnosticos Ausencias"

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True)

    _leave_diagnostic_code_uniq = models.Constraint('unique(code)',
                                                    'Ya existe un diagnóstico con este código, por favor verificar.')

    def _compute_display_name(self):
        result = []
        for record in self:
            record.display_name = "{} | {}".format(record.code,record.name)

    @api.model
    def _name_search(self, name, args=None, operator='ilike',
                     limit=100, name_get_uid=None,order=None):
        args = args or []
        if operator == 'ilike' and not (name or '').strip():
            domain = []
        else:
            domain = ['|', ('name', 'ilike', name),
                      ('code', 'ilike', name)]
        return self._search(expression.AND([domain, args]),
                            limit=limit, order=order,
                            access_rights_uid=name_get_uid)

class HrLeaveLine(models.Model):
    _name = 'hr.leave.line'
    _description = 'Lineas de Ausencia'
    _order = 'date desc'

    leave_id = fields.Many2one(comodel_name='hr.leave', string='Ausencia', required=True,ondelete='cascade')
    payslip_id = fields.Many2one(comodel_name='hr.payslip', string='Nónima')
    contract_id = fields.Many2one(string='Contrato', related='leave_id.contract_id')
    rule_id = fields.Many2one('hr.salary.rule', 'Reglas Salarial')
    date = fields.Date(string='Fecha')
    state = fields.Selection(
        string='Estado',
        selection=STATE,
        compute='_compute_state',
        store=True,
        default='draft'
    )
    amount = fields.Float(string='Valor')
    ibc_day = fields.Float(string='IBC Día',
                           help='Ingreso Base de Cotización diario usado para este día')
    ibc_base = fields.Float(string='Base Usada',
                            help='Base mensual usada para el cálculo (puede ser IBC, Sueldo, SMMLV, Forzado, etc)')
    ibc_original = fields.Float(string='IBC Mes Anterior',
                                help='IBC del mes anterior calculado desde la nómina')
    show_both_ibc = fields.Boolean(string='Mostrar Ambos IBC', compute='_compute_show_both_ibc', store=True,
                                   help='Si la base usada es diferente al IBC del mes anterior')
    rate_applied = fields.Float(string='% Aplicado',
                                help='Porcentaje aplicado según el rango de días')
    base_type = fields.Selection([
        ('ibc', 'IBC'),
        ('wage', 'Sueldo'),
        ('smmlv', 'SMMLV'),
        ('year', 'Promedio Ano'),
        ('forced', 'Forzado'),
        ('complemento', 'Complemento Empresa'),
    ], string='Tipo Base', help='Tipo de base usada para el calculo')
    
    is_complement = fields.Boolean(
        string='Es Complemento',
        default=False,
        help='LINEA DE COMPLEMENTO DE SALARIO\n'
             '------------------------------------------------------------\n'
             'Si esta marcado:\n'
             '  + Esta linea representa la diferencia que paga la empresa\n'
             '  + Se contabiliza como gasto directo de empresa\n'
             '  + NO es cuenta por cobrar a EPS\n'
             '------------------------------------------------------------\n'
             'Generada automaticamente cuando:\n'
             '  + Tipo de ausencia tiene "Completar salario" activo\n'
             '  + La EPS paga menos del 100%'
    )

    ibc_difference = fields.Float(
        string='Diferencia IBC',
        compute='_compute_ibc_difference',
        store=True,
        help='Diferencia entre el IBC para SS y el valor pagado (IBC - Pagado)'
    )

    @api.depends('amount', 'ibc_day')
    def _compute_show_both_ibc(self):
        """Determina si mostrar ambos valores: Valor a Pagar e IBC para SS.

        Se muestra ambos cuando son diferentes, es decir:
        - Valor a pagar (amount): Sueldo del contrato
        - IBC para SS (ibc_day): IBC del mes anterior
        """
        for line in self:
            if line.amount and line.ibc_day:
                # Comparar valor a pagar por día con IBC diario
                line.show_both_ibc = abs(line.amount - line.ibc_day) > 0.01
            else:
                line.show_both_ibc = False

    @api.depends('amount', 'ibc_day')
    def _compute_ibc_difference(self):
        """Calcula la diferencia entre IBC para SS y valor pagado."""
        for line in self:
            if line.ibc_day and line.amount:
                line.ibc_difference = line.ibc_day - line.amount
            else:
                line.ibc_difference = 0.0

    days_payslip = fields.Float(string='Dias en nomina')
    hours = fields.Float(string='Hora')
    days_assigned = fields.Float('Dias de asignacion')
    hours_assigned = fields.Float('Horas de asignacion')
    sequence = fields.Integer(string='Secuencia')
    name = fields.Char('Reason', size=128, help='Reason for holiday')
    day = fields.Selection([('0', 'Lunes'),
                            ('1', 'Martes'),
                            ('2', 'Miercoles'),
                            ('3', 'Jueves'),
                            ('4', 'Viernes'),
                            ('5', 'Sabado'),
                            ('6', 'Domingo'),
                            ], 'Dia Semana')
    days_work = fields.Float('Dias laborales')
    days_holiday = fields.Float('Dias Festivo', store=True, help='Cantidad de días festivos en esta línea')
    days_31 = fields.Float('Dias 31 laborales')
    days_holiday_31 = fields.Float('Dias 31 Festivo', store=True, help='Cantidad de días 31 que son festivos')
    
    # Campos de valores para festivos
    holiday_amount = fields.Float(
        string='Valor Días Festivos',
        digits=(16, 2),
        help='Valor monetario correspondiente a los días festivos de esta línea'
    )
    holiday_31_amount = fields.Float(
        string='Valor Días 31 Festivos',
        digits=(16, 2),
        help='Valor monetario correspondiente a los días 31 festivos de esta línea'
    )
    holiday_date = fields.Date(
        string='Fecha del Festivo',
        help='Fecha específica del festivo si esta línea corresponde a un día festivo'
    )
    is_virtual_day = fields.Boolean(
        string='Día Virtual',
        default=False,
        help='Indica si este registro corresponde a un día virtual añadido para completar cálculos.'
    )
    virtual_day_number = fields.Integer(
        string='Número de Día Virtual',
        help='Número del día virtual (29 o 30 para febrero)'
    )
    is_unused = fields.Boolean('No utilizado', default=False)
    unused_reason_id = fields.Many2one('hr.vacation.interruption.reason', 'Motivo de no uso')
    unused_detail = fields.Char('Detalle de no uso')
    unused_date = fields.Date('Fecha de marcado como no usado')
    will_be_used_later = fields.Boolean('Se usará después', default=False)
    future_use_date = fields.Date('Fecha futura de uso')

    # Campo para explicacion de formula
    formula_html = fields.Html(
        string='Formula',
        help='Explicacion detallada del calculo de este dia',
        sanitize=False
    )

    # Campo para icono del tipo de dia
    day_type_icon = fields.Html(
        string='Tipo',
        compute='_compute_day_type_icon',
        help='Icono que indica el tipo de dia'
    )

    @api.depends('days_holiday', 'days_31', 'days_work', 'day', 'is_holiday')
    def _compute_day_type_icon(self):
        for line in self:
            icons = []
            if line.is_holiday or line.days_holiday > 0:
                icons.append('<span class="badge text-bg-warning" title="Festivo">F</span>')
            if line.days_31 > 0:
                icons.append('<span class="badge text-bg-info" title="Dia 31">31</span>')
            if line.day in ('5', '6'):
                icons.append('<span class="badge text-bg-secondary" title="Fin de semana">W</span>')
            if line.days_work > 0 and not icons:
                icons.append('<span class="badge text-bg-success" title="Laboral">L</span>')
            if line.days_payslip == 0:
                icons.append('<span class="badge text-bg-danger" title="No paga">X</span>')
            line.day_type_icon = ' '.join(icons) if icons else '<span class="badge text-bg-light">-</span>'

    # Campos para festivos y fecha de regreso
    is_holiday = fields.Boolean(
        string='Es Festivo',
        compute='_compute_is_holiday',
        store=True,
        help='Indica si esta línea corresponde a un día festivo'
    )
    holiday_name = fields.Char(
        string='Nombre del Festivo',
        compute='_compute_is_holiday',
        store=True,
        help='Nombre del festivo si esta fecha es festiva'
    )
    return_date = fields.Date(
        string='Fecha de Regreso',
        compute='_compute_return_date',
        store=True,
        help='Siguiente día hábil después de esta ausencia (considerando sábados laborales)'
    )

    @api.depends('date', 'days_holiday', 'days_holiday_31', 'amount')
    def _compute_is_holiday(self):
        """Determina si la fecha es un festivo y obtiene su nombre, y calcula valores"""
        for line in self:
            if line.date:
                holiday = self.env['lavish.holidays'].search([('date', '=', line.date)], limit=1)
                if holiday:
                    line.is_holiday = True
                    line.holiday_name = holiday.name
                    line.holiday_date = holiday.date
                    
                    # Calcular valor de festivos si hay días festivos
                    if line.days_holiday > 0:
                        # Si hay amount y days_holiday, calcular proporción
                        if line.amount and line.days_payslip > 0:
                            amount_per_day = line.amount / line.days_payslip if line.days_payslip > 0 else 0
                            line.holiday_amount = amount_per_day * line.days_holiday
                        else:
                            line.holiday_amount = 0.0
                    else:
                        line.holiday_amount = 0.0
                    
                    # Calcular valor de días 31 festivos
                    if line.days_holiday_31 > 0:
                        if line.amount and line.days_payslip > 0:
                            amount_per_day = line.amount / line.days_payslip if line.days_payslip > 0 else 0
                            line.holiday_31_amount = amount_per_day * line.days_holiday_31
                        else:
                            line.holiday_31_amount = 0.0
                    else:
                        line.holiday_31_amount = 0.0
                else:
                    line.is_holiday = False
                    line.holiday_name = False
                    line.holiday_date = False
                    line.holiday_amount = 0.0
                    line.holiday_31_amount = 0.0
            else:
                line.is_holiday = False
                line.holiday_name = False
                line.holiday_date = False
                line.holiday_amount = 0.0
                line.holiday_31_amount = 0.0

    @api.depends('date', 'leave_id.employee_id.sabado')
    def _compute_return_date(self):
        """
        Calcula la fecha de regreso (siguiente día hábil).
        Considera:
        - Domingos (siempre descanso)
        - Sábados (si employee.sabado = False)
        - Festivos
        """
        for line in self:
            if not line.date or not line.leave_id:
                line.return_date = False
                continue

            works_saturday = line.leave_id.employee_id.sabado if line.leave_id.employee_id else False
            next_day = line.date + timedelta(days=1)

            # Buscar siguiente día hábil
            while True:
                is_saturday = next_day.weekday() == 5
                is_sunday = next_day.weekday() == 6
                is_holiday = self.env['lavish.holidays'].ensure_holidays(next_day)

                # Si es sábado y NO trabaja sábados, o es domingo, o es festivo: avanzar
                if (is_saturday and not works_saturday) or is_sunday or is_holiday:
                    next_day += timedelta(days=1)
                else:
                    break

            line.return_date = next_day

    @api.depends('leave_id.state','payslip_id', 'payslip_id.state')
    def _compute_state(self):
        for line in self:
            try:
                state = 'draft'
                if line.leave_id and line.leave_id.state == 'validate':
                    state = 'validated'
                if line.payslip_id and line.payslip_id.state in ['done', 'paid']:
                    state = 'paid'
                line.state = state
            except Exception as e:
                line.state = 'draft'

    def _validate_payslip_allows_change(self, action='modificar'):
        """
        Valida que la nomina asociada permita cambios en la linea.

        Args:
            action: Descripcion de la accion a realizar ('modificar', 'eliminar', 'cambiar estado')

        Raises:
            UserError: Si la nomina no permite cambios
        """
        self.ensure_one()
        if self.payslip_id and self.payslip_id.state not in ['draft', 'cancel', 'verify']:
            raise UserError(_(
                'No se puede {} la linea de ausencia porque esta asociada a la nomina {} que esta procesada.\n'
                'Primero restablezca la nomina a estado borrador.'
            ).format(action, self.payslip_id.name))

    @api.constrains('leave_id', 'payslip_id')
    def _check_leave_state_with_payslip(self):
        """Valida que cambios de estado de ausencia sean compatibles con nominas asociadas"""
        for line in self:
            if line.leave_id.state in ['draft', 'refuse', 'cancel']:
                line._validate_payslip_allows_change('cambiar estado de ausencia a ' + line.leave_id.state)  
    
    def belongs_category(self, categories):
        """Verifica si el tipo de ausencia de esta linea esta en las categorias dadas"""
        return self.leave_id.holiday_status_id.id in categories

    def unlink(self):
        """Elimina las lineas de ausencia validando que la nomina lo permita"""
        for line in self:
            line._validate_payslip_allows_change('eliminar')
        return super(HrLeaveLine, self).unlink()

class HolidaySyncYear(models.Model):
    _name = 'lavish.holidays.sync'
    _description = 'Control de Años Sincronizados para Festivos'

    year = fields.Integer('Año', required=True)
    sync_date = fields.Datetime('Fecha de sincronización', default=fields.Datetime.now)
    
    _year_unique = models.Constraint('unique(year)', 'El año debe ser único!')

class HolidaySync(models.Model):
    _inherit = 'lavish.holidays'

    @api.model
    def _is_year_synced(self, year):
        """Verifica si un año ya fue sincronizado"""
        return self.env['lavish.holidays.sync'].search_count([('year', '=', year)]) > 0

    @api.model
    def _mark_year_synced(self, year):
        """Marca un año como sincronizado"""
        if not self._is_year_synced(year):
            self.env['lavish.holidays.sync'].create({'year': year})

    @api.model
    def sync_holidays_for_year(self, year):
        """
        Sincroniza los festivos colombianos para un año si no estan ya sincronizados.
        Usa el metodo generate_holidays_for_year del modelo base lavish.holidays.
        """
        try:
            if self._is_year_synced(year):
                return True

            # Usar el metodo del modelo base que ya tiene toda la logica de festivos colombianos
            created = self.generate_holidays_for_year(year)

            self._mark_year_synced(year)
            return True

        except Exception as e:
            _logger.error('Error sincronizando festivos del año %s: %s', year, str(e))
            return False

    @api.model
    def ensure_holidays(self, check_date):
        """
        Asegura que los festivos estén creados para una fecha dada
        Retorna True si es festivo, False si no lo es
        """
        if isinstance(check_date, datetime):
            check_date = check_date.date()
            
        year = check_date.year
        if not self._is_year_synced(year):
            self.sync_holidays_for_year(year)
        return self.search_count([('date', '=', check_date)]) > 0

    @api.model
    def cron_sync_next_year(self):
        """Cron job para sincronizar el próximo año"""
        next_year = fields.Date.today().year + 1
        if not self._is_year_synced(next_year):
            self.sync_holidays_for_year(next_year)
