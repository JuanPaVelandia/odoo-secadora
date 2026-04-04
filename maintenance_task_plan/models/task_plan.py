from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MaintenanceTaskPlan(models.Model):
    _name = 'maintenance.task.plan'
    _description = 'Maintenance Task Plan'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    description = fields.Text(
        string='Description',
    )
    counter_type_id = fields.Many2one(
        'maintenance.counter.type',
        string='Counter Type',
        required=True,
    )
    counter_unit = fields.Char(
        related='counter_type_id.unit',
        string='Counter Unit',
    )
    interval = fields.Float(
        string='Interval',
        required=True,
    )
    category_id = fields.Many2one(
        'maintenance.equipment.category',
        string='Equipment Category',
    )
    equipment_ids = fields.Many2many(
        'maintenance.equipment',
        'maintenance_task_plan_equipment_rel',
        'plan_id',
        'equipment_id',
        string='Equipment',
    )
    task_line_ids = fields.One2many(
        'maintenance.task.plan.line',
        'plan_id',
        string='Tracking Lines',
    )
    active = fields.Boolean(
        default=True,
    )
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsible',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    equipment_count = fields.Integer(
        compute='_compute_equipment_count',
        string='Equipment Count',
    )
    overdue_count = fields.Integer(
        compute='_compute_overdue_count',
        string='Overdue Count',
    )

    @api.depends('equipment_ids')
    def _compute_equipment_count(self):
        for plan in self:
            plan.equipment_count = len(plan.equipment_ids)

    @api.depends('task_line_ids.state')
    def _compute_overdue_count(self):
        for plan in self:
            plan.overdue_count = len(
                plan.task_line_ids.filtered(lambda l: l.state == 'overdue')
            )

    @api.onchange('equipment_ids')
    def _onchange_equipment_ids(self):
        """Create/remove tracking lines when equipment changes."""
        existing_equipments = self.task_line_ids.mapped('equipment_id')
        new_equipments = self.equipment_ids - existing_equipments
        removed_equipments = existing_equipments - self.equipment_ids

        # Remove lines for removed equipment
        lines_to_remove = self.task_line_ids.filtered(
            lambda l: l.equipment_id in removed_equipments
        )
        for line in lines_to_remove:
            self.task_line_ids -= line

        # Add lines for new equipment
        for eq in new_equipments:
            self.task_line_ids += self.task_line_ids.new({
                'plan_id': self.id,
                'equipment_id': eq.id,
                'last_counter_reading': 0.0,
                'current_counter_reading': 0.0,
            })

    def write(self, vals):
        res = super().write(vals)
        if 'equipment_ids' in vals:
            self._sync_task_lines()
        return res

    def _sync_task_lines(self):
        """Synchronize task lines with equipment list."""
        for plan in self:
            existing_equipments = plan.task_line_ids.mapped('equipment_id')
            new_equipments = plan.equipment_ids - existing_equipments
            removed_equipments = existing_equipments - plan.equipment_ids

            # Remove lines for removed equipment
            plan.task_line_ids.filtered(
                lambda l: l.equipment_id in removed_equipments
            ).unlink()

            # Add lines for new equipment
            vals_list = []
            for eq in new_equipments:
                vals_list.append({
                    'plan_id': plan.id,
                    'equipment_id': eq.id,
                    'last_counter_reading': 0.0,
                    'current_counter_reading': 0.0,
                })
            if vals_list:
                self.env['maintenance.task.plan.line'].create(vals_list)

    def action_generate_requests(self):
        """Manual button to generate work orders now."""
        self.ensure_one()
        created = self.task_line_ids._generate_requests()
        if created:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Work Orders Generated'),
                    'message': _('%d work order(s) created.', len(created)),
                    'type': 'success',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('No Work Orders'),
                'message': _('No equipment has reached its counter threshold.'),
                'type': 'warning',
                'sticky': False,
            },
        }
