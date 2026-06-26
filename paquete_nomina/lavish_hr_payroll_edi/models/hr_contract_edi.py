# -*- coding: utf-8 -*-
"""
Extensión de hr.version para campos de nómina electrónica DIAN.
Agrega campos de forma de pago y método de pago requeridos para el XML.
En Odoo 19, hr.contract fue reemplazado por hr.version.
"""
from odoo import fields, models


class HrVersionEdi(models.Model):
    _inherit = 'hr.version'

    # Campos para forma y método de pago DIAN (nómina electrónica)
    way_pay_id = fields.Many2one(
        'hr.way.pay',
        string='Forma de Pago DIAN',
        help='Forma de pago según clasificación DIAN para nómina electrónica'
    )
    payment_method_dian_id = fields.Many2one(
        'hr.payment.method.dian',
        string='Método de Pago DIAN',
        help='Método de pago según clasificación DIAN para nómina electrónica'
    )
