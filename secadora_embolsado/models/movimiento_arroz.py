# -*- coding: utf-8 -*-

from odoo import models, fields


class MovimientoArroz(models.Model):
    _inherit = 'secadora.movimiento.arroz'

    tipo = fields.Selection(
        selection_add=[('embolsado', 'Embolsado')],
        ondelete={'embolsado': 'cascade'},
    )
    embolsado_viaje_id = fields.Many2one(
        'secadora.embolsado.viaje',
        string='Viaje de Embolsado',
        ondelete='set null',
        index=True,
    )
