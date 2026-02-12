# -*- coding: utf-8 -*-

from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    x_numero_tiquete = fields.Char(string='Numero de Tiquete')

    x_pesaje_id = fields.Many2one(
        'secadora.pesaje',
        string='Pesaje',
        index=True,
        help='Pesaje de bascula que origino este picking'
    )

    x_orden_servicio_id = fields.Many2one(
        'secadora.orden.servicio',
        string='Orden de Servicio',
        index=True,
        help='Orden de servicio asociada a este picking'
    )
