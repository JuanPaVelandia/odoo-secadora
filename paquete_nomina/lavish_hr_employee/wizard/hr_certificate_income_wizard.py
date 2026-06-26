# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import base64

class HrCertificateIncomeWizard(models.TransientModel):
    """Wizard para generar certificados de ingresos y retenciones"""
    _name = 'hr.certificate.income.wizard'
    _description = 'Asistente para Generar Certificado de Ingresos y Retenciones'

    # Configuración
    header_id = fields.Many2one(
        'hr.certificate.income.header',
        string='Configuración',
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        related='header_id.company_id',
        string='Compañía',
        store=True,
        readonly=True
    )
    year = fields.Integer(
        related='header_id.year',
        string='Año',
        store=True,
        readonly=True
    )

    # Selección de empleados
    employee_ids = fields.Many2many(
        'hr.employee',
        'certificate_income_wizard_employee_rel',
        'wizard_id',
        'employee_id',
        string='Empleados',
        domain="[('company_id', '=', company_id)]"
    )
    all_employees = fields.Boolean(
        string='Todos los Empleados',
        default=False,
        help='Genera certificados para todos los empleados de la compañía'
    )

    # Filtros
    department_ids = fields.Many2many(
        'hr.department',
        'certificate_income_wizard_dept_rel',
        'wizard_id',
        'department_id',
        string='Departamentos',
        domain="[('company_id', '=', company_id)]"
    )
    job_ids = fields.Many2many(
        'hr.job',
        'certificate_income_wizard_job_rel',
        'wizard_id',
        'job_id',
        string='Cargos',
        domain="[('company_id', '=', company_id')]"
    )

    # Fechas del periodo
    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: fields.Date.from_string(f'{fields.Date.today().year}-01-01')
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=lambda self: fields.Date.from_string(f'{fields.Date.today().year}-12-31')
    )

    # Año del periodo (calculado dinámicamente)
    period_year = fields.Integer(
        string='Año del Periodo',
        compute='_compute_period_year',
        store=True,
        readonly=True,
        help='Año calculado basado en la fecha de finalización del periodo'
    )

    # Opciones
    include_inactive = fields.Boolean(
        string='Incluir Inactivos',
        default=False,
        help='Incluye empleados que fueron retirados durante el año'
    )
    auto_compute = fields.Boolean(
        string='Cálculo Automático',
        default=True,
        help='Calcula automáticamente los valores basados en nóminas'
    )

    # Resultado
    certificate_count = fields.Integer(
        string='Certificados Generados',
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('processing', 'Procesando'),
        ('done', 'Completado'),
        ('error', 'Error')
    ], string='Estado', default='draft', readonly=True)

    error_message = fields.Text(
        string='Mensaje de Error',
        readonly=True
    )

    # Indicadores visuales de completitud
    config_status = fields.Html(
        string='Estado de Configuración',
        compute='_compute_config_status'
    )

    # Vista previa del certificado
    preview_html = fields.Html(
        string='Vista Previa del Certificado',
        compute='_compute_preview_html',
        sanitize=False
    )

    @api.depends('date_to')
    def _compute_period_year(self):
        """Calcula el año basado en la fecha de finalización"""
        for wizard in self:
            if wizard.date_to:
                wizard.period_year = wizard.date_to.year
            else:
                wizard.period_year = fields.Date.today().year

    @api.onchange('header_id')
    def _onchange_header_id(self):
        """Auto-llena parámetros desde configuración anual si están vacíos"""
        if self.header_id and not self.header_id.uvt_value:
            # Buscar parámetros anuales
            annual_params = self.env['hr.annual.parameters'].get_for_year(
                self.header_id.year,
                company_id=self.header_id.company_id.id,
                raise_if_not_found=False,
            )

            if annual_params and annual_params.value_uvt:
                self.header_id.write({
                    'uvt_value': annual_params.value_uvt,
                })

    @api.depends('header_id', 'header_id.report_template', 'employee_ids', 'date_from', 'date_to')
    def _compute_preview_html(self):
        """Genera vista previa del certificado con datos de ejemplo"""
        for wizard in self:
            if not wizard.header_id or not wizard.header_id.report_template:
                wizard.preview_html = '<div class="alert alert-info">Seleccione una configuración para ver la vista previa</div>'
                continue

            # Usar el primer empleado seleccionado o crear valores de ejemplo
            if wizard.employee_ids:
                employee = wizard.employee_ids[0]
                values = wizard._prepare_certificate_values(employee)
            else:
                # Valores de ejemplo
                values = wizard._get_sample_values()

            # Generar HTML
            html_content = wizard.header_id.report_template

            # Reemplazar valores
            for key, value in values.items():
                placeholder = '{' + key + '}'
                html_content = html_content.replace(placeholder, str(value))

            wizard.preview_html = html_content

    def _get_sample_values(self):
        """Genera valores de ejemplo para la vista previa"""
        sample_values = {}

        # Valores por defecto para cada secuencia
        for line in self.header_id.line_ids:
            key = f'val{line.sequence}'

            if line.calculation == 'date_issue':
                sample_values[key] = fields.Date.today().strftime('%d/%m/%Y')
            elif line.calculation == 'start_date_year':
                sample_values[key] = self.date_from.strftime('%d/%m/%Y') if self.date_from else '01/01/2024'
            elif line.calculation == 'end_date_year':
                sample_values[key] = self.date_to.strftime('%d/%m/%Y') if self.date_to else '31/12/2024'
            elif line.calculation in ('sum_rule', 'sum_sequence'):
                sample_values[key] = '$1,000,000.00'
            elif line.calculation == 'info':
                sample_values[key] = '[Dato del Empleado]'
            else:
                sample_values[key] = ''

        # Valores especiales
        sample_values.update({
            'year': self.period_year or fields.Date.today().year,
            'uvt_4500': f"${self.header_id.patrimony_cop:,.2f}" if self.header_id.patrimony_cop else '$0.00',
            'uvt_1400': f"${self.header_id.income_cop:,.2f}" if self.header_id.income_cop else '$0.00',
        })

        return sample_values

    @api.depends('header_id', 'header_id.configuration_complete')
    def _compute_config_status(self):
        """Genera indicadores visuales del estado de la configuración"""
        for wizard in self:
            if not wizard.header_id:
                wizard.config_status = '<span class="text-muted">Seleccione una configuración</span>'
                continue

            header = wizard.header_id
            html = '<div class="o_form_sheet">'

            # Estado general
            if header.configuration_complete:
                html += '<div class="alert alert-success" role="alert">'
                html += '<i class="fa fa-check-circle"></i> <strong>Configuración Completa</strong>'
                html += '<p class="mb-0">Todos los campos están correctamente configurados</p>'
                html += '</div>'
            else:
                html += '<div class="alert alert-warning" role="alert">'
                html += f'<i class="fa fa-exclamation-triangle"></i> <strong>Configuración Incompleta</strong>'
                html += f'<p class="mb-0">{header.missing_items_count} campos requieren configuración</p>'
                html += '</div>'

            # Detalles de campos configurados
            html += '<div class="row">'
            html += '<div class="col-md-12">'
            html += '<h6 class="mb-2">Estado de Campos:</h6>'
            html += '<ul class="list-group list-group-flush">'

            # Agrupar líneas por tipo
            income_lines = header.line_ids.filtered(lambda l: 36 <= l.sequence <= 49)
            contribution_lines = header.line_ids.filtered(lambda l: 50 <= l.sequence <= 55)
            other_lines = header.line_ids.filtered(lambda l: l.sequence > 55)

            for group_name, lines in [
                ('Ingresos (36-49)', income_lines),
                ('Aportes (50-55)', contribution_lines),
                ('Otros Ingresos (56+)', other_lines)
            ]:
                if lines:
                    configured = lines.filtered(lambda l: l.is_configured)
                    html += f'<li class="list-group-item d-flex justify-content-between align-items-center">'
                    html += f'{group_name}'
                    if len(configured) == len(lines):
                        html += '<span class="badge bg-success rounded-pill">'
                        html += f'<i class="fa fa-check"></i> {len(configured)}/{len(lines)}'
                        html += '</span>'
                    else:
                        html += '<span class="badge bg-warning rounded-pill">'
                        html += f'{len(configured)}/{len(lines)}'
                        html += '</span>'
                    html += '</li>'

            html += '</ul>'
            html += '</div>'
            html += '</div>'

            # Valores UVT
            html += '<div class="row mt-3">'
            html += '<div class="col-md-12">'
            html += '<h6 class="mb-2">Valores UVT Configurados:</h6>'
            html += '<table class="table table-sm">'
            html += '<tbody>'
            html += f'<tr><td>Valor UVT {header.year}:</td><td class="text-end"><strong>${header.uvt_value:,.2f}</strong></td></tr>'
            html += f'<tr><td>Límite Patrimonio (4.500 UVT):</td><td class="text-end">${header.patrimony_cop:,.2f}</td></tr>'
            html += f'<tr><td>Límite Ingresos (1.400 UVT):</td><td class="text-end">${header.income_cop:,.2f}</td></tr>'
            html += '</tbody>'
            html += '</table>'
            html += '</div>'
            html += '</div>'

            html += '</div>'
            wizard.config_status = html

    @api.onchange('all_employees')
    def _onchange_all_employees(self):
        """Limpia selección de empleados si se marca todos"""
        if self.all_employees:
            self.employee_ids = [(5, 0, 0)]

    @api.onchange('department_ids', 'job_ids')
    def _onchange_filters(self):
        """Actualiza empleados basado en filtros"""
        if not self.all_employees and (self.department_ids or self.job_ids):
            domain = [('company_id', '=', self.company_id.id)]

            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))

            if self.job_ids:
                domain.append(('job_id', 'in', self.job_ids.ids))

            if not self.include_inactive:
                domain.append(('active', '=', True))

            employees = self.env['hr.employee'].search(domain)
            self.employee_ids = [(6, 0, employees.ids)]

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Valida que las fechas sean coherentes"""
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('La fecha inicial no puede ser mayor que la fecha final'))

    def action_generate_certificates(self):
        """Genera los certificados para los empleados seleccionados"""
        self.ensure_one()

        # Validar configuración
        if not self.header_id.configuration_complete:
            raise UserError(_(
                'La configuración no está completa. '
                'Por favor complete la configuración antes de generar certificados.'
            ))

        # Obtener empleados
        if self.all_employees:
            domain = [('company_id', '=', self.company_id.id)]
            if not self.include_inactive:
                domain.append(('active', '=', True))
            employees = self.env['hr.employee'].search(domain)
        else:
            employees = self.employee_ids

        if not employees:
            raise UserError(_('Debe seleccionar al menos un empleado'))

        # Cambiar estado
        self.write({'state': 'processing'})

        try:
            # Generar certificados
            certificates_created = 0
            for employee in employees:
                cert_vals = self._prepare_certificate_values(employee)
                if cert_vals:
                    self._create_certificate(employee, cert_vals)
                    certificates_created += 1

            # Actualizar estado
            self.write({
                'state': 'done',
                'certificate_count': certificates_created
            })

            # Mostrar mensaje de éxito
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Certificados Generados'),
                    'message': _(f'Se generaron {certificates_created} certificados exitosamente'),
                    'sticky': False,
                    'type': 'success',
                }
            }

        except Exception as e:
            self.write({
                'state': 'error',
                'error_message': str(e)
            })
            raise UserError(_(f'Error al generar certificados: {str(e)}'))

    def _prepare_certificate_values(self, employee):
        """Prepara los valores para el certificado de un empleado"""
        self.ensure_one()

        values = {}

        # Procesar cada línea de configuración
        for line in self.header_id.line_ids:
            key = f'val{line.sequence}'

            if line.calculation == 'sum_rule':
                # Usar el método integrador que decide automáticamente entre
                # lógica contable, reglas salariales o categorías
                value = line.compute_line_value(employee, self.date_from, self.date_to)
                values[key] = f"${value:,.2f}" if value else '$0.00'

            elif line.calculation == 'info' and line.information_fields_id:
                # Obtener información de campo
                values[key] = self._get_field_value(
                    employee,
                    line.information_fields_id,
                    line.related_field_id
                )

            elif line.calculation == 'sum_sequence' and line.sequence_list_sum:
                # Sumar secuencias anteriores
                sequences = [int(s.strip()) for s in line.sequence_list_sum.split(',')]
                total = sum(values.get(f'val{seq}', 0) for seq in sequences)
                values[key] = total

            elif line.calculation == 'date_issue':
                values[key] = self.header_id.issue_date.strftime('%d/%m/%Y') if self.header_id.issue_date else ''

            elif line.calculation == 'start_date_year':
                values[key] = self.date_from.strftime('%d/%m/%Y')

            elif line.calculation == 'end_date_year':
                values[key] = self.date_to.strftime('%d/%m/%Y')

            else:
                values[key] = ''

        # Valores especiales
        values.update({
            'year': self.year,
            'uvt_4500': f"${self.header_id.patrimony_cop:,.2f}",
            'uvt_1400': f"${self.header_id.income_cop:,.2f}",
        })

        return values

    def _compute_salary_rules_sum(self, employee, salary_rules, date_from, date_to):
        """Calcula la suma de reglas salariales para un empleado en un periodo"""
        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'done'),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to)
        ])

        total = 0
        for payslip in payslips:
            for rule in salary_rules:
                line = payslip.line_ids.filtered(lambda l: l.salary_rule_id == rule)
                total += sum(line.mapped('total'))

        return total

    def _get_field_value(self, employee, field, related_field=None):
        """Obtiene el valor de un campo del empleado"""
        if not field:
            return ''

        value = employee[field.name]

        if related_field and value:
            value = value[related_field.name]

        # Formatear según tipo
        if isinstance(value, (int, float)):
            return f"${value:,.2f}"
        elif isinstance(value, datetime):
            return value.strftime('%d/%m/%Y')
        else:
            return str(value) if value else ''

    def _create_certificate(self, employee, values):
        """Crea el certificado PDF para un empleado"""
        # Generar HTML del certificado
        html_content = self.header_id.report_template

        # Reemplazar valores
        for key, value in values.items():
            html_content = html_content.replace(f'{{{key}}}', str(value))

        # TODO: Generar PDF usando ir.actions.report
        # Por ahora solo creamos el registro

        cert_vals = {
            'employee_id': employee.id,
            'header_id': self.header_id.id,
            'year': self.year,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'state': 'generated',
            'html_content': html_content,
        }

        return self.env['hr.withholding.and.income.certificate'].create(cert_vals)

    def action_reset(self):
        """Resetea el wizard al estado inicial"""
        self.write({
            'state': 'draft',
            'certificate_count': 0,
            'error_message': False
        })
        return {'type': 'ir.actions.act_window_close'}

    def action_view_certificates(self):
        """Muestra los certificados generados"""
        self.ensure_one()

        return {
            'name': _('Certificados Generados'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.withholding.and.income.certificate',
            'view_mode': 'list,form',
            'domain': [
                ('header_id', '=', self.header_id.id),
                ('year', '=', self.year)
            ],
            'context': {'create': False}
        }
