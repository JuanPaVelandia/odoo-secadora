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
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                continue

            product_line_ids = product_lines.ids

            # Leer asignaciones directamente de BD para evitar cache
            self.env.cr.execute("""
                SELECT equipment_id, percentage, request_id
                FROM maintenance_invoice_equipment
                WHERE move_id = %s
            """, (move.id,))
            eq_rows = self.env.cr.fetchall()

            if not eq_rows:
                continue

            # Borrar cost lines existentes de esta factura
            self.env.cr.execute("""
                DELETE FROM maintenance_equipment_cost_line
                WHERE move_line_id IN %s
            """, (tuple(product_line_ids),))

            # Crear nuevas cost lines
            for eq_id, percentage, request_id in eq_rows:
                for ml_id in product_line_ids:
                    self.env.cr.execute("""
                        INSERT INTO maintenance_equipment_cost_line
                            (move_line_id, equipment_id, percentage, request_id,
                             create_uid, create_date, write_uid, write_date)
                        VALUES (%s, %s, %s, %s, %s, NOW(), %s, NOW())
                    """, (ml_id, eq_id, percentage, request_id,
                          self.env.uid, self.env.uid))

            # Invalidar cache para que el ORM vea los cambios
            self.env['maintenance.equipment.cost.line'].invalidate_model()

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
