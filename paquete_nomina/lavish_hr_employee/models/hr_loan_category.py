# -*- coding: utf-8 -*-
from odoo import fields, models


class HrLoanCategory(models.Model):
    _name = 'hr.loan.category'
    _description = 'Loan Category'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    description = fields.Text()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
