from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )

    def _propagate_equipment_to_lines(self):
        """Propagar equipos asignados a nivel de factura a todas las líneas producto.

        Usa SQL para leer las asignaciones y crear las cost lines,
        luego fuerza el recálculo de campos stored via ORM.
        """
        CostLine = self.env['maintenance.equipment.cost.line']
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                continue

            product_line_ids = product_lines.ids

            # Leer asignaciones de BD
            self.env.cr.execute("""
                SELECT equipment_id, percentage
                FROM maintenance_invoice_equipment
                WHERE move_id = %s
            """, (move.id,))
            eq_rows = self.env.cr.fetchall()

            # Determinar qué combinaciones (move_line, equipment) ya existen
            existing = CostLine.search([
                ('move_line_id', 'in', product_line_ids),
            ])
            existing_keys = {
                (cl.move_line_id.id, cl.equipment_id.id): cl
                for cl in existing
            }

            desired_keys = set()
            for eq_id, percentage in eq_rows:
                for ml_id in product_line_ids:
                    desired_keys.add((ml_id, eq_id))

            # Eliminar cost lines que ya no están en la asignación
            to_remove = existing.filtered(
                lambda cl: (cl.move_line_id.id, cl.equipment_id.id) not in desired_keys
            )
            if to_remove:
                to_remove.unlink()

            # Actualizar porcentaje de existentes
            for key, cl in existing_keys.items():
                if key not in desired_keys:
                    continue
                eq_id = key[1]
                for r_eq_id, r_pct in eq_rows:
                    if r_eq_id == eq_id and cl.percentage != r_pct:
                        cl.percentage = r_pct
                        break

            # Crear solo los que faltan
            to_create = desired_keys - set(existing_keys.keys())
            if to_create:
                vals_list = []
                for ml_id, eq_id in to_create:
                    pct = next(p for e, p in eq_rows if e == eq_id)
                    vals_list.append({
                        'move_line_id': ml_id,
                        'equipment_id': eq_id,
                        'percentage': pct,
                    })
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
