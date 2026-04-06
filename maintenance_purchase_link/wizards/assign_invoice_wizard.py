from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AssignInvoiceWizard(models.TransientModel):
    _name = 'maintenance.assign.invoice.wizard'
    _description = 'Asignar factura a equipos'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        domain=[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')],
    )
    move_partner_id = fields.Many2one(
        related='move_id.partner_id',
        string='Proveedor',
    )
    move_amount = fields.Monetary(
        related='move_id.amount_untaxed',
        string='Subtotal factura',
    )
    currency_id = fields.Many2one(
        related='move_id.currency_id',
    )
    line_count = fields.Integer(
        string='Líneas de producto',
        compute='_compute_line_count',
    )
    line_ids = fields.One2many(
        'maintenance.assign.invoice.wizard.line',
        'wizard_id',
        string='Equipos',
    )
    total_percentage = fields.Float(
        string='Total %',
        compute='_compute_total_percentage',
    )

    @api.depends('move_id')
    def _compute_line_count(self):
        for wiz in self:
            if wiz.move_id:
                wiz.line_count = len(wiz.move_id.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                ))
            else:
                wiz.line_count = 0

    @api.depends('line_ids.percentage')
    def _compute_total_percentage(self):
        for wiz in self:
            wiz.total_percentage = sum(wiz.line_ids.mapped('percentage'))

    def action_assign(self):
        self.ensure_one()
        CostLine = self.env['maintenance.equipment.cost.line']

        if not self.line_ids:
            raise ValidationError(_('Debe agregar al menos un equipo.'))

        total = sum(self.line_ids.mapped('percentage'))
        if abs(total - 100.0) > 0.01:
            raise ValidationError(_(
                'Los porcentajes deben sumar exactamente 100%%. '
                'Actualmente suman %.1f%%.',
                total,
            ))

        product_lines = self.move_id.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        if not product_lines:
            raise ValidationError(_('La factura no tiene líneas de producto.'))

        # Eliminar cost lines existentes de esta factura
        existing = CostLine.search([
            ('move_line_id', 'in', product_lines.ids),
        ])
        if existing:
            existing.unlink()

        # Crear cost lines para cada equipo × línea de producto
        vals_list = []
        for wiz_line in self.line_ids:
            for ml in product_lines:
                vals_list.append({
                    'move_line_id': ml.id,
                    'equipment_id': wiz_line.equipment_id.id,
                    'percentage': wiz_line.percentage,
                    'request_id': wiz_line.request_id.id if wiz_line.request_id else False,
                })
        CostLine.create(vals_list)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Factura asignada'),
                'message': _(
                    '%(lines)d línea(s) × %(equipos)d equipo(s) = %(total)d asignaciones creadas.',
                    lines=len(product_lines),
                    equipos=len(self.line_ids),
                    total=len(vals_list),
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class AssignInvoiceWizardLine(models.TransientModel):
    _name = 'maintenance.assign.invoice.wizard.line'
    _description = 'Línea del wizard asignar factura'

    wizard_id = fields.Many2one(
        'maintenance.assign.invoice.wizard',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
        required=True,
    )
