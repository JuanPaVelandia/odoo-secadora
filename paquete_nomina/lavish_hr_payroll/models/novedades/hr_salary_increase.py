# -*- coding: utf-8 -*-
"""
Proceso de Aumento Salarial Masivo
==================================
Modelo para gestionar aumentos de salario de forma masiva.

Funcionalidades:
- Carga automatica de empleados con contrato activo
- Aumento por porcentaje o valor fijo
- Filtros: salario minimo, departamento
- Redondeo configurable (centenas, miles, etc)
- Seleccion individual o masiva
- Historial de cambios via chatter

Flujo:
1. Crear proceso (draft)
2. Configurar tipo de aumento y porcentaje/valor
3. Cargar empleados (aplica filtros)
4. Revisar y ajustar salarios individuales si es necesario
5. Confirmar (confirmed)
6. Aplicar cambios a contratos (done)
"""

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class HrSalaryIncrease(models.Model):
    _name = 'hr.salary.increase'
    _description = 'Proceso de Aumento Salarial'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        'Nombre',
        required=True,
        default=lambda self: f'Aumento Salarial {date.today().year}',
        tracking=True,
        help='Nombre descriptivo del proceso de aumento'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        default=lambda self: self.env.company,
        required=True,
        help='Empresa para la cual se aplica el aumento'
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('done', 'Aplicado'),
        ('cancelled', 'Cancelado'),
    ], default='draft', string='Estado', tracking=True)

    effective_date = fields.Date(
        'Fecha Efectiva',
        default=fields.Date.today,
        required=True,
        tracking=True,
        help='Fecha a partir de la cual aplica el aumento'
    )

    # Configuracion del aumento
    increase_type = fields.Selection([
        ('percentage', 'Porcentaje'),
        ('fixed', 'Valor Fijo'),
        ('increment', 'Incremento Fijo'),
    ], default='percentage', string='Tipo de Aumento', required=True,
       help='Porcentaje: Aumenta un % del salario actual. Valor Fijo: Establece el salario en un monto especifico. Incremento Fijo: Suma un monto fijo al salario actual.')

    increase_percentage = fields.Float(
        'Porcentaje (%)',
        digits=(8, 4),
        default=0.0,
        help='Porcentaje de aumento a aplicar (ej: 10.5 para 10.5%)'
    )

    increase_fixed = fields.Monetary(
        'Monto Fijo',
        currency_field='currency_id',
        help='Para Valor Fijo: Nuevo salario a establecer. Para Incremento Fijo: Monto a sumar al salario actual.'
    )

    round_to = fields.Selection([
        ('none', 'Sin Redondeo'),
        ('100', 'Centenas'),
        ('1000', 'Miles'),
        ('10000', 'Decenas de Miles'),
    ], default='1000', string='Redondear A',
       help='Redondea el nuevo salario al multiplo mas cercano')

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id'
    )

    # =========================================================================
    # FILTROS DE EMPLEADOS
    # =========================================================================
    filter_min_wage = fields.Monetary(
        'Salario Minimo Vigente',
        currency_field='currency_id',
        help='Solo incluir empleados con salario menor o igual a este valor. Dejar en 0 para incluir todos.'
    )

    filter_exact_min_wage = fields.Boolean(
        'Solo Salario Minimo Exacto',
        default=False,
        help='Si esta marcado, solo incluye empleados con salario exactamente igual al valor del filtro (con tolerancia de $1,000)'
    )

    filter_department_ids = fields.Many2many(
        'hr.department',
        string='Departamentos',
        help='Filtrar por departamentos especificos. Dejar vacio para incluir todos.'
    )

    filter_job_ids = fields.Many2many(
        'hr.job',
        string='Cargos',
        help='Filtrar por cargos especificos. Dejar vacio para incluir todos.'
    )

    # Lineas de empleados
    line_ids = fields.One2many(
        'hr.salary.increase.line',
        'increase_id',
        string='Empleados'
    )

    # Estadisticas
    total_employees = fields.Integer('Total Empleados', compute='_compute_stats')
    selected_count = fields.Integer('Seleccionados', compute='_compute_stats')
    applied_count = fields.Integer('Aplicados', compute='_compute_stats')
    total_increase = fields.Monetary(
        'Incremento Total Mensual',
        currency_field='currency_id',
        compute='_compute_stats'
    )

    notes = fields.Text('Notas')
    send_notification = fields.Boolean(
        'Enviar Notificacion',
        default=True,
        help='Enviar correo electronico a los empleados notificando el aumento'
    )

    # Cambios salariales generados
    change_wage_ids = fields.One2many(
        'hr.contract.change.wage',
        'salary_increase_id',
        string='Cambios Salariales Generados',
        readonly=True
    )

    @api.depends('line_ids', 'line_ids.selected', 'line_ids.applied', 'line_ids.increase_amount')
    def _compute_stats(self):
        for rec in self:
            rec.total_employees = len(rec.line_ids)
            rec.selected_count = len(rec.line_ids.filtered('selected'))
            rec.applied_count = len(rec.line_ids.filtered('applied'))
            rec.total_increase = sum(rec.line_ids.filtered('selected').mapped('increase_amount'))

    # =========================================================================
    # METODOS DE CALCULO
    # =========================================================================

    def _calculate_new_wage(self, current_wage):
        """
        Calcula el nuevo salario basado en la configuracion del proceso.
        Similar al patron de hr_payroll para calculos centralizados.

        :param current_wage: Salario actual del empleado
        :return: Nuevo salario calculado y redondeado
        """
        self.ensure_one()

        if not current_wage:
            return 0

        # Calcular nuevo salario segun tipo de aumento
        if self.increase_type == 'percentage':
            new_wage = current_wage * (1 + self.increase_percentage)
        elif self.increase_type == 'fixed':
            new_wage = self.increase_fixed
        else:  # increment
            new_wage = current_wage + self.increase_fixed

        # Aplicar redondeo si esta configurado
        if self.round_to and self.round_to != 'none':
            factor = int(self.round_to)
            new_wage = round(new_wage / factor) * factor

        return new_wage

    # =========================================================================
    # ACCIONES
    # =========================================================================

    def action_load_employees(self):
        """
        Carga empleados con contrato activo aplicando filtros configurados.

        Filtros aplicados:
        - filter_min_wage: Solo salarios <= este valor (para ajuste de minimo)
        - filter_department_ids: Solo estos departamentos
        - filter_job_ids: Solo estos cargos
        """
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Solo puede cargar empleados en estado borrador'))

        self.line_ids.unlink()

        # Construir dominio base
        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'open'),
        ]

        # Aplicar filtro de salario minimo
        if self.filter_min_wage > 0:
            if self.filter_exact_min_wage:
                # Filtro exacto con tolerancia de $1,000
                tolerance = 1000
                domain.append(('wage', '>=', self.filter_min_wage - tolerance))
                domain.append(('wage', '<=', self.filter_min_wage + tolerance))
            else:
                domain.append(('wage', '<=', self.filter_min_wage))

        # Aplicar filtro de departamentos
        if self.filter_department_ids:
            domain.append(('department_id', 'in', self.filter_department_ids.ids))

        # Aplicar filtro de cargos
        if self.filter_job_ids:
            domain.append(('job_id', 'in', self.filter_job_ids.ids))

        contracts = self.env['hr.contract'].search(domain)

        if not contracts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin Resultados'),
                    'message': _('No se encontraron contratos con los filtros aplicados'),
                    'type': 'warning',
                }
            }

        # Generar los datos de las lineas - similar a hr_payroll._get_payslip_lines()
        # Incluimos todos los datos explicitamente, no dependemos de computed fields
        line_vals = []
        for contract in contracts:
            current_wage = contract.wage
            new_wage = self._calculate_new_wage(current_wage)

            line_vals.append({
                'increase_id': self.id,
                'employee_id': contract.employee_id.id,
                'contract_id': contract.id,
                'department_id': contract.department_id.id if contract.department_id else False,
                'job_id': contract.job_id.id if contract.job_id else False,
                'current_wage': current_wage,
                'new_wage': new_wage,
                'selected': True,
            })

        # Crear lineas directamente - como hr_payroll.compute_sheet()
        self.env['hr.salary.increase.line'].create(line_vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Empleados Cargados'),
                'message': _('Se cargaron %s empleados') % len(contracts),
                'type': 'success',
            }
        }

    def action_calculate(self):
        """Recalcula los nuevos salarios - fuerza recomputo de las lineas"""
        self.ensure_one()
        # Forzar recomputo de los campos computed
        self.line_ids._compute_from_contract()
        self.line_ids._compute_new_wage()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recalculado'),
                'message': _('Se recalcularon los salarios de %s empleados') % len(self.line_ids),
                'type': 'success',
            }
        }

    def action_confirm(self):
        """Confirma el proceso de aumento"""
        self.ensure_one()
        if not self.line_ids.filtered('selected'):
            raise UserError(_('Seleccione al menos un empleado'))
        self.state = 'confirmed'

    def action_apply(self):
        """Aplica el aumento a los empleados seleccionados"""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Debe confirmar primero el proceso'))

        selected = self.line_ids.filtered(lambda l: l.selected and not l.applied)
        if not selected:
            raise UserError(_('No hay empleados pendientes de aplicar'))

        ChangeWage = self.env['hr.contract.change.wage']

        for line in selected:
            # Crear registro de historial salarial
            ChangeWage.create({
                'contract_id': line.contract_id.id,
                'date_start': self.effective_date,
                'wage': line.new_wage,
                'job_id': line.job_id.id if line.job_id else False,
                'reason': 'annual_update' if self.increase_type == 'percentage' else 'adjustment',
                'origin_type': 'salary_increase',
                'salary_increase_id': self.id,
            })

            # Actualizar el salario del contrato
            line.contract_id.wage = line.new_wage
            line.applied = True

        self.state = 'done'
        self.message_post(
            body=_('Aumento aplicado a %s empleados. Incremento total mensual: %s %s') % (
                len(selected),
                '{:,.0f}'.format(self.total_increase),
                self.currency_id.symbol
            )
        )

        # Enviar notificaciones por correo
        if self.send_notification:
            self._send_increase_notifications(selected)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Aumento Aplicado'),
                'message': _('Se aplico el aumento a %s empleados') % len(selected),
                'type': 'success',
            }
        }

    def _send_increase_notifications(self, lines):
        """Envia correo de notificacion a cada empleado con su aumento"""
        template = self.env.ref('lavish_hr_payroll.mail_template_salary_increase', raise_if_not_found=False)
        if not template:
            _logger.warning('Template de correo para aumento salarial no encontrado')
            return

        sent_count = 0
        for line in lines:
            if line.employee_id.work_email:
                try:
                    template.send_mail(line.id, force_send=True)
                    sent_count += 1
                except Exception as e:
                    _logger.error(f'Error enviando correo a {line.employee_id.name}: {e}')

        if sent_count > 0:
            self.message_post(
                body=_('Se enviaron %s notificaciones por correo electronico') % sent_count
            )

    def action_cancel(self):
        """Cancela el proceso"""
        self.state = 'cancelled'

    def action_draft(self):
        """Vuelve a borrador"""
        self.state = 'draft'

    def action_select_all(self):
        """Selecciona todos"""
        self.line_ids.write({'selected': True})

    def action_deselect_all(self):
        """Deselecciona todos"""
        self.line_ids.write({'selected': False})


class HrSalaryIncreaseLine(models.Model):
    _name = 'hr.salary.increase.line'
    _description = 'Linea de Aumento Salarial'
    _order = 'department_id, current_wage'

    increase_id = fields.Many2one(
        'hr.salary.increase',
        string='Proceso',
        ondelete='cascade'
    )

    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    contract_id = fields.Many2one(
        'hr.contract',
        string='Contrato',
        compute='_compute_contract_id',
        store=True,
        readonly=False,
        help='Contrato activo del empleado'
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Departamento',
        compute='_compute_from_contract',
        store=True,
        readonly=False
    )
    job_id = fields.Many2one(
        'hr.job',
        string='Cargo',
        compute='_compute_from_contract',
        store=True,
        readonly=False
    )

    current_wage = fields.Monetary(
        'Salario Actual',
        currency_field='currency_id',
        compute='_compute_from_contract',
        store=True,
        readonly=False
    )
    new_wage = fields.Monetary(
        'Nuevo Salario',
        currency_field='currency_id',
        compute='_compute_new_wage',
        store=True,
        readonly=False
    )

    increase_amount = fields.Monetary(
        'Incremento',
        currency_field='currency_id',
        compute='_compute_increase',
        store=True
    )
    increase_pct = fields.Float(
        'Incremento %',
        compute='_compute_increase',
        store=True,
        digits=(5, 2)
    )

    currency_id = fields.Many2one('res.currency', related='increase_id.currency_id')

    selected = fields.Boolean('Seleccionado', default=True)
    applied = fields.Boolean('Aplicado', default=False)

    # =========================================================================
    # COMPUTED FIELDS - Similar a hr_payroll
    # =========================================================================

    @api.depends('employee_id')
    def _compute_contract_id(self):
        """Obtiene el contrato activo del empleado - similar a hr_payroll"""
        for line in self:
            if not line.employee_id:
                line.contract_id = False
                continue
            # Si ya tiene contrato del mismo empleado, mantenerlo
            if line.contract_id and line.contract_id.employee_id == line.employee_id:
                continue
            # Buscar contrato activo
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', line.employee_id.id),
                ('state', '=', 'open'),
                ('company_id', '=', line.increase_id.company_id.id if line.increase_id else self.env.company.id),
            ], limit=1)
            line.contract_id = contract

    @api.depends('contract_id')
    def _compute_from_contract(self):
        """Obtiene datos del contrato - similar a hr_payroll"""
        for line in self:
            if line.contract_id:
                line.department_id = line.contract_id.department_id
                line.job_id = line.contract_id.job_id
                line.current_wage = line.contract_id.wage
            else:
                line.department_id = False
                line.job_id = False
                line.current_wage = 0

    @api.depends('current_wage', 'increase_id.increase_type', 'increase_id.increase_percentage',
                 'increase_id.increase_fixed', 'increase_id.round_to')
    def _compute_new_wage(self):
        """Calcula el nuevo salario basado en la configuracion del proceso"""
        for line in self:
            if not line.current_wage or not line.increase_id:
                line.new_wage = line.current_wage or 0
                continue

            increase = line.increase_id
            if increase.increase_type == 'percentage':
                new_wage = line.current_wage * (1 + increase.increase_percentage)
            elif increase.increase_type == 'fixed':
                new_wage = increase.increase_fixed
            else:  # increment
                new_wage = line.current_wage + increase.increase_fixed

            # Redondear
            if increase.round_to and increase.round_to != 'none':
                factor = int(increase.round_to)
                new_wage = round(new_wage / factor) * factor

            line.new_wage = new_wage

    @api.depends('current_wage', 'new_wage')
    def _compute_increase(self):
        for line in self:
            line.increase_amount = line.new_wage - line.current_wage
            if line.current_wage:
                # Almacenar como decimal (0.23 para 23%) para compatibilidad con widget percentage
                line.increase_pct = line.increase_amount / line.current_wage
            else:
                line.increase_pct = 0

    # =========================================================================
    # ONCHANGE - Para registros nuevos (NewId) en el formulario
    # =========================================================================

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Cuando cambia el empleado, buscar su contrato activo"""
        if not self.employee_id:
            self.contract_id = False
            return

        # Buscar contrato activo del empleado
        company_id = self.increase_id.company_id.id if self.increase_id else self.env.company.id
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'open'),
            ('company_id', '=', company_id),
        ], limit=1)
        self.contract_id = contract

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        """Cuando cambia el contrato, actualizar datos"""
        if self.contract_id:
            self.department_id = self.contract_id.department_id
            self.job_id = self.contract_id.job_id
            self.current_wage = self.contract_id.wage
            # Recalcular nuevo salario
            self._compute_new_wage_values()
        else:
            self.department_id = False
            self.job_id = False
            self.current_wage = 0
            self.new_wage = 0

    def _compute_new_wage_values(self):
        """Calcula el nuevo salario - usado por onchange"""
        if not self.current_wage or not self.increase_id:
            self.new_wage = self.current_wage or 0
            return

        increase = self.increase_id
        if increase.increase_type == 'percentage':
            new_wage = self.current_wage * (1 + increase.increase_percentage)
        elif increase.increase_type == 'fixed':
            new_wage = increase.increase_fixed
        else:  # increment
            new_wage = self.current_wage + increase.increase_fixed

        # Redondear
        if increase.round_to and increase.round_to != 'none':
            factor = int(increase.round_to)
            new_wage = round(new_wage / factor) * factor

        self.new_wage = new_wage
