from odoo import fields, models


class MaintenanceCounterType(models.Model):
    _name = 'maintenance.counter.type'
    _description = 'Counter Type'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    unit = fields.Char(
        string='Unit of Measure',
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
