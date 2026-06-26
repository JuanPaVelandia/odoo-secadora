# -*- coding: utf-8 -*-
"""
Reglas de deducciones para nómina electrónica DIAN.
"""
from odoo import fields, models


class HrDeductRule(models.Model):
    _name = 'hr.deduct.rule'
    _description = 'Regla de Deducción DIAN'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
    salary_rule_ids = fields.One2many(
        'hr.salary.rule', 'deduccion_rule_id',
        string='Reglas Salariales',
        help='Reglas salariales asociadas a esta deducción DIAN'
    )


class HrSalaryRuleDeduct(models.Model):
    _inherit = 'hr.salary.rule'

    deduccion_rule_id = fields.Many2one(
        'hr.deduct.rule',
        string='Regla Deducción DIAN',
        help='Regla de deducción para generación de XML DIAN'
    )
