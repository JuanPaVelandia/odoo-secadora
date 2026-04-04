from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    task_plan_id = fields.Many2one(
        'maintenance.task.plan',
        string='Task Plan',
    )
    task_plan_line_id = fields.Many2one(
        'maintenance.task.plan.line',
        string='Task Plan Line',
    )
    counter_type_id = fields.Many2one(
        related='task_plan_id.counter_type_id',
        string='Counter Type',
    )
    counter_reading_at_close = fields.Float(
        string='Counter Reading at Close',
    )
    counter_unit = fields.Char(
        related='task_plan_id.counter_type_id.unit',
        string='Counter Unit',
    )

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            self._check_close_task_plan()
        return res

    def _check_close_task_plan(self):
        """When a request is closed (stage done=True), update the task plan line."""
        for request in self:
            if not request.task_plan_line_id:
                continue
            if not request.stage_id.done:
                continue

            if not request.counter_reading_at_close:
                raise ValidationError(_(
                    'You must enter the counter reading at close '
                    'before completing work order "%(name)s".',
                    name=request.name,
                ))

            line = request.task_plan_line_id
            line.write({
                'last_counter_reading': request.counter_reading_at_close,
                'current_counter_reading': request.counter_reading_at_close,
                'last_request_id': request.id,
            })
