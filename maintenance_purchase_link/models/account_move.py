from odoo import api, fields, models, Command


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )

    def _propagate_equipment_to_lines(self):
        """Propagar equipos asignados a nivel de factura a todas las líneas producto."""
        CostLine = self.env['maintenance.equipment.cost.line']
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                continue

            # Eliminar asignaciones anteriores de las líneas de esta factura
            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])
            existing.unlink()

            # Crear nuevas asignaciones desde la plantilla de factura
            vals_list = []
            for eq_line in move.maintenance_equipment_line_ids:
                for ml in product_lines:
                    vals_list.append({
                        'move_line_id': ml.id,
                        'equipment_id': eq_line.equipment_id.id,
                        'percentage': eq_line.percentage,
                    })
            if vals_list:
                CostLine.create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'maintenance_equipment_line_ids' in vals:
            self._propagate_equipment_to_lines()
        return res
