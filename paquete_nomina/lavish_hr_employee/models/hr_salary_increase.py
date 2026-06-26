# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryIncrease(models.Model):
    _name = 'hr.salary.increase'
    _description = 'Salary Increase Process'

    name = fields.Char(required=True, default='Nuevo')
