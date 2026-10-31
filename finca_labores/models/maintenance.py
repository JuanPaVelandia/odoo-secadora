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


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    finca_dueno_id = fields.Many2one(
        'res.partner',
        string='Dueño en labores',
        domain=[('es_dueno_finca', '=', True)],
        help='A nombre de quién quedan los trabajos de este equipo, si no es '
             'su compañía. Un equipo de una sociedad está en la compañía de '
             'uno de los socios, pero sus pagos van a la cuenta de la sociedad.',
    )
