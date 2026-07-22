from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    equipment_cost_line_ids = fields.One2many(
        'maintenance.equipment.cost.line',
        'move_line_id',
        string='Asignación de equipos',
    )
    maintenance_equipment_ids = fields.Many2many(
        'maintenance.equipment',
        compute='_compute_maintenance_equipment_ids',
        inverse='_inverse_maintenance_equipment_ids',
        search='_search_maintenance_equipment_ids',
        string='Equipos de mantenimiento',
    )
    maintenance_request_ids = fields.Many2many(
        'maintenance.request',
        'account_move_line_maintenance_request_rel',
        'move_line_id',
        'request_id',
        string='Órdenes de trabajo',
    )

    @api.depends('equipment_cost_line_ids.equipment_id')
    def _compute_maintenance_equipment_ids(self):
        for line in self:
            line.maintenance_equipment_ids = line.equipment_cost_line_ids.equipment_id

    def _inverse_maintenance_equipment_ids(self):
        CostLine = self.env['maintenance.equipment.cost.line']
        for line in self:
            current = line.equipment_cost_line_ids.equipment_id
            new = line.maintenance_equipment_ids
            to_add = new - current
            to_remove = current - new
            for eq in to_add:
                CostLine.create({
                    'move_line_id': line.id,
                    'equipment_id': eq.id,
                    'percentage': 100.0,
                })
            line.equipment_cost_line_ids.filtered(
                lambda cl: cl.equipment_id in to_remove
            ).unlink()

    def _search_maintenance_equipment_ids(self, operator, value):
        cost_lines = self.env['maintenance.equipment.cost.line'].search([
            ('equipment_id', operator, value),
        ])
        return [('id', 'in', cost_lines.mapped('move_line_id').ids)]

    @api.constrains('equipment_cost_line_ids', 'maintenance_request_ids', 'analytic_distribution')
    def _check_maintenance_analytic(self):
        """No permitir asociar equipo/OT si la línea no tiene Unidad de negocio = Maquinaria."""
        # Una cuenta "Maquinaria" por compañía: aceptar cualquiera (sudo por
        # las reglas multi-compañía). Las claves pueden ser compuestas
        # ("16,45") cuando la línea combina varios planes analíticos.
        maquinaria_keys = {
            str(a.id) for a in self.env['account.analytic.account'].sudo().search([
                ('name', '=', 'Maquinaria'),
                ('plan_id.name', '=', 'Unidad de negocio'),
            ])
        }
        if not maquinaria_keys:
            return
        for line in self:
            if not line.equipment_cost_line_ids and not line.maintenance_request_ids:
                continue
            distribution = line.analytic_distribution or {}
            if not any(maquinaria_keys & set(k.split(',')) for k in distribution):
                raise ValidationError(_(
                    'Solo puede asociar equipos u órdenes de trabajo a líneas '
                    'con Unidad de negocio = "Maquinaria".'
                ))
