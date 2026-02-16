# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettingsCalidad(models.TransientModel):
    _inherit = 'res.config.settings'

    calidad_humedad_base = fields.Float(
        string='Humedad Base (%)',
        config_parameter='calidad.humedad_base',
        default=13.0,
        help='Humedad estándar (He) para cálculo de peso comercial'
    )

    calidad_impurezas_base = fields.Float(
        string='Impurezas Base (%)',
        config_parameter='calidad.impurezas_base',
        default=3.0,
        help='Impurezas estándar (Ie) para cálculo de peso comercial'
    )

    calidad_activar_peso_comercial = fields.Boolean(
        string='Activar Peso Comercial',
        config_parameter='calidad.activar_peso_comercial',
        default=True,
        help='Calcular peso comercial: Pc = Pb × ((100-Hr)/(100-He)) × ((100-Ir)/(100-Ie))'
    )
