# -*- coding: utf-8 -*-
"""
Métodos de pago según clasificación DIAN.
"""
from odoo import fields, models


class HrPaymentMethod(models.Model):
    _name = 'hr.payment.method.dian'
    _description = 'Método de Pago DIAN'

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', required=True)
    active = fields.Boolean(string='Activo', default=True)
