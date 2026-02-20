# -*- coding: utf-8 -*-

from odoo import models, fields


class SitioMuestra(models.Model):
    _inherit = 'secadora.sitio.muestra'

    es_contenedor = fields.Boolean(
        string='Es Contenedor',
        default=False,
        help='Marca si este sitio es una ubicación física de arroz (tolva, silo, bodega, etc.)'
    )
    sequence = fields.Integer(
        string='Orden',
        default=10,
        help='Orden de la columna en el tablero Kanban'
    )
    capacidad_kg = fields.Float(
        string='Capacidad (Kg)',
        digits=(12, 2),
        help='Capacidad máxima en kilogramos (informativo)'
    )
