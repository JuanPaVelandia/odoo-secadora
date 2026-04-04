from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    sequence_number = fields.Char(
        string='Nro. OT',
        readonly=True,
        copy=False,
        default='Nuevo',
    )
    task_plan_id = fields.Many2one(
        'maintenance.task.plan',
        string='Plan de tareas',
    )
    task_plan_line_id = fields.Many2one(
        'maintenance.task.plan.line',
        string='Línea del plan',
    )
    counter_type_id = fields.Many2one(
        related='task_plan_id.counter_type_id',
        string='Tipo de contador',
    )
    counter_reading_at_close = fields.Float(
        string='Lectura del contador al cerrar',
    )
    counter_unit = fields.Char(
        related='task_plan_id.counter_type_id.unit',
        string='Unidad',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('sequence_number', 'Nuevo') == 'Nuevo':
                vals['sequence_number'] = self.env['ir.sequence'].next_by_code(
                    'maintenance.request'
                ) or 'Nuevo'
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            self._check_close_task_plan()
        return res

    def _check_close_task_plan(self):
        """Al cerrar la OT (stage done=True), actualizar la línea del plan."""
        for request in self:
            if not request.task_plan_line_id:
                continue
            if not request.stage_id.done:
                continue

            if not request.counter_reading_at_close:
                raise ValidationError(_(
                    'Debe ingresar la lectura del contador al cerrar '
                    'antes de completar la OT "%(name)s".',
                    name=request.name,
                ))

            line = request.task_plan_line_id
            line.write({
                'last_counter_reading': request.counter_reading_at_close,
                'current_counter_reading': request.counter_reading_at_close,
                'last_request_id': request.id,
            })
