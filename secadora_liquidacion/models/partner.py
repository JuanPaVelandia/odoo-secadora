# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    tipo_deduccion_ids = fields.Many2many(
        'secadora.tipo.deduccion',
        'res_partner_tipo_deduccion_rel',
        'partner_id',
        'tipo_deduccion_id',
        string='Deducciones Automáticas',
        help='Deducciones que se aplican automáticamente al liquidar compras de este agricultor',
    )
    precio_compra_kg = fields.Float(
        string='Precio Compra ($/kg)',
        digits=(12, 2),
        help='Precio por defecto de compra de arroz para este agricultor. Si es mayor a 0, tiene prioridad sobre el catálogo de precios.',
    )
