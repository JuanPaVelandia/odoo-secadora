from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import calendar
import logging
from typing import Dict, List, Union, Optional, Tuple, Any, TypeVar, cast
from odoo.tools.safe_eval import safe_eval
_logger = logging.getLogger(__name__)

PRECISION_TECHNICAL = 10
PRECISION_DISPLAY = 2

T = TypeVar('T')


class HrConceptSkipWizard(models.TransientModel):
    _name = 'hr.concept.skip.wizard'
    _description = 'Asistente para Crear Saltos de Conceptos'
    
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True)
    employee_id = fields.Many2one(related='concept_id.employee_id', readonly=True)
    
    period_skip = fields.Date('Fecha de Salto', required=True, default=fields.Date.today)
    fortnight = fields.Selection([
        ('15', 'Primera quincena'),
        ('30', 'Segunda quincena')
    ], string='Quincena', required=True, default='15')
    
    recovery_type = fields.Selection([
        ('none', 'Sin recuperación'),
        ('next', 'Siguiente cuota'),
        ('distributed', 'Distribuido en varias cuotas'),
        ('specific_date', 'Fecha específica')
    ], string='Tipo de Recuperación', required=True, default='next')
    
    recovery_date = fields.Date('Fecha de Recuperación')
    installments_number = fields.Integer('Número de Cuotas', default=1)
    
    reason = fields.Text('Motivo', required=True)
    notes = fields.Text('Notas Adicionales')
    
    notify_employee = fields.Boolean('Notificar Empleado', default=True)
    notify_supervisor = fields.Boolean('Notificar Supervisor', default=True)
    
    related_absence_id = fields.Many2one('hr.leave', 'Ausencia Relacionada')
    auto_approve = fields.Boolean('Aprobar automáticamente', default=True)
    
    @api.onchange('period_skip', 'fortnight')
    def _onchange_period(self) -> None:
        """Actualiza la fecha al cambiar el período o quincena"""
        if self.period_skip:
            day = 15 if self.fortnight == '15' else self._get_last_day_of_month(self.period_skip).day
            self.period_skip = date(self.period_skip.year, self.period_skip.month, day)
    
    @api.onchange('recovery_type')
    def _onchange_recovery_type(self) -> None:
        """Actualiza campos relacionados al cambiar el tipo de recuperación"""
        if self.recovery_type == 'none':
            self.recovery_date = False
            self.installments_number = 0
        elif self.recovery_type == 'next':
            self.installments_number = 1
            if self.period_skip:
                if self.fortnight == '15':
                    self.recovery_date = self._get_last_day_of_month(self.period_skip)
                else:
                    next_month = self.period_skip + relativedelta(months=1)
                    self.recovery_date = date(next_month.year, next_month.month, 15)
        elif self.recovery_type == 'distributed':
            self.installments_number = 2
            self.recovery_date = False
        elif self.recovery_type == 'specific_date':
            self.installments_number = 1
    
    def _get_last_day_of_month(self, reference_date: date) -> date:
        """
        Obtiene el último día del mes de una fecha dada
        
        Args:
            reference_date: Fecha de referencia
            
        Returns:
            Fecha del último día del mes
        """
        next_month = reference_date + relativedelta(months=1, day=1)
        return next_month - timedelta(days=1)
    
    def action_create_skip(self) -> Dict[str, Any]:
        """
        Crea un nuevo salto con los datos del asistente
        
        Returns:
            Diccionario con resultado de la acción
        """
        self.ensure_one()
        if self.recovery_type == 'specific_date' and not self.recovery_date:
            raise UserError(_("Debe especificar una fecha de recuperación."))
            
        if self.recovery_type == 'distributed' and self.installments_number < 1:
            raise UserError(_("El número de cuotas para distribución debe ser al menos 1."))
        values = {
            'concept_id': self.concept_id.id,
            'period_skip': self.period_skip,
            'fortnight': self.fortnight,
            'recovery_type': self.recovery_type,
            'recovery_date': self.recovery_date,
            'installments_number': self.installments_number,
            'reason': self.reason,
            'notes': self.notes,
            'notify_employee': self.notify_employee,
            'notify_supervisor': self.notify_supervisor,
            'related_absence_id': self.related_absence_id.id if self.related_absence_id else False,
            'state': 'approved' if self.auto_approve else 'draft',
        }
        
        skip = self.env['hr.contract.concept.skip'].create(values)
        if self.auto_approve:
            skip.write({
                'approval_date': fields.Date.today(),
                'approved_by': self.env.user.id
            })
            skip._send_notifications('approve')
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.contract.concept.skip',
            'view_mode': 'form',
            'res_id': skip.id,
            'target': 'current',
        }


class HrConceptDoublePaymentWizard(models.TransientModel):
    _name = 'hr.concept.double.payment.wizard'
    _description = 'Asistente para Configurar Pago Doble'
    
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True)
    employee_id = fields.Many2one(related='concept_id.employee_id', readonly=True)
    
    payment_date = fields.Date('Fecha de Pago Doble', required=True, default=fields.Date.today)
    reason = fields.Text('Motivo', required=True)
    
    def action_confirm(self) -> Dict[str, Any]:
        """
        Configura el pago doble en el concepto
        
        Returns:
            Diccionario con resultado de la acción
        """
        self.ensure_one()
        self.concept_id.write({
            'force_double_payment': True,
            'double_payment_date': self.payment_date
        })
        
        msg = _("""
            <div class="o_mail_notification">
                <div><strong>Pago Doble Configurado</strong></div>
                <div>Se ha configurado un pago doble para la fecha %s.</div>
                <div>Motivo: %s</div>
            </div>
        """) % (
            self.payment_date.strftime('%d/%m/%Y'), 
            self.reason or _("No especificado")
        )
        
        self.concept_id.message_post(body=msg, subtype_xmlid="mail.mt_comment")
        
        return {'type': 'ir.actions.act_window_close'}


class HrConceptSimulationWizard(models.TransientModel):
    _name = 'hr.concept.simulation.wizard'
    _description = 'Asistente para Simulación de Concepto'
    
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True)
    employee_id = fields.Many2one(related='concept_id.employee_id', readonly=True)
    contract_id = fields.Many2one(related='concept_id.contract_id', readonly=True)
    
    simulation_date = fields.Date('Fecha de Simulación', default=fields.Date.today)
    is_first_fortnight = fields.Boolean('Primera Quincena', compute='_compute_fortnight')
    
    # Resultado de la simulación
    simulation_result = fields.Html('Resultado de Simulación', readonly=True)
    estimated_amount = fields.Float('Monto Estimado', compute='_compute_estimation')
    days_count = fields.Integer('Días Estimados', compute='_compute_estimation')
    
    # Acciones adicionales
    create_skip = fields.Boolean('Crear Salto', default=False)
    skip_reason = fields.Text('Motivo del Salto')
    
    @api.depends('simulation_date')
    def _compute_fortnight(self) -> None:
        """Determina si es primera o segunda quincena"""
        for record in self:
            record.is_first_fortnight = record.simulation_date.day <= 15
    
    @api.depends('concept_id', 'simulation_date', 'is_first_fortnight')
    def _compute_estimation(self) -> None:
        """Calcula estimación de monto y días"""
        for record in self:
            if not record.concept_id or not record.simulation_date:
                record.estimated_amount = 0.0
                record.days_count = 0
                continue
            if record.is_first_fortnight:
                date_from = date(record.simulation_date.year, record.simulation_date.month, 1)
                date_to = date(record.simulation_date.year, record.simulation_date.month, 15)
            else:
                date_from = date(record.simulation_date.year, record.simulation_date.month, 16)
                date_to = self._get_last_day_of_month(record.simulation_date)
                
            base_amount = record.concept_id._calculate_base_amount()
            if record.concept_id.modality_value == 'fijo':
                if record.concept_id.aplicar == '0':  # Ambas quincenas
                    record.estimated_amount = record.concept_id.compute_precise(base_amount, 2, '/')
                else:
                    record.estimated_amount = base_amount
                record.days_count = 15  # Valor por defecto
            else:
                daily_amount = record.concept_id.compute_precise(base_amount, 30, '/')
                dias_periodo = (date_to - date_from).days + 1
                record.days_count = dias_periodo
                record.estimated_amount = record.concept_id.compute_precise(daily_amount, dias_periodo, '*')
    
    def _get_last_day_of_month(self, reference_date: date) -> date:
        """
        Obtiene el último día del mes de una fecha dada
        
        Args:
            reference_date: Fecha de referencia
            
        Returns:
            Fecha del último día del mes
        """
        next_month = reference_date + relativedelta(months=1, day=1)
        return next_month - timedelta(days=1)
    
    def action_create_skip(self) -> Dict[str, Any]:
        """
        Abre asistente para crear salto desde la simulación
        
        Returns:
            Diccionario con acción para abrir el asistente
        """
        self.ensure_one()
        
        if not self.skip_reason:
            raise UserError(_("Debe especificar un motivo para crear el salto."))
            
        wizard = self.env['hr.concept.skip.wizard'].create({
            'concept_id': self.concept_id.id,
            'period_skip': self.simulation_date,
            'fortnight': '15' if self.is_first_fortnight else '30',
            'reason': self.skip_reason,
        })
        
        return {
            'name': _('Crear Salto de Cuota'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.concept.skip.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }


class HrConceptCloseWizard(models.TransientModel):
    _name = 'hr.concept.close.wizard'
    _description = 'Asistente para Cierre de Concepto'
    
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True)
    employee_id = fields.Many2one(related='concept_id.employee_id', readonly=True)
    
    closed_reason = fields.Text('Motivo de Cierre', required=True)
    
    # Información del concepto para confirmación
    accumulated_amount = fields.Float(related='concept_id.accumulated_amount', readonly=True)
    balance = fields.Float(related='concept_id.balance', readonly=True)
    
    payslip_id = fields.Many2one('hr.payslip', 'Nómina de Cierre', 
                              domain="[('employee_id', '=', employee_id), ('state', 'in', ['done', 'paid'])]")
    
    def action_close_concept(self) -> Dict[str, Any]:
        """
        Cierra el concepto con los datos del asistente
        
        Returns:
            Diccionario con resultado de la acción
        """
        self.ensure_one()
        self.concept_id.write({
            'closed_reason': self.closed_reason
        })
        
        if self.payslip_id:
            ctx = {'payslip_id': self.payslip_id.id}
            self.concept_id.with_context(ctx).action_close()
        else:
            self.concept_id.action_close()
        
        return {'type': 'ir.actions.act_window_close'}    
class HrConceptCloseWizard(models.TransientModel):
    _name = 'hr.concept.close.wizard'
    _description = 'Asistente para Cierre de Concepto'
    
    concept_id = fields.Many2one('hr.contract.concepts', 'Concepto', required=True)
    employee_id = fields.Many2one(related='concept_id.employee_id', readonly=True)
    
    closed_reason = fields.Text('Motivo de Cierre', required=True)
    
    # Información del concepto para confirmación
    accumulated_amount = fields.Float(related='concept_id.accumulated_amount', readonly=True)
    balance = fields.Float(related='concept_id.balance', readonly=True)
    
    payslip_id = fields.Many2one('hr.payslip', 'Nómina de Cierre', 
                              domain="[('employee_id', '=', employee_id), ('state', 'in', ['done', 'paid'])]")
    
    def action_close_concept(self) -> Dict[str, Any]:
        """
        Cierra el concepto con los datos del asistente
        
        Returns:
            Diccionario con resultado de la acción
        """
        self.ensure_one()
        self.concept_id.write({
            'closed_reason': self.closed_reason
        })
        
        if self.payslip_id:
            ctx = {'payslip_id': self.payslip_id.id}
            self.concept_id.with_context(ctx).action_close()
        else:
            self.concept_id.action_close()
        
        return {'type': 'ir.actions.act_window_close'}             
