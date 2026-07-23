# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    excluir_analisis = fields.Boolean(
        string='No requiere Análisis de Laboratorio',
        default=False,
        help='Si está marcado, los pesajes con este producto NO generan un '
             'análisis de laboratorio automático. Útil para productos sin '
             'control de calidad de arroz (ej: cascarilla, maíz, subproductos).',
    )
