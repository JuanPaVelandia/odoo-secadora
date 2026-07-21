# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartnerTransporte(models.Model):
    _inherit = 'res.partner'

    generar_flete_automatico = fields.Boolean(
        string='Generar Flete Automático',
        default=False,
        help='Si está marcado, al completar un pesaje con este tercero se creará un flete automáticamente.',
    )

    flete_pago = fields.Selection([
        ('agricultor', 'Agricultor paga directo'),
        ('secadora', 'Secadora paga y descuenta'),
    ], string='Pago de Flete', default='agricultor',
       help='Define quién paga el flete. Si "Secadora paga y descuenta", el costo se descontará al agricultor en la liquidación.')
