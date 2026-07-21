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
    fila = fields.Integer(
        string='Fila',
        default=1,
        help='Fila en la grilla del tablero 2D'
    )
    columna = fields.Integer(
        string='Columna',
        default=1,
        help='Columna en la grilla del tablero 2D'
    )
    es_punto_salida = fields.Boolean(
        string='Es Punto de Salida',
        default=False,
        help='Habilita el botón de despacho en esta ubicación del tablero',
    )
    ocultar_calidad = fields.Boolean(
        string='Ocultar Calidad',
        default=False,
        help='Si está marcado, las tarjetas en esta ubicación no muestran humedad ni impurezas. '
             'Útil para sitios post-secamiento donde esos datos ya no aplican.',
    )
