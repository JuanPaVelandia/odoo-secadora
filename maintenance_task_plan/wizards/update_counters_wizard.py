from odoo import api, fields, models, _


class UpdateCountersWizard(models.TransientModel):
    _name = 'maintenance.update.counters.wizard'
    _description = 'Actualizar Contadores'

    counter_type_id = fields.Many2one(
        'maintenance.counter.type',
        string='Tipo de contador',
        required=True,
    )
    line_ids = fields.One2many(
        'maintenance.update.counters.wizard.line',
        'wizard_id',
        string='Lecturas',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Pre-seleccionar Horómetro si existe
        hour_type = self.env['maintenance.counter.type'].search([
            ('unit', 'ilike', 'hora'),
        ], limit=1)
        if hour_type:
            res['counter_type_id'] = hour_type.id
        return res

    @api.onchange('counter_type_id')
    def _onchange_counter_type_id(self):
        self.line_ids = [(5, 0, 0)]
        if not self.counter_type_id:
            return

        plan_lines = self.env['maintenance.task.plan.line'].search([
            ('counter_type_id', '=', self.counter_type_id.id),
            ('plan_id.active', '=', True),
        ])

        # Agrupar por equipo, tomar la lectura más alta
        equipment_map = {}
        for pl in plan_lines:
            eq_id = pl.equipment_id.id
            if eq_id not in equipment_map or pl.current_counter_reading > equipment_map[eq_id]['current_reading']:
                equipment_map[eq_id] = {
                    'equipment_id': eq_id,
                    'equipment_name': pl.equipment_id.name,
                    'current_reading': pl.current_counter_reading,
                }

        vals = []
        for data in sorted(equipment_map.values(), key=lambda d: d['equipment_name']):
            vals.append((0, 0, {
                'equipment_id': data['equipment_id'],
                'current_reading': data['current_reading'],
                'new_reading': data['current_reading'],
            }))
        self.line_ids = vals

    def action_update(self):
        self.ensure_one()
        PlanLine = self.env['maintenance.task.plan.line']
        HorometroReading = self.env['maintenance.horometro.reading']
        updated = 0

        for wiz_line in self.line_ids:
            if wiz_line.new_reading <= wiz_line.current_reading:
                continue

            # Actualizar plan lines
            plan_lines = PlanLine.search([
                ('equipment_id', '=', wiz_line.equipment_id.id),
                ('counter_type_id', '=', self.counter_type_id.id),
                ('plan_id.active', '=', True),
            ])
            plan_lines.write({
                'current_counter_reading': wiz_line.new_reading,
            })

            # Crear lectura de horómetro en el historial
            HorometroReading.with_context(skip_task_plan_update=True).create({
                'equipment_id': wiz_line.equipment_id.id,
                'date': fields.Date.context_today(self),
                'value': wiz_line.new_reading,
                'user_id': self.env.user.id,
                'notes': _('Actualización masiva de contadores'),
            })

            # Generar OTs si se alcanzó el umbral
            plan_lines._generate_requests()

            updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contadores actualizados'),
                'message': _('%d equipo(s) actualizado(s).', updated),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class UpdateCountersWizardLine(models.TransientModel):
    _name = 'maintenance.update.counters.wizard.line'
    _description = 'Línea del wizard actualizar contadores'

    wizard_id = fields.Many2one(
        'maintenance.update.counters.wizard',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        readonly=True,
    )
    current_reading = fields.Float(
        string='Lectura actual',
        readonly=True,
    )
    new_reading = fields.Float(
        string='Nueva lectura',
    )
