from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # --- Ubicación ---
    lugar_id = fields.Many2one(
        'secadora.lugar',
        string='Ubicación',
    )
    origen_muestra_id = fields.Many2one(
        'secadora.origen.muestra',
        string='Área de proceso',
        help='Área dentro de la planta (Prelimpieza, Secamiento, '
             'Almacenamiento). Se reusa el catálogo de calidad para no '
             'duplicar el listado de áreas.',
    )
    parent_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Parte de',
        help='Equipo padre, cuando este registro es un componente '
             '(motor, alternador, etc.).',
    )
    component_ids = fields.One2many(
        'maintenance.equipment',
        'parent_equipment_id',
        string='Componentes',
    )
    component_count = fields.Integer(
        string='Nro. componentes',
        compute='_compute_component_count',
    )
    location_history_ids = fields.One2many(
        'maintenance.equipment.location.history',
        'equipment_id',
        string='Historial de ubicación',
    )
    location_history_count = fields.Integer(
        string='Nro. movimientos',
        compute='_compute_component_count',
    )

    # --- Costos (modelo intermedio) ---
    equipment_cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'equipment_id',
        string='Líneas de costo',
    )
    historic_cost_ids = fields.One2many(
        'maintenance.historic.cost',
        'equipment_id',
        string='Costos históricos',
    )
    historic_cost_total = fields.Monetary(
        string='Costo histórico (sin factura)',
        compute='_compute_maintenance_cost_total',
        store=True,
        currency_field='cost_currency_id',
    )
    maintenance_cost_total = fields.Monetary(
        string='Costo de mantenimiento (facturas)',
        compute='_compute_maintenance_cost_total',
        store=True,
        currency_field='cost_currency_id',
    )
    maintenance_cost_grand_total = fields.Monetary(
        string='Costo total de mantenimiento',
        compute='_compute_maintenance_cost_total',
        store=True,
        currency_field='cost_currency_id',
        help='Suma del costo facturado y del costo histórico importado.',
    )
    maintenance_invoice_count = fields.Integer(
        string='Nro. líneas de factura',
        compute='_compute_maintenance_cost_total',
        store=True,
    )
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        copy=False,
        help='Código del activo en el sistema de origen (Fracttal). '
             'Se usa para no duplicar en re-importaciones.',
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
        'historic_cost_ids.amount',
    )
    def _compute_maintenance_cost_total(self):
        for equipment in self:
            lines = equipment.equipment_cost_line_ids
            invoiced = sum(lines.mapped('amount'))
            historic = sum(equipment.historic_cost_ids.mapped('amount'))
            equipment.maintenance_cost_total = invoiced
            equipment.historic_cost_total = historic
            equipment.maintenance_cost_grand_total = invoiced + historic
            equipment.maintenance_invoice_count = len(lines)

    @api.depends('component_ids', 'location_history_ids')
    def _compute_component_count(self):
        for equipment in self:
            equipment.component_count = len(equipment.component_ids)
            equipment.location_history_count = len(equipment.location_history_ids)

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
        action = self.env['ir.actions.actions']._for_xml_id(
            'maintenance_purchase_link.action_equipment_cost_lines'
        )
        action['domain'] = [('equipment_id', '=', self.id)]
        action['context'] = dict(self.env.context, default_equipment_id=self.id)
        return action

    def action_view_historic_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos históricos',
            'res_model': 'maintenance.historic.cost',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }

    def action_view_location_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de ubicación',
            'res_model': 'maintenance.equipment.location.history',
            'view_mode': 'list,form',
            'domain': [('equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_equipment_id=self.id),
        }

    def action_view_components(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Componentes',
            'res_model': 'maintenance.equipment',
            'view_mode': 'list,form',
            'domain': [('parent_equipment_id', '=', self.id)],
            'context': dict(self.env.context, default_parent_equipment_id=self.id),
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
