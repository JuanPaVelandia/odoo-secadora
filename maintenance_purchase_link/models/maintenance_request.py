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
    total_cost = fields.Float(
        string='Costo total',
        compute='_compute_total_cost',
        store=True,
    )
    invoice_line_count = fields.Integer(
        string='Nro. líneas de factura',
        compute='_compute_total_cost',
        store=True,
    )

    @api.depends('invoice_line_ids', 'invoice_line_ids.price_subtotal')
    def _compute_total_cost(self):
        for request in self:
            lines = request.invoice_line_ids
            request.total_cost = sum(lines.mapped('price_subtotal'))
            request.invoice_line_count = len(lines)

    def action_view_invoice_costs(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'maintenance_purchase_link.action_maintenance_cost_lines'
        )
        action['domain'] = [('id', 'in', self.invoice_line_ids.ids)]
        action['context'] = dict(self.env.context, default_maintenance_request_ids=[(4, self.id)])
        return action
