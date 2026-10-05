# -*- coding: utf-8 -*-

from odoo import models, fields


class MaintenanceEquipmentCategory(models.Model):
    _inherit = 'maintenance.equipment.category'

    finca_valor_max_contrato = fields.Float(
        string='Valor máximo por contrato',
        digits=(12, 2),
        help='Tope que se paga a un operador por el mantenimiento de un equipo '
             'de esta categoría en la campaña (ej. Rastra 250.000, Sembradora '
             '1.250.000). Los trabajos que lo superan quedan marcados.',
    )
