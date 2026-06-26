# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
from datetime import timedelta

ITEM_TYPE_SELECTION = [
    ('shirt', 'Camisa/Sueter'),
    ('pants', 'Pantalon'),
    ('shoes', 'Zapatos'),
    ('helmet', 'Casco'),
    ('gloves', 'Guantes'),
    ('glasses', 'Gafas'),
    ('mask', 'Mascarilla'),
    ('vest', 'Chaleco'),
    ('boots', 'Botas'),
    ('other', 'Otro')
]

ITEMS_REQUIRING_SIZE = ('shirt', 'pants', 'shoes', 'boots')


class HrEppConfiguration(models.Model):
    _name = 'hr.epp.configuration'
    _description = 'Configuracion EPP y Dotacion'

    name = fields.Char('Nombre', required=True)
    active = fields.Boolean('Activo', default=True)
    company_id = fields.Many2one('res.company', 'Compania', default=lambda self: self.env.company)

    type = fields.Selection([
        ('epp', 'EPP - Elementos de Proteccion Personal'),
        ('dotacion', 'Dotacion - Uniformes')
    ], string='Tipo', required=True)

    frequency = fields.Integer('Frecuencia (meses)', default=3, required=True)
    generate_automatically = fields.Boolean('Generar automaticamente', default=True)
    last_generation_date = fields.Date('Ultima Generacion')

    department_ids = fields.Many2many('hr.department', 'hr_department_hr_epp_configuration_rel', 'hr_epp_configuration_id', 'hr_department_id', string='Departamentos')
    job_ids = fields.Many2many('hr.job', 'hr_epp_configuration_hr_job_rel', 'hr_epp_configuration_id', 'hr_job_id', string='Puestos de Trabajo')

    kit_line_ids = fields.One2many('hr.epp.configuration.line', 'configuration_id', string='Items del Kit')

    use_stock_location = fields.Boolean('Usar Control de Inventario', default=True)
    location_id = fields.Many2one('stock.location', 'Ubicacion EPP', domain="[('usage', '=', 'internal')]")

    supplier_ids = fields.Many2many('res.partner', 'hr_epp_configuration_res_partner_rel', 'hr_epp_configuration_id', 'res_partner_id', string='Proveedores', domain=[('supplier_rank', '>', 0)])

    sync_with_payroll = fields.Boolean('Sincronizar con Ciclos de Nomina', default=False)
    payroll_period_type = fields.Selection([('monthly', 'Mensual'), ('biweekly', 'Quincenal')], string='Tipo de Periodo')
    generate_on_period = fields.Selection([('first', 'Primera Quincena'), ('second', 'Segunda Quincena'), ('both', 'Ambos')], default='first')
    payroll_month_day = fields.Integer('Dia del Mes', default=1)

    is_template = fields.Boolean('Es Plantilla', default=False)
    auto_renew = fields.Boolean('Renovacion Automatica', default=False)

    @api.model
    def cron_generate_epp_requests(self):
        today = fields.Date.today()
        configs = self.search([('generate_automatically', '=', True), ('active', '=', True)])

        for config in configs:
            should_generate = False
            if config.sync_with_payroll:
                should_generate = config._check_payroll_cycle(today)
            else:
                if not config.last_generation_date:
                    should_generate = True
                else:
                    next_date = config.last_generation_date + relativedelta(months=config.frequency)
                    should_generate = today >= next_date

            if should_generate:
                config._generate_requests()

    def _check_payroll_cycle(self, today):
        self.ensure_one()
        if not self.payroll_period_type:
            return False

        if self.payroll_period_type == 'monthly':
            if self.generate_on_period == 'first':
                return today.day == self.payroll_month_day
            elif self.generate_on_period == 'second':
                last_day = (today.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).day
                return today.day == last_day
            else:
                return today.day == self.payroll_month_day or today.day == 15
        elif self.payroll_period_type == 'biweekly':
            if self.generate_on_period == 'first':
                return today.day == 1
            elif self.generate_on_period == 'second':
                return today.day == 15
            else:
                last_day = (today.replace(day=1) + relativedelta(months=1) - timedelta(days=1)).day
                return today.day in (15, last_day)
        return False

    def _generate_requests(self):
        self.ensure_one()
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.job_ids:
            domain.append(('job_id', 'in', self.job_ids.ids))

        employees = self.env['hr.employee'].search(domain)

        for employee in employees:
            has_payslip = self.env['hr.payslip'].search_count([
                ('employee_id', '=', employee.id),
                ('state', '=', 'done')
            ]) > 0

            if has_payslip:
                self._create_individual_request(employee)

        self.last_generation_date = fields.Date.today()

    def _create_individual_request(self, employee):
        self.ensure_one()
        request = self.env['hr.epp.request'].create({
            'employee_id': employee.id,
            'configuration_id': self.id,
            'type': self.type,
            'state': 'draft',
        })

        for line in self.kit_line_ids:
            size = self._get_employee_size(employee, line.item_type_id)
            self.env['hr.epp.request.line'].create({
                'request_id': request.id,
                'item_type_id': line.item_type_id.id if line.item_type_id else False,
                'product_id': line.product_id.id if line.product_id else False,
                'name': line.name,
                'quantity': line.quantity,
                'size': size,
            })
        return request

    def _get_employee_size(self, employee, item_type_id):
        """Obtiene la talla del empleado según el tipo de item."""
        if not item_type_id:
            return False

        size_type = item_type_id.size_type
        if size_type == 'clothing':
            return employee.shirt_size or 'M'
        elif size_type == 'shoes':
            return employee.shoe_size or '40'
        elif size_type == 'gloves':
            return employee.gloves_size if hasattr(employee, 'gloves_size') else '8'
        elif size_type == 'helmet':
            return employee.helmet_size if hasattr(employee, 'helmet_size') else 'M'
        return False


class HrEppConfigurationLine(models.Model):
    _name = 'hr.epp.configuration.line'
    _description = 'Linea de Configuracion EPP'

    configuration_id = fields.Many2one('hr.epp.configuration', 'Configuracion', ondelete='cascade')

    # Nuevo campo Many2one para tipo de item
    item_type_id = fields.Many2one(
        'hr.epp.item.type',
        string='Tipo',
        required=True,
        domain="[('is_subtype', '=', True)]",
        help='Seleccione el subtipo de item (ej: Protección Cabeza, Ropa Superior)'
    )

    # Campo relacionado para obtener el tipo padre
    item_type_parent_id = fields.Many2one(
        related='item_type_id.parent_id',
        string='Categoría',
        store=True,
        readonly=True
    )

    name = fields.Char('Descripcion', required=True)
    product_id = fields.Many2one('product.product', 'Producto')
    quantity = fields.Float('Cantidad', default=1.0)
    requires_size = fields.Boolean('Requiere Talla', compute='_compute_requires_size', store=True)

    @api.depends('item_type_id', 'item_type_id.requires_size')
    def _compute_requires_size(self):
        for line in self:
            line.requires_size = line.item_type_id.requires_size if line.item_type_id else False

    @api.onchange('item_type_id')
    def _onchange_item_type_id(self):
        """Sugerir nombre basado en el tipo seleccionado."""
        if self.item_type_id and not self.name:
            self.name = self.item_type_id.name
