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
    historic_cost_ids = fields.One2many(
        'maintenance.historic.cost',
        'request_id',
        string='Costos históricos',
    )
    historic_cost_total = fields.Monetary(
        string='Costo histórico (sin factura)',
        compute='_compute_cost_total',
        currency_field='cost_currency_id',
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
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        copy=False,
        help='Id de la OT en el sistema de origen (ej. OT-999). '
             'Se usa para no duplicar en re-importaciones.',
    )
    task_name = fields.Char(
        string='Tarea',
        help='Tarea tal como estaba registrada en el sistema de origen.',
    )

    @api.depends('cost_line_ids.amount', 'historic_cost_ids.amount')
    def _compute_cost_total(self):
        for request in self:
            invoiced = sum(request.cost_line_ids.mapped('amount'))
            historic = sum(request.historic_cost_ids.mapped('amount'))
            request.historic_cost_total = historic
            request.cost_total = invoiced + historic
            request.cost_count = (
                len(request.cost_line_ids) + len(request.historic_cost_ids)
            )

    def action_view_historic_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos históricos de la OT',
            'res_model': 'maintenance.historic.cost',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
            'context': dict(self.env.context, default_request_id=self.id),
        }

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
