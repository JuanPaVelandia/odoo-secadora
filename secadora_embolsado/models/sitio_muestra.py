# -*- coding: utf-8 -*-

from odoo import models, fields


class SitioMuestra(models.Model):
    _inherit = 'secadora.sitio.muestra'

    mostrar_estimacion_seco = fields.Boolean(
        string='Contenedor de Arroz Seco (Estimación)',
        default=False,
        help='El contenedor almacena arroz ya seco: las tarjetas muestran la '
             'estimación de peso seco (doble descuento por humedad e impureza) en '
             'lugar del verde de báscula, y los viajes de embolsado descuentan '
             'sobre esa base seca (convertida al equivalente verde de cada tarjeta).',
    )
