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
    is_maintenance_line = fields.Boolean(
        string='Es línea de mantenimiento',
        compute='_compute_is_maintenance_line',
        search='_search_is_maintenance_line',
        help='Indica si la línea tiene distribución analítica de Mantenimiento.',
    )

    @api.depends('analytic_distribution')
    def _compute_is_maintenance_line(self):
        maint_account = self.env.ref(
            'maintenance_purchase_link.analytic_account_mantenimiento',
            raise_if_not_found=False,
        )
        maint_key = str(maint_account.id) if maint_account else False
        for line in self:
            if maint_key and line.analytic_distribution:
                line.is_maintenance_line = maint_key in line.analytic_distribution
            else:
                line.is_maintenance_line = False

    def _search_is_maintenance_line(self, operator, value):
        maint_account = self.env.ref(
            'maintenance_purchase_link.analytic_account_mantenimiento',
            raise_if_not_found=False,
        )
        if not maint_account:
            return [('id', '=', False)]
        maint_key = str(maint_account.id)
        # analytic_distribution es un campo JSON; buscar las líneas que lo contienen
        positive = (operator == '=' and value) or (operator == '!=' and not value)
        if positive:
            self.env.cr.execute(
                "SELECT id FROM account_move_line WHERE analytic_distribution ? %s",
                [maint_key],
            )
        else:
            self.env.cr.execute(
                "SELECT id FROM account_move_line WHERE analytic_distribution IS NULL OR NOT analytic_distribution ? %s",
                [maint_key],
            )
        ids = [r[0] for r in self.env.cr.fetchall()]
        return [('id', 'in', ids)]

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
