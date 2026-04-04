from odoo import api, fields, models, _


class UpdateCountersWizard(models.TransientModel):
    _name = 'maintenance.update.counters.wizard'
    _description = 'Wizard Actualizar Contadores'

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

    @api.onchange('counter_type_id')
    def _onchange_counter_type_id(self):
        self.line_ids = [(5, 0, 0)]
        if not self.counter_type_id:
            return

        plan_lines = self.env['maintenance.task.plan.line'].search([
            ('counter_type_id', '=', self.counter_type_id.id),
            ('plan_id.active', '=', True),
        ])

        equipment_map = {}
        for pl in plan_lines:
            if pl.equipment_id.id not in equipment_map:
                equipment_map[pl.equipment_id.id] = {
                    'equipment_id': pl.equipment_id.id,
                    'current_reading': pl.current_counter_reading,
                }

        vals = []
        for data in equipment_map.values():
            vals.append((0, 0, {
                'equipment_id': data['equipment_id'],
                'current_reading': data['current_reading'],
                'new_reading': data['current_reading'],
            }))
        self.line_ids = vals

    def action_update(self):
        self.ensure_one()
        PlanLine = self.env['maintenance.task.plan.line']
        updated = 0

        for wiz_line in self.line_ids:
            if wiz_line.new_reading <= wiz_line.current_reading:
                continue

            plan_lines = PlanLine.search([
                ('equipment_id', '=', wiz_line.equipment_id.id),
                ('counter_type_id', '=', self.counter_type_id.id),
                ('plan_id.active', '=', True),
            ])
            plan_lines.write({
                'current_counter_reading': wiz_line.new_reading,
            })
            updated += len(plan_lines)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Contadores actualizados'),
                'message': _('%d línea(s) de seguimiento actualizada(s).', updated),
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
        string='Wizard',
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
