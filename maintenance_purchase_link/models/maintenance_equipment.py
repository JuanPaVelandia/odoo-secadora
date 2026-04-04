from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # --- Ubicación ---
    lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Ubicación',
    )

    # --- Costos (modelo intermedio) ---
    equipment_cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'equipment_id',
        string='Líneas de costo',
    )
    maintenance_cost_total = fields.Monetary(
        string='Costo total de mantenimiento',
        compute='_compute_maintenance_cost_total',
        store=True,
        currency_field='cost_currency_id',
    )
    maintenance_invoice_count = fields.Integer(
        string='Nro. líneas de factura',
        compute='_compute_maintenance_cost_total',
        store=True,
    )
    cost_currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    # --- Horómetro ---
    horometro_interval = fields.Float(
        string='Intervalo horómetro (horas)',
        help='Cada cuántas horas se genera una solicitud de mantenimiento preventivo.',
    )
    horometro_last_maintenance = fields.Float(
        string='Última lectura mant. (horas)',
        help='Lectura del horómetro en el último mantenimiento disparado.',
    )
    horometro_reading_ids = fields.One2many(
        'maintenance.horometro.reading',
        'equipment_id',
        string='Lecturas de horómetro',
    )
    horometro_current = fields.Float(
        string='Horómetro actual',
        compute='_compute_horometro_current',
    )
    horometro_reading_count = fields.Integer(
        string='Nro. lecturas',
        compute='_compute_horometro_current',
    )

    @api.depends(
        'equipment_cost_line_ids.amount',
    )
    def _compute_maintenance_cost_total(self):
        for equipment in self:
            lines = equipment.equipment_cost_line_ids
            equipment.maintenance_cost_total = sum(lines.mapped('amount'))
            equipment.maintenance_invoice_count = len(lines)

    @api.depends('horometro_reading_ids.value')
    def _compute_horometro_current(self):
        for equipment in self:
            readings = equipment.horometro_reading_ids
            equipment.horometro_reading_count = len(readings)
            if readings:
                equipment.horometro_current = readings[0].value  # ordered desc
            else:
                equipment.horometro_current = 0.0

    def action_view_maintenance_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos de mantenimiento',
            'res_model': 'maintenance.equipment.cost.line',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }

    def action_view_horometro_readings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lecturas de horómetro',
            'res_model': 'maintenance.horometro.reading',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }
