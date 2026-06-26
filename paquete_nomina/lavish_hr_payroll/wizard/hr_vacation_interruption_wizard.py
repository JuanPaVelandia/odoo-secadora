# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class HrVacationInterruptionWizard(models.TransientModel):
    _name = 'hr.vacation.interruption.wizard'
    _description = 'Wizard para Interrupcion de Vacaciones'

    leave_id = fields.Many2one('hr.leave', string='Vacaciones', required=True, readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', related='leave_id.employee_id', readonly=True)
    date_from = fields.Date(string='Fecha Inicio Vacaciones', related='leave_id.request_date_from', readonly=True)
    date_to = fields.Date(string='Fecha Fin Vacaciones', related='leave_id.request_date_to', readonly=True)
    total_days = fields.Float(string='Dias Totales', related='leave_id.number_of_days', readonly=True)

    interruption_date = fields.Date(
        string='Fecha de Interrupcion',
        required=True,
        help='Fecha en que se interrumpen las vacaciones. El empleado regresa a trabajar el dia siguiente.'
    )
    reason_id = fields.Many2one(
        'hr.vacation.interruption.reason',
        string='Motivo de Interrupcion',
        required=True,
        help='Seleccione el motivo por el cual se interrumpen las vacaciones.'
    )
    detail = fields.Text(
        string='Detalle',
        help='Descripcion adicional sobre la interrupcion.'
    )
    days_enjoyed = fields.Float(
        string='Dias Disfrutados',
        compute='_compute_days',
        store=True,
        help='Dias de vacaciones efectivamente disfrutados hasta la fecha de interrupcion.'
    )
    days_returned = fields.Float(
        string='Dias a Devolver',
        compute='_compute_days',
        store=True,
        help='Dias de vacaciones que se devuelven al saldo del empleado.'
    )
    will_return = fields.Boolean(
        string='Retomara Vacaciones',
        default=False,
        help='Indica si el empleado retomara las vacaciones en una fecha posterior.'
    )
    return_date = fields.Date(
        string='Fecha para Retomar',
        help='Fecha en que el empleado retomara las vacaciones pendientes.'
    )

    @api.depends('interruption_date', 'leave_id.request_date_from', 'leave_id.number_of_days')
    def _compute_days(self):
        for wizard in self:
            if wizard.interruption_date and wizard.leave_id.request_date_from:
                # Dias disfrutados = desde inicio hasta fecha de interrupcion (inclusive)
                days_enjoyed = (wizard.interruption_date - wizard.leave_id.request_date_from).days + 1
                days_enjoyed = max(0, min(days_enjoyed, wizard.leave_id.number_of_days))
                wizard.days_enjoyed = days_enjoyed
                wizard.days_returned = wizard.leave_id.number_of_days - days_enjoyed
            else:
                wizard.days_enjoyed = 0
                wizard.days_returned = 0

    @api.constrains('interruption_date')
    def _check_interruption_date(self):
        for wizard in self:
            if wizard.interruption_date:
                if wizard.interruption_date < wizard.leave_id.request_date_from:
                    raise ValidationError(_('La fecha de interrupcion no puede ser anterior al inicio de las vacaciones.'))
                if wizard.interruption_date > wizard.leave_id.request_date_to:
                    raise ValidationError(_('La fecha de interrupcion no puede ser posterior al fin de las vacaciones.'))

    @api.constrains('return_date', 'will_return')
    def _check_return_date(self):
        for wizard in self:
            if wizard.will_return and wizard.return_date:
                if wizard.return_date <= wizard.interruption_date:
                    raise ValidationError(_('La fecha para retomar vacaciones debe ser posterior a la fecha de interrupcion.'))

    def action_confirm(self):
        """Confirmar la interrupcion de vacaciones"""
        self.ensure_one()

        if self.days_returned <= 0:
            raise UserError(_('No hay dias para devolver. La fecha de interrupcion debe ser anterior al fin de las vacaciones.'))

        return self.leave_id.interrupt_vacation(
            interruption_date=self.interruption_date,
            reason_id=self.reason_id.id,
            detail=self.detail or '',
            days_returned=self.days_returned,
            will_return=self.will_return,
            return_date=self.return_date
        )
