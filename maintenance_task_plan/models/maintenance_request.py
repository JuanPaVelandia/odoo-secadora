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
        if 'stage_id' in vals or 'counter_reading_at_close' in vals:
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
                # No lanzar error aquí — puede que aún no hayan llenado la lectura.
                # Se validará cuando intenten guardar con la etapa done.
                continue

            line = request.task_plan_line_id
            # Solo actualizar si la lectura es mayor a la última registrada
            if request.counter_reading_at_close > line.last_counter_reading:
                line.write({
                    'last_counter_reading': request.counter_reading_at_close,
                    'current_counter_reading': request.counter_reading_at_close,
                    'last_request_id': request.id,
                })
                # Registrar lectura en el historial de horómetro
                self.env['maintenance.horometro.reading'].with_context(
                    skip_task_plan_update=True,
                ).create({
                    'equipment_id': request.equipment_id.id,
                    'date': fields.Date.context_today(request),
                    'value': request.counter_reading_at_close,
                    'user_id': self.env.user.id,
                    'notes': _('Lectura al cerrar OT: %(ot)s', ot=request.sequence_number or request.name),
                })

    @api.constrains('stage_id', 'counter_reading_at_close')
    def _check_counter_at_close_required(self):
        """Validar que se llene la lectura antes de cerrar y que no sea menor a la última."""
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
            last = request.task_plan_line_id.last_counter_reading
            if request.counter_reading_at_close < last:
                unit = request.counter_unit or ''
                raise ValidationError(_(
                    'La lectura del contador (%(nueva).0f %(unidad)s) no puede ser menor '
                    'a la última lectura registrada (%(ultima).0f %(unidad)s).',
                    nueva=request.counter_reading_at_close,
                    ultima=last,
                    unidad=unit,
                ))
