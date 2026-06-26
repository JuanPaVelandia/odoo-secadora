# -*- coding: utf-8 -*-
"""
WIZARD: Creación Rápida Individual

Permite crear solicitudes individuales de EPP/Dotación/Exámenes
desde una plantilla de forma rápida
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class WizardEppQuickCreate(models.TransientModel):
    """
    Wizard para crear solicitud/certificado individual rápidamente

    USO:
    - Seleccionar empleado
    - Seleccionar configuración/plantilla
    - Click: Crear
    """
    _name = 'wizard.epp.quick.create'
    _description = 'Creación Rápida Individual'

    # ========================================================================
    # PASO 1: TIPO
    # ========================================================================

    type = fields.Selection([
        ('epp', 'EPP'),
        ('dotacion', 'Dotación'),
        ('medical', 'Examen Médico'),
    ], string='Tipo', required=True, default='dotacion')

    # ========================================================================
    # PASO 2: EMPLEADO
    # ========================================================================

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        domain=[('active', '=', True)]
    )

    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        readonly=True
    )

    job_id = fields.Many2one(
        'hr.job',
        related='employee_id.job_id',
        readonly=True
    )

    # ========================================================================
    # PASO 3: CONFIGURACIÓN/PLANTILLA
    # ========================================================================

    configuration_id = fields.Many2one(
        'hr.epp.configuration',
        string='Plantilla/Configuración',
        domain="[('type', '=', type), ('active', '=', True)]"
    )

    # Vista previa del kit
    kit_line_ids = fields.One2many(
        related='configuration_id.kit_line_ids',
        readonly=True
    )

    # ========================================================================
    # PASO 4: DATOS ADICIONALES (EPP/Dotación)
    # ========================================================================

    request_date = fields.Date(
        'Fecha Solicitud',
        default=fields.Date.today
    )

    notes = fields.Text('Observaciones')

    # ========================================================================
    # PASO 4: DATOS ADICIONALES (Examen Médico)
    # ========================================================================

    provider_id = fields.Many2one(
        'res.partner',
        string='Proveedor Médico',
        domain=[('supplier_rank', '>', 0)]
    )

    certificate_type = fields.Selection([
        ('aptitude', 'Certificado de Aptitud Laboral'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('psychosensory', 'Psicosensométrico'),
        ('occupational', 'Examen Ocupacional'),
        ('periodic', 'Examen Periódico'),
        ('retirement', 'Examen de Retiro'),
        ('drug_test', 'Prueba de Drogas'),
        ('other', 'Otro')
    ], string='Tipo de Examen')

    schedule_date = fields.Datetime('Fecha Programada')

    validity_months = fields.Integer(
        'Vigencia (meses)',
        default=12
    )

    # ========================================================================
    # MÉTODOS
    # ========================================================================

    @api.onchange('configuration_id')
    def _onchange_configuration_id(self):
        """Auto-completar campos desde configuración"""
        if self.configuration_id:
            # Si es examen médico
            if self.type not in ('epp', 'dotacion'):
                if self.configuration_id.default_provider_id:
                    self.provider_id = self.configuration_id.default_provider_id

                if self.configuration_id.validity_months:
                    self.validity_months = self.configuration_id.validity_months

    def action_create(self):
        """Crear solicitud/certificado"""
        self.ensure_one()

        if self.type in ('epp', 'dotacion'):
            return self._create_epp_request()
        else:
            return self._create_medical_certificate()

    def _create_epp_request(self):
        """Crear solicitud de EPP/Dotación"""
        # Crear solicitud
        request = self.env['hr.epp.request'].create({
            'employee_id': self.employee_id.id,
            'type': self.type,
            'configuration_id': self.configuration_id.id if self.configuration_id else False,
            'request_date': self.request_date,
            'notes': self.notes,
            'state': 'draft',
        })

        # Agregar líneas del kit
        if self.configuration_id:
            for kit_line in self.configuration_id.kit_line_ids:
                size = self._get_employee_size(kit_line.item_type)

                self.env['hr.epp.request.line'].create({
                    'request_id': request.id,
                    'item_type': kit_line.item_type,
                    'product_id': kit_line.product_id.id if kit_line.product_id else False,
                    'name': kit_line.name,
                    'quantity': kit_line.quantity,
                    'size': size,
                })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.epp.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_medical_certificate(self):
        """Crear certificado médico"""
        expiry_date = fields.Date.today() + relativedelta(months=self.validity_months)

        cert = self.env['hr.medical.certificate'].create({
            'employee_id': self.employee_id.id,
            'provider_id': self.provider_id.id if self.provider_id else False,
            'certificate_type': self.certificate_type or 'occupational',
            'configuration_id': self.configuration_id.id if self.configuration_id else False,
            'schedule_date': self.schedule_date,
            'issue_date': fields.Date.today(),
            'expiry_date': expiry_date,
            'observations': self.notes,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.medical.certificate',
            'res_id': cert.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_employee_size(self, item_type):
        """Obtiene talla del empleado"""
        if item_type == 'shirt':
            return self.employee_id.shirt_size or 'M'
        elif item_type == 'pants':
            return self.employee_id.pants_size or '32'
        elif item_type in ('shoes', 'boots'):
            return self.employee_id.shoe_size or '40'
        return False


class WizardMedicalCertificateRenew(models.TransientModel):
    """
    Wizard para renovar certificado médico

    Pre-completa datos del certificado original
    """
    _name = 'wizard.medical.certificate.renew'
    _description = 'Renovar Certificado Médico'

    original_certificate_id = fields.Many2one(
        'hr.medical.certificate',
        string='Certificado Original',
        required=True,
        readonly=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        readonly=True
    )

    provider_id = fields.Many2one(
        'res.partner',
        string='Proveedor Médico',
        domain=[('supplier_rank', '>', 0)]
    )

    certificate_type = fields.Selection([
        ('aptitude', 'Certificado de Aptitud Laboral'),
        ('height_work', 'Trabajo en Alturas'),
        ('confined_spaces', 'Espacios Confinados'),
        ('psychosensory', 'Psicosensométrico'),
        ('occupational', 'Examen Ocupacional'),
        ('periodic', 'Examen Periódico'),
        ('retirement', 'Examen de Retiro'),
        ('drug_test', 'Prueba de Drogas'),
        ('other', 'Otro')
    ], string='Tipo de Examen', required=True)

    schedule_date = fields.Datetime('Fecha Programada')

    issue_date = fields.Date(
        'Fecha de Emisión',
        default=fields.Date.today,
        required=True
    )

    validity_months = fields.Integer(
        'Vigencia (meses)',
        default=12,
        required=True
    )

    expiry_date = fields.Date(
        'Fecha de Vencimiento',
        compute='_compute_expiry_date',
        store=True
    )

    @api.depends('issue_date', 'validity_months')
    def _compute_expiry_date(self):
        for wizard in self:
            if wizard.issue_date and wizard.validity_months:
                wizard.expiry_date = wizard.issue_date + relativedelta(
                    months=wizard.validity_months
                )
            else:
                wizard.expiry_date = False

    def action_create_renewal(self):
        """Crear certificado de renovación"""
        self.ensure_one()

        # Validar que no tenga renovación ya
        if self.original_certificate_id.renewed_by_certificate_id:
            raise UserError(_(
                'El certificado original ya tiene una renovación: %s'
            ) % self.original_certificate_id.renewed_by_certificate_id.name)

        # Crear nuevo certificado
        new_cert = self.env['hr.medical.certificate'].create({
            'employee_id': self.employee_id.id,
            'provider_id': self.provider_id.id,
            'certificate_type': self.certificate_type,
            'schedule_date': self.schedule_date,
            'issue_date': self.issue_date,
            'expiry_date': self.expiry_date,
            'renewal_certificate_id': self.original_certificate_id.id,
            'configuration_id': self.original_certificate_id.configuration_id.id,
            'template_id': self.original_certificate_id.template_id.id,
            'state': 'scheduled',
            'result': 'pending',
        })

        # Actualizar certificado original
        self.original_certificate_id.renewed_by_certificate_id = new_cert.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.medical.certificate',
            'res_id': new_cert.id,
            'view_mode': 'form',
            'target': 'current',
        }
