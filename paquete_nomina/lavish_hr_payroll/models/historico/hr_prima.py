# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import math

class HrHistoryPrima(models.Model):
    _name = 'hr.history.prima'
    _description = 'Historico de prima'
    
    employee_id = fields.Many2one('hr.employee', 'Empleado')
    employee_identification = fields.Char('Identificación empleado')
    initial_accrual_date = fields.Date('Fecha inicial de causación')
    final_accrual_date = fields.Date('Fecha final de causación')
    settlement_date = fields.Date('Fecha de liquidación')
    time = fields.Float('Tiempo')
    base_value = fields.Float('Valor base')
    bonus_value = fields.Float('Valor de prima')
    payslip = fields.Many2one('hr.payslip', 'Liquidación')
    contract_id = fields.Many2one('hr.contract', 'Contrato')
    type = fields.Selection([
        ('normal', 'Normal'),
        ('adjustment', 'Ajuste'),
        ('settlement', 'Liquidación')
    ], string='Tipo', default='normal', help='Normal: Primera vez, Ajuste: Recálculo, Liquidación: Terminación contrato')
    note = fields.Text('Nota')
    
    @api.depends('employee_id', 'employee_id.name', 'initial_accrual_date', 'final_accrual_date')
    def _compute_display_name(self):
        for record in self:
            employee_name = record.employee_id.name if record.employee_id else ''
            record.display_name = "Prima {} del {} al {}".format(
                employee_name,
                str(record.initial_accrual_date),
                str(record.final_accrual_date)
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
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
