from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )

    def _post(self, soft=True):
        """Al publicar factura, crear cost lines para líneas con analítica de Mantenimiento."""
        posted = super()._post(soft=soft)
        posted._auto_create_maintenance_cost_lines()
        return posted

    def _auto_create_maintenance_cost_lines(self):
        """Crear cost lines automáticamente para líneas con analítica de Mantenimiento."""
        CostLine = self.env['maintenance.equipment.cost.line']
        maint_account = self.env.ref(
            'maintenance_purchase_link.analytic_account_mantenimiento',
            raise_if_not_found=False,
        )
        if not maint_account:
            return

        maint_key = str(maint_account.id)

        for move in self.filtered(lambda m: m.move_type == 'in_invoice'):
            for ml in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                distribution = ml.analytic_distribution or {}
                if maint_key not in distribution:
                    continue

                # Solo crear si no existe ya una cost line para esta línea
                existing = CostLine.search([
                    ('move_line_id', '=', ml.id),
                ], limit=1)
                if existing:
                    continue

                CostLine.create({
                    'move_line_id': ml.id,
                    # Sin equipo ni OT — se asignan después desde mantenimiento
                })

    def _propagate_equipment_to_lines(self):
        """Propagar equipos a cost lines. Solo agrega nuevos, nunca borra ni sobreescribe."""
        CostLine = self.env['maintenance.equipment.cost.line']
        for move in self:
            product_lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                continue

            self.env.cr.execute("""
                SELECT equipment_id, percentage
                FROM maintenance_invoice_equipment
                WHERE move_id = %s
            """, (move.id,))
            eq_rows = self.env.cr.fetchall()

            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])
            existing_keys = {
                (cl.move_line_id.id, cl.equipment_id.id)
                for cl in existing
            }

            vals_list = []
            for eq_id, percentage in eq_rows:
                for ml in product_lines:
                    if (ml.id, eq_id) not in existing_keys:
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
