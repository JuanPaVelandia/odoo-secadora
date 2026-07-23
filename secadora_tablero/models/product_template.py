# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    excluir_tablero = fields.Boolean(
        string='No llevar al Tablero de Arroz',
        default=False,
        help='Si está marcado, los pesajes de entrada con este producto NO '
             'crean una posición en el Tablero de Arroz. Útil para subproductos '
             'o desechos que no se almacenan en las torres/silos (ej: cascarilla).',
    )
