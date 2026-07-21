from odoo import fields, models


class MaintenanceCounterType(models.Model):
    _name = 'maintenance.counter.type'
    _description = 'Tipo de Contador'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    unit = fields.Char(
        string='Unidad de medida',
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
