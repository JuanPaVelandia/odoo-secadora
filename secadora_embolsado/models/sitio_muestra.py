# -*- coding: utf-8 -*-

from odoo import models, fields


class SitioMuestra(models.Model):
    _inherit = 'secadora.sitio.muestra'

    mostrar_estimacion_seco = fields.Boolean(
        string='Mostrar Estimación de Seco',
        default=False,
        help='Las tarjetas en este contenedor muestran la estimación de peso seco '
             '(doble descuento por humedad e impureza) en lugar del peso verde de báscula.',
    )
