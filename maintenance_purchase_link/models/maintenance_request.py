from odoo import _, api, fields, models


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
    ot_number = fields.Char(
        string='Nro. de OT',
        index=True,
        copy=False,
        readonly=True,
        # Sin `default`: lo asigna create(). Un default consumiría un número
        # de la secuencia cada vez que se abre el formulario, aunque no se
        # llegue a guardar.
        help='Número consecutivo de la orden (OT-1241, OT-1242, …). '
             'Continúa la serie que traía Fracttal.',
    )
    external_ref = fields.Char(
        string='Referencia externa',
        index=True,
        copy=False,
        help='Id de la OT en el sistema de origen. Se usa para no duplicar '
             'en re-importaciones.',
    )
    task_name = fields.Char(
        string='Tarea',
        help='Tarea tal como estaba registrada en el sistema de origen.',
    )

    _unique_ot_number = models.Constraint(
        'UNIQUE(ot_number)',
        'Ya existe una orden de trabajo con ese número.',
    )

    @api.model
    def _siguiente_ot_number(self):
        return self.env['ir.sequence'].next_by_code('maintenance.request.ot')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Las OT importadas traen su número de origen; el resto lo toma
            # de la secuencia, que continúa esa misma serie.
            if not vals.get('ot_number'):
                vals['ot_number'] = self._siguiente_ot_number()
        return super().create(vals_list)

    @api.depends('ot_number', 'name')
    def _compute_display_name(self):
        for request in self:
            nombre = request.name or ''
            if request.ot_number and nombre:
                request.display_name = f'[{request.ot_number}] {nombre}'
            else:
                # Una solicitud recién creada aún no tiene nombre: mostrar
                # "False" sería peor que mostrar solo el número.
                request.display_name = request.ot_number or nombre or _('Nueva solicitud')

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
