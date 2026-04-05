from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MaintenanceTaskPlan(models.Model):
    _name = 'maintenance.task.plan'
    _description = 'Plan de Tareas de Mantenimiento'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    description = fields.Text(
        string='Descripción / Instrucciones',
    )
    counter_type_id = fields.Many2one(
        'maintenance.counter.type',
        string='Tipo de contador',
        required=True,
    )
    counter_unit = fields.Char(
        related='counter_type_id.unit',
        string='Unidad',
    )
    interval = fields.Float(
        string='Intervalo',
        required=True,
    )
    category_id = fields.Many2one(
        'maintenance.equipment.category',
        string='Categoría de equipo',
    )
    equipment_ids = fields.Many2many(
        'maintenance.equipment',
        'maintenance_task_plan_equipment_rel',
        'plan_id',
        'equipment_id',
        string='Equipos',
    )
    task_line_ids = fields.One2many(
        'maintenance.task.plan.line',
        'plan_id',
        string='Líneas de seguimiento',
    )
    active = fields.Boolean(
        default=True,
    )
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsable',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )
    equipment_count = fields.Integer(
        compute='_compute_equipment_count',
        string='Cantidad de equipos',
    )
    overdue_count = fields.Integer(
        compute='_compute_overdue_count',
        string='Vencidas',
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_task_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'equipment_ids' in vals:
            self._sync_task_lines()
        return res

    def _sync_task_lines(self):
        """Sincronizar líneas de seguimiento con lista de equipos."""
        PlanLine = self.env['maintenance.task.plan.line']
        for plan in self:
            existing_equipments = plan.task_line_ids.mapped('equipment_id')
            new_equipments = plan.equipment_ids - existing_equipments
            removed_equipments = existing_equipments - plan.equipment_ids

            plan.task_line_ids.filtered(
                lambda l: l.equipment_id in removed_equipments
            ).unlink()

            vals_list = []
            for eq in new_equipments:
                vals_list.append({
                    'plan_id': plan.id,
                    'equipment_id': eq.id,
                    'last_counter_reading': 0.0,
                    'current_counter_reading': 0.0,
                })
            if vals_list:
                PlanLine.create(vals_list)

    def action_generate_requests(self):
        """Botón manual para generar OTs ahora."""
        self.ensure_one()
        created = self.task_line_ids._generate_requests()
        if created:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('OTs generadas'),
                    'message': _('%d orden(es) de trabajo creada(s).', len(created)),
                    'type': 'success',
                    'sticky': False,
                },
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sin OTs'),
                'message': _('Ningún equipo ha alcanzado el umbral del contador.'),
                'type': 'warning',
                'sticky': False,
            },
        }
