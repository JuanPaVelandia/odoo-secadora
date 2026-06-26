# -*- coding: utf-8 -*-
"""
Modelo hr.contract.change.wage - Historial de cambios salariales.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrContractChangeWage(models.Model):
    _name = 'hr.contract.change.wage'
    _description = 'Cambios salario básico'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char('Referencia', compute='_compute_name', store=True)
    date_start = fields.Date('Fecha inicial', required=True, tracking=True)
    wage = fields.Float('Salario basico', help='Seguimiento de los cambios en el salario basico', tracking=True)
    contract_id = fields.Many2one('hr.contract', 'Contrato', required=True, ondelete='cascade')
    employee_id = fields.Many2one(related='contract_id.employee_id', store=True, string='Empleado')

    # Campos editables para capturar el estado completo en el momento del cambio
    job_id = fields.Many2one('hr.job', string='Cargo', ondelete='set null', tracking=True,
                             help='Cargo del empleado en el momento del cambio')
    department_id = fields.Many2one('hr.department', string='Departamento', ondelete='set null', tracking=True,
                                    help='Departamento en el momento del cambio')
    tipo_cotizante_id = fields.Many2one('hr.tipo.cotizante', string='Tipo Cotizante PILA', tracking=True,
                                        help='Tipo de cotizante PILA en el momento del cambio')
    tipo_coti_id = fields.Many2one('hr.tipo.cotizante', string='Tipo Cot. Empleado', tracking=True,
                                   help='Tipo de cotizante del empleado en el momento del cambio')
    subtipo_coti_id = fields.Many2one('hr.subtipo.cotizante', string='Subtipo Cotizante', tracking=True,
                                      help='Subtipo de cotizante en el momento del cambio')

    # Campos related (solo lectura) para referencia
    company_id = fields.Many2one(
        related='contract_id.company_id',
        string='Empresa',
        store=True,
        readonly=True,
    )
    contract_category = fields.Selection(
        related='contract_id.contract_category',
        string='Categoria Contrato',
        store=True,
        readonly=True,
    )

    reason = fields.Selection([
        ('start', 'Inicio de contrato'),
        ('annual_update', 'Actualización anual'),
        ('adjustment', 'Ajuste general'),
        ('legal', 'Ajuste por normativa legal'),
        ('collective', 'Negociación colectiva'),
        ('business_decision', 'Decisión empresarial'),
        ('performance', 'Desempeño'),
        ('promotion', 'Promoción'),
        ('market_adjustment', 'Ajuste al mercado'),
        ('restructuring', 'Reestructuración'),
        ('other', 'Otro')
    ], string='Motivo del cambio', tracking=True)
    other_reason = fields.Char('Otro motivo')

    # Origen del cambio salarial
    origin_type = fields.Selection([
        ('manual', 'Manual'),
        ('salary_increase', 'Proceso Aumento Masivo'),
        ('import', 'Importacion'),
        ('system', 'Sistema'),
    ], string='Tipo de Origen', default='manual', tracking=True)

    salary_increase_id = fields.Many2one(
        'hr.salary.increase',
        string='Proceso de Aumento',
        help='Proceso de aumento salarial masivo que origino este cambio'
    )

    apply_retroactive = fields.Boolean('Aplicar retroactivo', default=False)
    retroactive_date = fields.Date('Fecha desde retroactivo')

    # Campo de estado para flujo de trabajo
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Aprobado'),
    ], string='Estado', default='draft', tracking=True, copy=False)

    wage_old = fields.Float('Salario anterior', compute='_compute_wage_old', store=True)
    difference = fields.Float('Diferencia', compute='_compute_difference', store=True)
    difference_percentage = fields.Float('Porcentaje diferencia', compute='_compute_difference',
                                       store=True, digits=(16, 4))

    _change_wage_uniq = models.Constraint('unique(contract_id, date_start, wage, job_id)',
                                          'Ya existe un cambio de salario igual a este')

    @api.model
    def _auto_init(self):
        """Normalize legacy varchar refs before ORM applies many2one FK."""
        self.env.cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'hr_contract_change_wage'
              AND column_name = 'salary_increase_id'
        """)
        row = self.env.cr.fetchone()
        if row and row[0] in ('character varying', 'text'):
            self.env.cr.execute("""
                ALTER TABLE hr_contract_change_wage
                DROP CONSTRAINT IF EXISTS hr_contract_change_wage_salary_increase_id_fkey
            """)
            self.env.cr.execute("""
                ALTER TABLE hr_contract_change_wage
                ALTER COLUMN salary_increase_id TYPE integer
                USING (
                    CASE
                        WHEN salary_increase_id IS NULL OR salary_increase_id = '' THEN NULL
                        WHEN salary_increase_id ~ '^[0-9]+$' THEN salary_increase_id::integer
                        WHEN salary_increase_id ~ '^hr\\.salary\\.increase,[0-9]+$' THEN split_part(salary_increase_id, ',', 2)::integer
                        ELSE NULL
                    END
                )
            """)
            self.env.cr.execute("""
                UPDATE hr_contract_change_wage cw
                SET salary_increase_id = NULL
                WHERE salary_increase_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM hr_salary_increase si WHERE si.id = cw.salary_increase_id
                  )
            """)
        return super()._auto_init()

    def action_approve(self):
        """Aprobar el cambio de salario y actualizar el contrato"""
        for record in self:
            record.write({'state': 'approved'})
            # Actualizar el salario en el contrato si es el cambio mas reciente
            last_change = self.search([
                ('contract_id', '=', record.contract_id.id),
                ('state', '=', 'approved')
            ], order='date_start desc', limit=1)
            if last_change.id == record.id:
                record.contract_id.write({
                    'wage': record.wage,
                    'date_last_wage': record.date_start,
                    'wage_old': record.wage_old,
                })
                if record.job_id:
                    record.contract_id.write({'job_id': record.job_id.id})
            record.message_post(body=_("Cambio salarial aprobado. Nuevo salario: %s") % "{:,.0f}".format(record.wage))
        return True

    def action_draft(self):
        """Volver el cambio a borrador"""
        for record in self:
            record.write({'state': 'draft'})
            record.message_post(body=_("Cambio salarial devuelto a borrador"))
        return True

    def action_print(self):
        """Imprimir el reporte de cambio salarial"""
        return self.env.ref('lavish_hr_employee.action_report_change_wage').report_action(self)

    def action_send_email(self):
        """Enviar notificacion por email"""
        self.ensure_one()
        template = self.env.ref('lavish_hr_employee.email_template_change_wage', raise_if_not_found=False)
        if template:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Enviar Notificacion'),
                'res_model': 'mail.compose.message',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_model': 'hr.contract.change.wage',
                    'default_res_ids': self.ids,
                    'default_template_id': template.id,
                    'default_composition_mode': 'comment',
                    'force_email': True,
                },
            }
        else:
            raise UserError(_("No se encontro la plantilla de correo. Por favor configure la plantilla 'email_template_change_wage'."))
        return True

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        """Llena automaticamente los campos con valores actuales del contrato y empleado"""
        if self.contract_id:
            self.job_id = self.contract_id.job_id
            self.department_id = self.contract_id.department_id
            self.tipo_cotizante_id = self.contract_id.tipo_cotizante_id
            # Valores del empleado
            if self.contract_id.employee_id:
                self.tipo_coti_id = self.contract_id.employee_id.tipo_coti_id
                self.subtipo_coti_id = self.contract_id.employee_id.subtipo_coti_id

    @api.depends('contract_id', 'date_start', 'wage')
    def _compute_name(self):
        for record in self:
            if record.contract_id and record.date_start:
                employee_name = record.contract_id.employee_id.name or 'Sin empleado'
                date_str = record.date_start.strftime('%d/%m/%Y') if record.date_start else ''
                record.name = f"{employee_name} - {date_str} - ${record.wage:,.0f}"
            else:
                record.name = 'Nuevo cambio salarial'

    @api.depends('contract_id', 'date_start')
    def _compute_wage_old(self):
        for record in self:
            if record.contract_id and record.date_start:
                # Buscar cambio salarial anterior
                prev_change = self.search([
                    ('contract_id', '=', record.contract_id.id),
                    ('date_start', '<', record.date_start)
                ], order='date_start desc', limit=1)
                
                if prev_change:
                    record.wage_old = prev_change.wage
                else:
                    # Si no hay cambios previos, usar el salario actual
                    record.wage_old = record.contract_id.wage
            else:
                record.wage_old = 0
    
    @api.depends('wage', 'wage_old')
    def _compute_difference(self):
        for record in self:
            record.difference = record.wage - record.wage_old
            record.difference_percentage = (record.difference / record.wage_old * 100) if record.wage_old else 0.0
    _change_wage_uniq = models.Constraint('unique(contract_id, date_start, wage, job_id)', 'Ya existe un cambio de salario igual a este')
