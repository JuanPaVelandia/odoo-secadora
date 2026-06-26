# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
import base64
import io
import zipfile
import logging

_logger = logging.getLogger(__name__)


class HrEppBatch(models.Model):
    """
    Lote de Entregas EPP/Dotación y Exámenes Médicos

    Modelo PERMANENTE que registra entregas masivas a múltiples empleados.
    Los registros quedan guardados con historial completo.
    """
    _name = 'hr.epp.batch'
    _description = 'Lote de Entregas EPP/Dotación'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # ========================================================================
    # INFORMACIÓN BÁSICA
    # ========================================================================

    name = fields.Char(
        string='Número de Lote',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo'
    )

    batch_type = fields.Selection([
        ('epp', 'EPP - Elementos de Protección Personal'),
        ('dotacion', 'Dotación - Uniformes'),
        ('medical_exam', 'Exámenes Médicos Masivos'),
    ], string='Tipo de Lote',
       required=True,
       tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    # ========================================================================
    # FECHAS
    # ========================================================================

    batch_date = fields.Date(
        string='Fecha del Lote',
        required=True,
        default=fields.Date.today,
        tracking=True
    )

    delivery_planned_date = fields.Date(
        string='Fecha Entrega Planeada',
        help='Fecha en que se planea entregar a los empleados'
    )

    # ========================================================================
    # EMPLEADOS Y SOLICITUDES
    # ========================================================================

    total_employees = fields.Integer(
        string='Total Empleados',
        compute='_compute_totals',
        store=True
    )

    request_ids = fields.One2many(
        'hr.epp.request',
        'batch_id',
        string='Solicitudes Generadas',
        help='Solicitudes individuales por empleado'
    )

    certificate_ids = fields.One2many(
        'hr.medical.certificate',
        'batch_id',
        string='Certificados Médicos Generados'
    )

    @api.depends('request_ids', 'certificate_ids')
    def _compute_totals(self):
        for batch in self:
            if batch.batch_type in ('epp', 'dotacion'):
                batch.total_employees = len(batch.request_ids)
            else:
                batch.total_employees = len(batch.certificate_ids)

    # ========================================================================
    # BODEGA/UBICACIÓN - CONFIGURABLE
    # ========================================================================

    use_stock_location = fields.Boolean(
        string='Usar Control de Inventario',
        default=False,
        help='Generar movimientos de stock (solo para control, no bloquea)'
    )

    default_location_id = fields.Many2one(
        'stock.location',
        string='Bodega por Defecto',
        domain="[('usage', '=', 'internal')]",
        help='Bodega por defecto, se puede sobrescribir por empleado'
    )

    allow_employee_location = fields.Boolean(
        string='Permitir Bodega por Empleado',
        default=True,
        help='Permite que cada empleado tenga su bodega asignada'
    )

    # ========================================================================
    # ESTADO
    # ========================================================================

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmado'),
        ('in_progress', 'En Proceso'),
        ('delivered', 'Entregado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado',
       default='draft',
       required=True,
       tracking=True)

    # ========================================================================
    # ESTADÍSTICAS
    # ========================================================================

    requests_draft = fields.Integer(
        string='Borradores',
        compute='_compute_statistics',
        store=True
    )

    requests_approved = fields.Integer(
        string='Aprobadas',
        compute='_compute_statistics',
        store=True
    )

    requests_delivered = fields.Integer(
        string='Entregadas',
        compute='_compute_statistics',
        store=True
    )

    progress_percentage = fields.Float(
        string='% Progreso',
        compute='_compute_statistics',
        store=True
    )

    @api.depends('request_ids.state', 'certificate_ids.state')
    def _compute_statistics(self):
        for batch in self:
            if batch.batch_type in ('epp', 'dotacion'):
                all_requests = batch.request_ids
                batch.requests_draft = len(all_requests.filtered(lambda r: r.state == 'draft'))
                batch.requests_approved = len(all_requests.filtered(lambda r: r.state in ('approved', 'picking')))
                batch.requests_delivered = len(all_requests.filtered(lambda r: r.state == 'delivered'))

                total = len(all_requests)
                if total > 0:
                    batch.progress_percentage = (batch.requests_delivered / total) * 100
                else:
                    batch.progress_percentage = 0
            else:
                all_certs = batch.certificate_ids
                batch.requests_draft = len(all_certs.filtered(lambda c: c.state == 'scheduled'))
                batch.requests_approved = len(all_certs.filtered(lambda c: c.state == 'in_process'))
                batch.requests_delivered = len(all_certs.filtered(lambda c: c.state == 'valid'))

                total = len(all_certs)
                if total > 0:
                    batch.progress_percentage = (batch.requests_delivered / total) * 100
                else:
                    batch.progress_percentage = 0

    notes = fields.Text(
        string='Notas',
        help='Notas u observaciones del lote'
    )

    # ========================================================================
    # SECUENCIA
    # ========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                if vals.get('batch_type') == 'epp':
                    vals['name'] = self.env['ir.sequence'].next_by_code('hr.epp.batch') or 'BATCH-EPP'
                elif vals.get('batch_type') == 'dotacion':
                    vals['name'] = self.env['ir.sequence'].next_by_code('hr.dotacion.batch') or 'BATCH-DOT'
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('hr.medical.batch') or 'BATCH-MED'
        return super().create(vals_list)

    # ========================================================================
    # MÉTODOS DE WORKFLOW
    # ========================================================================

    def action_confirm(self):
        """Confirmar lote"""
        self.ensure_one()

        if not self.request_ids and not self.certificate_ids:
            raise UserError(_('Debe generar solicitudes/certificados primero'))

        self.state = 'confirmed'

    def action_start(self):
        """Iniciar proceso de entrega"""
        self.ensure_one()

        if self.batch_type in ('epp', 'dotacion'):
            for request in self.request_ids.filtered(lambda r: r.state == 'draft'):
                request.action_approve()

        self.state = 'in_progress'

    def action_deliver_all(self):
        """Marcar todas como entregadas"""
        self.ensure_one()

        if self.batch_type in ('epp', 'dotacion'):
            for request in self.request_ids.filtered(lambda r: r.state != 'delivered'):
                try:
                    request.action_deliver()
                except Exception as e:
                    _logger.warning(f"Could not deliver request {request.name}: {str(e)}")

        self.state = 'delivered'

    def action_cancel(self):
        """Cancelar lote"""
        self.ensure_one()

        for request in self.request_ids.filtered(lambda r: r.state not in ('delivered', 'cancelled')):
            request.action_cancel()

        self.state = 'cancelled'

    # ========================================================================
    # IMPRESIÓN MASIVA
    # ========================================================================

    def action_print_all(self):
        """Imprimir todos los formatos individuales"""
        self.ensure_one()

        if self.batch_type in ('epp', 'dotacion'):
            return self.env.ref('lavish_hr_employee.action_report_epp_delivery').report_action(
                self.request_ids
            )
        else:
            return self.env.ref('lavish_hr_employee.action_report_medical_certificate').report_action(
                self.certificate_ids
            )

    def action_download_all_zip(self):
        """Descargar todos los PDFs en un ZIP"""
        self.ensure_one()

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if self.batch_type in ('epp', 'dotacion'):
                report = self.env.ref('lavish_hr_employee.action_report_epp_delivery')

                for request in self.request_ids:
                    try:
                        pdf_content, _ = report._render_qweb_pdf(request.ids)
                        filename = f"{request.name}_{request.employee_id.name}.pdf"
                        filename = filename.replace('/', '_').replace(' ', '_')
                        zip_file.writestr(filename, pdf_content)
                    except Exception as e:
                        _logger.error(f"Error generating PDF for {request.name}: {str(e)}")
            else:
                report = self.env.ref('lavish_hr_employee.action_report_medical_certificate')

                for cert in self.certificate_ids:
                    try:
                        pdf_content, _ = report._render_qweb_pdf(cert.ids)
                        filename = f"{cert.name}_{cert.employee_id.name}.pdf"
                        filename = filename.replace('/', '_').replace(' ', '_')
                        zip_file.writestr(filename, pdf_content)
                    except Exception as e:
                        _logger.error(f"Error generating PDF for {cert.name}: {str(e)}")

        zip_buffer.seek(0)
        zip_data = base64.b64encode(zip_buffer.read())

        attachment = self.env['ir.attachment'].create({
            'name': f'{self.name}_Documentos.zip',
            'type': 'binary',
            'datas': zip_data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/zip'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ========================================================================
    # ENVÍO POR CORREO MASIVO
    # ========================================================================

    def action_send_emails(self):
        """Enviar correos a todos los empleados"""
        self.ensure_one()

        sent_count = 0

        if self.batch_type in ('epp', 'dotacion'):
            template = self.env.ref('lavish_hr_employee.email_template_epp_delivery', False)

            if not template:
                raise UserError(_('No se encontró plantilla de correo para EPP'))

            for request in self.request_ids:
                if request.employee_id.work_email:
                    try:
                        template.send_mail(request.id, force_send=False)
                        sent_count += 1
                    except Exception as e:
                        _logger.warning(f"Could not send email to {request.employee_id.name}: {str(e)}")
        else:
            template = self.env.ref('lavish_hr_employee.email_template_medical_certificate', False)

            if not template:
                raise UserError(_('No se encontró plantilla de correo para certificados'))

            for cert in self.certificate_ids:
                if cert.employee_id.work_email:
                    try:
                        template.send_mail(cert.id, force_send=False)
                        sent_count += 1
                    except Exception as e:
                        _logger.warning(f"Could not send email to {cert.employee_id.name}: {str(e)}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correos Enviados'),
                'message': _('Se enviaron %d correos electrónicos exitosamente') % sent_count,
                'type': 'success',
                'sticky': False,
            }
        }

    # ========================================================================
    # ABRIR WIZARD DE GENERACIÓN
    # ========================================================================

    def action_generate_requests(self):
        """Abrir wizard para filtrar empleados y generar solicitudes"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Generar Solicitudes/Exámenes'),
            'res_model': 'wizard.epp.batch.generate',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_batch_id': self.id,
                'default_batch_type': self.batch_type,
            }
        }
