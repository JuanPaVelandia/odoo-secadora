# -*- coding: utf-8 -*-

from odoo import models, fields


class AnalisisLab(models.Model):
    _inherit = 'secadora.analisis.lab'

    silobolsa_id = fields.Many2one(
        'secadora.silobolsa',
        string='Silobolsa',
        ondelete='restrict',
        index=True,
    )
    seccion_silobolsa = fields.Char(
        string='Sección de Silobolsa',
        help='Sección muestreada de la silobolsa (ej: "Sección 1", "0–20 m").',
    )
