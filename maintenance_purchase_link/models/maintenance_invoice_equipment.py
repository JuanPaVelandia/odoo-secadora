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
        # No es obligatorio: la orden de trabajo puede indicarse antes de
        # saber a qué equipo se imputa el costo. Una fila sin equipo solo
        # transporta la OT hasta que se elija uno.
        ondelete='cascade',
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        default=100.0,
    )
    request_id = fields.Many2one(
        'maintenance.request',
        string='Orden de trabajo',
    )

    _unique_move_equipment = models.Constraint(
        'UNIQUE(move_id, equipment_id)',
        'Un equipo solo puede asignarse una vez por factura.',
    )

    @api.constrains('equipment_id', 'move_id')
    def _check_una_sola_fila_sin_equipo(self):
        """Sin equipo solo tiene sentido una fila: la que lleva la OT.

        El UNIQUE de Postgres no lo cubre porque los NULL no colisionan entre
        sí, y varias filas vacías dejarían la factura con una asignación
        ambigua.
        """
        for rec in self.filtered(lambda r: not r.equipment_id):
            otras = self.sudo().search_count([
                ('move_id', '=', rec.move_id.id),
                ('equipment_id', '=', False),
                ('id', '!=', rec.id),
            ])
            if otras:
                raise ValidationError(_(
                    'Solo puede haber una fila sin equipo por factura.'
                ))

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
            # sudo: las filas pueden referirse a equipos de otra compañía que
            # el usuario no tiene activa; sin él la suma los ignoraba y el
            # reparto podía pasar del 100% sin avisar.
            # La fila que solo lleva la OT no reparte nada: contar su 100%
            # haría imposible añadir después el equipo.
            total = sum(
                self.sudo().search([
                    ('move_id', '=', rec.move_id.id),
                    ('equipment_id', '!=', False),
                ]).mapped('percentage')
            )
            if total > 100.0:
                raise ValidationError(_(
                    'La suma de porcentajes de equipos en la factura '
                    '"%(invoice)s" excede el 100%% (actual: %(total).1f%%).',
                    invoice=rec.move_id.name,
                    total=total,
                ))
