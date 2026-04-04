from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    maintenance_equipment_ids = fields.Many2many(
        'maintenance.equipment',
        'account_move_line_maintenance_equipment_rel',
        'move_line_id',
        'equipment_id',
        string='Equipos de mantenimiento',
    )
    maintenance_request_ids = fields.Many2many(
        'maintenance.request',
        'account_move_line_maintenance_request_rel',
        'move_line_id',
        'request_id',
        string='Órdenes de trabajo',
    )
    @api.constrains('maintenance_equipment_ids', 'maintenance_request_ids', 'analytic_distribution')
    def _check_maintenance_analytic(self):
        """No permitir asociar equipo/OT si la línea no tiene analítica de Mantenimiento."""
        maint_account = self.env.ref(
            'maintenance_purchase_link.analytic_account_mantenimiento',
            raise_if_not_found=False,
        )
        if not maint_account:
            return
        maint_key = str(maint_account.id)
        for line in self:
            if not line.maintenance_equipment_ids and not line.maintenance_request_ids:
                continue
            distribution = line.analytic_distribution or {}
            if maint_key not in distribution:
                raise ValidationError(_(
                    'Solo puede asociar equipos u órdenes de trabajo a líneas '
                    'con distribución analítica de "Mantenimiento".'
                ))
