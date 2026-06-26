# -*- coding: utf-8 -*-
"""
Reglas de devengados para nómina electrónica DIAN.
"""
from odoo import fields, models


class HrAccruedRule(models.Model):
    _name = 'hr.accrued.rule'
    _description = 'Regla de Devengado DIAN'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
    salary_rule_ids = fields.One2many(
        'hr.salary.rule', 'devengado_rule_id',
        string='Reglas Salariales',
        help='Reglas salariales asociadas a este devengado DIAN'
    )


class HrSalaryRuleAccrued(models.Model):
    _inherit = 'hr.salary.rule'

    devengado_rule_id = fields.Many2one(
        'hr.accrued.rule',
        string='Regla Devengado DIAN',
        help='Regla de devengado para generación de XML DIAN'
    )
    dev_or_ded = fields.Selection([
        ('devengo', 'Devengado'),
        ('deduccion', 'Deducción'),
    ], string='Tipo DIAN')
