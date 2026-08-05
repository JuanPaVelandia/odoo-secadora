# -*- coding: utf-8 -*-
import io
import json
import base64
import logging
import zipfile
from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CERTIFICATE_TYPES = [
    ('ica', 'Retención de ICA'),
    ('iva', 'Retención de IVA'),
    ('timbre', 'Retención de Timbre'),
    ('fuente', 'Retención en la Fuente'),
]

CERTIFICATE_STATES = [
    ('pending', 'Pendiente'),
    ('in_progress', 'En Curso'),
    ('sent', 'Enviado'),
    ('error', 'Error'),
]


class L10nCoExogenousCertificateHistory(models.Model):
    _name = 'l10n_co.exogenous_certificate_history'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Registro histórico de certificados de retención'
    _check_company_auto = True
    _order = 'notification_date desc, id desc'
    _rec_name = 'display_name'

    # --- Relaciones principales ---
    config_id = fields.Many2one('l10n_co.exogenous_certificate_config',
        string='Configuración',
        required=True,
        ondelete='restrict',
        tracking=True,
        check_company=True)

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Tercero',
        required=True,
        tracking=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compañía',
        related='config_id.company_id',
        store=True,
        readonly=True)

    # --- Tipo y clasificación ---
    certificate_type = fields.Selection(
        selection=CERTIFICATE_TYPES,
        string='Tipo certificado',
        related='config_id.certificate_type',
        store=True,
        readonly=True)

    city_id = fields.Many2one(
        comodel_name='res.city',
        string='Ciudad',
        help='Ciudad del certificado. Para ICA permite emitir por ciudad')

    # --- Período del certificado ---
    date_from = fields.Date(
        string='Fecha inicial',
        required=True,
        tracking=True)

    date_to = fields.Date(
        string='Fecha final',
        required=True,
        tracking=True)

    year = fields.Integer(
        string='Año gravable',
        compute='_compute_year',
        store=True)

    # --- Fechas de control ---
    generation_date = fields.Datetime(
        string='Fecha generación',
        readonly=True,
        tracking=True,
        help='Fecha y hora en la que se generó el certificado')

    notification_date = fields.Datetime(
        string='Fecha notificación',
        readonly=True,
        tracking=True,
        help='Fecha y hora en la que se notificó el envío por correo')

    send_date = fields.Datetime(
        string='Fecha envío',
        readonly=True,
        tracking=True,
        help='Fecha y hora en la que el servidor envió el correo')

    # --- Envío por correo ---
    email = fields.Char(
        string='Correo',
        help='Correo electrónico al cual se envió el certificado')

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Usuario',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True)

    # --- Estado ---
    state = fields.Selection(
        selection=CERTIFICATE_STATES,
        string='Estado',
        default='pending',
        required=True,
        tracking=True)

    error_message = fields.Text(
        string='Mensaje de error',
        readonly=True)

    # --- Consecutivo y archivo ---
    consecutive = fields.Char(
        string='Consecutivo',
        readonly=True,
        tracking=True)

    pdf_file = fields.Binary(
        string='Archivo PDF',
        readonly=True,
        attachment=True)

    pdf_filename = fields.Char(
        string='Nombre archivo PDF',
        readonly=True)

    # --- Datos del certificado (snapshot) ---
    certificate_data = fields.Text(
        string='Datos del certificado',
        readonly=True,
        help='Datos calculados al momento de la generación (JSON)')

    # --- Auxiliar agrupado ---
    total_base = fields.Float(
        string='Base retención',
        digits=(16, 2),
        readonly=True)

    total_retained = fields.Float(
        string='Total retenido',
        digits=(16, 2),
        readonly=True)

    display_name = fields.Char(
        compute='_compute_display_name', store=True)

    @api.depends('date_from')
    def _compute_year(self):
        for rec in self:
            rec.year = rec.date_from.year if rec.date_from else 0

    @api.depends('certificate_type', 'partner_id', 'consecutive')
    def _compute_display_name(self):
        type_labels = dict(CERTIFICATE_TYPES)
        for rec in self:
            parts = [type_labels.get(rec.certificate_type, '')]
            if rec.consecutive:
                parts.append(rec.consecutive)
            if rec.partner_id:
                parts.append(rec.partner_id.name or '')
            rec.display_name = ' - '.join(parts)

    def action_regenerate_pdf(self):
        """Regenera el PDF del certificado usando los datos almacenados"""
        self.ensure_one()
        if not self.certificate_data:
            raise UserError(_('No hay datos del certificado para regenerar. Debe generar el certificado desde el wizard'))

        import json
        try:
            cert_data = json.loads(self.certificate_data)
        except (json.JSONDecodeError, TypeError):
            raise UserError(_('Los datos del certificado están corruptos'))

        # On regeneration, refresh dates so the PDF footer reflects the actual
        # generation_date / notification_date stored on this history record
        # (not the snapshot from when the wizard first ran).
        now = fields.Datetime.now()
        cert_data['generation_date'] = fields.Datetime.to_string(now)
        if self.notification_date:
            cert_data['notification_date'] = fields.Datetime.to_string(self.notification_date)

        # Strip leading account code from each line's account_name. This cleans
        # legacy snapshots that were stored before the wizard started doing the
        # strip, so reprinting an old certificate gives the same clean output.
        import re as _re
        for line in cert_data.get('lines', []) or []:
            raw = line.get('account_name', '') or ''
            line['account_name'] = _re.sub(r'^\s*\d+\s+', '', raw)

        report_action = self.env.ref(
            'l10n_co_exogenous_information_reporting.action_report_certificate_retention',
            raise_if_not_found=False)

        if not report_action:
            raise UserError(_('No se encontró la plantilla de reporte'))

        import base64
        # v14 signature: _render_qweb_pdf(self, res_ids=None, data=None) — no
        # report_ref positional arg (that was added in v15+). Pass the history
        # record id as res_ids so the report engine has a document to render.
        pdf_content, _ = report_action._render_qweb_pdf(
            res_ids=[self.id],
            data={'cert_data': cert_data})

        type_labels = dict(CERTIFICATE_TYPES)
        filename = 'Certificado_%s_%s_%s.pdf' % (
            type_labels.get(self.certificate_type, ''),
            self.partner_id.vat or self.partner_id.name,
            self.year,
        )

        self.write({
            'pdf_file': base64.b64encode(pdf_content),
            'pdf_filename': filename,
            'generation_date': now,
            'certificate_data': json.dumps(cert_data, default=str),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/pdf_file/{filename}?download=true',
            'target': 'new',
        }

    def action_resend_certificate(self):
        """Reenvía el certificado al tercero"""
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(_('No hay certificado PDF generado para reenviar'))
        if not self.email:
            self.email = self.partner_id.email
        if not self.email:
            raise UserError(_('El tercero no tiene correo electrónico configurado'))

        try:
            self._send_certificate_email()
            self.write({
                'state': 'sent',
                'send_date': fields.Datetime.now(),
                'error_message': False,
            })
        except Exception as e:
            self.write({
                'state': 'error',
                'error_message': str(e),
            })
            _logger.exception("Error reenviando certificado %s", self.display_name)

    def action_view_pdf(self):
        """Abre el PDF del certificado en una nueva pestaña"""
        self.ensure_one()
        if not self.pdf_file:
            raise UserError(_('No hay certificado PDF generado'))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/pdf_file/{self.pdf_filename}?download=true',
            'target': 'new',
        }

    # ===== ACCIONES MASIVAS (multi-registro) =====

    def action_mass_send_email(self):
        """Envío masivo de certificados seleccionados por correo"""
        sent = 0
        errors = 0
        for rec in self:
            if not rec.pdf_file:
                continue
            if not rec.email and not rec.partner_id.email:
                rec.write({'state': 'error', 'error_message': _('Sin correo electrónico')})
                errors += 1
                continue
            if not rec.email:
                rec.email = rec.partner_id.email
            try:
                rec.write({'notification_date': fields.Datetime.now(), 'state': 'in_progress'})
                rec._send_certificate_email()
                rec.write({'state': 'sent', 'send_date': fields.Datetime.now(), 'error_message': False})
                sent += 1
            except Exception as e:
                rec.write({'state': 'error', 'error_message': str(e)})
                errors += 1
                _logger.warning("Error enviando certificado a %s: %s", rec.partner_id.name, str(e))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Envío masivo completado'),
                'message': _('%d enviados, %d errores') % (sent, errors),
                'type': 'success' if not errors else 'warning',
                'sticky': False,
            }
        }

    def action_download_all_zip(self):
        """Descarga todos los certificados seleccionados en un ZIP"""
        records_with_pdf = self.filtered(lambda r: r.pdf_file)
        if not records_with_pdf:
            raise UserError(_('No hay certificados PDF para descargar'))

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for rec in records_with_pdf:
                pdf_data = base64.b64decode(rec.pdf_file)
                filename = rec.pdf_filename or 'certificado_%s.pdf' % rec.id
                zf.writestr(filename, pdf_data)

        zip_buffer.seek(0)
        zip_b64 = base64.b64encode(zip_buffer.read())

        # Crear attachment temporal
        attachment = self.env['ir.attachment'].create({
            'name': 'Certificados_Retencion.zip',
            'type': 'binary',
            'datas': zip_b64,
            'mimetype': 'application/zip',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d/Certificados_Retencion.zip?download=true' % attachment.id,
            'target': 'new',
        }

    def action_print_all_pdf(self):
        """Imprime todos los certificados seleccionados en un solo PDF"""
        records_with_data = self.filtered(lambda r: r.certificate_data)
        if not records_with_data:
            raise UserError(_('No hay certificados con datos para imprimir'))

        all_cert_data = []
        for rec in records_with_data:
            try:
                cert_data = json.loads(rec.certificate_data)
                cert_data['consecutive'] = rec.consecutive or ''
                all_cert_data.append(cert_data)
            except (json.JSONDecodeError, TypeError):
                continue

        if not all_cert_data:
            raise UserError(_('No se pudieron cargar los datos de los certificados'))

        report_action = self.env.ref(
            'l10n_co_exogenous_information_reporting.action_report_certificate_retention',
            raise_if_not_found=True)

        return report_action.report_action(self, data={'cert_data': all_cert_data})

    def action_export_auxiliary(self):
        """Exporta el auxiliar agrupado por tercero y cuenta a Excel"""
        if not self:
            raise UserError(_('No hay registros seleccionados'))

        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = Workbook()
        ws = wb.active
        ws.title = 'Auxiliar Certificados'

        # Encabezado
        header_fill = PatternFill(start_color='003366', end_color='003366', fill_type='solid')
        header_font = Font(color='FFFFFF', bold=True, size=10)

        headers = ['Tipo', 'NIT', 'Tercero', 'Cuenta', 'Ciudad',
                   'Base Retención', 'Total Retenido', 'Consecutivo',
                   'Fecha Generación', 'Estado']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

        type_labels = dict(CERTIFICATE_TYPES)
        row = 2
        for rec in self.sorted(key=lambda r: (r.certificate_type, r.partner_id.name or '')):
            ws.cell(row=row, column=1, value=type_labels.get(rec.certificate_type, ''))
            ws.cell(row=row, column=2, value=rec.partner_id.vat or '')
            ws.cell(row=row, column=3, value=rec.partner_id.name or '')
            ws.cell(row=row, column=4, value=rec.city_id.name if rec.city_id else '')
            ws.cell(row=row, column=5, value=rec.city_id.name if rec.city_id else '')
            ws.cell(row=row, column=6, value=rec.total_base)
            ws.cell(row=row, column=7, value=rec.total_retained)
            ws.cell(row=row, column=8, value=rec.consecutive or '')
            ws.cell(row=row, column=9, value=str(rec.generation_date or ''))
            ws.cell(row=row, column=10, value=dict(CERTIFICATE_STATES).get(rec.state, ''))
            row += 1

        # Ajustar anchos
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Auxiliar_Certificados.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(buffer.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d/Auxiliar_Certificados.xlsx?download=true' % attachment.id,
            'target': 'new',
        }

    def _send_certificate_email(self):
        """Envía el certificado por correo electrónico al tercero"""
        self.ensure_one()
        template = self.env.ref(
            'l10n_co_exogenous_information_reporting.mail_template_certificate_retention',
            raise_if_not_found=False)

        if template:
            template.send_mail(self.id, force_send=True)
        else:
            # Envío directo si no hay template
            mail_values = {
                'subject': _('Certificado de %s - %s') % (
                    dict(CERTIFICATE_TYPES).get(self.certificate_type, ''),
                    self.company_id.name),
                'email_from': self.company_id.email or self.env.user.email,
                'email_to': self.email,
                'body_html': _('<p>Adjunto encontrará su certificado de retención.</p>'),
                'attachment_ids': [Command.create({
                    'name': self.pdf_filename or 'certificado.pdf',
                    'datas': self.pdf_file,
                    'mimetype': 'application/pdf',
                })],
            }
            mail = self.env['mail.mail'].sudo().create(mail_values)
            mail.send()
