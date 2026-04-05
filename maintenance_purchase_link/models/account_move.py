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
            existing.with_context(skip_invoice_sync=True).unlink()

            # Crear nuevas asignaciones desde la plantilla de factura
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

    def _sync_equipment_from_cost_lines(self):
        """Sincronizar pestaña Mantenimiento desde cost lines (sentido inverso)."""
        InvoiceEquipment = self.env['maintenance.invoice.equipment']
        for move in self.with_context(skip_propagate=True):
            # Obtener resumen de equipos desde cost lines
            cost_lines = self.env['maintenance.equipment.cost.line'].search([
                ('move_id', '=', move.id),
            ])

            # Agrupar por equipo: tomar el porcentaje y OT del primer cost line
            equipment_map = {}
            for cl in cost_lines:
                if cl.equipment_id.id not in equipment_map:
                    equipment_map[cl.equipment_id.id] = {
                        'equipment_id': cl.equipment_id.id,
                        'percentage': cl.percentage,
                        'request_id': cl.request_id.id if cl.request_id else False,
                    }

            # Eliminar y recrear las líneas de la pestaña (sin disparar propagación)
            move.maintenance_equipment_line_ids.unlink()
            vals_list = []
            for data in equipment_map.values():
                vals_list.append({
                    'move_id': move.id,
                    'equipment_id': data['equipment_id'],
                    'percentage': data['percentage'],
                    'request_id': data['request_id'],
                })
            if vals_list:
                InvoiceEquipment.create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'maintenance_equipment_line_ids' in vals and \
                not self.env.context.get('skip_propagate'):
            self._propagate_equipment_to_lines()
        return res
