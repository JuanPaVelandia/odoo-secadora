# -*- coding: utf-8 -*-
"""
Wizard para generación masiva de certificados laborales.
Permite seleccionar múltiples contratos y generar/enviar/imprimir certificados.
"""
import html

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class HrLaborCertificateWizard(models.TransientModel):
    _name = 'hr.labor.certificate.wizard'
    _description = 'Wizard para generar certificados laborales masivamente'

    # ============================================
    # Campos de configuración
    # ============================================
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True)

    date_generation = fields.Date(
        string='Fecha de generación',
        default=fields.Date.today,
        required=True)

    info_to = fields.Char(
        string='Dirigido a',
        help='Texto para el campo "Dirigido a" en todos los certificados')

    partner_id = fields.Many2one(
        'res.partner',
        string='Tercero/Destinatario',
        help='Contacto destinatario para todos los certificados (opcional)')

    # ============================================
    # Modo de selección
    # ============================================
    selection_mode = fields.Selection([
        ('all', 'Todos los contratos activos'),
        ('department', 'Por Departamento'),
        ('job', 'Por Cargo'),
        ('manual', 'Selección manual'),
    ], string='Modo de selección', default='manual', required=True)

    # ============================================
    # Filtros de selección
    # ============================================
    department_ids = fields.Many2many(
        'hr.department',
        'hr_labor_cert_wizard_department_rel',
        'wizard_id',
        'department_id',
        string='Departamentos',
        domain="[('company_id', '=', company_id)]")

    job_ids = fields.Many2many(
        'hr.job',
        'hr_labor_cert_wizard_job_rel',
        'wizard_id',
        'job_id',
        string='Cargos',
        domain="[('company_id', '=', company_id)]")

    contract_ids = fields.Many2many(
        'hr.contract',
        'hr_labor_cert_wizard_contract_rel',
        'wizard_id',
        'contract_id',
        string='Contratos',
        domain="[('company_id', '=', company_id), ('state', 'in', include_inactive and ['open', 'close'] or ['open'])]")

    include_inactive = fields.Boolean(
        string='Incluir contratos finalizados',
        default=False,
        help='Incluir también contratos que ya no están activos')

    # ============================================
    # Acción a realizar
    # ============================================
    action_type = fields.Selection([
        ('generate', 'Solo Generar'),
        ('generate_print', 'Generar e Imprimir'),
        ('generate_send', 'Generar y Enviar por Correo'),
    ], string='Acción', default='generate', required=True)

    # ============================================
    # Estilo del certificado
    # ============================================
    certificate_style = fields.Selection([
        ('classic', 'Clásico'),
        ('modern', 'Moderno'),
        ('formal', 'Formal / Ejecutivo'),
        ('minimal', 'Minimalista'),
        ('elegant', 'Elegante'),
        ('corporate', 'Corporativo'),
    ], string='Estilo del Certificado', default='classic', required=True,
        help='Seleccione el estilo visual para los certificados a generar')

    use_template_style = fields.Boolean(
        string='Usar estilo de plantilla',
        default=True,
        help='Si está marcado, usa el estilo configurado en la plantilla. Si no, usa el estilo seleccionado aquí.')

    # ============================================
    # Campos de información
    # ============================================
    contract_count = fields.Integer(
        string='Contratos seleccionados',
        compute='_compute_contract_count')

    preview_html = fields.Html(
        string='Vista previa',
        compute='_compute_preview_html')

    # ============================================
    # Estado del wizard
    # ============================================
    state = fields.Selection([
        ('draft', 'Configuración'),
        ('preview', 'Vista previa'),
        ('done', 'Completado'),
    ], string='Estado', default='draft')

    generated_certificate_ids = fields.Many2many(
        'hr.labor.certificate.history',
        'hr_labor_cert_wizard_generated_rel',
        'wizard_id',
        'certificate_id',
        string='Certificados generados',
        readonly=True)

    # ============================================
    # Métodos computados
    # ============================================

    @api.depends('selection_mode', 'department_ids', 'job_ids', 'contract_ids',
                 'company_id', 'include_inactive')
    def _compute_contract_count(self):
        for wizard in self:
            contracts = wizard._get_contracts()
            wizard.contract_count = len(contracts)

    @api.depends('contract_count', 'selection_mode', 'department_ids', 'job_ids')
    def _compute_preview_html(self):
        for wizard in self:
            contracts = wizard._get_contracts()

            if not contracts:
                wizard.preview_html = '<p class="text-muted">No hay contratos seleccionados</p>'
                continue

            preview_content = f'''
                <div class="alert alert-info">
                    <strong>Contratos a procesar: {len(contracts)}</strong>
                </div>
                <table class="table table-sm table-striped">
                    <thead>
                        <tr>
                            <th>Empleado</th>
                            <th>Contrato</th>
                            <th>Departamento</th>
                            <th>Cargo</th>
                        </tr>
                    </thead>
                    <tbody>
            '''

            for contract in contracts[:20]:  # Mostrar máximo 20 para preview
                employee_name = html.escape(contract.employee_id.name or '')
                contract_name = html.escape(contract.name or '')
                department_name = html.escape(contract.department_id.name) if contract.department_id else '-'
                job_name = html.escape(contract.job_id.name) if contract.job_id else '-'
                preview_content += f'''
                    <tr>
                        <td>{employee_name}</td>
                        <td>{contract_name}</td>
                        <td>{department_name}</td>
                        <td>{job_name}</td>
                    </tr>
                '''

            if len(contracts) > 20:
                preview_content += f'''
                    <tr>
                        <td colspan="4" class="text-center text-muted">
                            ... y {len(contracts) - 20} contratos más
                        </td>
                    </tr>
                '''

            preview_content += '''
                    </tbody>
                </table>
            '''
            wizard.preview_html = preview_content

    # ============================================
    # Métodos de negocio
    # ============================================

    def _get_contracts(self):
        """Obtiene los contratos según el modo de selección."""
        self.ensure_one()

        if self.selection_mode == 'manual':
            return self.contract_ids

        domain = [('company_id', '=', self.company_id.id)]

        if not self.include_inactive:
            domain.append(('state', '=', 'open'))
        else:
            domain.append(('state', 'in', ['open', 'close']))

        if self.selection_mode == 'department' and self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))

        if self.selection_mode == 'job' and self.job_ids:
            domain.append(('job_id', 'in', self.job_ids.ids))

        return self.env['hr.contract'].search(domain)

    def action_preview(self):
        """Muestra la vista previa de los contratos a procesar."""
        self.ensure_one()

        contracts = self._get_contracts()
        if not contracts:
            raise UserError(_('No hay contratos que coincidan con los filtros seleccionados.'))

        self.write({'state': 'preview'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Certificados Laborales'),
            'res_model': 'hr.labor.certificate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_back(self):
        """Regresa a la configuración."""
        self.write({'state': 'draft'})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Certificados Laborales'),
            'res_model': 'hr.labor.certificate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_generate_certificates(self):
        """Genera los certificados laborales para los contratos seleccionados."""
        self.ensure_one()

        contracts = self._get_contracts()
        if not contracts:
            raise UserError(_('No hay contratos seleccionados.'))

        # Validar que existe plantilla de certificado
        template = self.env['hr.labor.certificate.template'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        if not template:
            raise ValidationError(_(
                'No existe una plantilla de certificado laboral configurada para la compañía %s. '
                'Por favor configure una plantilla antes de generar certificados.'
            ) % self.company_id.name)

        # Aplicar estilo seleccionado si no usa el de la plantilla
        original_style = template.certificate_style
        if not self.use_template_style:
            template.write({'certificate_style': self.certificate_style})

        # Crear certificados
        try:
            certificates = self.env['hr.labor.certificate.history'].generate_certificates_batch(
                contract_ids=contracts.ids,
                info_to=self.info_to,
                partner_id=self.partner_id.id if self.partner_id else False,
                date_generation=self.date_generation,
            )
        finally:
            # Restaurar estilo original si se cambió
            if not self.use_template_style:
                template.write({'certificate_style': original_style})

        # Generar PDFs
        certificates.action_generate_batch()

        # Ejecutar acción según configuración
        result = None
        if self.action_type == 'generate_print':
            result = certificates.action_print_batch()
        elif self.action_type == 'generate_send':
            certificates.action_send_batch()

        # Actualizar wizard
        self.write({
            'state': 'done',
            'generated_certificate_ids': [(6, 0, certificates.ids)],
        })

        if result:
            return result

        # Mostrar notificación y abrir vista de certificados generados
        return {
            'type': 'ir.actions.act_window',
            'name': _('Certificados Generados'),
            'res_model': 'hr.labor.certificate.history',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', certificates.ids)],
            'target': 'current',
            'context': {
                'create': False,
            },
        }

    def action_open_certificates(self):
        """Abre la vista de certificados generados."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Certificados Generados'),
            'res_model': 'hr.labor.certificate.history',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.generated_certificate_ids.ids)],
            'target': 'current',
        }

    @api.onchange('selection_mode')
    def _onchange_selection_mode(self):
        """Limpia los filtros cuando cambia el modo de selección."""
        if self.selection_mode == 'all':
            self.department_ids = False
            self.job_ids = False
            self.contract_ids = False
        elif self.selection_mode == 'department':
            self.job_ids = False
            self.contract_ids = False
        elif self.selection_mode == 'job':
            self.department_ids = False
            self.contract_ids = False
        elif self.selection_mode == 'manual':
            self.department_ids = False
            self.job_ids = False

    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Limpia los filtros cuando cambia la compañía."""
        self.department_ids = False
        self.job_ids = False
        self.contract_ids = False
