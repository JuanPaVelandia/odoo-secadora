# -*- coding: utf-8 -*-
"""Semilla entregada a terceros a cambio de arroz.

Parte de la semilla se le manda a otros agricultores sin factura: después
pagan devolviendo arroz. Solo se quiere saber cuánta se le ha mandado a cada
uno. La semilla sale por dos caminos —el pesaje de salida de la secadora y la
remisión de una bodega—, pero los dos terminan en `secadora.despacho.bultos`;
la marca va ahí y el informe sale de un solo lugar.
"""

from odoo import api, fields, models


class DespachoBultosTercero(models.Model):
    _inherit = 'secadora.despacho.bultos'

    tercero_semilla_id = fields.Many2one(
        'res.partner',
        string='A cambio de arroz para',
        index=True,
        help='Si estos bultos se le entregan a un tercero que los paga '
             'devolviendo arroz, el tercero. Vacío = no es una entrega a '
             'cambio de arroz.',
    )
    remision_id = fields.Many2one(
        'secadora.remision.bodega',
        string='Remisión',
        ondelete='set null',
        index=True,
    )
    fecha_entrega = fields.Date(
        string='Fecha',
        compute='_compute_fecha_entrega',
        store=True,
    )
    variedad_id = fields.Many2one(
        related='registro_bultos_id.variedad_id',
        string='Variedad',
        store=True,
    )
    bodega_id = fields.Many2one(
        related='registro_bultos_id.bodega_id',
        string='Sale de',
        store=True,
    )
    es_semilla = fields.Boolean(
        related='registro_bultos_id.es_semilla',
        string='Semilla',
        store=True,
    )

    @api.depends('remision_id.fecha', 'pesaje_id.fecha')
    def _compute_fecha_entrega(self):
        for rec in self:
            rec.fecha_entrega = rec.remision_id.fecha or rec.pesaje_id.fecha
