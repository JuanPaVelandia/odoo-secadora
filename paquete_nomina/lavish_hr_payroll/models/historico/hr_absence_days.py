# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAbsenceDays(models.Model):
    _name = 'hr.absence.days'
    _description = 'Ausencias'

    sequence = fields.Integer(
        string='Secuencia',
        required=True,
        index=True,
        default=5,
        help='Use to arrange calculation sequence'
    )
    payroll_id = fields.Many2one('hr.payslip', string='Payroll')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    leave_type = fields.Char(string='Leave Type')
    total_days = fields.Float(string='Dias Totales')
    days_used = fields.Float(string='Dias a usar')
    days = fields.Float(string='Dias Usado')
    total = fields.Float(string='pendiente')
    leave_id = fields.Many2one('hr.leave', string='Novedad')
    work_entry_type_id = fields.Many2one(
        'hr.work.entry.type',
        related="leave_id.holiday_status_id.work_entry_type_id",
        string='Type',
        required=True,
        help="The code that can be used in the salary rules"
    )
    days_unused = fields.Float('Dias no utilizados')
    is_interrupted = fields.Boolean('Interrupcion', default=False)
    interruption_reason_id = fields.Many2one('hr.vacation.interruption.reason', 'Motivo interrupcion')
    interruption_date = fields.Date('Fecha interrupcion')
    return_later = fields.Boolean('Retornara despues', default=False)
    return_date = fields.Date('Fecha de retorno')
    start_date = fields.Date('Fecha Inicio')
    end_date = fields.Date('Fecha Fin')
    is_hour_leave = fields.Boolean('Aus por horas', default=False)
    hours_per_day = fields.Float('Horas por dias')
