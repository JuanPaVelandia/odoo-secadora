from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    maintenance_equipment_line_ids = fields.One2many(
        'maintenance.invoice.equipment',
        'move_id',
        string='Equipos de mantenimiento',
    )
    maintenance_cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'move_id',
        string='Costos de mantenimiento',
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

            # Obtener asignaciones deseadas desde la plantilla
            desired = {}
            for eq_line in move.maintenance_equipment_line_ids:
                desired[eq_line.equipment_id.id] = {
                    'percentage': eq_line.percentage,
                    'request_id': eq_line.request_id.id if eq_line.request_id else False,
                }

            # Obtener cost lines existentes
            existing = CostLine.search([
                ('move_line_id', 'in', product_lines.ids),
            ])

            # Equipos existentes en cost lines
            existing_equipment_ids = set(existing.mapped('equipment_id').ids)
            desired_equipment_ids = set(desired.keys())

            # Eliminar cost lines de equipos que ya no están en la plantilla
            to_remove = existing.filtered(
                lambda cl: cl.equipment_id.id not in desired_equipment_ids
            )
            to_remove.unlink()

            # Actualizar cost lines existentes (porcentaje y OT)
            for cl in existing.filtered(lambda c: c.equipment_id.id in desired_equipment_ids):
                data = desired[cl.equipment_id.id]
                update_vals = {}
                if cl.percentage != data['percentage']:
                    update_vals['percentage'] = data['percentage']
                if (cl.request_id.id or False) != data['request_id']:
                    update_vals['request_id'] = data['request_id']
                if update_vals:
                    cl.write(update_vals)

            # Crear cost lines para equipos nuevos
            new_equipment_ids = desired_equipment_ids - existing_equipment_ids
            vals_list = []
            for eq_id in new_equipment_ids:
                data = desired[eq_id]
                for ml in product_lines:
                    vals_list.append({
                        'move_line_id': ml.id,
                        'equipment_id': eq_id,
                        'percentage': data['percentage'],
                        'request_id': data['request_id'],
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
        # Quitar maintenance_cost_line_ids del write para evitar que
        # el ORM sobreescriba cost lines con datos viejos del formulario
        vals.pop('maintenance_cost_line_ids', None)
        res = super().write(vals)
        if 'maintenance_equipment_line_ids' in vals:
            self._propagate_equipment_to_lines()
        return res
