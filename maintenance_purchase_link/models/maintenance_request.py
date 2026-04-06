from odoo import api, fields, models


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    invoice_line_ids = fields.Many2many(
        'account.move.line',
        'account_move_line_maintenance_request_rel',
        'request_id',
        'move_line_id',
        string='Líneas de factura',
    )
    cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'request_id',
        string='Costos asignados',
    )
    cost_total = fields.Monetary(
        string='Costo total',
        compute='_compute_cost_total',
        currency_field='cost_currency_id',
    )
    cost_count = fields.Integer(
        string='Nro. costos',
        compute='_compute_cost_total',
    )
    cost_currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    @api.depends('cost_line_ids.amount')
    def _compute_cost_total(self):
        for request in self:
            request.cost_total = sum(request.cost_line_ids.mapped('amount'))
            request.cost_count = len(request.cost_line_ids)

    def action_view_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos de la OT',
            'res_model': 'maintenance.equipment.cost.line',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
        }

    def action_assign_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar factura',
            'res_model': 'maintenance.assign.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_equipment_id': self.equipment_id.id if self.equipment_id else False,
            },
        }
