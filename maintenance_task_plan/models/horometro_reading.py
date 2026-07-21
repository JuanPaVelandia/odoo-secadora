from odoo import api, models


class MaintenanceHorometroReading(models.Model):
    _inherit = 'maintenance.horometro.reading'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_task_plan_update'):
            records._update_task_plan_lines()
        return records

    def _update_task_plan_lines(self):
        """Al registrar lectura de horómetro, actualizar las líneas de plan de tareas."""
        PlanLine = self.env['maintenance.task.plan.line']
        # Buscar el counter type de horómetro
        hour_meter_types = self.env['maintenance.counter.type'].search([
            ('unit', 'ilike', 'hora'),
        ])
        if not hour_meter_types:
            return

        for reading in self:
            plan_lines = PlanLine.search([
                ('equipment_id', '=', reading.equipment_id.id),
                ('counter_type_id', 'in', hour_meter_types.ids),
                ('plan_id.active', '=', True),
            ])
            if plan_lines:
                plan_lines.write({
                    'current_counter_reading': reading.value,
                })
                # Generar OTs automáticamente si alcanzó el umbral
                plan_lines._generate_requests()
