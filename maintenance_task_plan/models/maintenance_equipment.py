from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    task_plan_line_ids = fields.One2many(
        'maintenance.task.plan.line',
        'equipment_id',
        string='Líneas de plan de tareas',
    )
    task_plan_count = fields.Integer(
        string='Planes de mant.',
        compute='_compute_task_plan_count',
    )

    @api.depends('task_plan_line_ids')
    def _compute_task_plan_count(self):
        for eq in self:
            eq.task_plan_count = len(eq.task_plan_line_ids)

    def action_view_task_plans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Planes de mantenimiento',
            'res_model': 'maintenance.task.plan.line',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
        }
