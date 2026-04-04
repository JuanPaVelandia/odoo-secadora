from odoo import api, fields, models, _


class MaintenanceTaskPlanLine(models.Model):
    _name = 'maintenance.task.plan.line'
    _description = 'Task Plan Tracking Line'
    _order = 'state desc, remaining'
    _rec_name = 'display_name'

    plan_id = fields.Many2one(
        'maintenance.task.plan',
        string='Task Plan',
        required=True,
        ondelete='cascade',
    )
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Equipment',
        required=True,
    )
    counter_type_id = fields.Many2one(
        related='plan_id.counter_type_id',
        store=True,
        string='Counter Type',
    )
    counter_unit = fields.Char(
        related='plan_id.counter_type_id.unit',
        string='Unit',
    )
    interval = fields.Float(
        related='plan_id.interval',
        string='Interval',
    )
    last_counter_reading = fields.Float(
        string='Last Reading',
    )
    next_counter_reading = fields.Float(
        string='Next Reading',
        compute='_compute_next_counter_reading',
        store=True,
    )
    current_counter_reading = fields.Float(
        string='Current Reading',
    )
    remaining = fields.Float(
        string='Remaining',
        compute='_compute_remaining',
        store=True,
    )
    progress_percentage = fields.Float(
        string='Progress (%)',
        compute='_compute_remaining',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('ok', 'OK'),
            ('warning', 'Upcoming'),
            ('overdue', 'Overdue'),
        ],
        string='State',
        compute='_compute_remaining',
        store=True,
    )
    last_request_id = fields.Many2one(
        'maintenance.request',
        string='Last Work Order',
    )
    request_count = fields.Integer(
        string='Work Order Count',
        compute='_compute_request_count',
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        store=True,
    )

    @api.depends('display_name')
    def _compute_display_name(self):
        for line in self:
            line.display_name = f"{line.plan_id.name} - {line.equipment_id.name}"

    @api.depends('last_counter_reading', 'plan_id.interval')
    def _compute_next_counter_reading(self):
        for line in self:
            line.next_counter_reading = line.last_counter_reading + line.plan_id.interval

    @api.depends('next_counter_reading', 'current_counter_reading', 'plan_id.interval')
    def _compute_remaining(self):
        for line in self:
            interval = line.plan_id.interval or 1.0
            line.remaining = line.next_counter_reading - line.current_counter_reading
            elapsed = line.current_counter_reading - line.last_counter_reading
            line.progress_percentage = min((elapsed / interval) * 100.0, 100.0) if interval else 0.0

            if line.remaining <= 0:
                line.state = 'overdue'
            elif line.remaining <= (interval * 0.10):
                line.state = 'warning'
            else:
                line.state = 'ok'

    def _compute_request_count(self):
        Request = self.env['maintenance.request']
        for line in self:
            line.request_count = Request.search_count([
                ('task_plan_line_id', '=', line.id),
            ])

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Work Orders'),
            'res_model': 'maintenance.request',
            'view_mode': 'list,form',
            'domain': [('task_plan_line_id', '=', self.id)],
        }

    def _generate_requests(self):
        """Generate work orders for lines that have reached their threshold."""
        Request = self.env['maintenance.request']
        created = self.env['maintenance.request']

        for line in self:
            if line.current_counter_reading < line.next_counter_reading:
                continue

            # Check if there is already an open request for this line
            open_request = Request.search([
                ('task_plan_line_id', '=', line.id),
                ('stage_id.done', '=', False),
            ], limit=1)
            if open_request:
                continue

            request = Request.create({
                'name': f"{line.plan_id.name} - {line.equipment_id.name}",
                'equipment_id': line.equipment_id.id,
                'task_plan_id': line.plan_id.id,
                'task_plan_line_id': line.id,
                'user_id': line.plan_id.responsible_user_id.id or False,
                'category_id': line.plan_id.category_id.id or False,
                'description': line.plan_id.description or '',
            })
            line.last_request_id = request.id
            created |= request

        return created

    @api.model
    def _cron_generate_task_plan_requests(self):
        """Cron job: generate work orders for all overdue lines."""
        lines = self.search([
            ('state', '=', 'overdue'),
            ('plan_id.active', '=', True),
        ])
        lines._generate_requests()
