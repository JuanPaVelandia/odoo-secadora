# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class WizardMassEppRequest(models.TransientModel):
    _name = 'wizard.mass.epp.request'
    _description = 'Solicitud Masiva de EPP/Dotación'

    name = fields.Char('Nombre del Lote', required=True, default=lambda self: _('Solicitud Masiva %s') % fields.Date.today())
    type = fields.Selection([
        ('epp', 'EPP - Elementos de Protección Personal'),
        ('dotacion', 'Dotación - Uniformes')
    ], string='Tipo', required=True, default='dotacion')

    configuration_id = fields.Many2one('hr.epp.configuration', 'Configuración', required=True,
                                       domain="[('type', '=', type)]")

    # Filtros para seleccionar empleados
    department_ids = fields.Many2many('hr.department', 'wizard_mass_epp_request_hr_department_rel',
                                       'wizard_id', 'hr_department_id',
                                       string='Departamentos',
                                       help='Si está vacío, se aplicará a todos los departamentos')
    job_ids = fields.Many2many('hr.job', 'wizard_mass_epp_request_hr_job_rel',
                                'wizard_id', 'hr_job_id',
                                string='Puestos de Trabajo',
                                help='Si está vacío, se aplicará a todos los puestos')
    employee_ids = fields.Many2many('hr.employee', 'wizard_mass_epp_request_hr_employee_rel',
                                     'wizard_id', 'hr_employee_id',
                                     string='Empleados',
                                     help='Seleccione empleados específicos o deje vacío para usar filtros')

    # Opciones
    only_need_renewal = fields.Boolean('Solo empleados que necesitan renovación',
                                        default=True,
                                        help='Solo incluir empleados cuya última dotación fue hace más de 3 meses')
    exclude_with_pending = fields.Boolean('Excluir con solicitudes pendientes',
                                           default=True,
                                           help='No crear solicitudes para empleados que ya tienen solicitudes pendientes')

    # Información de entrega
    delivery_location = fields.Selection([
        ('office', 'Oficina Principal'),
        ('warehouse', 'Almacén'),
        ('worksite', 'Sitio de Trabajo'),
        ('other', 'Otro')
    ], string='Lugar de Entrega', default='office')

    delivery_notes = fields.Text('Notas Generales')

    # Resumen
    employee_count = fields.Integer('Empleados Seleccionados', compute='_compute_employee_count')
    preview_line_ids = fields.One2many('wizard.mass.epp.request.line', 'wizard_id', 'Vista Previa de Empleados')

    @api.depends('employee_ids', 'department_ids', 'job_ids', 'only_need_renewal', 'exclude_with_pending')
    def _compute_employee_count(self):
        for wizard in self:
            employees = wizard._get_eligible_employees()
            wizard.employee_count = len(employees)

    def _get_eligible_employees(self):
        """Obtener empleados elegibles según filtros"""
        self.ensure_one()

        domain = [('active', '=', True)]

        # Si hay empleados específicos seleccionados, usar esos
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        else:
            # Filtrar por departamento
            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))

            # Filtrar por puesto
            if self.job_ids:
                domain.append(('job_id', 'in', self.job_ids.ids))

        employees = self.env['hr.employee'].search(domain)

        # Filtrar por necesidad de renovación
        if self.only_need_renewal:
            from dateutil.relativedelta import relativedelta
            three_months_ago = fields.Date.today() - relativedelta(months=3)

            employees = employees.filtered(
                lambda e: not e.last_dotacion_date or e.last_dotacion_date <= three_months_ago
            )

        # Excluir con solicitudes pendientes
        if self.exclude_with_pending:
            pending_employees = self.env['hr.epp.request'].search([
                ('employee_id', 'in', employees.ids),
                ('state', 'in', ['draft', 'requested', 'approved', 'picking'])
            ]).mapped('employee_id')

            employees = employees - pending_employees

        return employees

    def action_preview_employees(self):
        """Mostrar vista previa de empleados que recibirán solicitudes"""
        self.ensure_one()

        # Limpiar líneas previas
        self.preview_line_ids.unlink()

        # Obtener empleados elegibles
        employees = self._get_eligible_employees()

        # Crear líneas de preview
        for employee in employees:
            # Calcular items que recibirá
            items_text = []
            for line in self.configuration_id.kit_line_ids:
                size = ''
                if line.item_type == 'shirt':
                    size = employee.shirt_size or 'M'
                elif line.item_type == 'pants':
                    size = employee.pants_size or '32'
                elif line.item_type == 'shoes':
                    size = employee.shoe_size or '40'

                item_desc = f"{line.name} (Cant: {line.quantity}"
                if size:
                    item_desc += f", Talla: {size}"
                item_desc += ")"
                items_text.append(item_desc)

            self.env['wizard.mass.epp.request.line'].create({
                'wizard_id': self.id,
                'employee_id': employee.id,
                'items_preview': '\n'.join(items_text),
                'last_delivery': employee.last_dotacion_date,
            })

        # Actualizar vista para mostrar las líneas
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.mass.epp.request',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create_requests(self):
        """Crear solicitudes masivas para todos los empleados elegibles"""
        self.ensure_one()

        if not self.configuration_id:
            raise UserError(_('Debe seleccionar una configuración'))

        employees = self._get_eligible_employees()

        if not employees:
            raise UserError(_('No hay empleados elegibles para crear solicitudes'))

        created_requests = []

        for employee in employees:
            # Crear solicitud individual
            request = self.env['hr.epp.request'].create({
                'employee_id': employee.id,
                'type': self.type,
                'configuration_id': self.configuration_id.id,
                'state': 'draft',
                'request_date': fields.Date.today(),
                'delivery_location': self.delivery_location,
                'delivery_notes': self.delivery_notes,
            })

            # Agregar items del kit con tallas del empleado
            for line in self.configuration_id.kit_line_ids:
                size = False
                product_id = line.product_id.id if line.product_id else False

                if line.item_type == 'shirt':
                    size = employee.shirt_size or 'M'
                    if employee.default_shirt_product_id:
                        product_id = employee.default_shirt_product_id.id
                elif line.item_type == 'pants':
                    size = employee.pants_size or '32'
                    if employee.default_pants_product_id:
                        product_id = employee.default_pants_product_id.id
                elif line.item_type == 'shoes':
                    size = employee.shoe_size or '40'
                    if employee.default_shoes_product_id:
                        product_id = employee.default_shoes_product_id.id

                self.env['hr.epp.request.line'].create({
                    'request_id': request.id,
                    'item_type': line.item_type,
                    'product_id': product_id,
                    'name': line.name,
                    'quantity': line.quantity,
                    'size': size,
                })

            # Enviar a estado "Solicitado" automáticamente
            if request.line_ids:
                request.action_request()

            created_requests.append(request.id)

        # Mostrar resultado
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitudes Creadas'),
            'res_model': 'hr.epp.request',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_requests)],
            'context': {'create': False},
        }


class WizardMassEppRequestLine(models.TransientModel):
    _name = 'wizard.mass.epp.request.line'
    _description = 'Línea de Vista Previa de Solicitud Masiva'

    wizard_id = fields.Many2one('wizard.mass.epp.request', 'Wizard', ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', 'Empleado', readonly=True)
    department_id = fields.Many2one('hr.department', 'Departamento', related='employee_id.department_id', readonly=True)
    job_id = fields.Many2one('hr.job', 'Puesto', related='employee_id.job_id', readonly=True)
    items_preview = fields.Text('Items a Recibir', readonly=True)
    last_delivery = fields.Date('Última Entrega', readonly=True)
