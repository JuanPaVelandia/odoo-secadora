from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    maintenance_invoice_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_line_maintenance_equipment_rel',
        'equipment_id',
        'move_line_id',
        string='Líneas de factura de mantenimiento',
    )
    maintenance_cost_total = fields.Float(
        string='Costo total de mantenimiento',
        compute='_compute_maintenance_cost_total',
        store=True,
    )
    maintenance_invoice_count = fields.Integer(
        string='Nro. líneas de factura',
        compute='_compute_maintenance_cost_total',
        store=True,
    )

    @api.depends('maintenance_invoice_line_ids', 'maintenance_invoice_line_ids.price_subtotal')
    def _compute_maintenance_cost_total(self):
        for equipment in self:
            lines = equipment.maintenance_invoice_line_ids
            equipment.maintenance_cost_total = sum(lines.mapped('price_subtotal'))
            equipment.maintenance_invoice_count = len(lines)

    def action_view_maintenance_costs(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'maintenance_purchase_link.action_maintenance_cost_lines'
        )
        action['domain'] = [('id', 'in', self.maintenance_invoice_line_ids.ids)]
        action['context'] = dict(self.env.context, default_maintenance_equipment_ids=[(4, self.id)])
        return action
