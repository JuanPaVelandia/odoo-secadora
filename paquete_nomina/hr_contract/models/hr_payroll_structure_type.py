# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'

    name = fields.Char('Salary Structure Type')
    default_schedule_pay = fields.Selection(
        [
            ('bi-weekly', 'Quincenal'),
            ('monthly', 'Mensual'),
        ],
        string='Default Schedule Pay',
        default='monthly',
    )
    default_resource_calendar_id = fields.Many2one(
        'resource.calendar', 'Default Working Hours',
        default=lambda self: self.env.company.resource_calendar_id)
    country_id = fields.Many2one('res.country', string='Country', default=lambda self: self.env.company.country_id)
    country_code = fields.Char(related="country_id.code")

    def _get_default_struct_id(self):
        self.ensure_one()
        if 'default_struct_id' in self._fields and self.default_struct_id:
            return self.default_struct_id
        if 'hr.payroll.structure' not in self.env:
            return False
        return self.env['hr.payroll.structure'].search([('type_id', '=', self.id)], limit=1)
