from odoo import api, fields, models


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

            # Leer asignaciones de BD (evitar cache)
            self.env.cr.execute("""
                SELECT equipment_id, percentage
                FROM maintenance_invoice_equipment
                WHERE move_id = %s
            """, (move.id,))
            eq_rows = self.env.cr.fetchall()

            # Borrar cost lines existentes via ORM
            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])
            existing.unlink()

            # Crear nuevas cost lines via ORM (para que computed fields funcionen)
            vals_list = []
            for eq_id, percentage in eq_rows:
                for ml in product_lines:
                    vals_list.append({
                        'move_line_id': ml.id,
                        'equipment_id': eq_id,
                        'percentage': percentage,
                    })
            if vals_list:
                CostLine.create(vals_list)

    def action_view_cost_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Costos asignados',
            'res_model': 'maintenance.equipment.cost.line',
            'view_mode': 'list,form',
            'domain': [('move_id', '=', self.id)],
        }

    def write(self, vals):
        res = super().write(vals)
        if 'maintenance_equipment_line_ids' in vals:
            self._propagate_equipment_to_lines()
        return res
