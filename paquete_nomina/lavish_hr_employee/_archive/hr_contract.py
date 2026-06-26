# -*- coding: utf-8 -*-
import base64
import time
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from pytz import timezone

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

CONTRACT_GROUP_ID_HELP = """
Este campo permite agrupar los contratos, según se va a calcular la nómina.
Sirve para grupos que no sea por banco, centro de costo y/o ciudad de desempeño.
"""
ARL_ID_HELP = "ARL en el caso que el empleado sea independiente"
ANALYTIC_DISTRIBUTION_TOTAL_WARN = """: La suma de las distribuciones analíticas debe ser 100.0%%,
Valor actual: %s%%"""
CONTRACT_EXTENSION_NO_RECORD_WARN = """
Para prorrogar el contrato por favor registre una prorroga
"""
CONTRACT_EXTENSION_MAX_WARN = """
No es posible realizar una prórroga por un periodo inferior
a un año despues de tener 3 o más prórrogas
"""
NO_PARTNER_REF_WARN = """
No se encontró el numero de documento en el contacto
"""
IN_FORCE_CONTRACT_WARN = """
El empleado yá tiene un contrato activo: %s.
"""

NO_WAGE_HISTORY = """
El contrato %s no tiene un historial de salarios.
"""

MANY_WAGE_HISTORY = """
El contrato %s tiene %s cambios salariales en este rango %s a %s.
Solo se permite 1 por periodo.
"""

LAST_ONE = -1
import calendar
import logging
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Union, cast

from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 2

T = TypeVar('T')
def days360(start_date, end_date, method_eu=True):
    """Compute number of days between two dates regarding all months
    as 30-day months"""

    start_day = start_date.day
    start_month = start_date.month
    start_year = start_date.year
    end_day = end_date.day
    end_month = end_date.month
    end_year = end_date.year

    if (
            start_day == 31 or
            (
                method_eu is False and
                start_month == 2 and (
                    start_day == 29 or (
                        start_day == 28 and
                        calendar.isleap(start_year) is False
                    )
                )
            )
    ):
        start_day = 30

    if end_day == 31:
        if method_eu is False and start_day != 30:
            end_day = 1

            if end_month == 12:
                end_year += 1
                end_month = 1
            else:
                end_month += 1
        else:
            end_day = 30
    if end_month == 2 and end_day in (28, 29):
        end_day = 30

    return (
        end_day + end_month * 30 + end_year * 360 -
        start_day - start_month * 30 - start_year * 360 + 1
    )
class HrContractChangeWage(models.Model):
    _name = 'hr.contract.change.wage'
    _description = 'Cambios salario básico'
    _order = 'date_start'
    
    date_start = fields.Date('Fecha inicial')
    wage = fields.Float('Salario básico', help='Seguimiento de los cambios en el salario básico')
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    job_id = fields.Many2one('hr.job', string='Cargo')
    
    reason = fields.Selection([
        ('start', 'Inicio de contrato'),
        ('annual_update', 'Actualización anual'),
        ('adjustment', 'Ajuste general'),
        ('legal', 'Ajuste por normativa legal'),
        ('collective', 'Negociación colectiva'),
        ('business_decision', 'Decisión empresarial'),
        ('performance', 'Desempeño'),
        ('promotion', 'Promoción'),
        ('market_adjustment', 'Ajuste al mercado'),
        ('restructuring', 'Reestructuración'),
        ('other', 'Otro')
    ], string='Motivo del cambio')
    other_reason = fields.Char('Otro motivo')
    
    wage_adjustment_id = fields.Many2one('hr.wage.adjustment', string='Ajuste salarial origen')
    
    apply_retroactive = fields.Boolean('Aplicar retroactivo', default=False)
    retroactive_date = fields.Date('Fecha desde retroactivo')
    
    wage_old = fields.Float('Salario anterior', compute='_compute_wage_old', store=True)
    difference = fields.Float('Diferencia', compute='_compute_difference', store=True)
    difference_percentage = fields.Float('Porcentaje diferencia', compute='_compute_difference', 
                                       store=True, digits=(16, 4))
    
    _change_wage_uniq = models.Constraint('unique(contract_id, date_start, wage, job_id)',
                                          'Ya existe un cambio de salario igual a este')
    
    @api.depends('contract_id', 'date_start')
    def _compute_wage_old(self):
        for record in self:
            if record.contract_id and record.date_start:
                # Buscar cambio salarial anterior
                prev_change = self.search([
                    ('contract_id', '=', record.contract_id.id),
                    ('date_start', '<', record.date_start)
                ], order='date_start desc', limit=1)
                
                if prev_change:
                    record.wage_old = prev_change.wage
                else:
                    # Si no hay cambios previos, usar el salario actual
                    record.wage_old = record.contract_id.wage
            else:
                record.wage_old = 0
    
    @api.depends('wage', 'wage_old')
    def _compute_difference(self):
        for record in self:
            record.difference = record.wage - record.wage_old
            record.difference_percentage = (record.difference / record.wage_old * 100) if record.wage_old else 0.0
    _change_wage_uniq = models.Constraint('unique(contract_id, date_start, wage, job_id)', 'Ya existe un cambio de salario igual a este')


class HrContractConceptSkip(models.Model):
    _name = 'hr.contract.concept.skip'
    _description = 'Control de Saltos de Cuotas'
    _inherit = ['mail.thread']
    _order = 'period_skip desc'

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True, ondelete='cascade')
    period_skip = fields.Date('Fecha de Salto', required=True)
    period_double = fields.Boolean('Recuperar con pago doble', default=True,
        help='Si está marcado, el valor saltado se recuperará con pago doble en la siguiente cuota')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Confirmado')
    ], string='Estado', default='draft', tracking=True)

    @api.depends('concept_id', 'period_skip')
    def _compute_name(self):
        for record in self:
            if record.concept_id and record.period_skip:
                indicator = '1Q' if record.period_skip.day <= 15 else '2Q'
                record.name = f"Salto {indicator} {record.period_skip.strftime('%m/%Y')}"
            else:
                record.name = "Nuevo Salto"

    def action_approve(self):
        """Confirmar el salto"""
        self.write({'state': 'approved'})
        self.message_post(body=_("Salto confirmado para %s") % self.period_skip.strftime('%d/%m/%Y'))

    def check_skip_applies(self, date_from, date_to):
        """Valida si el salto aplica para el período"""
        self.ensure_one()
        if self.state != 'approved':
            return False
        return date_from <= self.period_skip <= date_to


class HrContractConcepts(models.Model):
    _name = 'hr.contract.concepts'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Deducciones o Devengos, conceptos de nómina'
    _order = 'sequence, date_start desc, id desc'

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    sequence = fields.Integer('Secuencia', default=10)
    type_employee = fields.Many2one('hr.types.employee', string='Tipo de Empleado', store=True, readonly=True)
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', string='Compañía', default=lambda self: self.env.company)
    
    # Campos de configuración principal
    input_id = fields.Many2one('hr.salary.rule', 'Regla', required=True, 
                              help='Regla salarial', domain=[('novedad_ded','=','cont')])
    show_voucher = fields.Boolean('Mostrar', help='Indica si se muestra o no en el comprobante de nomina')
    
    # Campos de clasificación
    type_deduction = fields.Selection([
        ('P', 'Prestamo empresa'),
        ('A', 'Ahorro'),
        ('S', 'Seguro'),
        ('L', 'Libranza'),
        ('E', 'Embargo'),
        ('R', 'Retencion'),
        ('O', 'Otros')
    ], 'Tipo deduccion')
    
    monthly_behavior = fields.Selection([
        ('equal', 'Mismo valor en ambas quincenas'),
        ('proportional', 'Proporcional a días'),
        ('divided', 'Dividir en partes iguales')
    ], string='Comportamiento Mensual', default='equal', tracking=True)
    
    type_emb = fields.Selection([
        ('ECA', 'Emb. Cuotas alimentarias'),
        ('EDJ', 'Emb. Depósito judicial'),
        ('EI', 'Emb. ICETEX'),
        ('EJ', 'Emb. Ejecutivo'),
        ('O', 'Otros')
    ], 'Tipo Embargo')
    
    # Campos de configuración de período
    period = fields.Selection([
        ('limited', 'Limitado'),
        ('indefinite', 'Indefinido')
    ], 'Limite')
    
    # Campos de configuración de monto
    amount_select = fields.Selection([
        ('percentage', 'Porcentaje (%)'),
        ('fix', 'Monto fijo'),
        ('min', 'Base minimo'),
    ], string='Tipo de Monto', index=True, required=True, default='fix')
    
    amount = fields.Float('Importe/porcentaje', required=True)
    minimum_amount = fields.Float('Monto Mínimo', help='Monto mínimo a aplicar cuando se usa porcentaje')
    maximum_amount = fields.Float('Monto Máximo', help='Monto máximo a aplicar cuando se usa porcentaje')
    
    # Campos de control de aplicación
    aplicar = fields.Selection([
        ('15','Primera quincena'),
        ('30','Segunda quincena'),
        ('0','Siempre')
    ], 'Aplicar cobro', required=True)
    
    modality_value = fields.Selection([
        ('fijo', 'Valor fijo'),
        ('diario', 'Valor diario'),
        ('diario_efectivo', 'Valor diario del día efectivamente laborado')
    ], 'Modalidad de valor', default='fijo', tracking=True)
    
    # Campos de exclusión de días - NUEVOS CAMPOS NECESARIOS
    excluir_sabados = fields.Boolean('Excluir sábados', default=False)
    excluir_domingos = fields.Boolean('Excluir domingos', default=False)
    excluir_festivos = fields.Boolean('Excluir festivos', default=False)
    descontar_dia_31 = fields.Boolean('Descontar día 31', default=True,
        help='Si está marcado, se descontará el día 31 del mes (como en la nómina colombiana)')
    
    # Campos de fechas
    date_start = fields.Date('Fecha Inicial')
    date_end = fields.Date('Fecha Final')
    
    # Campos de relación
    partner_id = fields.Many2one('hr.employee.entities', 'Entidad')
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True,
                                 ondelete='cascade', index=True)
    employee_id = fields.Many2one(related='contract_id.employee_id', store=True)
    payroll_structure_ids = fields.Many2many('hr.payroll.structure', 
                                           string='Estructuras Salariales')
    payslip_ids = fields.Many2many('hr.payslip', string='Nóminas Relacionadas')
    base_structure_only = fields.Boolean('Aplicar solo en estructuras base', 
        default=True,
        help='Si está marcado, el concepto se aplicará solo en estructuras base')
    
    # Campos de control de descuentos
    discount_rule = fields.Many2many('hr.salary.rule', string='Reglas de descuento')
    discount_categoria = fields.Many2many('hr.salary.rule.category',
                                        string='Categorias de descuento')
    description = fields.Char(string='Descripcion')    
    
    # Campos de control de pagos dobles
    force_double_payment = fields.Boolean('Forzar Pago Doble')
    double_payment_date = fields.Date('Fecha Pago Doble')
    last_double_payment = fields.Date('Último Pago Doble', readonly=True)
    
    # Campos de control de saltos
    skip_ids = fields.One2many('hr.contract.concept.skip', 'concept_id', 'Control de Saltos')
    # Campos informativos
    detail = fields.Text('Notas', help='Notas')
    embargo_judged = fields.Char('Juzgado')
    embargo_process = fields.Char('Proceso')
    
    # Campos de documento
    attached = fields.Binary('Adjunto')
    attached_name = fields.Char('Nombre adjunto')
    
    # Campos de estado y tracking
    state = fields.Selection([
        ('draft', 'Por Aprobar'),
        ('done', 'Aprobado'),
        ('cancel', 'Cancelado / Finalizado')
    ], string='Estado', default='draft', required=True, tracking=True)
    
    # Campos computados
    balance = fields.Float('Saldo Pendiente', compute='_compute_balance', store=True)
    total_paid = fields.Float('Total Pagado', compute='_compute_balance', store=True)
    next_payment_date = fields.Date('Próximo Pago', compute='_compute_next_payment')
    simulation_text = fields.Html('Detalle de Simulación', compute='_compute_simulation_details')
    active_period = fields.Boolean('Periodo Activo', compute='_compute_active_period')
    accumulated_amount = fields.Float('Monto Acumulado', compute='_compute_accumulated')
    remaining_installments = fields.Integer('Cuotas Restantes', compute='_compute_remaining')
    line_ids = fields.One2many('hr.payslip.line', 'concept_id', string='Líneas de Nómina',
        help='Líneas de nómina donde se ha aplicado este concepto')
    payroll_account_id = fields.Many2one('account.account', string="Cuenta Contable")
    
    _check_amount_positive = models.Constraint('CHECK(amount >= 0)', 'El monto debe ser positivo')
    _date_check = models.Constraint('CHECK((date_start IS NULL AND date_end IS NULL) OR (date_start <= date_end))',
                                    'La fecha final debe ser posterior a la fecha inicial')

    @api.depends('input_id', 'contract_id', 'type_deduction')
    def _compute_name(self):
        for record in self:
            name_parts = []
            if record.id:
                name_parts.append(f'# {record.id}')
            if record.input_id:
                name_parts.append(record.input_id.name)
            if record.type_deduction:
                name_parts.append(dict(record._fields['type_deduction'].selection).get(record.type_deduction))
            record.name = " - ".join(filter(None, name_parts))

    @api.depends('line_ids', 'line_ids.total')
    def _compute_accumulated(self):
        for record in self:
            record.accumulated_amount = sum(record.line_ids.mapped('total'))

    @api.depends('period', 'amount', 'line_ids', 'date_end', 'date_start', 'aplicar', 
                 'modality_value', 'amount_select', 'monthly_behavior')
    def _compute_balance(self):
        for record in self:
            total_paid = sum(record.line_ids.mapped('total'))
            record.total_paid = total_paid

            if record.period == 'indefinite':
                record.balance = 0
                continue

            base_per_period = record._get_amount_per_period()
            total_periods = record._calculate_total_periods()
            total_expected = base_per_period * total_periods
            record.balance = total_expected - total_paid

    def _get_amount_per_period(self):
        """Calcula el monto por período considerando el comportamiento mensual"""
        base_amount = self._calculate_base_amount()
        
        if self.modality_value != 'fijo':
            # Para modalidad diaria, se calcula por día usando 30 días base
            daily_amount = base_amount / 30
            if self.aplicar == '0':
                return daily_amount * 30
            else:
                return daily_amount * 15
        
        # Para valor fijo, aplicar comportamiento mensual
        if self.monthly_behavior == 'equal':
            return base_amount
        elif self.monthly_behavior == 'divided':
            if self.aplicar == '0':
                return base_amount / 2
            else:
                return base_amount
        elif self.monthly_behavior == 'proportional':
            # Proporcional a 15 días por quincena
            if self.aplicar == '0':
                return base_amount / 2
            else:
                return base_amount
        
        return base_amount

    def _calculate_total_periods(self):
        """Calcula el número total de períodos"""
        if not self.date_start or not self.date_end:
            return 1

        start_date = self.date_start
        end_date = self.date_end
        months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month + 1

        if self.aplicar == '0':
            total_periods = months * 2
            if start_date.day > 15:
                total_periods -= 1
            if end_date.day < 15:
                total_periods -= 1
        else:
            total_periods = months
            if self.aplicar == '15' and start_date.day > 15:
                total_periods -= 1
            elif self.aplicar == '30' and start_date.day <= 15:
                total_periods -= 1

        return max(total_periods, 1)

    @api.depends('balance', 'line_ids', 'date_end')
    def _compute_remaining(self):
        for record in self:
            if record.period == 'indefinite' or not record.balance:
                record.remaining_installments = 0
                continue
            total_periods = record._calculate_total_periods()
            applied_periods = len(record.line_ids.filtered(lambda l: l.slip_id.state in ['done', 'paid']))
            record.remaining_installments = max(total_periods - applied_periods, 0)

    def _calculate_next_payment_date(self, reference_date):
        """Calcula la próxima fecha de pago considerando saltos y reglas"""
        self.ensure_one()

        if not self._is_period_active(reference_date):
            return False

        next_date = self._get_base_payment_date(reference_date)
        if not next_date:
            return False

        last_payslip_line = self._get_last_payslip_line()
        if last_payslip_line:
            next_date = self._adjust_date_after_last_payment(last_payslip_line, next_date)

        next_date = self._adjust_for_payment_rules(next_date)
        
        # Verificar saltos confirmados
        active_skip = self._get_active_skip(next_date, next_date)
        if active_skip:
            # Saltar al siguiente período
            if self.aplicar == '15':
                if next_date.day <= 15:
                    next_date = next_date + relativedelta(day=16)
                else:
                    next_date = next_date + relativedelta(months=1, day=1)
            elif self.aplicar == '30':
                next_date = next_date + relativedelta(months=1, day=1)
            else:
                next_date = next_date + relativedelta(days=15)

        return next_date

    def _is_period_active(self, reference_date):
        """Verifica si el período está activo"""
        if self.date_start and self.date_start > reference_date:
            return False
        if self.date_end and self.date_end < reference_date:
            return False
        return True

    def _get_base_payment_date(self, reference_date):
        """Obtiene la fecha base inicial para el cálculo"""
        if self.date_start and self.date_start > reference_date:
            return self.date_start
        return reference_date

    def _get_last_payslip_line(self):
        """Obtiene la última línea de nómina procesada"""
        return self.line_ids.filtered(
            lambda l: l.slip_id.state in ['done', 'paid']
        ).sorted(lambda l: l.slip_id.date_to, reverse=True)[:1]

    def _adjust_date_after_last_payment(self, last_line, next_date):
        """Ajusta la fecha considerando el último pago"""
        if not last_line:
            return next_date
            
        last_date = last_line.slip_id.date_to
        
        if next_date <= last_date:
            if self.aplicar == '15':
                if last_date.day <= 15:
                    return last_date.replace(day=16)
                return last_date + relativedelta(months=1, day=1)
            elif self.aplicar == '30':
                if last_date.day <= 15:
                    return last_date.replace(day=16)
                return last_date + relativedelta(months=1, day=1)
            else:
                return last_date + relativedelta(days=1)
                
        return next_date

    def _adjust_for_payment_rules(self, date):
        """Ajusta la fecha según las reglas de quincena"""
        if self.aplicar == '15':
            if date.day > 15:
                return date + relativedelta(months=1, day=1)
        elif self.aplicar == '30':
            if date.day <= 15:
                return date + relativedelta(day=16)
        return date

    @api.depends('date_start', 'date_end')
    def _compute_active_period(self):
        """Calcula si el período está activo"""
        today = fields.Date.today()
        for record in self:
            record.active_period = record._is_period_active(today)

    @api.depends('date_start', 'aplicar', 'skip_ids', 'line_ids', 'line_ids.slip_id.state')
    def _compute_next_payment(self):
        """Calcula la próxima fecha de pago"""
        today = fields.Date.today()
        for record in self:
            record.next_payment_date = record._calculate_next_payment_date(today)

    @api.depends('amount', 'modality_value', 'amount_select', 'aplicar', 'type_deduction', 
                 'skip_ids', 'force_double_payment', 'monthly_behavior', 'excluir_sabados',
                 'excluir_domingos', 'excluir_festivos', 'descontar_dia_31')
    def _compute_simulation_details(self):
        for record in self:
            simulation_text = record._generate_simulation_text()
            record.simulation_text = simulation_text

    def _generate_simulation_text(self):
        """Genera el texto detallado de la simulación con comportamiento mensual y exclusiones"""
        self.ensure_one()
        
        # Cálculo base del monto
        base_amount = self._calculate_base_amount()
        
        # Determinar valores por quincena según comportamiento
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                first_fortnight = base_amount if self.aplicar in ['15', '0'] else 0
                second_fortnight = base_amount if self.aplicar in ['30', '0'] else 0
            elif self.monthly_behavior == 'divided':
                half_amount = base_amount / 2
                first_fortnight = half_amount if self.aplicar in ['15', '0'] else 0
                second_fortnight = half_amount if self.aplicar in ['30', '0'] else 0
            else:  # proportional
                first_fortnight = (base_amount * 15 / 30) if self.aplicar in ['15', '0'] else 0
                second_fortnight = (base_amount * 15 / 30) if self.aplicar in ['30', '0'] else 0
        else:
            # Para modalidad diaria
            daily_amount = base_amount / 30
            first_fortnight = daily_amount * 15 if self.aplicar in ['15', '0'] else 0
            second_fortnight = daily_amount * 15 if self.aplicar in ['30', '0'] else 0
        
        # Cálculo diario
        daily_amount = base_amount / 30 if self.modality_value != 'fijo' else 0
        
        # Ejemplo con días normales y con exclusiones
        normal_days = 30
        excluded_days = 0
        if self.excluir_sabados:
            excluded_days += 4
        if self.excluir_domingos:
            excluded_days += 4
        if self.descontar_dia_31:
            excluded_days += 1 if calendar.monthrange(fields.Date.today().year, fields.Date.today().month)[1] == 31 else 0
        
        working_days = normal_days - excluded_days
        
        behavior_text = dict(self._fields['monthly_behavior'].selection).get(self.monthly_behavior, '')
        
        return f"""
        <div style="font-family: system-ui; max-width: 800px; line-height: 1.6;">
            <!-- Información de comportamiento mensual -->
            <div style="margin-bottom: 20px; padding: 15px; background-color: #e3f2fd; border-radius: 4px; border: 1px solid #bbdefb;">
                <div style="font-size: 0.9em; color: #1565c0; font-weight: bold;">Comportamiento Mensual: {behavior_text}</div>
                {(self.excluir_sabados or self.excluir_domingos or self.excluir_festivos or self.descontar_dia_31) and f'''
                <div style="margin-top: 10px; font-size: 0.85em; color: #0d47a1;">
                    Exclusiones activas:
                    {self.excluir_sabados and '<span style="margin-right: 10px;">✓ Sábados</span>' or ''}
                    {self.excluir_domingos and '<span style="margin-right: 10px;">✓ Domingos</span>' or ''}
                    {self.excluir_festivos and '<span style="margin-right: 10px;">✓ Festivos</span>' or ''}
                    {self.descontar_dia_31 and '<span style="margin-right: 10px;">✓ Día 31</span>' or ''}
                </div>''' or ''}
            </div>
            
            <!-- Valores por quincena -->
            <div style="display: flex; gap: 20px; margin-bottom: 20px;">
                <div style="flex: 1; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                    <div style="font-size: 0.9em; color: #6c757d;">Primera Quincena</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529; margin: 8px 0;">
                        ${first_fortnight:,.2f}
                    </div>
                    <div style="font-size: 0.8em; color: #6c757d;">
                        {self.aplicar == '15' and '100%' or self.aplicar == '0' and ('50%' if self.monthly_behavior == 'divided' else 'Proporcional') or 'No aplica'}
                    </div>
                </div>
                <div style="flex: 1; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                    <div style="font-size: 0.9em; color: #6c757d;">Segunda Quincena</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529; margin: 8px 0;">
                        ${second_fortnight:,.2f}
                    </div>
                    <div style="font-size: 0.8em; color: #6c757d;">
                        {self.aplicar == '30' and '100%' or self.aplicar == '0' and ('50%' if self.monthly_behavior == 'divided' else 'Proporcional') or 'No aplica'}
                    </div>
                </div>
            </div>

            {daily_amount > 0 and f'''
            <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border: 1px solid #dee2e6;">
                <div style="margin-bottom: 15px;">
                    <div style="font-size: 0.9em; color: #6c757d;">Valor por día</div>
                    <div style="font-size: 1.4em; font-weight: bold; color: #212529;">
                        ${daily_amount:,.2f}
                    </div>
                </div>

                <div style="display: flex; gap: 20px;">
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #6c757d;">Mes Completo ({normal_days} días)</div>
                        <div style="font-size: 1.2em; color: #212529; margin-top: 5px;">
                            ${daily_amount * normal_days:,.2f}
                        </div>
                    </div>
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #6c757d;">
                            Con Exclusiones ({working_days} días)
                        </div>
                        <div style="font-size: 1.2em; color: #212529; margin-top: 5px;">
                            ${daily_amount * working_days:,.2f}
                        </div>
                        <div style="font-size: 0.8em; color: #dc3545;">
                            -{excluded_days} días excluidos
                        </div>
                    </div>
                </div>
            </div>''' or ''}

            {self.skip_ids and f'''
            <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-radius: 4px; border: 1px solid #ffeeba;">
                <div style="font-size: 0.9em; color: #856404;">Casos con Saltos</div>
                <div style="display: flex; gap: 20px; margin-top: 10px;">
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #856404;">Con Salto</div>
                        <div style="font-size: 1.2em; color: #856404; margin-top: 5px;">
                            $0.00
                        </div>
                    </div>
                    <div style="flex: 1; padding: 10px; background-color: white; border-radius: 4px;">
                        <div style="font-size: 0.9em; color: #856404;">Recuperación ({self.monthly_behavior == 'divided' and 'Mitad y mitad' or self.monthly_behavior == 'equal' and 'Mismo valor' or 'Proporcional'})</div>
                        <div style="font-size: 1.2em; color: #856404; margin-top: 5px;">
                            ${base_amount * 2 if self.monthly_behavior == 'equal' else base_amount:,.2f}
                        </div>
                    </div>
                </div>
            </div>''' or ''}
        </div>
        """

    def _calculate_base_amount(self):
        """Calcula el monto base según el tipo de cálculo"""
        if self.amount_select == 'percentage':
            base_salary = self.contract_id.wage
            return (base_salary * self.amount / 100)
        return self.amount

    def _calculate_days_excluded(self, start_date, end_date):
        """
        Calcula los días excluidos en un período según la configuración
        Returns: tupla (días_excluidos, sabados, domingos, festivos)
        """
        current_date = start_date
        dias_excluidos = 0
        sabados = 0
        domingos = 0
        festivos = 0
        
        while current_date <= end_date:
            if current_date.weekday() == 5 and self.excluir_sabados:
                sabados += 1
                dias_excluidos += 1
            elif current_date.weekday() == 6 and self.excluir_domingos:
                domingos += 1
                dias_excluidos += 1
            elif current_date.day == 31 and self.descontar_dia_31:
                dias_excluidos += 1
                
            if self.excluir_festivos:
                is_holiday = self.env['lavish.holidays'].search_count([('date', '=', current_date)])
                if is_holiday:
                    festivos += 1
                    if current_date.weekday() < 5: 
                        dias_excluidos += 1
                        
            current_date += timedelta(days=1)
            
        return (dias_excluidos, sabados, domingos, festivos)

    def get_amount_for_period_payslip(self, date_from, date_to):
        """Obtener monto para un período específico considerando todas las reglas"""
        self.ensure_one()
        
        if not self._is_valid_period(date_from, date_to):
            return 0

        base_amount = self._calculate_period_amount_slip(date_from, date_to)
        multiplier = self._get_period_multiplier(date_from, date_to)
        sign = 1        
        if self.input_id.dev_or_ded == 'deduccion':
            sign = -1
        return base_amount * multiplier * sign

    def _calculate_period_amount_slip(self, date_from, date_to):
        """Calcula el monto base para el período según la modalidad"""
        base_amount = self.amount
        if self.input_id.dev_or_ded == 'deduccion':
            base_amount = base_amount * -1
        if self.modality_value == 'fijo':
            return base_amount
            
        days = (date_to - date_from).days + 1
        if self.modality_value == 'diario_efectivo':
            return (base_amount / 30) * days
            
        if self.modality_value == 'diario':
            worked_days = self._get_worked_days(date_from, date_to)
            qty = 0
            if worked_days:
                qty = sum(d.number_of_days for d in worked_days)
            return (base_amount / 30) * qty
            
        return base_amount

    def get_amount_for_period(self, date_from, date_to):
        """Obtener monto para un período específico considerando todas las reglas"""
        self.ensure_one()
        
        if not self._is_valid_period(date_from, date_to):
            return 0

        base_amount = self._calculate_period_amount(date_from, date_to)
        multiplier = self._get_period_multiplier(date_from, date_to)
        sign = 1        
        if self.input_id.dev_or_ded == 'deduccion':
            sign = -1
        return base_amount * multiplier * sign

    def _is_valid_period(self, date_from, date_to):
        """Valida si el período es válido para aplicar el concepto"""
        if self.date_start and date_from < self.date_start:
            return False
        if self.date_end and date_to > self.date_end:
            return False
        if not self.active_period:
            return False
        if self.state != 'done':
            return False
        return True

    def _calculate_period_amount(self, date_from, date_to):
        """Calcula el monto base para el período según modalidad y comportamiento"""
        base_amount = self._calculate_base_amount()
        
        # Si es valor fijo, aplicar comportamiento mensual
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                # Mismo valor en ambas quincenas
                return base_amount
            elif self.monthly_behavior == 'divided':
                # Dividir en partes iguales
                if self.aplicar == '0':  # Aplica siempre
                    return base_amount / 2
                else:
                    return base_amount
            elif self.monthly_behavior == 'proportional':
                # Proporcional a días del período
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                return (base_amount * days_in_period) / days_in_month
        
        # Para modalidad diaria, calcular según días trabajados
        days = (date_to - date_from).days + 1
        if self.modality_value == 'diario_efectivo':
            # Restar días excluidos
            excluded, _, _, _ = self._calculate_days_excluded(date_from, date_to)
            days = days - excluded
            return (base_amount / 30) * days
        elif self.modality_value == 'diario':
            worked_days = self._get_worked_days(date_from, date_to)
            qty = sum(d.number_of_days for d in worked_days) if worked_days else days
            return (base_amount / 30) * qty
        
        return base_amount

    def _get_worked_days(self, date_from, date_to):
        """Obtiene los días efectivamente trabajados en el período"""
        return self.env['hr.payslip.worked_days'].search([
            ('payslip_id.employee_id', '=', self.contract_id.employee_id.id),
            ('payslip_id.date_from', '>=', date_from),
            ('payslip_id.struct_id.process', '=', 'nomina'),
            ('payslip_id.date_to', '<=', date_to),
            ('code', '=', 'WORK100'),
        ])

    def _get_period_multiplier(self, date_from, date_to):
        """Obtiene el multiplicador del período considerando pagos dobles y saltos"""
        # Verificar pago doble forzado
        if self.force_double_payment and self.double_payment_date:
            if date_from <= self.double_payment_date <= date_to:
                self._mark_double_payment_applied()
                return 2

        # Verificar saltos programados
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                return 2
            return 0

        # Verificar aplicación según quincena
        if self.aplicar == '15' and date_to.day > 15:
            return 0
        elif self.aplicar == '30' and date_from.day <= 15:
            return 0

        return 1

    def _get_active_skip(self, date_from, date_to):
        """Obtiene el salto activo para el período si existe"""
        for skip in self.skip_ids:
            if skip.check_skip_applies(date_from, date_to):
                return skip
        return False

    def _mark_double_payment_applied(self):
        """Marca el pago doble como aplicado"""
        self.write({
            'force_double_payment': False,
            'last_double_payment': self.double_payment_date,
            'double_payment_date': False
        })

    def get_computed_amount_for_payslip(self, payslip, date_from, date_to, localdict):
        """
        Calcula el monto para la nómina según configuración y localdict.
        """
        self.ensure_one()
        precision = 2
        contract = localdict['contract']
        # Filtrar días trabajados WORK100 desde el payslip
        wd100 = payslip.worked_days_line_ids.filtered(lambda w: w.code == 'WORK100')
        annual_params = localdict['annual_parameters']
        
        if not self._should_apply_in_period(payslip, date_from, date_to, localdict):
            return self._no_apply(
                _("""El concepto no se aplica en el período seleccionado. 
                Verifique la configuración de fechas y condiciones."""),
                f"{date_from} - {date_to}"
            )
        
        # Aviso si contrato mensual con concepto quincenal
        aviso = None
        if contract.method_schedule_pay == 'monthly' and self.aplicar in ('15', '30'):
            aviso = _('[AVISO] Contrato mensual con concepto quincenal, se usará periodo real')
        
        days = 0
        # Días naturales en el periodo
        raw_days = (date_to - date_from).days + 1
        
        # Calcular días según WORK100 o exclusiones
        if wd100 and not contract.subcontract_type:
            if payslip.struct_type_id.wage_type == 'hourly':
                raw_days = wd100.number_of_hours / annual_params.hours_daily
            else:
                raw_days = wd100.number_of_days
            
            excluded = 0
            if self.excluir_sabados:
                excluded += localdict.get('sabado', 0)
            if self.excluir_domingos:
                excluded += localdict.get('domingos', 0)
            if self.excluir_festivos:
                excluded += localdict.get('festivos', 0)
            
            days = max(0, raw_days - excluded)
        else:
            days = raw_days
            
        # Limitar días al máximo del mes y redondear
        max_days = calendar.monthrange(date_to.year, date_to.month)[1]
        days = min(days, max_days)
        days = round(days, precision)

        # Construir pasos
        steps = []
        step = 1
        if aviso:
            steps.append(f"{step}. {aviso}")
            step += 1
            
        # Base
        if self.amount_select == 'percentage':
            base_amt = contract.wage * (self.amount / 100)
            steps.append(f"{step}. Base: {self.amount}% de {contract.wage:,.2f} = {base_amt:,.2f}")
        else:
            base_amt = self.amount
            steps.append(f"{step}. Base fija: {base_amt:,.2f}")
        step += 1
        
        # Modalidad
        modal = dict(self._fields['modality_value'].selection)[self.modality_value]
        steps.append(f"{step}. Modalidad valor: {modal}")
        step += 1
        
        # Comportamiento mensual
        behavior = dict(self._fields['monthly_behavior'].selection)[self.monthly_behavior]
        steps.append(f"{step}. Comportamiento mensual: {behavior}")
        step += 1
        
        # Días
        steps.append(f"{step}. Días computados: {days:.2f}")
        step += 1

        # Cálculo final según modalidad y comportamiento
        if self.modality_value == 'fijo':
            if self.monthly_behavior == 'equal':
                amt = base_amt
                steps.append(f"{step}. Valor fijo con comportamiento igual: {amt:,.2f}")
                fmt = f"{base_amt:,.2f}"
            elif self.monthly_behavior == 'divided':
                if self.aplicar == '0':
                    amt = base_amt / 2
                    fmt = f"{base_amt:,.2f} ÷ 2 = {amt:,.2f}"
                    steps.append(f"{step}. Dividido en partes iguales: {fmt}")
                else:
                    amt = base_amt
                    fmt = f"{base_amt:,.2f}"
                    steps.append(f"{step}. Valor completo para quincena: {amt:,.2f}")
            else:  # proportional
                days_in_period = (date_to - date_from).days + 1
                days_in_month = calendar.monthrange(date_to.year, date_to.month)[1]
                amt = (base_amt * days_in_period) / days_in_month
                fmt = f"({base_amt:,.2f} × {days_in_period}) ÷ {days_in_month} = {amt:,.2f}"
                steps.append(f"{step}. Proporcional a días: {fmt}")
        else:
            daily = base_amt / 30
            steps.append(f"{step}. Valor diario: {base_amt:,.2f} ÷ 30 = {daily:,.2f}")
            step += 1
            amt = daily * days
            fmt = f"{daily:,.2f} × {days:.2f} = {amt:,.2f}"
            steps.append(f"{step}. Cálculo diario × días = {fmt}")
        step += 1

        # Verificar saltos
        skip = self._get_active_skip(date_from, date_to)
        if skip:
            if skip.period_double:
                amt = amt * 2
                steps.append(f"{step}. Aplicando pago doble por salto: {amt:,.2f}")
                step += 1
            else:
                amt = 0
                steps.append(f"{step}. Período saltado: monto = 0")
                step += 1

        # Signo
        result_amt = round(amt, precision)
        is_deduction = self.input_id.dev_or_ded == 'deduccion' if self.input_id else False
        if is_deduction and result_amt > 0:
            result_amt = -result_amt
            fmt += " ×(-1)"
            steps.append(f"{step}. Ajuste signo deducción = {result_amt:,.2f}")

        # Actualizar estado
        self.write({
            'payslip_ids': [(4, payslip.id)]
        })
        
        if self.total_paid:
            step += 1
            steps.append(f"{step}. Total pagado previo = {self.total_paid:,.2f}")

        # Construir nombre dinámico
        indicator = '1Q' if date_to.day <= 15 else '2Q'
        name = f"{self.input_id.name} - {indicator} {date_to.month}/{date_to.year}"
        if self.modality_value != 'fijo':
            name += f" ({days:.0f}d)"

        detail_html = self._build_concept_html_log(
            periodo=f"{indicator} {date_to.month}/{date_to.year}",
            aplicado=True,
            descripcion=_('Cálculo de') + f" {self.input_id.name}",
            rango_log=[
                ('Monto base', f"{base_amt:,.2f}"), 
                ('Días', f"{days:.2f}"),
                ('Comportamiento', behavior)
            ],
            pasos=steps,
            monto_final=result_amt,
            formula=fmt
        )
        _logger.error({
            'create_line': True,
            'values': {
                'name': name,
                'code': self.input_id.code,
                'amount': result_amt,
                'quantity': 1 if self.modality_value == 'fijo' else days,
                'rate': 100,
                'concept_id': self.id,
            },
            'skip_info': {},
            'formula': fmt,
            'detail_html': detail_html
        })
        return {
            'create_line': True,
            'values': {
                'name': name,
                'code': self.input_id.code,
                'amount': result_amt,
                'quantity': 1 if self.modality_value == 'fijo' else days,
                'rate': 100,
                'concept_id': self.id,
            },
            'skip_info': {},
            'formula': fmt,
            'detail_html': detail_html
        }
    def _should_apply_in_period(self, payslip, date_from, date_to, localdict):
        if self.aplicar == '30': 
            if date_from.day <= 15:
                return False
        
        elif self.aplicar == '15':
            if date_from.day > 15:
                return False
        if self.date_start and not (self.date_start < date_to or self.date_start == date_to):
            return False
            
        if self.date_end and not (self.date_end > date_from or self.date_end == date_from):
            return False
        
        if self.state != 'done':
            return False
        return True


    def _no_apply(self, reason, period):
        """Retorna estructura cuando no se aplica el concepto"""
        return {
            'create_line': False,
            'values': {},
            'skip_info': {
                'reason': reason,
                'period': period
            },
            'formula': '',
            'detail_html': f'<div style="color: #dc3545;">{reason}</div>'
        }

    def _get_justified_absence_codes(self):
        """Retorna los códigos de ausencias justificadas"""
        return ['LEAVE90', 'LEAVE100', 'LEAVE110', 'LEAVE120']

    def _build_concept_html_log(self, periodo, aplicado, descripcion, rango_log, pasos, monto_final, formula):
        """Construye el HTML del log de cálculo"""
        pasos_html = ''.join([f'<li>{paso}</li>' for paso in pasos])
        rango_html = ''.join([f'<tr><td>{key}</td><td>{value}</td></tr>' for key, value in rango_log])
        
        return f"""
        <div style="font-family: system-ui; padding: 20px; background: #f8f9fa; border-radius: 8px;">
            <h4 style="color: #212529; margin-bottom: 10px;">{descripcion}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
                <div>
                    <strong>Período:</strong> {periodo}<br>
                    <strong>Estado:</strong> {'<span style="color: #28a745;">Aplicado</span>' if aplicado else '<span style="color: #dc3545;">No aplicado</span>'}
                </div>
                <div>
                    <table style="width: 100%; border-collapse: collapse;">
                        {rango_html}
                    </table>
                </div>
            </div>
            <div style="background: white; padding: 15px; border-radius: 4px; margin-bottom: 15px;">
                <strong>Pasos del cálculo:</strong>
                <ol style="margin: 10px 0; padding-left: 20px;">
                    {pasos_html}
                </ol>
            </div>
            <div style="background: #e3f2fd; padding: 15px; border-radius: 4px; text-align: center;">
                <strong>Fórmula:</strong> {formula}<br>
                <strong style="font-size: 1.2em; color: #1976d2;">Monto Final: ${monto_final:,.2f}</strong>
            </div>
        </div>
        """

    # Métodos de acción
    def action_draft(self):
        """Pasar a borrador"""
        self.write({'state': 'draft'})

    def action_approve(self):
        """Aprobar concepto"""
        self.write({'state': 'done'})

    def action_cancel(self):
        """Cancelar concepto"""
        self.write({'state': 'cancel'})

    def action_force_double_payment(self):
        """Forzar pago doble"""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Solo se puede forzar pago doble en conceptos aprobados'))
            
        next_date = self._calculate_next_payment_date(fields.Date.today())
        if not next_date:
            raise UserError(_('No se puede determinar la próxima fecha de pago'))
            
        self.write({
            'force_double_payment': True,
            'double_payment_date': next_date
        })

    def action_cancel_double_payment(self):
        """Cancelar pago doble programado"""
        self.write({
            'force_double_payment': False,
            'double_payment_date': False
        })

    def apply_to_payslip(self, payslip):
        """Aplicar concepto a una nómina específica"""
        self.ensure_one()
        
        # Validar estado del concepto
        if self.state != 'done':
            return False

        # Obtener valores para la nómina
        values = self._get_payslip_values(payslip)
        if not values['amount']:
            return False

        # Crear línea de nómina
        line = self.env['hr.payslip.line'].create({
            'slip_id': payslip.id,
            'salary_rule_id': self.input_id.id,
            'contract_id': self.contract_id.id,
            'employee_id': payslip.employee_id.id,
            'concept_id': self.id,
            'amount': values['amount'],
            'total': values['amount'], 
            'quantity': 1.0,
            'rate': 100.0,
            **values
        })

        return line

    def _get_payslip_values(self, payslip):
        """Obtener valores para la línea de nómina"""
        self.ensure_one()
        values = {
            'name': self.input_id.name,
            'code': self.input_id.code,
            'sequence': self.sequence,
        }
        
        amount = self.get_amount_for_period(payslip.date_from, payslip.date_to)
        if self.amount_select == 'percentage':
            values['rate'] = self.amount
            values['amount'] = amount
        else:
            values['amount'] = amount
            
        return values

    def unlink(self):
        for record in self:
            if record.line_ids:
                raise ValidationError(_('No se puede eliminar una novedad que ha sido aplicada en nómina. '
                                    'Solo se puede cancelar para mantener el histórico.'))
        return super().unlink()

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_lines(self):
        if any(record.line_ids for record in self):
            raise ValidationError(_('No se puede eliminar una novedad que ha sido aplicada en nómina. '
                                'Solo se puede cancelar para mantener el histórico.'))

    # ==================== MÉTODOS DE ACCIÓN ====================

    def view_simulation(self):
        """Mostrar información de simulación del concepto"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Simulación de Concepto'),
                'message': self.simulation_text if self.simulation_text else _('Configure el concepto y calcule una nómina para ver la simulación'),
                'sticky': True,
                'type': 'info'
            }
        }

    def action_create_skip(self):
        """Crear un salto para este concepto"""
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_('Solo se pueden crear saltos para conceptos aprobados'))

        if not self.allow_skips:
            raise UserError(_('Este concepto no permite crear saltos'))

        # Crear salto en borrador para el próximo período
        next_date = self.next_payment_date or fields.Date.today()

        skip = self.env['hr.contract.concept.skip'].create({
            'concept_id': self.id,
            'period_skip': next_date,
            'fortnight': self.aplicar if self.aplicar in ['15', '30'] else '15',
            'reason': _('Salto creado manualmente'),
            'state': 'draft',
        })

        return {
            'name': _('Salto de Concepto'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.concept.skip',
            'res_id': skip.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def view_skips(self):
        """Ver todos los saltos de este concepto"""
        self.ensure_one()
        return {
            'name': _('Saltos - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.concept.skip',
            'domain': [('concept_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_concept_id': self.id}
        }

    def view_payslip_lines(self):
        """Ver todas las líneas de nómina de este concepto"""
        self.ensure_one()
        return {
            'name': _('Líneas de Nómina - %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.line',
            'domain': [('concept_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {
                'create': False,
                'delete': False,
            }
        }

    def action_close(self):
        """Cerrar el concepto"""
        self.ensure_one()

        if self.state != 'done':
            raise UserError(_('Solo se pueden cerrar conceptos aprobados'))

        if not self.close_ready:
            raise UserError(_('Este concepto no está listo para cerrar. Verifique que el saldo sea cero o cercano a cero.'))

        payslip_id = self.env.context.get('payslip_id')

        self.write({
            'state': 'closed',
            'closed_date': fields.Date.today(),
            'closed_payslip_id': payslip_id if payslip_id else False,
        })

        self.message_post(
            body=_('Concepto cerrado. Saldo final: $%s') % '{:,.2f}'.format(self.balance)
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Concepto Cerrado'),
                'message': _('El concepto ha sido cerrado exitosamente'),
                'type': 'success',
                'sticky': False,
            }
        }

class hr_contractual_modifications(models.Model):
    _name = 'hr.contractual.modifications'
    _description = 'Modificaciones contractuales'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade',  index=True)
    date = fields.Date('Fecha', required=True)
    description = fields.Char('Descripción de modificacion contractual', required=True)
    attached = fields.Many2one('documents.document', string='Adjunto')
    prorroga = fields.Boolean(string='Prórroga')
    wage = fields.Float('Salario basico', help='Seguimento de los cambios en el salario basico')
    sequence = fields.Integer('Numero de Prórroga')
    date_from = fields.Date('Fecha de Inicio Prórroga')
    date_to = fields.Date('Fecha de Fin Prórroga')

    @api.onchange('wage')
    def _change_wage(self):
        for line in self:
            if line.wage !=0:
                line.contract_id.change_wage_ids.create({'wage': line.wage,
                                                                    'date_start' : self.date_from,
                                                                    'contract_id':  line.contract_id.id, }) 
                line.contract_id.change_wage()

#Deducciones para retención en la fuente
class hr_contract_deductions_rtf(models.Model):
    _name = 'hr.contract.deductions.rtf'
    _description = 'Reglas salariales para retención en la fuente'

    input_id = fields.Many2one('hr.salary.rule', 'Regla', required=True, help='Regla salarial', domain="[('type_concepts','=','tributaria')]")
    date_start = fields.Date('Fecha Inicial')
    date_end = fields.Date('Fecha Final')
    number_months = fields.Integer('N° Meses')
    value_total = fields.Float('Valor Total')
    value_monthly = fields.Float('Valor Mensualizado')
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade', index=True)

    #Validaciones
    @api.onchange('value_total')
    def _onchange_value_total(self):
        for record in self:
            if record.value_total > 0:
                if not record.date_start:
                    raise UserError(_('No se ha especificado la fecha inicial.'))        
                if not record.date_end:
                    raise UserError(_('No se ha especificado la fecha final'))   

                nSecondDif = (record.date_end - record.date_start).total_seconds()
                nMinutesDif = round(nSecondDif/60,0)
                nHoursDif = round(nMinutesDif/60,0)
                nDaysDif = round(nHoursDif/24,0)
                nMonthsDif = round(nDaysDif/30,0)

                if nMonthsDif != 0:
                    if record.number_months>0:
                        self.value_monthly = record.value_total / record.number_months
                    else:
                        self.value_monthly = record.value_total / 12
                else:    
                    raise UserError(_('La fecha inicial es mayor que la fecha final, por favor verificar.'))       

    @api.onchange('value_monthly')
    def _onchange_value_monthly(self):
        for record in self:
            if record.value_monthly > 0:
                if not record.date_start:
                    raise UserError(_('No se ha especificado la fecha inicial.'))        
                if not record.date_end:
                    raise UserError(_('No se ha especificado la fecha final'))   

                nSecondDif = (record.date_end - record.date_start).total_seconds()
                nMinutesDif = round(nSecondDif/60,0)
                nHoursDif = round(nMinutesDif/60,0)
                nDaysDif = round(nHoursDif/24,0)
                nMonthsDif = round(nDaysDif/30,0)

                if nMonthsDif != 0:
                    if record.number_months>0:
                        self.value_total = record.value_monthly * record.number_months
                    else:
                        self.value_total = record.value_monthly * 12
                else:    
                    raise UserError(_('La fecha inicial es mayor que la fecha final, por favor verificar.'))    

    _change_deductionsrtf_uniq = models.Constraint('unique(input_id, contract_id)', 'Ya existe esta deducción para este contrato, por favor verficar.')

class hr_type_of_jurisdiction(models.Model):
    _name = 'hr.type.of.jurisdiction'
    _description = 'Tipo de Fuero'

    name = fields.Char('Tipo de Fuero')

    _type_of_jurisdiction_uniq = models.Constraint('unique(name)',
                                                   'Ya existe este tipo de fuero, por favor verificar.')

#Histórico de contratación
class hr_contract_history(models.Model):
    _inherit = 'hr.contract.history'

    state = fields.Selection(selection_add=[('finished', 'Finalizado Por Liquidar')],ondelete={"finished": "set null"})

class hr_employee_endowment(models.Model):
    _name = 'hr.employee.endowment'
    _description = 'Dotación'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    date = fields.Date('Fecha de Entrega')
    supplies = fields.Char('Descripción - Periodo de entrega')
    attached = fields.Many2one('documents.document', string='Adjunto')

#Contratos
class hr_contract(models.Model):
    _inherit = 'hr.contract'
    
    @api.model
    def _get_default_deductions_rtf_ids(self):
        salary_rules_rtf = self.env['hr.salary.rule'].search([('type_concepts', '=', 'tributaria')])
        data = []
        for rule in salary_rules_rtf:
            info = (0,0,{'input_id':rule.id})
            data.append(info)

        return data

    state = fields.Selection(selection_add=[('finished', 'Finalizado Por Liquidar'),
                                        ('close', 'Vencido'),
                                        ], ondelete={'finished': 'set default'} )
    analytic_account_id = fields.Many2one('account.analytic.account', tracking=True)
    job_id = fields.Many2one('hr.job', tracking=True)
    company_id = fields.Many2one('res.company', tracking=True)
    sequence = fields.Char(string="Secuencia", default="/", readonly=True)
    retirement_date = fields.Date('Fecha retiro', tracking=True)
    change_wage_ids = fields.One2many('hr.contract.change.wage', 'contract_id', 'Cambios salario')
    concepts_ids = fields.One2many('hr.contract.concepts', 'contract_id', 'Devengos & Deducciones', domain=[('state', '!=', 'cancel')])
    contract_modification_history = fields.One2many('hr.contractual.modifications', 'contract_id','Modificaciones contractuales')
    deductions_rtf_ids = fields.One2many('hr.contract.deductions.rtf', 'contract_id', 'Deducciones retención en la fuente', default=_get_default_deductions_rtf_ids, tracking=True)
    risk_id = fields.Many2one('hr.contract.risk', string='Riesgo profesional', tracking=True)
    z_economic_activity_level_risk_id = fields.Many2one('lavish.economic.activity.level.risk', string='Actividad económica por nivel de riesgo', tracking=True)
    economic_activity_level_risk_id = fields.Many2one('lavish.economic.activity.level.risk', string='Actividad económica por nivel de riesgo', tracking=True)
    contract_type = fields.Selection([('obra', 'Contrato por Obra o Labor'), 
                                      ('fijo', 'Contrato de Trabajo a Término Fijo'),
                                      ('fijo_parcial', 'Contrato de Trabajo a Término Fijo Tiempo Parcial'),
                                      ('indefinido', 'Contrato de Trabajo a Término Indefinido'),
                                      ('aprendizaje', 'Contrato de Aprendizaje'), 
                                      ('temporal', 'Contrato Temporal, ocasional o accidental')], 'Tipo de Contrato',required=True, default='obra', tracking=True)
    subcontract_type = fields.Selection([('obra_parcial', 'Parcial'),
                                         ('obra_integral', 'Parcial Integral')], 'SubTipo de Contrato', tracking=True)
    modality_salary = fields.Selection([('basico', 'Básico'), 
                                      ('sostenimiento', 'Cuota de sostenimiento'), 
                                      ('integral', 'Integral'),
                                      ('especie', 'En especie'), 
                                      ('variable', 'Variable')], 'Modalidad de salario', required=True, default='basico', tracking=True)
    modality_aux = fields.Selection([('basico', 'Sin variación'), 
                                        ('variable', 'Variable'),
                                      ('no', 'Sin aux'), ], 'Auxilio de transporte en prestaciones sociales', default='basico', tracking=True)
    code_sena = fields.Char('Código SENA')                                
    view_inherit_employee = fields.Boolean('Viene de empleado')    
    type_employee = fields.Many2one(string='Tipo de empleado', store=True, readonly=True, related='employee_id.type_employee')
    not_validate_top_auxtransportation = fields.Boolean(string='No validar tope de auxilio de transporte', tracking=True)
    not_pay_overtime = fields.Boolean(string='No liquidarle horas extras', tracking=True)
    pay_auxtransportation = fields.Boolean(string='Liquidar auxilio de transporte a fin de mes', tracking=True)
    not_pay_auxtransportation = fields.Boolean(string='No liquidar auxilio de transporte', tracking=True)
    info_project = fields.Char(related='employee_id.info_project', store=True)
    branch_id = fields.Many2one(related='employee_id.branch_id', store=True)
    emp_work_address_id = fields.Many2one(related='employee_id.address_id',string="Ubicación laboral", store=True)
    emp_identification_id = fields.Char(related='employee_id.identification_id',string="Número de identificación", store=True)
    fecha_ibc = fields.Date('Fecha IBC Anterior')
    u_ibc = fields.Float('IBC Anterior')
    factor = fields.Float(
        string='Factor salarial',
        help='Factor aplicado al salario para contratos de tiempo parcial (Ej: 0.5 = 50%, 0.25 = 25%)'
    )
    proyectar_fondos = fields.Boolean('Proyectar Fondos')
    proyectar_ret = fields.Boolean('Proyectar Retenciones')
    parcial = fields.Boolean(
        string='Tiempo parcial',
        help='Marque si es contrato de tiempo parcial (para BASIC004 y días manuales)'
    )
    pensionado = fields.Boolean('Pensionado')
    date_to = fields.Date('Finalización contrato fijo')
    sena_code = fields.Char('SENA code')
    date_prima = fields.Date('Ultima Fecha de liquidación de prima')
    u_prima = fields.Float('Ultima Prov. Prima') 
    date_cesantias = fields.Date('Ultima Fecha de liquidación de cesantías')
    u_cesantias = fields.Float('Ultima Prov. Cesantia')
    date_vacaciones = fields.Date('Ultima Fecha de liquidación de vacaciones')
    u_vacaciones  = fields.Float('Ultima Prov. vacaciones')
    retention_procedure = fields.Selection([('100', 'Procedimiento 1'),
                                            ('102', 'Procedimiento 2'),
                                            ('extranjero_no_residente', 'Extranjero No Residente'),
                                            ('fixed', 'Valor fijo')], 'Procedimiento retención', default='100', tracking=True)
    fixed_value_retention_procedure = fields.Float('Valor fijo retención', tracking=True)
    method_schedule_pay = fields.Selection([('bi-weekly', 'Quincenal'),
                                            ('monthly', 'Mensual')], 'Frecuencia de Pago', tracking=True)
    apr_prod_date = fields.Date('Fecha de cambio a etapa productiva',
                                help="Marcar unicamente cuando el aprendiz pase a etapa productiva")
    only_wage = fields.Selection([('wage', 'Solo Salario Base'),
                                    ('wage_dev', 'Salario + Devengos'),
                                    ('wage_dev_exc', 'Salario + Devengos (Excluidos)')
                                ], string='Validación para Auxilio Transporte', default='wage', help='Determina cómo se valida el tope para el auxilio de transporte')
    dev_aux = fields.Boolean(string="Devolver Auxilio Transporte",  help='Determina cómo se valida la Devolucion para el auxilio de transporte')
    type_of_jurisdiction = fields.Many2one('hr.type.of.jurisdiction', string ='Tipo de Fuero')                             
    date_i = fields.Date('Fecha Inicial')
    date_f = fields.Date('Fecha Final')
    relocated = fields.Char('Reubicados')
    previous_positions = fields.Char('Cargo anterior')
    new_positions = fields.Char('Cargo nuevo')
    time_with_the_state = fields.Char('Tiempo que lleva con el estado')
    date_last_wage = fields.Date('Fecha Ultimo sueldo')
    wage_old = fields.Float('Salario basico', help='Seguimento de los cambios en el salario basico')
    skip_commute_allowance = fields.Boolean(string='Omitir Auxilio de Transporte')
    remote_work_allowance = fields.Boolean(string='Aplica Auxilio de Conectividad')
    minimum_wage = fields.Boolean(string='Devenga Salario Mínimo')
    ley_2101 = fields.Boolean(string='disminucion jornada laboral')
    limit_deductions = fields.Boolean(string='Limitar Deducciones al 50% de Devengos')
    #Pestaña de dotacion
    employee_endowment_ids = fields.One2many('hr.employee.endowment', 'contract_id', 'Dotación')
    progress = fields.Float('Progreso', compute='_compute_progress')
    paysplip_ids = fields.One2many(
        string='Historial de Nominas', comodel_name='hr.payslip',
        inverse_name='contract_id')
    trial_date_start = fields.Date("Inicio Periodo de Prueba", compute="_compute_periodo_prueba", store=True, readonly=False)
    trial_date_end = fields.Date("Fin Periodo de Prueba", compute="_compute_periodo_prueba", store=True, readonly=False)

    # Campos para días manuales
    use_manual_days = fields.Boolean(
        string='Usar días manuales por defecto',
        default=False,
        help='Si se activa, las nóminas generadas usarán automáticamente los días manuales configurados'
    )
    manual_days = fields.Float(
        string='Días manuales por defecto',
        help='Días a considerar por defecto en el cálculo de nómina cuando se active "Usar días manuales"'
    )
    contract_type_icon_html = fields.Html(
        string='Icono',
        compute='_compute_contract_type_icon',
        help='Icono Font Awesome según el tipo de contrato'
    )

    @api.depends('contract_type', 'subcontract_type', 'modality_salary')
    def _compute_contract_type_icon(self):
        """Asigna icono Font Awesome según el tipo de contrato."""
        for record in self:
            icons = {
                'obra': ('fa-briefcase', 'Obra o Labor'),
                'fijo': ('fa-calendar-check-o', 'Término Fijo'),
                'fijo_parcial': ('fa-calendar-times-o', 'Fijo Tiempo Parcial'),
                'indefinido': ('fa-infinity', 'Indefinido'),
                'aprendizaje': ('fa-graduation-cap', 'Aprendizaje'),
                'temporal': ('fa-clock-o', 'Temporal'),
            }

            # Determinar icono y título
            if record.subcontract_type:
                icon_class = 'fa-puzzle-piece'
                title = 'Subcontrato'
            elif record.modality_salary == 'integral':
                icon_class = 'fa-star'
                title = 'Salario Integral'
            elif record.modality_salary == 'sostenimiento':
                icon_class = 'fa-graduation-cap'
                title = 'Sostenimiento'
            else:
                icon_class, title = icons.get(record.contract_type, ('fa-file-text-o', 'Contrato'))

            # Generar HTML del icono
            record.contract_type_icon_html = f'<i class="fa {icon_class}" style="font-size: 18px; color: #007bff;" title="{title}"></i>'

    @api.onchange('parcial')
    def _onchange_parcial(self):
        """Cuando se activa 'parcial', establece valores por defecto."""
        if self.parcial:
            if not self.factor or self.factor == 0:
                self.factor = 0.5
            if not self.use_manual_days:
                self.use_manual_days = True
        else:
            # Al desactivar, limpiar los campos relacionados
            self.factor = 0.0
            self.use_manual_days = False
            self.manual_days = 0.0

    @api.depends('date_start')
    def _compute_periodo_prueba(self):
        for record in self:
            if record.date_start:
                start_dt = record.date_start
                date_end = start_dt - relativedelta(days=1) + relativedelta(months=2)
                record.trial_date_start = record.date_start
                record.trial_date_end = date_end
            else:
                record.trial_date_start = False
                record.trial_date_end = False

    #@api.depends('date_start', 'date_end')
    def _compute_progress(self):
        for record in self:
            if record.date_start and record.date_end:
                total_days = (record.date_end - record.date_start).days
                elapsed_days = (datetime.now().date() - record.date_start).days
                record.progress = (elapsed_days / total_days) * 100 if total_days > 0 else 0
            else:
                record.progress = 0 

    def _compute_display_name(self):
        for record in self:
            record.display_name = "{} | {}".format(record.sequence,record.employee_id.name)

    def get_selection_label(self, field_name):
        """
        Obtiene la etiqueta en español de un campo Selection usando _description_selection().

        Args:
            field_name (str): Nombre del campo Selection

        Returns:
            str: Etiqueta del valor actual del campo en español, o '' si no existe

        Ejemplo:
            contract.get_selection_label('contract_type')  # Retorna 'Contrato por Obra o Labor'
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

    def extend_contract(self):
        """Extend contract end date"""
        max_extensions, min_days = 3, 360
        for contract in self:
            if not contract.contract_modification_history:
                raise ValidationError(CONTRACT_EXTENSION_NO_RECORD_WARN)
            last_extension = contract.contract_modification_history.sorted(key=lambda r: r.sequence and r.prorroga)[LAST_ONE]
            contract.date_end = last_extension.date_to
            contract.state = 'open'
            if len(contract.contract_modification_history.filtered(lambda r: r.prorroga)) <= max_extensions:
                continue
            extension_span_days = self.dias360(
                last_extension.date_from, last_extension.date_to)                
            if extension_span_days < min_days:
                raise ValidationError(CONTRACT_EXTENSION_MAX_WARN)

    @api.model
    def update_state(self):
        contracts = self.search([
            ('state', '=', 'open'), ('kanban_state', '!=', 'blocked'),
            '|',
            '&',
            ('date_end', '<=', fields.Date.to_string(date.today() + relativedelta(days=7))),
            ('date_end', '>=', fields.Date.to_string(date.today() + relativedelta(days=1))),
            '&',
            ('visa_expire', '<=', fields.Date.to_string(date.today() + relativedelta(days=60))),
            ('visa_expire', '>=', fields.Date.to_string(date.today() + relativedelta(days=1))),
        ])

        for contract in contracts:
            contract.activity_schedule(
                'mail.mail_activity_data_todo', contract.date_end,
                _("The contract of %s is about to expire.", contract.employee_id.name),
                user_id=contract.hr_responsible_id.id or self.env.uid)

        contracts.write({'kanban_state': 'blocked'})

        self.search([
            ('state', '=', 'open'),
            '|',
            ('date_end', '<=', fields.Date.to_string(date.today() + relativedelta(days=1))),
            ('visa_expire', '<=', fields.Date.to_string(date.today() + relativedelta(days=1))),
        ]).write({
            'state': 'finished'
        })

        self.search([('state', '=', 'draft'), ('kanban_state', '=', 'done'),
                     ('date_start', '<=', fields.Date.to_string(date.today())), ]).write({
            'state': 'open'
        })

        contract_ids = self.search([('date_end', '=', False), ('state', '=', 'finished'), ('employee_id', '!=', False)])
        # Ensure all finished contract followed by a new contract have a end date.
        # If finished contract has no finished date, the work entries will be generated for an unlimited period.
        for contract in contract_ids:
            next_contract = self.search([
                ('employee_id', '=', contract.employee_id.id),
                ('state', 'not in', ['cancel', 'new']),
                ('date_start', '>', contract.date_start)
            ], order="date_start asc", limit=1)
            if next_contract:
                contract.date_end = next_contract.date_start - relativedelta(days=1)
                continue
            next_contract = self.search([
                ('employee_id', '=', contract.employee_id.id),
                ('date_start', '>', contract.date_start)
            ], order="date_start asc", limit=1)
            if next_contract:
                contract.date_end = next_contract.date_start - relativedelta(days=1)

        return True

    def action_state_open(self):
        self.write({'state':'open'})

    def action_state_cancel(self):
        self.write({'state':'cancel'})

    def action_state_finished(self):
        self.write({'state':'finished'})

    @api.depends('change_wage_ids')
    @api.onchange('change_wage_ids')
    def change_wage(self):
        for record in self:
            for change in sorted(record.change_wage_ids, key=lambda x: x.date_start):
                record.wage = change.wage
                record.job_id = change.job_id
                record.wage_old = change.wage
                record.date_last_wage = change.date_start

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['sequence'] = self.env['ir.sequence'].next_by_code('hr.contract.seq') or ' '
        obj_contract = super().create(vals_list)
        return obj_contract
    
    def get_wage_in_date(self,process_date):
        wage_in_date = self.wage
        for change in sorted(self.change_wage_ids, key=lambda x: x.date_start):
            if process_date >= change.date_start:
                wage_in_date = change.wage
        return wage_in_date


    def generate_labor_certificate(self):
        ctx = self.env.context.copy()
        ctx.update({'default_contract_id': self.id, 'default_date_generation': fields.Date.today()})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Certificado laboral',
            'res_model': 'hr.labor.certificate.history',
            'domain': [],
            'view_mode': 'form',
            'target':'new',
            'context': ctx
        }

    def get_contract_type(self):
        if self.contract_type:
            model_type = dict(self._fields['contract_type'].selection).get(self.contract_type)
            return model_type.upper()
        else:
            return ''

    def get_date_text(self,date,calculated_week=0):
        #Mes
        month = ''
        month = 'Enero' if date.month == 1 else month
        month = 'Febrero' if date.month == 2 else month
        month = 'Marzo' if date.month == 3 else month
        month = 'Abril' if date.month == 4 else month
        month = 'Mayo' if date.month == 5 else month
        month = 'Junio' if date.month == 6 else month
        month = 'Julio' if date.month == 7 else month
        month = 'Agosto' if date.month == 8 else month
        month = 'Septiembre' if date.month == 9 else month
        month = 'Octubre' if date.month == 10 else month
        month = 'Noviembre' if date.month == 11 else month
        month = 'Diciembre' if date.month == 12 else month
        #Dia de la semana
        week = ''
        week = 'Lunes' if date.weekday() == 0 else week
        week = 'Martes' if date.weekday() == 1 else week
        week = 'Miercoles' if date.weekday() == 2 else week
        week = 'Jueves' if date.weekday() == 3 else week
        week = 'Viernes' if date.weekday() == 4 else week
        week = 'Sábado' if date.weekday() == 5 else week
        week = 'Domingo' if date.weekday() == 6 else week
        
        if calculated_week == 0:
            date_text = date.strftime('%d de '+month+' del %Y')
        else:
            date_text = date.strftime(week+', %d de '+month+' del %Y')

        return date_text

    def get_amount_text(self, valor):
        letter_amount = self.numero_to_letras(float(valor))         
        return letter_amount.upper()

    def get_average_concept_heyrec(self): #Promedio horas extra
        promedio = False
        model_payslip = self.env['hr.payslip']
        model_payslip_line = self.env['hr.payslip.line']
        today = datetime.today()
        date_start =  today + relativedelta(months=-3)
        today_str = today.strftime("%Y-%m-01")
        date_start_str = date_start.strftime("%Y-%m-01")
        slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str),('contract_id','=',self.id),('state','=','done')])
        lines_ids = model_payslip_line.search([('slip_id','in',slips_ids.ids),('category_id.code','=','HEYREC')])
        if lines_ids:
            total = sum([i.total for i in model_payslip_line.browse(lines_ids.ids)])
            if len(slips_ids)/2 > 0:
                promedio = total/(len(slips_ids)/2)                            
        return promedio

    def get_average_concept_certificate(self,salary_rule_id,last,average,value_contract,payment_frequency): #Promedio horas extra
        model_payslip = self.env['hr.payslip']
        model_payslip_line = self.env['hr.payslip.line']
        today = datetime.today()
        if last == True:
            total = False
            date_start = today + relativedelta(months=-1)
            today_str = today.strftime("%Y-%m-01")
            date_start_str = date_start.strftime("%Y-%m-01")
            slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str), ('contract_id', '=', self.id),('state', '=', 'done')])
            lines_ids = model_payslip_line.search([('slip_id', 'in', slips_ids.ids), ('salary_rule_id', '=', salary_rule_id.id)])
            if lines_ids:
                total = sum([i.total for i in model_payslip_line.browse(lines_ids.ids)])
            return total
        if average == True:
            promedio = False
            date_start =  today + relativedelta(months=-3)
            today_str = today.strftime("%Y-%m-01")
            date_start_str = date_start.strftime("%Y-%m-01")
            slips_ids = model_payslip.search([('date_from','>=',date_start_str),('date_to','<=',today_str),('contract_id','=',self.id),('state','in',['done','paid'])])
            lines_ids = model_payslip_line.search([('slip_id','in',slips_ids.ids),('salary_rule_id','=',salary_rule_id.id)])
            if lines_ids:
                total = sum([i.total for i in model_payslip_line.browse(lines_ids.ids)])
                if payment_frequency == 'biweekly':
                    if len(slips_ids)/2 > 0:
                        promedio = total/(len(slips_ids)/2)
                else:
                    if len(slips_ids) > 0:
                        promedio = total/(len(slips_ids))
            return promedio
        if value_contract == True:
            obj_concept = self.concepts_ids.filtered(lambda x: x.input_id.id == salary_rule_id.id)
            if len(obj_concept) == 1:
                rule_value = sum([i.amount for i in obj_concept])
                if obj_concept.aplicar == '0':
                    rule_value = rule_value * 2
                if obj_concept.input_id.modality_value == 'diario':
                    rule_value = rule_value * 30
                return rule_value
            else:
                return 0
        return 0

    def get_signature_certification(self):
        res = {'nombre':'NO AUTORIZADO', 'cargo':'NO AUTORIZADO','firma':''}
        obj_user = self.env['res.users'].search([('signature_certification_laboral','=',True)])
        for user in obj_user:
            res['nombre'] = user.name
            res['cargo'] = 'Dirección Nacional de Talento Humano'
            res['firma'] = user.signature_documents

        return res
    def generate_report_severance(self):
        ctx = self.env.context.copy()
        ctx.update({'default_contract_id': self.id})

        return {
            'type': 'ir.actions.act_window',
            'name': 'Carta para retiro de cesantías',
            'res_model': 'lavish.retirement.severance.pay',
            'domain': [],
            'view_mode': 'form',
            'target':'new',
            'context': ctx
        }
    
    def has_change_salary(self, date_from, date_to):
        wages_in_period = filter(
            lambda x: date_from <= x.date_start <= date_to, self.change_wage_ids)
        return len(list(wages_in_period)) >= 1 

    def get_pend_vac(self, date_calc=None, sus=0):
        """
        Calcula días pendientes de vacaciones.
        Considera días disfrutados, compensados en dinero, interrupciones e incapacidades.
        """
        if date_calc:
            date_calc = date_calc
        else:
            date_calc = datetime.now()

        # Consulta corregida SIN GROUP BY para evitar duplicados
        vac_book_q = """
            SELECT
                COALESCE(SUM(vb.business_units), 0) as total_business,
                COALESCE(SUM(vb.holiday_value), 0) as total_holiday,
                COALESCE(SUM(vb.units_of_money), 0) as total_money,
                COALESCE(SUM(vb.days_returned), 0) as total_returned,
                COALESCE(SUM(vb.disability_days), 0) as total_disability
            FROM hr_vacation vb
            INNER JOIN hr_contract hc ON hc.id = vb.contract_id
            LEFT JOIN hr_payslip hp ON hp.id = vb.payslip
            WHERE hc.id = %s
            AND (hp.date_liquidacion <= %s OR vb.payslip IS NULL)
        """

        self._cr.execute(vac_book_q, (self.id, date_calc))
        result = self._cr.fetchone()

        # Procesar resultados
        lic = sus  # Licencias no remuneradas
        if result:
            total_business = result[0] or 0
            total_holiday = result[1] or 0
            total_money = result[2] or 0
            total_returned = result[3] or 0
            total_disability = result[4] or 0

            # Sumar festivos a licencias
            lic += total_holiday

            # Días tomados = días hábiles + días en dinero - días devueltos - días de incapacidad
            taken = total_business + total_money - total_returned - total_disability
        else:
            taken = 0

        # Calcular días trabajados
        k_dt_start = self.date_start
        init_date = self.env.company.init_vac_date
        if init_date and k_dt_start < init_date:
            k_dt_start = self.env.company.init_vac_date
        dt_end = date_calc
        days = days360(k_dt_start, dt_end)
        days_wo_lic = days - lic

        # Calcular días causados según tipo de empleado
        if not self.employee_id.indicador_especial_id.code == '1':
            dv_total = float(days_wo_lic) * 15 / 360
        else:
            dv_total = float(days_wo_lic) * 30 / 360

        # Días pendientes
        dv_pend = dv_total - taken
        return dv_pend

#Historico generación de certificados laborales
class hr_labor_certificate_history(models.Model):
    _name = 'hr.labor.certificate.history'
    _description = 'Historico de certificados laborales generados'
    _order = 'contract_id,date_generation'

    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    sequence = fields.Char(string="Secuencia", default="/", readonly=True)
    date_generation = fields.Date('Fecha generación', required=True)
    info_to = fields.Char(string='Dirigido a', required=True)
    pdf = fields.Binary(string='Certificado')
    pdf_name = fields.Char(string='Filename Certificado')

    _labor_certificate_history_uniq = models.Constraint('unique(contract_id, sequence)', 'Ya existe un certificado con esta secuencia, por favor verificar.')

    def _compute_display_name(self):
        for record in self:
            record.display_name = "Certificado {} de {}".format(record.sequence,record.contract_id.name)

    def get_hr_labor_certificate_template(self):
        obj = self.env['hr.labor.certificate.template'].search([('company_id','=',self.contract_id.employee_id.company_id.id)])
        if len(obj) == 0:
            raise ValidationError(_('No tiene configurada plantilla de certificado laboral. Por favor verifique!'))
        return obj

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['sequence'] = self.env['ir.sequence'].next_by_code('hr.labor.certificate.history.seq') or ' '
        obj_contract = super().create(vals_list)
        return obj_contract

    def generate_report(self):
        datas = {
            'ids': self.contract_id.ids,
            'model': 'hr.labor.certificate.history'
        }

        report_name = 'lavish_hr_employee.report_certificacion_laboral'
        pdf = self.env['ir.actions.report']._render_qweb_pdf("lavish_hr_employee.report_certificacion_laboral_action", self.id)[0] #self.env.ref('lavish_hr_employee.report_certificacion_laboral_action',False)._render_qweb_pdf(self.id)[0]
        pdf = base64.b64encode(pdf)
        self.pdf = pdf#base64.encodebytes(pdf)
        self.pdf_name = f'Certificado - {self.contract_id.name} - {self.sequence}.pdf'

        #Guardar en documentos
        # Crear adjunto
        name = f'Certificado - {self.contract_id.name} - {self.sequence}.pdf'


        return {
            'type': 'ir.actions.report',
            'report_name': report_name,
            'report_type': 'qweb-pdf',
            'datas': datas,
            # 'context': self._context
        }


class lavish_retirement_severance_pay(models.Model):
    _name = 'lavish.retirement.severance.pay'
    _description = 'Carta para retiro de cesantías'

    def get_contrib_id(self):
        return self.env['hr.contribution.register'].search([('type_entities', '=', 'cesantias')], limit=1).id

    contract_id = fields.Many2one('hr.contract',string='Contrato')
    contrib_id = fields.Many2one('hr.contribution.register', 'Tipo Entidad', help='Concepto de aporte', required=True, default=get_contrib_id)
    directed_to = fields.Many2one('hr.employee.entities',string='Dirigido a', domain="[('types_entities','in',[contrib_id])]", required=True)
    withdrawal_value = fields.Float(string='Valor del retiro')
    withdrawal_concept_partial = fields.Selection([
        ('1', 'Educación Superior'),
        ('2', 'Educación para el Trabajo y el Desarrollo Humano'),
        ('3', 'Créditos del ICETEX'),
        ('4', 'Compra de lote o vivienda'),
        ('5', 'Reparaciones locativas'),
        ('6', 'Pago de créditos hipotecarios'),
        ('7', 'Pago de impuesto predial o de valorización')
    ], string="Concepto de retiro parcial")
    withdrawal_concept_total = fields.Selection([
        ('1', 'Terminación del contrato'),
        ('2', 'Llamamiento al servicio militar'),
        ('3', 'Adopción del sistema de salario integral'),
        ('4', 'Sustitución patronal'),
        ('5', 'Fallecimiento del afiliado')
    ],string="Concepto de retiro total")
    withdrawal_type = fields.Selection([
        ('termination', 'Retiro por terminación'),
        ('partial', 'Retiro parcial')
    ], string='Tipo de retiro')
    pdf = fields.Binary(string='Carta para retiro de cesantías')
    pdf_name = fields.Char(string='Filename Carta para retiro de cesantías')

    def generate_report_severance_pay(self):
        datas = {
            'id': self.id,
            'model': 'lavish.retirement.severance.pay'
        }

        report_name = 'lavish_hr_employee.report_retirement_severance_pay'
        pdf = self.env['ir.actions.report']._render_qweb_pdf("lavish_hr_employee.report_retirement_severance_pay_action", self.id)[0] #self.env.ref('lavish_hr_employee.report_retirement_severance_pay_action', False)._render_qweb_pdf(self.id)[0]
        pdf = base64.b64encode(pdf)
        self.pdf = pdf  # base64.encodebytes(pdf)
        self.pdf_name = f'Carta para retiro de cesantías - {self.contract_id.name}.pdf'

        # Guardar en documentos
        # Crear adjunto
        name = f'Carta para retiro de cesantías - {self.contract_id.name}.pdf'
        obj_attachment = self.env['ir.attachment'].create({
            'name': name,
            'store_fname': name,
            'res_name': name,
            'type': 'binary',
            'res_model': 'res.partner',
            'res_id': self.contract_id.employee_id.work_contact_id.id,
            'datas': pdf,
        })
        # Asociar adjunto a documento de Odoo
        doc_vals = {
            'name': name,
            'owner_id': self.contract_id.employee_id.user_id.id if self.contract_id.employee_id.user_id else self.env.user.id,
            'partner_id': self.contract_id.employee_id.work_contact_id.id,
            'folder_id': self.env.user.company_id.documents_hr_folder.id,
            'tag_ids': self.env.user.company_id.validated_certificate.ids,
            'type': 'binary',
            'attachment_id': obj_attachment.id
        }
        self.env['documents.document'].sudo().create(doc_vals)

        return {
            'type': 'ir.actions.report',
            'report_name': 'lavish_hr_employee.report_retirement_severance_pay',
            'report_type': 'qweb-pdf',
            'datas': datas
        }

class resource_calendar(models.Model):
    _inherit = 'resource.calendar'

    type_working_schedule = fields.Selection([
        ('employees', 'Empleados'),
        ('tasks', 'Tareas Proyectos'),
        ('other', 'Otro')
    ], string='Tipo Horario')
    consider_holidays = fields.Boolean(string='Tener en Cuenta Festivos')

    @api.model
    def get_working_hours_payroll(self, schedule, date_from, date_to):
        DSDF = '%Y-%m-%d'
        res = []
        date_from = date_from -timedelta(hours=5)
        nb_of_days = (date_to - date_from).days + 1
        
        for day in range(nb_of_days):
            dateinit = date_from + timedelta(days=day)
            hour_from = 0.0 if day > 0 else float(dateinit.hour) + float(dateinit.minute) / 60.0
            hour_to = 24 if day + 1 != nb_of_days else float(date_to.hour) + float(date_to.minute) / 60.0

            day_of_week = dateinit.weekday()
            working_hours = 0
            
            for reg in schedule.attendance_ids:
                if int(reg.dayofweek) == day_of_week:
                    from_hour = max(hour_from, reg.hour_from)
                    to_hour = min(hour_to, reg.hour_to)
                    working_hours += max(0, to_hour - from_hour)

            working_days = working_hours / schedule.hours_per_day if schedule.hours_per_day else 0
            date = dateinit.strftime(DSDF)
            res.append({
                'date': date, 
                'hours': working_hours,
                'days': working_days, 
                'week_day': str(day_of_week)
            })

        return res


class resource_calendar_attendance(models.Model):
    _inherit = 'resource.calendar.attendance'

    daytime_hours = fields.Float(string='Horas Diurnas',compute='_get_jornada_hours',store=True)
    night_hours = fields.Float(string='Horas Nocturnas',compute='_get_jornada_hours',store=True)

    @api.depends('hour_from','hour_to')
    def _get_jornada_hours(self):
        for record in self:
            hour_from = record.hour_from if record.hour_from else 0
            hour_to = record.hour_to if record.hour_to else 0
            #Calcular horas diurnas y nocturnas
            daytime_hours_initial = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.daytime_hours_initial')) or False
            daytime_hours_finally = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.daytime_hours_finally')) or False
            night_hours_initial = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.night_hours_initial')) or False
            night_hours_finally = float(self.env['ir.config_parameter'].sudo().get_param('lavish_planning.night_hours_finally')) or False
            if daytime_hours_initial and daytime_hours_finally and night_hours_initial and night_hours_finally:
                if hour_from >= daytime_hours_initial and hour_to <= daytime_hours_finally:
                    record.night_hours = 0
                    record.daytime_hours = hour_to - hour_from + 24 if hour_to < hour_from else hour_to - hour_from
                elif (hour_from >= night_hours_initial and hour_to <= 24) or (hour_from >= 0 and hour_to <= night_hours_finally):
                    record.night_hours = hour_to - hour_from + 24 if hour_to < hour_from else hour_to - hour_from
                    record.daytime_hours = 0
                elif hour_from >= daytime_hours_initial and hour_from <= daytime_hours_finally and hour_to >= daytime_hours_finally:
                    record.night_hours = hour_to - daytime_hours_finally + 24 if hour_to < daytime_hours_finally else hour_to - daytime_hours_finally
                    record.daytime_hours = daytime_hours_finally - hour_from + 24 if daytime_hours_finally < hour_from else daytime_hours_finally - hour_from
                elif (hour_from <= daytime_hours_initial and hour_to >= daytime_hours_finally and hour_to <= daytime_hours_finally)\
                        or (hour_from <= daytime_hours_initial and hour_to >= daytime_hours_initial and hour_to <= daytime_hours_finally):
                    record.night_hours = daytime_hours_initial - hour_from + 24 if daytime_hours_initial < hour_from else daytime_hours_initial - hour_from
                    record.daytime_hours = hour_to - daytime_hours_initial + 24 if hour_to < daytime_hours_initial else hour_to - daytime_hours_initial
                elif hour_from <= daytime_hours_initial and hour_to >= daytime_hours_finally:
                    record.night_hours = daytime_hours_initial - hour_from + 24 if daytime_hours_initial < hour_from else daytime_hours_initial - hour_from
                    record.daytime_hours = daytime_hours_finally - daytime_hours_initial + 24 if daytime_hours_finally < daytime_hours_initial else daytime_hours_finally - daytime_hours_initial
                    record.night_hours += hour_to - daytime_hours_finally + 24 if hour_to < daytime_hours_finally else hour_to - daytime_hours_finally
                else:
                    record.night_hours = 0
                    record.daytime_hours = 0
            else:
                record.night_hours = 0
                record.daytime_hours = 0

class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'
    
    concept_id = fields.Many2one('hr.contract.concepts', string='Concepto Relacionado', 
                                ondelete='set null', index=True)
    fortnight_indicator = fields.Char(string='Quincena', help='Indicador de quincena (1Q/2Q)')
    period = fields.Char(string='Periodo', help='Período en formato MES/AÑO')
    is_deduction = fields.Boolean(string='Es Deducción')
    pending_review = fields.Boolean(string='Pendiente de Revisión', 
                                  help='Indica si esta línea necesita revisión después del cálculo')
    reviewed = fields.Boolean(string='Revisado', 
                            help='Indica si la línea ya fue revisada')
    days_count = fields.Float(string='Días Contados', 
                            help='Número de días considerados para este concepto')
    formula_used = fields.Text(string='Fórmula Utilizada', 
                             help='Fórmula utilizada para calcular el valor')
    skip_id = fields.Many2one('hr.contract.concept.skip', string='Salto Aplicado', 
                            help='Salto aplicado en esta línea, si corresponde')
    double_payment = fields.Boolean(string='Pago Doble', 
                                  help='Indica si esta línea representa un pago doble')
    manual_adjustment = fields.Boolean(string='Ajuste Manual', 
                                     help='Indica si el valor fue ajustado manualmente')
    original_amount = fields.Float(string='Monto Original', 
                                 help='Monto antes del ajuste manual')
    adjustment_reason = fields.Text(string='Razón del Ajuste', 
                                  help='Motivo del ajuste manual')
    adjusted_by = fields.Many2one('res.users', string='Ajustado por', 
                                help='Usuario que realizó el ajuste manual')
    adjustment_date = fields.Datetime(string='Fecha de Ajuste', 
                                    help='Fecha y hora del ajuste manual')
    
    # Métodos adicionales
    def mark_as_reviewed(self) -> None:
        """Marca la línea como revisada"""
        self.ensure_one()
        self.write({
            'reviewed': True,
            'adjusted_by': self.env.user.id,
            'adjustment_date': fields.Datetime.now()
        })
        
    def reset_review_status(self) -> None:
        """Reinicia el estado de revisión"""
        self.ensure_one()
        self.write({
            'reviewed': False,
            'adjustment_reason': False
        })
    
    def apply_manual_adjustment(self, new_amount: float, reason: str) -> None:
        """
        Aplica un ajuste manual al monto de la línea
        
        Args:
            new_amount: Nuevo monto a aplicar
            reason: Razón del ajuste
        """
        self.ensure_one()
        if not self.manual_adjustment:
            original = self.amount
        else:
            original = self.original_amount
        self.write({
            'manual_adjustment': True,
            'original_amount': original,
            'amount': new_amount,
            'adjustment_reason': reason,
            'adjusted_by': self.env.user.id,
            'adjustment_date': fields.Datetime.now(),
            'reviewed': True
        })
        if self.slip_id:
            msg = _("""
                <div class="o_mail_notification">
                    <div><strong>Ajuste Manual en Línea de Nómina</strong></div>
                    <div>Concepto: %s</div>
                    <div>Valor Original: %s</div>
                    <div>Nuevo Valor: %s</div>
                    <div>Motivo: %s</div>
                </div>
            """) % (
                self.name or '',
                self.company_id.currency_id.symbol + ' ' + str(original),
                self.company_id.currency_id.symbol + ' ' + str(new_amount),
                reason or ''
            )
            self.slip_id.message_post(body=msg, subtype_xmlid="mail.mt_note")
            
    def revert_manual_adjustment(self) -> None:
        """Revierte el ajuste manual a los valores originales"""
        self.ensure_one()
        if not self.manual_adjustment:
            return
        self.write({
            'amount': self.original_amount,
            'manual_adjustment': False,
            'adjustment_reason': False,
            'reviewed': True
        })
        if self.slip_id:
            msg = _("""
                <div class="o_mail_notification">
                    <div><strong>Ajuste Manual Revertido</strong></div>
                    <div>Concepto: %s</div>
                    <div>Valor Restaurado: %s</div>
                </div>
            """) % (
                self.name or '',
                self.company_id.currency_id.symbol + ' ' + str(self.amount)
            )
            self.slip_id.message_post(body=msg, subtype_xmlid="mail.mt_note")
