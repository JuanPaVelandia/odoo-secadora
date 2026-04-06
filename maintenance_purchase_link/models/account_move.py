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

            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])
            existing.with_context(skip_invoice_sync=True).unlink()

            vals_list = []
            for eq_line in move.maintenance_equipment_line_ids:
                for ml in product_lines:
                    vals = {
                        'move_line_id': ml.id,
                        'equipment_id': eq_line.equipment_id.id,
                        'percentage': eq_line.percentage,
                    }
                    if eq_line.request_id:
                        vals['request_id'] = eq_line.request_id.id
                    vals_list.append(vals)
            if vals_list:
                CostLine.with_context(skip_invoice_sync=True).create(vals_list)

    def action_sync_from_cost_lines(self):
        """Botón manual para sincronizar pestaña desde cost lines."""
        InvoiceEquipment = self.env['maintenance.invoice.equipment']
        for move in self:
            cost_lines = self.env['maintenance.equipment.cost.line'].search([
                ('move_id', '=', move.id),
            ])

            equipment_map = {}
            for cl in cost_lines:
                if cl.equipment_id.id not in equipment_map:
                    equipment_map[cl.equipment_id.id] = {
                        'equipment_id': cl.equipment_id.id,
                        'percentage': cl.percentage,
                        'request_id': cl.request_id.id if cl.request_id else False,
                    }

            # Borrar directamente por SQL para no disparar writes del ORM
            existing_ids = InvoiceEquipment.search([('move_id', '=', move.id)]).ids
            if existing_ids:
                self.env.cr.execute(
                    "DELETE FROM maintenance_invoice_equipment WHERE id IN %s",
                    (tuple(existing_ids),)
                )
                InvoiceEquipment.invalidate_model()

            for data in equipment_map.values():
                self.env.cr.execute(
                    """INSERT INTO maintenance_invoice_equipment
                       (move_id, equipment_id, percentage, request_id,
                        create_uid, create_date, write_uid, write_date)
                       VALUES (%s, %s, %s, %s, %s, NOW(), %s, NOW())""",
                    (move.id, data['equipment_id'], data['percentage'],
                     data['request_id'] or None,
                     self.env.uid, self.env.uid)
                )
            InvoiceEquipment.invalidate_model()

    def write(self, vals):
        res = super().write(vals)
        if 'maintenance_equipment_line_ids' in vals:
            self._propagate_equipment_to_lines()
        return res
