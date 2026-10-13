# -*- coding: utf-8 -*-

from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    es_vehiculo = fields.Boolean(
        string='Vehículo (recibe ACPM de logística)',
        help='Aparece como destino del ACPM de logística en el módulo Combustible.',
    )
