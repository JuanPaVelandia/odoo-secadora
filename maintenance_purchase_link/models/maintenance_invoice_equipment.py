from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MaintenanceInvoiceEquipment(models.Model):
    _name = 'maintenance.invoice.equipment'
    _description = 'Equipo asignado a nivel de factura'

    move_id = fields.Many2one(
        'account.move',
        string='Factura',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipo',
        required=True,
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
    )

    _sql_constraints = [
        (
            'unique_move_equipment',
            'UNIQUE(move_id, equipment_id)',
            'Un equipo solo puede asignarse una vez por factura.',
        ),
    ]

    @api.constrains('percentage')
    def _check_percentage_range(self):
        for rec in self:
            if rec.percentage < 0 or rec.percentage > 100:
                raise ValidationError(_(
                    'El porcentaje debe estar entre 0 y 100.'
                ))

    @api.constrains('percentage', 'move_id')
    def _check_total_percentage(self):
        for rec in self:
            total = sum(
                self.search([
                    ('move_id', '=', rec.move_id.id),
                ]).mapped('percentage')
            )
            if total > 100.0:
                raise ValidationError(_(
                    'La suma de porcentajes de equipos en la factura '
                    '"%(invoice)s" excede el 100%% (actual: %(total).1f%%).',
                    invoice=rec.move_id.name,
                    total=total,
                ))
