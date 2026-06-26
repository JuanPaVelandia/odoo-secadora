# -*- coding: utf-8 -*-
"""
Extensión de hr.employee para agregar bodega asignada y distancia al trabajo
"""

from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Bodega asignada para EPP/Dotación
    default_location_id = fields.Many2one(
        'stock.location',
        string='Bodega Asignada',
        domain="[('usage', '=', 'internal')]",
        help='Bodega de inventario asignada a este empleado para EPP/Dotación'
    )

    # Distancia al trabajo para auxilio de transporte
    # NOTA: Odoo tiene campo nativo km_home_work. Este es alternativo.
    distance_to_work_km = fields.Float(
        string='Distancia al trabajo (km)',
        help='Distancia alternativa. Preferir usar km_home_work (campo nativo Odoo).'
    )

    # Campo de marcado manual para empleados que viven cerca
    lives_near_work = fields.Boolean(
        string='Vive cerca del trabajo',
        help='Marcar si el empleado vive a menos de 1km del lugar de trabajo. '
             'No recibira auxilio de transporte segun Decreto 1258/1959.'
    )
