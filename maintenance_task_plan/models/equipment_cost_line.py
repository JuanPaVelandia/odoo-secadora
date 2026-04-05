from odoo import fields, models


class MaintenanceEquipmentCostLine(models.Model):
    _inherit = 'maintenance.equipment.cost.line'

    task_plan_id = fields.Many2one(
        related='request_id.task_plan_id',
        store=True,
        string='Tarea',
    )
