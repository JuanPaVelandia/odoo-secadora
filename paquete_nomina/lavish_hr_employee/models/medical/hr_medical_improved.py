# -*- coding: utf-8 -*-
"""
MEJORAS AL SISTEMA DE EXÁMENES MÉDICOS

Cambios principales:
1. Lógica simplificada y clara
2. Control de vencimientos automatizado
3. Proveedores con campo correcto (partner_id)
4. Plantillas médicas mejoradas
5. Recordatorios inteligentes
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

class HrMedicalCertificateImproved(models.Model):
    """
    Mejoras al certificado médico

    CAMBIOS:
    - Workflow simplificado
    - Control de vencimiento claro
    - Renovación automática
    - Alertas configurables
    """
    _inherit = 'hr.medical.certificate'

    # ========================================================================
    # MEJORA 1: ESTADOS SIMPLIFICADOS
    # ========================================================================

    # Agregar campos de control
    renewal_certificate_id = fields.Many2one(
        'hr.medical.certificate',
        string='Renovación de',
        help='Si este certificado es renovación de otro'
    )

    renewed_by_certificate_id = fields.Many2one(
        'hr.medical.certificate',
        string='Renovado por',
        help='Certificado que renovó este'
    )

    is_renewal = fields.Boolean(
        'Es Renovación',
        compute='_compute_is_renewal',
        store=True
    )

    # ========================================================================
    # MEJORA 2: CONTROL DE VENCIMIENTO CLARO
    # ========================================================================

    days_to_expiry = fields.Integer(
        'Días para Vencer',
        compute='_compute_days_to_expiry',
        store=True
    )

    expiry_status = fields.Selection([
        ('valid', 'Vigente'),
        ('warning', 'Por Vencer (Alerta)'),
        ('critical', 'Crítico (< 7 días)'),
        ('expired', 'Vencido'),
    ], string='Estado de Vencimiento',
       compute='_compute_expiry_status',
       store=True)

    next_exam_date = fields.Date(
        'Próximo Examen',
        compute='_compute_next_exam_date',
        store=True,
        help='Fecha sugerida para el próximo examen'
    )

    # ========================================================================
    # MEJORA 3: RECORDATORIOS AUTOMÁTICOS
    # ========================================================================

    reminder_30_sent = fields.Boolean('Recordatorio 30 días enviado')
    reminder_15_sent = fields.Boolean('Recordatorio 15 días enviado')
    reminder_7_sent = fields.Boolean('Recordatorio 7 días enviado')
    reminder_expired_sent = fields.Boolean('Notificación vencido enviada')

    responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsable',
        help='Usuario responsable de gestionar este certificado'
    )

    # ========================================================================
    # MEJORA 4: INTEGRACIÓN CON CONFIGURACIÓN
    # ========================================================================

    configuration_id = fields.Many2one(
        'hr.epp.configuration',
        string='Configuración',
        help='Configuración usada para generar este certificado'
    )

    auto_renew = fields.Boolean(
        'Renovación Automática',
        compute='_compute_auto_renew',
        store=False,
    )

    @api.depends('configuration_id')
    def _compute_auto_renew(self):
        for rec in self:
            rec.auto_renew = rec.configuration_id.auto_renew if rec.configuration_id else False

    # ========================================================================
    # COMPUTES MEJORADOS
    # ========================================================================

    @api.depends('renewal_certificate_id')
    def _compute_is_renewal(self):
        for cert in self:
            cert.is_renewal = bool(cert.renewal_certificate_id)

    @api.depends('expiry_date')
    def _compute_days_to_expiry(self):
        """Calcula días para vencer"""
        today = fields.Date.today()
        for cert in self:
            if cert.expiry_date:
                delta = (cert.expiry_date - today).days
                cert.days_to_expiry = delta
            else:
                cert.days_to_expiry = 0

    @api.depends('days_to_expiry', 'state')
    def _compute_expiry_status(self):
        """Estado de vencimiento más claro"""
        for cert in self:
            if cert.state == 'expired' or cert.days_to_expiry < 0:
                cert.expiry_status = 'expired'
            elif cert.days_to_expiry <= 7:
                cert.expiry_status = 'critical'
            elif cert.days_to_expiry <= 30:
                cert.expiry_status = 'warning'
            else:
                cert.expiry_status = 'valid'

    @api.depends('expiry_date', 'template_id.validity_months')
    def _compute_next_exam_date(self):
        """Sugiere fecha del próximo examen"""
        for cert in self:
            if cert.expiry_date:
                # Restar 7 días al vencimiento para hacer el próximo examen
                cert.next_exam_date = cert.expiry_date - timedelta(days=7)
            else:
                cert.next_exam_date = False

    # ========================================================================
    # MÉTODOS MEJORADOS
    # ========================================================================

    @api.model
    def cron_send_expiry_reminders(self):
        """
        Cron mejorado para enviar recordatorios

        MEJORAS:
        - Recordatorios en 30, 15 y 7 días
        - Notificación de vencido
        - Creación automática de renovación
        """
        today = fields.Date.today()

        # Buscar certificados vigentes
        certs = self.search([
            ('state', 'in', ['valid', 'expiring']),
            ('expiry_date', '!=', False),
        ])

        for cert in certs:
            days_left = (cert.expiry_date - today).days

            # Recordatorio 30 días
            if days_left == 30 and not cert.reminder_30_sent:
                cert._send_reminder('30_days')
                cert.reminder_30_sent = True

            # Recordatorio 15 días
            elif days_left == 15 and not cert.reminder_15_sent:
                cert._send_reminder('15_days')
                cert.reminder_15_sent = True

            # Recordatorio 7 días (CRÍTICO)
            elif days_left == 7 and not cert.reminder_7_sent:
                cert._send_reminder('7_days')
                cert.reminder_7_sent = True
                # Crear actividad urgente
                cert._create_urgent_activity()

            # VENCIDO
            elif days_left < 0 and not cert.reminder_expired_sent:
                cert._send_reminder('expired')
                cert.reminder_expired_sent = True
                # Auto-renovar si está configurado
                if cert.auto_renew:
                    cert._auto_renew_certificate()

    def _send_reminder(self, reminder_type):
        """Envía recordatorio según tipo"""
        self.ensure_one()

        templates = {
            '30_days': 'lavish_hr_employee.email_template_medical_reminder_30',
            '15_days': 'lavish_hr_employee.email_template_medical_reminder_15',
            '7_days': 'lavish_hr_employee.email_template_medical_reminder_7',
            'expired': 'lavish_hr_employee.email_template_medical_expired',
        }

        template_ref = templates.get(reminder_type)
        if not template_ref:
            return

        template = self.env.ref(template_ref, raise_if_not_found=False)
        if not template:
            # Fallback: notificación interna
            self._send_fallback_notification(reminder_type)
            return

        # Enviar correo al empleado
        if self.employee_id.work_email:
            template.send_mail(self.id, force_send=True)

        # Enviar copia al responsable
        if self.responsible_user_id and self.responsible_user_id.partner_id:
            self.message_post(
                body=self._get_reminder_message(reminder_type),
                partner_ids=[self.responsible_user_id.partner_id.id],
                message_type='notification',
            )

    def _send_fallback_notification(self, reminder_type):
        """Notificación interna si no hay template"""
        self.ensure_one()

        messages = {
            '30_days': _('El certificado médico vence en 30 días'),
            '15_days': _('ALERTA: El certificado médico vence en 15 días'),
            '7_days': _('URGENTE: El certificado médico vence en 7 días'),
            'expired': _('VENCIDO: El certificado médico está vencido'),
        }

        self.message_post(
            body=messages.get(reminder_type, _('Recordatorio de vencimiento')),
            message_type='notification',
        )

    def _get_reminder_message(self, reminder_type):
        """Genera mensaje de recordatorio"""
        self.ensure_one()

        messages = {
            '30_days': _(
                '<p>El certificado médico <strong>%s</strong> de '
                '<strong>%s</strong> vence en <strong>30 días</strong> '
                '(%s).</p>'
                '<p>Por favor, programar renovación.</p>'
            ),
            '15_days': _(
                '<p><span style="color: orange;">⚠️ ALERTA</span></p>'
                '<p>El certificado médico <strong>%s</strong> de '
                '<strong>%s</strong> vence en <strong>15 días</strong> '
                '(%s).</p>'
                '<p>Acción requerida pronto.</p>'
            ),
            '7_days': _(
                '<p><span style="color: red;">🚨 URGENTE</span></p>'
                '<p>El certificado médico <strong>%s</strong> de '
                '<strong>%s</strong> vence en <strong>7 días</strong> '
                '(%s).</p>'
                '<p>Programar renovación INMEDIATAMENTE.</p>'
            ),
            'expired': _(
                '<p><span style="color: red;">❌ VENCIDO</span></p>'
                '<p>El certificado médico <strong>%s</strong> de '
                '<strong>%s</strong> VENCIÓ el %s.</p>'
                '<p>Renovación requerida.</p>'
            ),
        }

        template = messages.get(reminder_type, '')
        return template % (
            self.name,
            self.employee_id.name,
            self.expiry_date.strftime('%d/%m/%Y') if self.expiry_date else ''
        )

    def _create_urgent_activity(self):
        """Crea actividad urgente"""
        self.ensure_one()

        user_id = self.responsible_user_id or self.env.user
        if self.employee_id.parent_id and self.employee_id.parent_id.user_id:
            user_id = self.employee_id.parent_id.user_id

        self.env['mail.activity'].create({
            'summary': _('URGENTE: Renovar Certificado Médico'),
            'note': _(
                'El certificado %s de %s vence el %s (7 días).\n'
                'Programar renovación inmediatamente.'
            ) % (self.name, self.employee_id.name, self.expiry_date),
            'date_deadline': fields.Date.today() + timedelta(days=7),
            'user_id': user_id.id,
            'res_model_id': self.env.ref('lavish_hr_employee.model_hr_medical_certificate').id,
            'res_id': self.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
        })

    def _auto_renew_certificate(self):
        """Crea automáticamente certificado de renovación"""
        self.ensure_one()

        if self.renewed_by_certificate_id:
            # Ya tiene renovación
            return

        # Calcular nueva fecha de emisión y vencimiento
        new_issue_date = self.expiry_date + timedelta(days=1)
        validity_months = self.template_id.validity_months if self.template_id else 12
        new_expiry_date = new_issue_date + relativedelta(months=validity_months)

        # Crear nuevo certificado
        new_cert = self.create({
            'employee_id': self.employee_id.id,
            'provider_id': self.provider_id.id,
            'template_id': self.template_id.id if self.template_id else False,
            'certificate_type': self.certificate_type,
            'configuration_id': self.configuration_id.id if self.configuration_id else False,
            'issue_date': new_issue_date,
            'expiry_date': new_expiry_date,
            'renewal_certificate_id': self.id,
            'state': 'scheduled',
            'result': 'pending',
            'responsible_user_id': self.responsible_user_id.id if self.responsible_user_id else False,
        })

        # Actualizar referencia
        self.renewed_by_certificate_id = new_cert.id

        # Notificar
        self.message_post(
            body=_('Certificado renovado automáticamente: %s') % new_cert.name,
            message_type='notification',
        )

        return new_cert

    # ========================================================================
    # ACCIONES MEJORADAS
    # ========================================================================

    def action_renew(self):
        """Renovar certificado manualmente"""
        self.ensure_one()

        if self.renewed_by_certificate_id:
            raise UserError(_('Este certificado ya fue renovado: %s') % self.renewed_by_certificate_id.name)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Renovar Certificado Médico'),
            'res_model': 'wizard.medical.certificate.renew',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_original_certificate_id': self.id,
                'default_employee_id': self.employee_id.id,
                'default_provider_id': self.provider_id.id,
                'default_certificate_type': self.certificate_type,
            }
        }

    def action_view_renewal(self):
        """Ver certificado de renovación"""
        self.ensure_one()

        if not self.renewed_by_certificate_id:
            raise UserError(_('Este certificado no tiene renovación'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.medical.certificate',
            'res_id': self.renewed_by_certificate_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_original(self):
        """Ver certificado original"""
        self.ensure_one()

        if not self.renewal_certificate_id:
            raise UserError(_('Este certificado no es renovación de otro'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.medical.certificate',
            'res_id': self.renewal_certificate_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
