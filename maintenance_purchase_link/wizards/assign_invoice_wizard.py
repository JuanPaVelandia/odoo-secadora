from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AssignInvoiceWizard(models.TransientModel):
    _name = 'maintenance.assign.invoice.wizard'
    _description = 'Asignar factura a equipo'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        domain=[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')],
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

    # Info de la factura seleccionada
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

    @api.depends('move_id')
    def _compute_line_count(self):
        for wiz in self:
            if wiz.move_id:
                wiz.line_count = len(wiz.move_id.invoice_line_ids.filtered(
                    lambda l: l.display_type == 'product'
                ))
            else:
                wiz.line_count = 0

    @api.constrains('percentage')
    def _check_percentage(self):
        for wiz in self:
            if wiz.percentage <= 0 or wiz.percentage > 100:
                raise ValidationError(_('El porcentaje debe estar entre 0 y 100.'))

    def action_assign(self):
        self.ensure_one()
        CostLine = self.env['maintenance.equipment.cost.line']

        product_lines = self.move_id.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product'
        )
        if not product_lines:
            raise ValidationError(_('La factura no tiene líneas de producto.'))

        # Verificar que no se exceda 100% por línea
        for ml in product_lines:
            existing_pct = sum(
                CostLine.search([
                    ('move_line_id', '=', ml.id),
                ]).mapped('percentage')
            )
            if existing_pct + self.percentage > 100.0:
                raise ValidationError(_(
                    'La línea "%(line)s" ya tiene %(existing).0f%% asignado. '
                    'No se puede agregar %(new).0f%% más.',
                    line=ml.name,
                    existing=existing_pct,
                    new=self.percentage,
                ))

        # Crear cost lines para todas las líneas de producto
        created = 0
        for ml in product_lines:
            # Verificar si ya existe esta combinación
            exists = CostLine.search([
                ('move_line_id', '=', ml.id),
                ('equipment_id', '=', self.equipment_id.id),
            ], limit=1)
            if exists:
                continue

            CostLine.create({
                'move_line_id': ml.id,
                'equipment_id': self.equipment_id.id,
                'percentage': self.percentage,
                'request_id': self.request_id.id if self.request_id else False,
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Factura asignada'),
                'message': _('%(count)d línea(s) asignada(s) al equipo %(equipo)s.',
                             count=created, equipo=self.equipment_id.name),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
