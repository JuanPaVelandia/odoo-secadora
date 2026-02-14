# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettingsCalidad(models.TransientModel):
    _inherit = 'res.config.settings'

    calidad_humedad_base = fields.Float(
        string='Humedad Base (%)',
        config_parameter='calidad.humedad_base',
        default=13.0,
        help='Humedad base para cálculo de peso comercial (normalmente 13%)'
    )

    calidad_activar_peso_comercial = fields.Boolean(
        string='Activar Peso Comercial',
        config_parameter='calidad.activar_peso_comercial',
        default=True,
        help='Calcular peso comercial ajustado por humedad en análisis de laboratorio'
    )

    calidad_activar_descuentos = fields.Boolean(
        string='Activar Descuentos por Calidad',
        config_parameter='calidad.activar_descuentos',
        default=False,
        help='Aplicar descuentos de peso según reglas de calidad'
    )
