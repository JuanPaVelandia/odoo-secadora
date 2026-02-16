# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettingsCalidad(models.TransientModel):
    _inherit = 'res.config.settings'

    calidad_activar_peso_comercial = fields.Boolean(
        string='Activar Peso Comercial',
        config_parameter='calidad.activar_peso_comercial',
        default=True,
        help='Calcular peso comercial usando las reglas de descuento por calidad'
    )
