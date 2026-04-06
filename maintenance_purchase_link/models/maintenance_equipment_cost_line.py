from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceEquipmentCostLine(models.Model):
    _name = 'maintenance.equipment.cost.line'
    _description = 'Línea de costo por equipo'
    _order = 'date desc, id desc'

    move_line_id = fields.Many2one(
        'account.move.line',
        string='Línea de factura',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
        ondelete='cascade',
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
    )
    amount = fields.Monetary(
        string='Monto',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id',
    )

    # Related fields for reporting/grouping
    move_id = fields.Many2one(
        related='move_line_id.move_id',
        store=True,
        string='Factura',
    )
    date = fields.Date(
        related='move_line_id.date',
        store=True,
        string='Fecha',
    )
    partner_id = fields.Many2one(
        related='move_line_id.partner_id',
        store=True,
        string='Proveedor',
    )
    currency_id = fields.Many2one(
        related='move_line_id.currency_id',
    )
    product_id = fields.Many2one(
        related='move_line_id.product_id',
        store=True,
        string='Recurso',
    )
    product_description = fields.Char(
        related='move_line_id.name',
        string='Descripción',
    )
    quantity = fields.Float(
        related='move_line_id.quantity',
        string='Cantidad',
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        compute='_compute_attachment_ids',
        string='Adjuntos',
    )
    attachment_count = fields.Integer(
        compute='_compute_attachment_ids',
        string='Nro. adjuntos',
    )

    def _compute_attachment_ids(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            attachments = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', rec.move_id.id),
            ])
            rec.attachment_ids = attachments
            rec.attachment_count = len(attachments)


    _sql_constraints = [
        (
            'unique_line_equipment',
            'UNIQUE(move_line_id, equipment_id)',
            'Un equipo solo puede asignarse una vez por línea de factura.',
        ),
    ]

    @api.constrains('percentage')
    def _check_percentage_range(self):
        for rec in self:
            if rec.percentage < 0 or rec.percentage > 100:
                raise ValidationError(_(
                    'El porcentaje debe estar entre 0 y 100.'
                ))

    @api.constrains('percentage', 'move_line_id')
    def _check_total_percentage(self):
        for rec in self:
            total = sum(
                self.search([
                    ('move_line_id', '=', rec.move_line_id.id),
                ]).mapped('percentage')
            )
            if total > 100.0:
                raise ValidationError(_(
                    'La suma de porcentajes para la línea "%(line)s" '
                    'excede el 100%% (actual: %(total).1f%%).',
                    line=rec.move_line_id.name or rec.move_line_id.move_name,
                    total=total,
                ))

    def action_view_attachments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjuntos de factura',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [
                ('res_model', '=', 'account.move'),
                ('res_id', '=', self.move_id.id),
            ],
        }

    @api.depends('move_line_id.price_subtotal', 'percentage')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.move_line_id.price_subtotal * rec.percentage / 100.0
