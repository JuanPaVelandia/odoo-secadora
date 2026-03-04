# -*- coding: utf-8 -*-

from odoo import models, fields


class SecadoraPesaje(models.Model):
    _inherit = 'secadora.pesaje'

    liquidacion_id = fields.Many2one(
        'secadora.liquidacion',
        string='Liquidación',
        index=True,
        readonly=True,
        copy=False,
    )
