# -*- coding: utf-8 -*-

from odoo import models, fields


class ServicioRegla(models.Model):
    _inherit = 'secadora.servicio.regla'

    es_cuadrilla = fields.Boolean(
        string='Servicio de Cuadrilla',
        default=False,
        help='Marcar si este servicio lo presta la cuadrilla y debe incluirse en las liquidaciones de cuadrilla',
    )
