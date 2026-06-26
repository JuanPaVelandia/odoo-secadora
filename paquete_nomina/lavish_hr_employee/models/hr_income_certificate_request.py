# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class HrIncomeCertificateRequest(models.Model):
    _name = 'hr.income.certificate.request'
    _description = 'Solicitud de Certificado de Ingresos y Retenciones'
    _order = 'request_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Número de Solicitud',
        required=True,
        copy=False,
        readonly=True,
        default='Nuevo',
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado',
        required=True,
        readonly=True,
        tracking=True
    )

    header_id = fields.Many2one(
        'hr.certificate.income.header',
        string='Configuración del Certificado',
        required=True,
        readonly=True,
        tracking=True
    )

    year = fields.Integer(
        string='Año Fiscal',
        required=True,
        readonly=True,
        tracking=True
    )

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        readonly=True,
        tracking=True
    )

    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        readonly=True,
        tracking=True
    )

    request_date = fields.Datetime(
        string='Fecha de Solicitud',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        tracking=True
    )

    generation_date = fields.Datetime(
        string='Fecha de Generación',
        readonly=True,
        tracking=True
    )

    notes = fields.Text(
        string='Observaciones',
        readonly=True,
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('done', 'Generado'),
        ('cancelled', 'Cancelado')
    ], string='Estado', default='draft', required=True, tracking=True)

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='employee_id.company_id',
        store=True,
        readonly=True
    )

    # PDF generado (opcional, para cache)
    pdf_file = fields.Binary(
        string='Certificado PDF',
        readonly=True,
        attachment=True
    )

    pdf_filename = fields.Char(
        string='Nombre del Archivo',
        readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override para asignar secuencia"""
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                year = vals.get('year', fields.Date.today().year)
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.income.certificate.request'
                ) or f'CIR/{year}/{self.env["ir.sequence"].next_by_code("default") or "001"}'

        return super().create(vals_list)

    def action_generate(self):
        """Generar el certificado"""
        self.ensure_one()

        if self.state == 'done':
            raise ValidationError(_('El certificado ya ha sido generado'))

        # Generar PDF usando el wizard
        wizard = self.env['hr.certificate.income.wizard'].create({
            'header_id': self.header_id.id,
            'employee_ids': [(6, 0, [self.employee_id.id])],
            'date_from': self.date_from,
            'date_to': self.date_to,
        })

        # Generar PDF
        pdf_content, content_type = self.env['ir.actions.report']._render_qweb_pdf(
            'lavish_hr_employee.action_report_certificate_income', [wizard.id]
        )

        # Guardar PDF
        self.write({
            'pdf_file': pdf_content,
            'pdf_filename': f'Certificado_Ingresos_{self.employee_id.name}_{self.year}.pdf',
            'generation_date': fields.Datetime.now(),
            'state': 'done'
        })

        # Mensaje de seguimiento
        self.message_post(
            body=_('Certificado de ingresos generado exitosamente para el período %s - %s') % (
                self.date_from, self.date_to
            )
        )

        return True

    def action_cancel(self):
        """Cancelar la solicitud"""
        self.ensure_one()
        self.state = 'cancelled'

    def action_draft(self):
        """Volver a borrador"""
        self.ensure_one()
        self.state = 'draft'
