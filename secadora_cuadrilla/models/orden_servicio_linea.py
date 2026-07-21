# -*- coding: utf-8 -*-

from odoo import models, fields


class OrdenServicioLinea(models.Model):
    _inherit = 'secadora.orden.servicio.linea'

    es_cuadrilla = fields.Boolean(
        string='Servicio de Cuadrilla',
        default=False,
        help='Indica que este servicio lo presta la cuadrilla',
    )
    cuadrilla_liquidacion_linea_id = fields.Many2one(
        'secadora.cuadrilla.liquidacion.linea',
        string='Línea Liquidación Cuadrilla',
        ondelete='set null',
        copy=False,
    )
    cuadrilla_liquidacion_id = fields.Many2one(
        'secadora.cuadrilla.liquidacion',
        string='Liquidación Cuadrilla',
        related='cuadrilla_liquidacion_linea_id.liquidacion_id',
        store=True,
    )
