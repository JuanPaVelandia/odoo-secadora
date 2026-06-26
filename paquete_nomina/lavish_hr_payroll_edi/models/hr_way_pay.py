# -*- coding: utf-8 -*-
"""
Formas de pago según clasificación DIAN.
"""
from odoo import fields, models


class HrWayPay(models.Model):
    _name = 'hr.way.pay'
    _description = 'Forma de Pago DIAN'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    active = fields.Boolean(string='Activo', default=True)
